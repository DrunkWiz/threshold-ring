"""Delivering a notification, and the encoding trap in doing so."""

import unittest

from threshold.notify import Notifier


class Push(unittest.TestCase):
    def notifier(self, seen, status=200):
        def opener(url, headers, data):
            seen["url"] = url
            seen["headers"] = headers
            seen["data"] = data
            return status, b""

        return Notifier(ntfy_topic="a-topic", opener=opener)

    def test_an_em_dash_in_the_title_does_not_break_the_push(self):
        """Every caption is "<subject> - <action>" with an em dash.

        HTTP headers are latin-1, so encoding one raised UnicodeEncodeError
        inside urllib and came back as "push unreachable". The push channel
        was therefore broken for every real notification while working
        perfectly for any test message typed in ASCII — which is exactly how
        it survived to be found by sending one live.
        """
        seen = {}
        delivery = self.notifier(seen).send(
            ["push"], title="An animal — moving across the frame", body="body"
        )[0]

        self.assertTrue(delivery.ok)
        self.assertEqual(seen["headers"]["Title"], "An animal - moving across the frame")
        seen["headers"]["Title"].encode("latin-1")  # would raise if still unsafe

    def test_anything_else_unencodable_is_replaced_rather_than_raising(self):
        seen = {}
        delivery = self.notifier(seen).send(["push"], title="door 中文", body="body")[0]

        self.assertTrue(delivery.ok)
        seen["headers"]["Title"].encode("latin-1")

    def test_the_body_keeps_its_unicode(self):
        """Only the header is latin-1. The body is UTF-8 and should not be
        flattened — the spoken sentence is what a person actually reads."""
        seen = {}
        self.notifier(seen).send(["push"], title="t", body="An animal — at the door")[0]

        self.assertIn("—", seen["data"].decode("utf-8"))

    def test_no_topic_says_which_variable_to_set(self):
        delivery = Notifier().send(["push"], title="t", body="b")[0]
        self.assertFalse(delivery.ok)
        self.assertIn("THRESHOLD_NTFY_TOPIC", delivery.detail)


if __name__ == "__main__":
    unittest.main()
