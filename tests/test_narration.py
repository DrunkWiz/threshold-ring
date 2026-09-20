"""What gets said out loud."""

import unittest

from threshold.events import Event
from threshold.narration import announcement, caption, reason, render


class Announcement(unittest.TestCase):
    def test_a_delivery(self):
        event = Event(
            subject="person",
            descriptors=("wearing a delivery uniform", "holding a parcel"),
            action="standing at the door",
            confidence=0.9,
        )
        self.assertEqual(
            announcement(event),
            "Someone wearing a delivery uniform and holding a parcel is standing at the door.",
        )

    def test_names_the_zone_when_there_is_one(self):
        event = Event(subject="vehicle", action="pulling up", zone_ids=("z1",), confidence=0.9)
        said = announcement(event, zone_names={"z1": "the driveway"})
        self.assertIn("In the driveway.", said)

    def test_says_how_long_only_when_it_is_worth_saying(self):
        brief = Event(subject="person", action="passing", dwell_s=4, confidence=0.9)
        waiting = Event(subject="person", action="waiting", dwell_s=45, confidence=0.9)
        self.assertNotIn("seconds", announcement(brief))
        self.assertIn("45 seconds", announcement(waiting))

    def test_uncertainty_is_spoken_not_shown_as_a_number(self):
        """A person deciding whether to open their door deserves to know the
        machine is unsure, in words they can act on."""
        event = Event(subject="person", action="at the door", confidence=0.2)
        self.assertIn("not certain", announcement(event))

    def test_nothing_there(self):
        self.assertEqual(announcement(Event(subject="nothing")), "Nothing is at the door.")

    def test_a_failed_description_says_so(self):
        event = Event(subject="unknown", provider="none")
        self.assertIn("could not be described", announcement(event))

    def test_every_announcement_is_one_sentence_ending_in_a_full_stop(self):
        for subject in ("person", "vehicle", "animal", "package", "unknown"):
            said = announcement(Event(subject=subject, action="moving", confidence=0.9))
            self.assertTrue(said.endswith("."), said)
            self.assertNotIn("  ", said)

    def test_deterministic(self):
        # A screen reader that says it differently each time is unusable.
        event = Event(subject="person", descriptors=("in a red coat",), action="waiting", confidence=0.9)
        self.assertEqual({announcement(event) for _ in range(20)}, {announcement(event)})


class Caption(unittest.TestCase):
    def test_short_enough_to_read(self):
        event = Event(subject="person", action="standing at the door holding something large and unwieldy")
        self.assertLessEqual(len(caption(event)), 80)


class Reason(unittest.TestCase):
    def test_a_rule_is_quoted_back(self):
        self.assertIn("you asked", reason(Event(subject="person"), matched_rules=["Night vehicles"]))

    def test_an_anomaly_speaks_for_itself(self):
        self.assertEqual(reason(Event(), anomaly="Nothing this morning."), "Nothing this morning.")

    def test_background_movement_says_it_was_not_passed_on(self):
        self.assertIn("Not passed on", reason(Event(subject="animal")))


class Render(unittest.TestCase):
    def test_returns_all_three(self):
        out = render(Event(subject="person", action="at the door", confidence=0.9))
        self.assertEqual(set(out), {"announcement", "caption", "reason"})


if __name__ == "__main__":
    unittest.main()
