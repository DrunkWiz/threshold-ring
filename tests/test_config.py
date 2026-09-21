"""Reading configuration from the environment, including the `.env` file.

The loader exists because `.env` used to be read only by `scripts/demo.sh`.
Keys written there were ignored in silence by `python -m threshold.server`,
so you set AWS credentials, got canned descriptions anyway, and nothing in
the output explained why.
"""

import os
import tempfile
import unittest
from pathlib import Path

from threshold.config import load_dotenv


class DotEnv(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, ".env")
        self.touched: list[str] = []

    def tearDown(self):
        for key in self.touched:
            os.environ.pop(key, None)

    def write(self, text: str) -> str:
        Path(self.path).write_text(text, encoding="utf-8")
        return self.path

    def track(self, *keys: str) -> None:
        self.touched.extend(keys)

    def test_values_reach_the_environment(self):
        self.track("THRESHOLD_TEST_REGION")
        load_dotenv(self.write("THRESHOLD_TEST_REGION=us-east-1\n"))
        self.assertEqual(os.environ["THRESHOLD_TEST_REGION"], "us-east-1")

    def test_a_real_environment_variable_beats_the_file(self):
        """A one-off `RING_TOKEN=... python -m threshold.server` has to win.

        The opposite would be the same class of bug this loader was written to
        remove: a stale value quietly overriding the one you just typed.
        """
        self.track("THRESHOLD_TEST_TOKEN")
        os.environ["THRESHOLD_TEST_TOKEN"] = "from-the-shell"
        load_dotenv(self.write("THRESHOLD_TEST_TOKEN=from-the-file\n"))
        self.assertEqual(os.environ["THRESHOLD_TEST_TOKEN"], "from-the-shell")

    def test_comments_blank_lines_quotes_and_export_are_all_handled(self):
        """`.env.example` is what people copy, so whatever it contains has to
        parse — including the `export` prefix people paste out of a README."""
        self.track("THRESHOLD_TEST_A", "THRESHOLD_TEST_B", "THRESHOLD_TEST_C")
        load_dotenv(self.write(
            "# a comment\n"
            "\n"
            "THRESHOLD_TEST_A=plain\n"
            'THRESHOLD_TEST_B="quoted value"\n'
            "export THRESHOLD_TEST_C=exported\n"
            "a line with no equals sign\n"
        ))
        self.assertEqual(os.environ["THRESHOLD_TEST_A"], "plain")
        self.assertEqual(os.environ["THRESHOLD_TEST_B"], "quoted value")
        self.assertEqual(os.environ["THRESHOLD_TEST_C"], "exported")

    def test_a_missing_file_is_not_an_error(self):
        """A judge who clones and runs without ever writing a `.env` must not
        meet a stack trace on the first command."""
        load_dotenv(os.path.join(self.dir, "definitely-not-here.env"))


if __name__ == "__main__":
    unittest.main()
