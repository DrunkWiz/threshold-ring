"""The whole pipeline, and the HTTP surface, with no network anywhere."""

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from threshold.app import Threshold
from threshold.config import Config
from threshold.providers import Chain
from threshold.providers.fake import FakeProvider
from threshold.server import Handler


def app(**overrides) -> Threshold:
    config = Config(db_path=os.path.join(tempfile.mkdtemp(), "t.db"), offline=True, **overrides)
    return Threshold(config)


class Pipeline(unittest.TestCase):
    def test_connect_reads_the_device_and_its_zones(self):
        threshold = app()
        info = threshold.connect()
        self.assertEqual(info["device"]["name"], "Playground Device")
        self.assertEqual(len(info["zones"][0]["vertices"]), 8)
        self.assertEqual(info["capabilities"]["max_resolution"], 1080)

    def test_one_observation_runs_all_three_consumers(self):
        threshold = app()
        threshold.connect()
        threshold.add_rule("Say out loud when a person is at the door")
        threshold.chain = Chain([FakeProvider([{"subject": "person", "action": "waiting", "confidence": 0.9,
                                                "point": {"x": 0.5, "y": 0.5}, "summary": "Someone is waiting."}])])
        threshold.perception.chain = threshold.chain

        result = threshold.observe(frames=["x"])

        self.assertEqual(result["event"]["subject"], "person")                 # perception
        self.assertEqual(threshold.memory.count(), 1)                           # memory
        self.assertTrue(result["decisions"][0]["fired"])                        # rules
        self.assertIn("waiting", result["narration"]["announcement"])           # narration
        self.assertIn("speech", [d["channel"] for d in result["deliveries"]])   # notify

    def test_an_animal_is_recorded_but_not_passed_on(self):
        """The whole point of the product: eleven of twelve alerts are a cat."""
        threshold = app()
        threshold.connect()
        threshold.add_rule("Say out loud when a person is at the door")
        result = threshold.observe(frames=["x"])  # the fake answers with birds
        self.assertEqual(result["event"]["subject"], "animal")
        self.assertFalse(result["noteworthy"])
        self.assertEqual(result["deliveries"], [])
        self.assertEqual(threshold.memory.count(), 1)  # still remembered

    def test_seeded_history_is_labelled_and_separable(self):
        threshold = app()
        threshold.connect()
        threshold.seed_history()
        state = threshold.state()
        self.assertGreater(state["counts"]["seeded"], 20)
        self.assertEqual(state["counts"]["live"], 0)
        self.assertTrue(all(e["source"] == "seeded" for e in state["events"]))

    def test_seeding_twice_does_not_double_the_history(self):
        threshold = app()
        threshold.connect()
        first = threshold.seed_history()["seeded"]
        second = threshold.seed_history()["seeded"]
        self.assertEqual(first, second)
        self.assertEqual(threshold.memory.count(source="seeded"), first)

    def test_rules_can_be_added_and_removed(self):
        threshold = app()
        added = threshold.add_rule("Tell me if a vehicle stops in the driveway after dark")
        self.assertIn("vehicle", added["explanation"])
        self.assertTrue(threshold.remove_rule(added["rule"]["id"]))
        self.assertFalse(threshold.remove_rule("nope"))

    def test_token_state_names_the_read_only_scope(self):
        threshold = app()
        threshold.token = "h.eyJzY29wZXMiOlsiYXZhLnYxOnJlYWQiXSwiZXhwIjo0MTAyNDQ0ODAwfQ.s"
        state = threshold.token_state()
        self.assertTrue(state["read_only"])
        self.assertGreater(state["seconds_left"], 0)


class Http(unittest.TestCase):
    """A real socket, because the WHEP proxy and the JSON edges are where the
    mistakes live."""

    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer

        cls.threshold = app()
        cls.threshold.connect()
        cls.threshold.preset_rules()
        Handler.app = cls.threshold
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def get(self, path):
        with urllib.request.urlopen(self.url(path)) as resp:
            return json.loads(resp.read())

    def post(self, path, payload, *, raw=None, content_type="application/json"):
        data = raw if raw is not None else json.dumps(payload).encode()
        request = urllib.request.Request(self.url(path), data=data, headers={"Content-Type": content_type})
        with urllib.request.urlopen(request) as resp:
            return resp.status, resp.read(), dict(resp.headers)

    def test_state(self):
        state = self.get("/api/state")
        self.assertEqual(len(state["rules"]), 3)
        self.assertEqual(state["device"]["name"], "Playground Device")

    def test_observe_accepts_a_data_url(self):
        status, body, _ = self.post("/api/observe", {"frames": ["data:image/jpeg;base64,ZmFrZQ=="]})
        self.assertEqual(status, 200)
        self.assertIn("narration", json.loads(body))

    def test_observe_without_frames_is_a_clear_400(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/observe", {"frames": []})
        self.assertEqual(ctx.exception.code, 400)
        self.assertIn("no frames", json.loads(ctx.exception.read())["error"])

    def test_malformed_json_is_a_400_not_a_500(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/observe", None, raw=b"{not json")
        self.assertEqual(ctx.exception.code, 400)

    def test_whep_proxy_returns_the_sdp_answer_and_location(self):
        """The token never reaches the browser; this is the exchange that
        keeps it that way."""
        status, body, headers = self.post("/api/whep", None, raw=b"v=0\r\n", content_type="application/sdp")
        self.assertEqual(status, 201)
        self.assertTrue(body.decode().startswith("v=0"))
        self.assertIn("Location", headers)

    def test_static_files_are_served_and_traversal_is_refused(self):
        with urllib.request.urlopen(self.url("/")) as resp:
            self.assertIn(b"Threshold", resp.read())
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.url("/../threshold/config.py"))
        self.assertIn(ctx.exception.code, (400, 404))

    def test_unknown_endpoint(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/nope", {})
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
