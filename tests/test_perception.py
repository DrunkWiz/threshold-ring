"""Perception, the provider chain, salvage, and the SigV4 signing."""

import json
import unittest

from threshold.events import Event
from threshold.perception import Perception
from threshold.providers import Chain, ProviderError, build_chain
from threshold.providers.bedrock import BedrockProvider
from threshold.providers.ollama import OllamaProvider
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

    def test_a_bedrock_api_key_is_sent_as_a_bearer_token_and_never_signed(self):
        """A Bedrock API key replaces SigV4 rather than feeding it.

        Signing a request that already carries a bearer token produces a 403
        that reads like a bad key, so the two paths have to be exclusive.
        """
        seen = {}

        def opener(url, headers, body):
            seen.update(headers)
            return 200, json.dumps({"content": [{"type": "text", "text": "{}"}]}).encode()

        BedrockProvider(api_key="ABSKtest", opener=opener).complete_json(system="s", prompt="p")

        self.assertEqual(seen["Authorization"], "Bearer ABSKtest")
        self.assertNotIn("X-Amz-Date", seen)
        self.assertNotIn("X-Amz-Content-Sha256", seen)

    def test_the_api_key_wins_over_an_access_key_pair(self):
        """Both can be present — a leftover pair in the shell, a key in .env.
        The key is the narrower credential, so it is the one to use.
        """
        provider = BedrockProvider.from_env({
            "AWS_BEARER_TOKEN_BEDROCK": "ABSKtest",
            "AWS_ACCESS_KEY_ID": "AKIAEXAMPLE",
            "AWS_SECRET_ACCESS_KEY": "secret",
        })
        self.assertEqual(provider.api_key, "ABSKtest")

    def test_no_credentials_at_all_drops_the_rung(self):
        self.assertIsNone(BedrockProvider.from_env({}))
        self.assertIsNone(BedrockProvider.from_env({"AWS_REGION": "us-east-1"}))

    def test_403_is_explained_rather_than_relayed(self):
        provider = BedrockProvider("AK", "sk", opener=lambda *a: (403, b"AccessDenied"))
        with self.assertRaises(ProviderError) as ctx:
            provider.complete_json(system="s", prompt="p")
        self.assertIn("model access", str(ctx.exception))

    def test_what_aws_said_survives_the_403(self):
        """AWS names the real cause; we used to replace it with a guess.

        A service control policy denying the action cannot be fixed by any of
        the things our own advice suggests, so swallowing the message sent
        people to change permissions that were never the problem. Found for
        real against an account inside an organisation that denies
        bedrock:CallWithBearerToken.
        """
        body = json.dumps({
            "Message": "User: arn:aws:iam::1:user/x is not authorized to perform: "
                       "bedrock:CallWithBearerToken with an explicit deny in a service control policy"
        }).encode()
        provider = BedrockProvider(api_key="ABSKtest", opener=lambda *a: (403, body))

        with self.assertRaises(ProviderError) as ctx:
            provider.complete_json(system="s", prompt="p")

        self.assertIn("service control policy", str(ctx.exception))
        self.assertIn("CallWithBearerToken", str(ctx.exception))

    def test_prose_instead_of_json_is_a_malformed_error(self):
        response = json.dumps({"content": [{"type": "text", "text": "I think it is a cat."}]}).encode()
        provider = BedrockProvider("AK", "sk", opener=lambda *a: (200, response))
        with self.assertRaises(ProviderError) as ctx:
            provider.complete_json(system="s", prompt="p")
        self.assertEqual(ctx.exception.kind, "malformed")


class LocalModel(unittest.TestCase):
    """The Ollama rung: a vision model on the same machine as the doorbell."""

    def ollama(self, status, body, seen=None):
        def opener(url, headers, payload):
            if seen is not None:
                seen["url"] = url
                seen["payload"] = json.loads(payload)
            return status, body

        return OllamaProvider("a-model", opener=opener)

    def answering(self, content: str) -> bytes:
        return json.dumps({"message": {"role": "assistant", "content": content}}).encode()

    def test_unconfigured_drops_out_without_touching_the_network(self):
        """No model named means the rung is absent, not broken. Otherwise every
        run without Ollama pays for a refused connection before falling back."""
        self.assertIsNone(OllamaProvider.from_env({}))
        self.assertIsNone(OllamaProvider.from_env({"THRESHOLD_OLLAMA_MODEL": "   "}))

    def test_named_model_builds_against_localhost_by_default(self):
        provider = OllamaProvider.from_env({"THRESHOLD_OLLAMA_MODEL": "qwen3.5:9b"})
        self.assertEqual(provider.model, "qwen3.5:9b")
        self.assertEqual(provider.host, "http://127.0.0.1:11434")

    def test_images_ride_on_the_message_and_thinking_is_off(self):
        """Two things this API does differently from Bedrock.

        Images are bare base64 on the message rather than content blocks, and
        num_predict caps thinking and answer together — so a reasoning model
        left to think spends the whole budget and returns empty content, which
        surfaces as "no JSON object" and looks like a parser bug. Found live
        against qwen3.5:9b.
        """
        seen = {}
        provider = self.ollama(200, self.answering('{"subject": "person"}'), seen)

        result = provider.complete_json(system="s", prompt="p", images=["Zm9v"])

        self.assertEqual(result, {"subject": "person"})
        self.assertEqual(seen["payload"]["messages"][1]["images"], ["Zm9v"])
        self.assertIs(seen["payload"]["think"], False)
        self.assertIn("/api/chat", seen["url"])

    def test_a_missing_model_says_which_one(self):
        provider = self.ollama(404, b'{"error": "model not found"}')
        with self.assertRaises(ProviderError) as ctx:
            provider.complete_json(system="s", prompt="p")
        self.assertEqual(ctx.exception.kind, "missing_model")
        self.assertIn("a-model", str(ctx.exception))


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
