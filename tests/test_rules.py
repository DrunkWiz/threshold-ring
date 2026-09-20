"""Compiling rules, and evaluating them the same way every time."""

import time
import unittest

from threshold.events import Event
from threshold.providers import Chain, ProviderError
from threshold.providers.fake import FakeProvider
from threshold.rules import Rule, compile_rule, evaluate, keyword_compile
from threshold.rules.evaluate import _in_window, channels_for


def at(clock: str) -> float:
    return time.mktime(time.strptime(f"2026-09-21 {clock}", "%Y-%m-%d %H:%M"))


class KeywordCompiler(unittest.TestCase):
    def test_subject(self):
        self.assertEqual(keyword_compile("tell me about a van")["subject"], "vehicle")
        self.assertEqual(keyword_compile("when somebody knocks")["subject"], "person")
        self.assertEqual(keyword_compile("if a parcel is left")["subject"], "package")

    def test_dwell_in_words_and_digits(self):
        self.assertEqual(keyword_compile("waits more than 30 seconds")["min_dwell_s"], 30)
        self.assertEqual(keyword_compile("stays longer than two minutes")["min_dwell_s"], 120)

    def test_window_across_midnight(self):
        payload = keyword_compile("anyone between 11pm and 6am")
        self.assertEqual(payload["time_window"], {"from": "23:00", "to": "06:00"})

    def test_channels_come_from_the_verb(self):
        self.assertIn("speech", keyword_compile("say out loud when someone arrives")["channels"])
        self.assertIn("push", keyword_compile("notify my phone about vehicles")["channels"])

    def test_an_unparsed_sentence_widens_rather_than_silences(self):
        """A rule we cannot read should be noisy, not silent.

        A noisy rule gets corrected; a silent one gets trusted and then misses
        the thing it was written for.
        """
        rule = Rule.from_payload(keyword_compile("something something"))
        self.assertEqual(rule.subject, "any")
        self.assertEqual(rule.zone, "any")
        self.assertTrue(evaluate(rule, Event(subject="person")).fired)


class ModelCompiler(unittest.TestCase):
    def test_model_output_is_used_when_a_real_provider_answers(self):
        provider = FakeProvider([{"name": "Night vehicles", "subject": "vehicle", "zone": "inside", "night_only": True}])
        provider.name = "bedrock"  # pretend to be real; the fake's name is what is checked
        rule, attempts = compile_rule("anything", Chain([provider]))
        self.assertEqual(rule.subject, "vehicle")
        self.assertEqual(rule.compiled_by, "bedrock")
        self.assertTrue(attempts and attempts[0]["ok"])

    def test_falls_back_to_keywords_when_every_provider_fails(self):
        class Broken(FakeProvider):
            name = "broken"

            def complete_json(self, **kwargs):
                raise ProviderError("no")

        rule, _ = compile_rule("tell me about a van at night", Chain([Broken()]))
        self.assertEqual(rule.subject, "vehicle")
        self.assertEqual(rule.compiled_by, "keyword")

    def test_a_nonsense_payload_does_not_produce_a_nonsense_rule(self):
        provider = FakeProvider([{"subject": "dragon", "min_dwell_s": "soon", "channels": ["telepathy"]}])
        provider.name = "bedrock"
        rule, _ = compile_rule("x", Chain([provider]))
        self.assertEqual(rule.subject, "any")
        self.assertEqual(rule.min_dwell_s, 0.0)
        self.assertEqual(rule.channels, ("screen",))


class Windows(unittest.TestCase):
    def test_ordinary_window(self):
        self.assertTrue(_in_window(600, 540, 660))
        self.assertFalse(_in_window(700, 540, 660))

    def test_window_that_wraps_midnight(self):
        # The most common thing anyone asks a doorbell for, and the easiest to
        # get backwards — a naive start <= m <= end is silent all night.
        self.assertTrue(_in_window(30, 1380, 360))
        self.assertTrue(_in_window(1400, 1380, 360))
        self.assertFalse(_in_window(720, 1380, 360))

    def test_boundaries_are_inclusive(self):
        self.assertTrue(_in_window(540, 540, 660))
        self.assertTrue(_in_window(660, 540, 660))


class Evaluation(unittest.TestCase):
    def setUp(self):
        self.rule, _ = compile_rule("Notify my phone if a person comes between 11pm and 6am")

    def test_fires_and_explains(self):
        decision = evaluate(self.rule, Event(at=at("02:30"), subject="person"))
        self.assertTrue(decision.fired)
        self.assertIn("within 23:00 to 06:00", decision.explain())

    def test_refusal_says_which_clause_blocked_it(self):
        decision = evaluate(self.rule, Event(at=at("14:10"), subject="person"))
        self.assertFalse(decision.fired)
        self.assertEqual([c.name for c in decision.blocking], ["window"])
        self.assertIn("14:10", decision.explain())

    def test_wrong_subject_reads_grammatically(self):
        decision = evaluate(self.rule, Event(at=at("02:30"), subject="animal"))
        self.assertIn("saw an animal", decision.explain())

    def test_same_input_always_same_answer(self):
        """The property the whole design exists for."""
        event = Event(at=at("02:30"), subject="person")
        answers = {evaluate(self.rule, event).fired for _ in range(50)}
        self.assertEqual(answers, {True})

    def test_disabled_rule_never_fires(self):
        rule = Rule(enabled=False, name="off")
        self.assertFalse(evaluate(rule, Event(subject="person")).fired)

    def test_zone_conditions(self):
        inside = Rule(name="in", zone="inside")
        outside = Rule(name="out", zone="outside")
        in_zone = Event(subject="person", zone_ids=("z1",))
        no_zone = Event(subject="person")
        self.assertTrue(evaluate(inside, in_zone).fired)
        self.assertFalse(evaluate(inside, no_zone).fired)
        self.assertTrue(evaluate(outside, no_zone).fired)

    def test_dwell_and_confidence(self):
        rule = Rule(name="waiting", min_dwell_s=30, min_confidence=0.8)
        self.assertFalse(evaluate(rule, Event(dwell_s=10, confidence=0.9)).fired)
        self.assertFalse(evaluate(rule, Event(dwell_s=40, confidence=0.5)).fired)
        self.assertTrue(evaluate(rule, Event(dwell_s=40, confidence=0.9)).fired)

    def test_channels_only_come_from_rules_that_fired(self):
        loud = Rule(name="loud", subject="person", channels=("speech", "push"))
        quiet = Rule(name="quiet", subject="vehicle", channels=("screen",))
        event = Event(subject="person")
        decisions = [evaluate(loud, event), evaluate(quiet, event)]
        self.assertEqual(channels_for(decisions, [loud, quiet]), ("speech", "push"))


if __name__ == "__main__":
    unittest.main()
