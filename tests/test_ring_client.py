"""The client, against the emulator and against every failure the API has."""

import unittest

from ring_client import (
    DEVICE_ID,
    Emulator,
    Forbidden,
    NotFound,
    RateLimited,
    RingClient,
    RingError,
    TokenExpired,
    TokenInvalid,
    token_expiry,
    token_scopes,
)

# header.{"scopes":["ava.v1:read"],"exp":4102444800}.signature  (exp in 2100)
LIVE_TOKEN = "h.eyJzY29wZXMiOlsiYXZhLnYxOnJlYWQiXSwiZXhwIjo0MTAyNDQ0ODAwfQ.s"
# exp in 2001
DEAD_TOKEN = "h.eyJzY29wZXMiOlsiYXZhLnYxOnJlYWQiXSwiZXhwIjo5OTk5OTk5OTl9.s"


def client(**kwargs):
    emulator = kwargs.pop("emulator", None) or Emulator()
    return RingClient(kwargs.pop("token", LIVE_TOKEN), opener=emulator.opener, sleep=lambda _: None, **kwargs), emulator


class TokenIntrospection(unittest.TestCase):
    def test_reads_expiry_and_scopes(self):
        self.assertEqual(token_expiry(LIVE_TOKEN), 4102444800.0)
        self.assertEqual(token_scopes(LIVE_TOKEN), ("ava.v1:read",))

    def test_survives_a_token_that_is_not_a_jwt(self):
        self.assertIsNone(token_expiry("not-a-token"))
        self.assertEqual(token_scopes(""), ())


class Resources(unittest.TestCase):
    def test_devices(self):
        c, _ = client()
        devices = c.devices()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].name, "Playground Device")

    def test_zone_geometry_survives_the_round_trip(self):
        c, _ = client()
        zones = c.configurations(DEVICE_ID).zones
        self.assertEqual(len(zones), 1)
        self.assertEqual(len(zones[0].vertices), 8)
        self.assertEqual(zones[0].vertices[3], (1.0, 0.6))

    def test_capabilities_report_no_sensors(self):
        """The Playground doorbell reports every sensor family as null.

        Worth a test: a project built around sensors would be building blind,
        and this is where that would be noticed.
        """
        c, _ = client()
        caps = c.capabilities(DEVICE_ID)
        self.assertEqual(caps.sensors, ())
        self.assertTrue(caps.motion_detection)
        self.assertEqual(caps.video_max_resolution, 1080)

    def test_history_is_empty(self):
        c, _ = client()
        self.assertEqual(c.history(DEVICE_ID), [])

    def test_status_and_user(self):
        c, _ = client()
        self.assertTrue(c.status(DEVICE_ID).online)
        self.assertEqual(c.user().first_name, "Playground")


class Failures(unittest.TestCase):
    def test_expired_token_never_leaves_the_process(self):
        c, emulator = client(token=DEAD_TOKEN)
        with self.assertRaises(TokenExpired):
            c.devices()
        self.assertEqual(emulator.calls, [])  # no wasted round trip

    def test_401_without_expiry_is_an_invalid_token(self):
        c, _ = client(emulator=Emulator(fail_with=401))
        with self.assertRaises(TokenInvalid):
            c.devices()

    def test_403_names_the_scopes(self):
        c, _ = client(emulator=Emulator(fail_with=403))
        with self.assertRaises(Forbidden) as ctx:
            c.devices()
        self.assertIn("ava.v1:read", str(ctx.exception))
        self.assertIn("read-only", str(ctx.exception))

    def test_writes_are_refused_by_the_emulator_too(self):
        """The emulator refuses writes because the real token would.

        Learning that offline is the whole point of having an emulator.
        """
        c, _ = client()
        with self.assertRaises(Forbidden):
            c._json("POST", f"/v1/devices/{DEVICE_ID}/media/snapshots", body=b"{}")

    def test_404(self):
        c, _ = client()
        with self.assertRaises(NotFound):
            c._json("GET", "/v1/nope")

    def test_429_is_retried_then_raised(self):
        c, emulator = client(emulator=Emulator(fail_with=429), max_retries=2)
        with self.assertRaises(RateLimited):
            c.devices()
        self.assertEqual(len(emulator.calls), 3)  # original plus two retries

    def test_html_error_page_is_explained(self):
        def opener(method, url, headers, body):
            return 200, b"<html>proxy error</html>", {}

        c = RingClient(LIVE_TOKEN, opener=opener)
        with self.assertRaises(RingError) as ctx:
            c.devices()
        self.assertIn("not JSON", str(ctx.exception))


class Whep(unittest.TestCase):
    def test_session_returns_answer_and_location(self):
        c, _ = client()
        answer, location = c.start_whep_session(DEVICE_ID, "v=0\r\n")
        self.assertTrue(answer.startswith("v=0"))
        self.assertIn("emulated-session", location)


if __name__ == "__main__":
    unittest.main()
