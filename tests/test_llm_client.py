from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.llm_client import (
    _get_client,
    _load_dotenv,
    call_text_llm,
    llm_stream_sink,
    reset_client,
)


class LlmClientTests(unittest.TestCase):
    def setUp(self):
        reset_client()

    def tearDown(self):
        reset_client()

    def test_returns_none_when_no_api_keys_set(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("ast_pilot.llm_client._load_dotenv"):
            result = call_text_llm("hello")
        self.assertIsNone(result)

    def test_returns_text_from_openai_compatible_client(self) -> None:
        fake_message = MagicMock()
        fake_message.content = "response text"

        fake_choice = MagicMock()
        fake_choice.message = fake_message

        fake_response = MagicMock()
        fake_response.choices = [fake_choice]

        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_response

        with patch("ast_pilot.llm_client._get_client", return_value=fake_client):
            result = call_text_llm("test prompt")

        self.assertEqual(result, "response text")
        fake_client.chat.completions.create.assert_called_once()

    def test_expect_json_returns_none_on_invalid_json(self) -> None:
        fake_message = MagicMock()
        fake_message.content = "not json at all"

        fake_choice = MagicMock()
        fake_choice.message = fake_message

        fake_response = MagicMock()
        fake_response.choices = [fake_choice]

        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_response

        with patch("ast_pilot.llm_client._get_client", return_value=fake_client):
            result = call_text_llm("test", expect_json=True)

        self.assertIsNone(result)

    def test_expect_json_returns_valid_json(self) -> None:
        fake_message = MagicMock()
        fake_message.content = '{"issues": []}'

        fake_choice = MagicMock()
        fake_choice.message = fake_message

        fake_response = MagicMock()
        fake_response.choices = [fake_choice]

        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_response

        with patch("ast_pilot.llm_client._get_client", return_value=fake_client):
            result = call_text_llm("test", expect_json=True)

        self.assertEqual(result, '{"issues": []}')

    def test_handles_response_content_parts(self) -> None:
        fake_message = MagicMock()
        fake_message.content = [
            {"type": "text", "text": "hello"},
            {"type": "text", "text": " world"},
        ]

        fake_choice = MagicMock()
        fake_choice.message = fake_message

        fake_response = MagicMock()
        fake_response.choices = [fake_choice]

        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_response

        with patch("ast_pilot.llm_client._get_client", return_value=fake_client):
            result = call_text_llm("test prompt")

        self.assertEqual(result, "hello world")

    def test_returns_none_on_exception(self) -> None:
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = RuntimeError("API error")

        with patch("ast_pilot.llm_client._get_client", return_value=fake_client):
            result = call_text_llm("test")

        self.assertIsNone(result)

    def test_model_env_var_is_forwarded(self) -> None:
        fake_message = MagicMock()
        fake_message.content = "ok"

        fake_choice = MagicMock()
        fake_choice.message = fake_message

        fake_response = MagicMock()
        fake_response.choices = [fake_choice]

        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_response

        with (
            patch("ast_pilot.llm_client._get_client", return_value=fake_client),
            patch.dict(os.environ, {"AST_PILOT_MODEL": "custom-model-123"}),
        ):
            call_text_llm("test")

        call_kwargs = fake_client.chat.completions.create.call_args
        self.assertEqual(call_kwargs.kwargs["model"], "custom-model-123")

    def test_load_dotenv_parses_quotes_and_inline_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            nested = root / "nested"
            nested.mkdir()
            (root / ".env").write_text(
                'HUD_API_KEY="dotenv-key" # inline comment\nAST_PILOT_MODEL=haiku-test\n',
                encoding="utf-8",
            )

            previous_cwd = Path.cwd()
            os.chdir(nested)
            try:
                with patch.dict(os.environ, {}, clear=True):
                    _load_dotenv()
                    self.assertEqual(os.environ["HUD_API_KEY"], "dotenv-key")
                    self.assertEqual(os.environ["AST_PILOT_MODEL"], "haiku-test")
            finally:
                os.chdir(previous_cwd)

    def test_streams_chunks_to_sink_when_registered(self) -> None:
        """With a sink set, call_text_llm takes the streaming path, forwards
        stream=True to the client, and pushes each delta to the sink while
        still returning the accumulated text."""

        def make_event(delta_text: str | None) -> MagicMock:
            event = MagicMock()
            choice = MagicMock()
            choice.delta.content = delta_text
            event.choices = [choice]
            return event

        events = [make_event("Hello "), make_event("world"), make_event(None)]

        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = iter(events)

        chunks: list[str] = []
        token = llm_stream_sink.set(chunks.append)
        try:
            with patch("ast_pilot.llm_client._get_client", return_value=fake_client):
                result = call_text_llm("test prompt")
        finally:
            llm_stream_sink.reset(token)

        self.assertEqual(result, "Hello world")
        self.assertEqual(chunks, ["Hello ", "world"])
        call_kwargs = fake_client.chat.completions.create.call_args
        self.assertTrue(call_kwargs.kwargs.get("stream"))

    def test_streaming_sink_exceptions_do_not_break_the_call(self) -> None:
        """A glitchy TUI must not take down the LLM call. Sink errors are
        swallowed and the final text still comes back intact."""

        def make_event(delta_text: str) -> MagicMock:
            event = MagicMock()
            choice = MagicMock()
            choice.delta.content = delta_text
            event.choices = [choice]
            return event

        events = [make_event("ok"), make_event("ay")]

        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = iter(events)

        def bad_sink(_chunk: str) -> None:
            raise RuntimeError("ui crashed")

        token = llm_stream_sink.set(bad_sink)
        try:
            with patch("ast_pilot.llm_client._get_client", return_value=fake_client):
                result = call_text_llm("test prompt")
        finally:
            llm_stream_sink.reset(token)

        self.assertEqual(result, "okay")

    def test_blocking_path_still_used_without_sink(self) -> None:
        """Regression guard: with no sink, the old non-streaming API call
        must be used. Tests and production stay on the blocking path by
        default, so nothing else has to opt-out."""
        fake_message = MagicMock()
        fake_message.content = "blocking result"
        fake_choice = MagicMock()
        fake_choice.message = fake_message
        fake_response = MagicMock()
        fake_response.choices = [fake_choice]

        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_response

        with patch("ast_pilot.llm_client._get_client", return_value=fake_client):
            result = call_text_llm("test prompt")

        self.assertEqual(result, "blocking result")
        call_kwargs = fake_client.chat.completions.create.call_args
        self.assertNotIn("stream", call_kwargs.kwargs)

    def test_get_client_rebuilds_when_api_key_changes(self) -> None:
        fake_openai = types.ModuleType("openai")

        class FakeOpenAI:
            def __init__(self, *, api_key: str, base_url: str):
                self.api_key = api_key
                self.base_url = base_url

        fake_openai.OpenAI = FakeOpenAI

        with patch.dict(sys.modules, {"openai": fake_openai}, clear=False):
            with (
                patch("ast_pilot.llm_client._load_dotenv"),
                patch.dict(os.environ, {"HUD_API_KEY": "key-one"}, clear=True),
            ):
                first = _get_client()

            with (
                patch("ast_pilot.llm_client._load_dotenv"),
                patch.dict(os.environ, {"HUD_API_KEY": "key-two"}, clear=True),
            ):
                second = _get_client()

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertIsNot(first, second)
        self.assertEqual(first.api_key, "key-one")
        self.assertEqual(second.api_key, "key-two")


if __name__ == "__main__":
    unittest.main()
