"""The baseline, and the three anomalies computed from it."""

import os
import tempfile
import time
import unittest

from threshold.events import Event
from threshold.memory import Memory


class Fixture(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.now = time.mktime(time.strptime("2026-09-21 09:30", "%Y-%m-%d %H:%M"))
        self.memory = Memory(os.path.join(self.dir, "t.db"), clock=lambda: self.now)

    def tearDown(self):
        self.memory.close()

    def carer_fortnight(self, *, skip_today=False):
        """A carer at 09:15 every day for a fortnight, minus today if asked."""
        for day in range(14, 0, -1):
            if skip_today and day == 1:
                continue
            at = self.now - day * 86400
            lt = time.localtime(at)
            when = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 9, 15, 0, 0, 0, -1))
            self.memory.record(Event(at=when, subject="person", source="seeded", summary="carer"))


class Storage(unittest.TestCase):
    def setUp(self):
        self.memory = Memory(os.path.join(tempfile.mkdtemp(), "t.db"))

    def test_round_trip_keeps_every_field(self):
        event = Event(
            subject="person",
            descriptors=("in a blue coat", "carrying a box"),
            zone_ids=("z1", "z2"),
            point=(0.4, 0.6),
            dwell_s=12.5,
            night=True,
            confidence=0.83,
            summary="someone at the door",
        )
        self.memory.record(event)
        stored = self.memory.recent()[0]
        self.assertEqual(stored, event)

    def test_seeded_and_live_are_counted_apart(self):
        self.memory.record(Event(subject="person", source="seeded"))
        self.memory.record(Event(subject="person", source="live"))
        self.assertEqual(self.memory.count(source="seeded"), 1)
        self.assertEqual(len(self.memory.recent(include_seeded=False)), 1)

    def test_clearing_seeded_leaves_live_alone(self):
        self.memory.record(Event(source="seeded"))
        self.memory.record(Event(source="live"))
        self.memory.clear(source="seeded")
        self.assertEqual(self.memory.count(), 1)


class Silence(Fixture):
    def test_fires_when_a_reliable_hour_goes_empty(self):
        self.carer_fortnight(skip_today=True)
        anomaly = self.memory.check_silence()
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly.kind, "silence")
        self.assertIn("Monday", anomaly.message)

    def test_the_message_is_a_sentence_not_a_template(self):
        """This is the line a family member reads when a carer has not come.

        The format string produced "there are usually about 1", which is the
        kind of seam that makes someone trust the rest of it less — and it is
        the most emotionally loaded sentence the product produces.
        """
        from threshold.memory import _usually

        self.assertEqual(_usually(0.9), "there is usually one visit")
        self.assertEqual(_usually(1.0), "there is usually one visit")
        self.assertEqual(_usually(3.4), "there are usually about 3 visits")

        self.carer_fortnight(skip_today=True)
        message = self.memory.check_silence().message
        self.assertNotIn("about 1.", message)
        self.assertIn("usually", message)

    def test_looking_and_seeing_nothing_does_not_count_as_something(self):
        """An event whose subject is "nothing" must not suppress the alert.

        It is the same observation the anomaly is reporting. Counting it as
        activity meant that with "watch continuously" on — an observation
        every fifteen seconds — the silence alert could never fire, which
        quietly disabled the one feature aimed at the caretaking case.
        """
        self.carer_fortnight(skip_today=True)
        self.memory.record(Event(at=self.now - 60, subject="nothing"))
        self.assertIsNotNone(self.memory.check_silence())

    def test_stays_quiet_when_the_visit_happened(self):
        self.carer_fortnight()
        self.memory.record(Event(at=self.now - 600, subject="person"))
        self.assertIsNone(self.memory.check_silence())

    def test_says_nothing_without_enough_history(self):
        """Two days is not a routine, and claiming otherwise would frighten
        someone about their parent for no reason."""
        for day in (1, 2):
            self.memory.record(Event(at=self.now - day * 86400, subject="person", source="seeded"))
        self.assertIsNone(self.memory.check_silence())

    def test_ignores_an_hour_that_was_never_busy(self):
        self.memory.record(Event(at=self.now - 9 * 86400, subject="person", source="seeded"))
        for day in range(1, 8):
            self.memory.record(Event(at=self.now - day * 86400 - 40000, subject="animal", source="seeded"))
        self.assertIsNone(self.memory.check_silence())


class Novelty(Fixture):
    def test_a_person_at_an_unseen_hour(self):
        self.carer_fortnight()
        middle_of_the_night = self.now - 9 * 3600
        found = self.memory.check_event(Event(at=middle_of_the_night, subject="person"))
        self.assertEqual([a.kind for a in found], ["novelty"])

    def test_a_person_at_the_usual_hour_is_not_news(self):
        self.carer_fortnight()
        found = self.memory.check_event(Event(at=self.now - 900, subject="person"))
        self.assertEqual(found, [])

    def test_animals_do_not_raise_novelty(self):
        # A fox at a new hour is not a thing to tell a person about at 3am.
        self.carer_fortnight()
        found = self.memory.check_event(Event(at=self.now - 9 * 3600, subject="animal"))
        self.assertEqual(found, [])


class Frequency(Fixture):
    def test_four_visits_in_an_hour(self):
        for minutes in (50, 35, 20):
            self.memory.record(Event(at=self.now - minutes * 60, subject="person"))
        found = self.memory.check_event(Event(at=self.now, subject="person"))
        self.assertIn("frequency", [a.kind for a in found])

    def test_the_same_visits_spread_over_a_day_are_not_a_spike(self):
        for hours in (20, 14, 8):
            self.memory.record(Event(at=self.now - hours * 3600, subject="person"))
        found = self.memory.check_event(Event(at=self.now, subject="person"))
        self.assertNotIn("frequency", [a.kind for a in found])

    def test_the_message_says_an_animal_not_a_animal(self):
        """The rules engine got its article right and these two did not.

        It reached the screen during a live run — "That is 7 visits by a
        animal within an hour" — which is the kind of thing a judge reads as
        carelessness everywhere else in the project.
        """
        for minutes in (50, 35, 20):
            self.memory.record(Event(at=self.now - minutes * 60, subject="animal"))
        found = self.memory.check_event(Event(at=self.now, subject="animal"))

        message = next(a.message for a in found if a.kind == "frequency")
        self.assertIn("by an animal", message)
        self.assertNotIn("a animal", message)


if __name__ == "__main__":
    unittest.main()
