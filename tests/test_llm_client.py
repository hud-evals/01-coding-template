from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.llm_client import call_text_llm, reset_client


class LlmClientTests(unittest.TestCase):
    def setUp(self):
        reset_client()

    def tearDown(self):
        reset_client()

    def test_returns_none_when_no_api_keys_set(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
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


if __name__ == "__main__":
    unittest.main()
