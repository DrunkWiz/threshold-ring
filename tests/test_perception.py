"""Perception, the provider chain, salvage, and the SigV4 signing."""

import json
import unittest

from threshold.events import Event
from threshold.perception import Perception
from threshold.providers import Chain, ProviderError, build_chain
from threshold.providers.bedrock import BedrockProvider
from threshold.providers.fake import FakeProvider
from threshold.providers.salvage import salvage_json


class Salvage(unittest.TestCase):
    def test_plain_object(self):
        self.assertEqual(salvage_json('{"a": 1}'), {"a": 1})

    def test_fenced_with_preamble_and_epilogue(self):
        text = 'Sure! Here you go:\n```json\n{"subject": "person"}\n```\nHope that helps.'
        self.assertEqual(salvage_json(text), {"subject": "person"})

    def test_braces_inside_strings_do_not_confuse_it(self):
        # The reason this is brace counting and not a regex.
        self.assertEqual(salvage_json('{"note": "a } inside"}'), {"note": "a } inside"})

    def test_nested_objects_survive(self):
        self.assertEqual(salvage_json('prose {"p": {"x": [1, 2]}} more'), {"p": {"x": [1, 2]}})

    def test_a_bare_array_is_not_an_object(self):
        self.assertIsNone(salvage_json("[1, 2, 3]"))

    def test_nothing_to_find(self):
        self.assertIsNone(salvage_json("I cannot help with that."))
        self.assertIsNone(salvage_json(""))


class ChainBehaviour(unittest.TestCase):
    def test_first_provider_that_answers_wins(self):
        class Broken(FakeProvider):
            name = "broken"

            def complete_json(self, **kwargs):
                raise ProviderError("down", kind="unreachable")

        chain = Chain([Broken(), FakeProvider([{"ok": True}])])
        result, name = chain.complete_json(system="s", prompt="p")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(name, "fake")
        self.assertEqual([a["ok"] for a in chain.attempts], [False, True])

    def test_a_crashing_provider_does_not_end_the_turn(self):
        class Exploding(FakeProvider):
            name = "boom"

            def complete_json(self, **kwargs):
                raise RuntimeError("bug in the provider")

        chain = Chain([Exploding(), FakeProvider([{"ok": 1}])])
        self.assertEqual(chain.complete_json(system="s", prompt="p")[0], {"ok": 1})

    def test_everything_failing_raises(self):
        class Broken(FakeProvider):
            name = "broken"

            def complete_json(self, **kwargs):
                raise ProviderError("down")

        with self.assertRaises(ProviderError):
            Chain([Broken()]).complete_json(system="s", prompt="p")

    def test_unconfigured_providers_drop_out_before_any_network_call(self):
        chain = build_chain({})  # no AWS credentials in this environment
        self.assertEqual([p.name for p in chain], ["fake"])

    def test_env_pins_the_first_rung(self):
        chain = build_chain({"THRESHOLD_PROVIDER": "fake", "THRESHOLD_FAKE_MODEL": "1"})
        self.assertEqual(chain[0].name, "fake")


class Signing(unittest.TestCase):
    """The SigV4 signature, checked against a recorded request rather than
    against the real service — which the test suite must never reach."""

    def test_signs_and_parses_a_response(self):
        seen = {}

        def opener(url, headers, body):
            seen["url"] = url
            seen["headers"] = headers
            seen["body"] = json.loads(body)
            return 200, json.dumps({"content": [{"type": "text", "text": '{"subject": "person"}'}]}).encode()

        provider = BedrockProvider("AKIAEXAMPLE", "secret", region="us-east-1", opener=opener)
        result = provider.complete_json(system="s", prompt="p", images=["Zm9v"])

        self.assertEqual(result, {"subject": "person"})
        self.assertIn("bedrock-runtime.us-east-1.amazonaws.com", seen["url"])
        auth = seen["headers"]["Authorization"]
        self.assertTrue(auth.startswith("AWS4-HMAC-SHA256 Credential=AKIAEXAMPLE/"))
        self.assertIn("SignedHeaders=host;x-amz-content-sha256;x-amz-date", auth)
        self.assertEqual(seen["body"]["messages"][0]["content"][0]["type"], "image")

    def test_session_token_is_signed_in(self):
        seen = {}

        def opener(url, headers, body):
            seen.update(headers)
            return 200, json.dumps({"content": [{"type": "text", "text": "{}"}]}).encode()

        BedrockProvider("AK", "sk", session_token="tok", opener=opener).complete_json(system="s", prompt="p")
        self.assertEqual(seen["X-Amz-Security-Token"], "tok")
        self.assertIn("x-amz-security-token", seen["Authorization"])

    def test_403_is_explained_rather_than_relayed(self):
        provider = BedrockProvider("AK", "sk", opener=lambda *a: (403, b"AccessDenied"))
        with self.assertRaises(ProviderError) as ctx:
            provider.complete_json(system="s", prompt="p")
        self.assertIn("model access", str(ctx.exception))

    def test_prose_instead_of_json_is_a_malformed_error(self):
        response = json.dumps({"content": [{"type": "text", "text": "I think it is a cat."}]}).encode()
        provider = BedrockProvider("AK", "sk", opener=lambda *a: (200, response))
        with self.assertRaises(ProviderError) as ctx:
            provider.complete_json(system="s", prompt="p")
        self.assertEqual(ctx.exception.kind, "malformed")


class Observing(unittest.TestCase):
    class FakeZone:
        id = "z1"
        vertices = ((0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6))

    def test_the_zone_is_decided_by_geometry_not_by_the_model(self):
        """The model is never asked which zone something is in.

        It would agree with whatever the prompt suggested. The polygon test is
        arithmetic, so it cannot be talked round.
        """
        provider = FakeProvider([{"subject": "person", "point": {"x": 0.5, "y": 0.5}, "zone_ids": ["made-up"]}])
        event = Perception(Chain([provider])).observe(frames=["x"], zones=[self.FakeZone()])
        self.assertEqual(event.zone_ids, ("z1",))

    def test_a_point_outside_every_zone(self):
        provider = FakeProvider([{"subject": "person", "point": {"x": 0.9, "y": 0.9}}])
        event = Perception(Chain([provider])).observe(frames=["x"], zones=[self.FakeZone()])
        self.assertEqual(event.zone_ids, ())

    def test_total_failure_still_produces_an_event(self):
        """Silence is the one thing a doorbell must not do.

        If every provider is down, the event still records that something
        happened and says the description is missing.
        """
        class Broken(FakeProvider):
            name = "broken"

            def complete_json(self, **kwargs):
                raise ProviderError("down")

        event = Perception(Chain([Broken()])).observe(frames=["x"], trigger="ding")
        self.assertEqual(event.provider, "none")
        self.assertEqual(event.trigger, "ding")
        self.assertIn("could not be generated", event.summary)

    def test_unknown_subjects_are_coerced(self):
        provider = FakeProvider([{"subject": "burglar", "confidence": 5}])
        event = Perception(Chain([provider])).observe(frames=["x"])
        self.assertEqual(event.subject, "unknown")
        self.assertEqual(event.confidence, 1.0)

    def test_background_movement_is_not_noteworthy(self):
        self.assertFalse(Event(subject="animal", confidence=0.9).is_noteworthy)
        self.assertTrue(Event(subject="person", confidence=0.9).is_noteworthy)

    def test_the_prompt_forbids_guessing_who_someone_is(self):
        from threshold.perception import SYSTEM

        self.assertIn("Never guess a person's race", SYSTEM)
        self.assertIn("Never guess intent", SYSTEM)


if __name__ == "__main__":
    unittest.main()
