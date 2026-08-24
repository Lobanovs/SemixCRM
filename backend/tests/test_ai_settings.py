from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import database
from backend.ai.client import AiError, load_settings
from backend.ai.settings import (
    DEFAULT_MODEL,
    init_settings_schema,
    remove_saved_key,
    safe_settings,
    save_settings,
)
from backend.main import app


class AiSettingsStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(database, "DB_PATH", Path(self.temp_dir.name) / "ai-settings.sqlite3")
        self.path_patch.start()
        database.init_db()
        init_settings_schema()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_environment_is_used_before_local_settings_exist(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENCODE_API_KEY": "env-key",
                "OPENCODE_MODEL": "glm-5.2",
                "OPENCODE_TIMEOUT": "37",
            },
            clear=False,
        ):
            settings = load_settings()

        self.assertEqual("env-key", settings.api_key)
        self.assertEqual("glm-5.2", settings.model)
        self.assertEqual(37, settings.timeout)

    def test_safe_settings_never_returns_the_key(self) -> None:
        save_settings(api_key="go-secret-1234", model="deepseek-v4-flash", timeout=45)

        public = safe_settings()

        self.assertNotIn("go-secret-1234", repr(public))
        self.assertNotIn("api_key", public)
        self.assertTrue(public["api_key_configured"])
        self.assertEqual("••••1234", public["api_key_hint"])
        self.assertEqual("database", public["api_key_source"])

    def test_database_values_take_precedence_over_environment(self) -> None:
        with patch.dict(os.environ, {"OPENCODE_API_KEY": "env-key"}, clear=False):
            save_settings(api_key="db-key", model="deepseek-v4-flash", timeout=45)

            settings = load_settings()

        self.assertEqual("db-key", settings.api_key)
        self.assertEqual("deepseek-v4-flash", settings.model)
        self.assertEqual(45, settings.timeout)

    def test_omitted_key_preserves_the_saved_key(self) -> None:
        save_settings(api_key="db-key", model="deepseek-v4-flash", timeout=45)

        save_settings(api_key=None, model="glm-5.2", timeout=60)

        self.assertEqual("db-key", load_settings().api_key)
        self.assertEqual("glm-5.2", load_settings().model)

    def test_removing_saved_key_explicitly_disables_environment_fallback(self) -> None:
        with patch.dict(os.environ, {"OPENCODE_API_KEY": "env-key"}, clear=False):
            save_settings(api_key="db-key", model="deepseek-v4-flash", timeout=45)

            removed = remove_saved_key()

            self.assertTrue(removed)
            self.assertEqual("", load_settings().api_key)
            self.assertFalse(safe_settings()["enabled"])

    def test_supported_model_and_timeout_are_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "модель"):
            save_settings(api_key="key", model="qwen3-coder", timeout=45)
        with self.assertRaisesRegex(ValueError, "Таймаут"):
            save_settings(api_key="key", model=DEFAULT_MODEL, timeout=2)

    def test_gpt_5_6_luna_is_supported(self) -> None:
        models = {item["id"]: item["label"] for item in safe_settings()["supported_models"]}
        self.assertEqual("GPT-5.6 Luna", models["gpt-5.6-luna"])

        save_settings(api_key="key", model="gpt-5.6-luna", timeout=45)
        self.assertEqual("gpt-5.6-luna", load_settings().model)


class AiSettingsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(database, "DB_PATH", Path(self.temp_dir.name) / "ai-settings-api.sqlite3")
        self.path_patch.start()
        self.environment_patch = patch.dict(
            os.environ,
            {
                "OPENCODE_API_KEY": "",
                "OPENCODE_MODEL": DEFAULT_MODEL,
                "OPENCODE_TIMEOUT": "90",
            },
            clear=False,
        )
        self.environment_patch.start()
        self.registry_patch = patch("backend.main.build_adapters", return_value={})
        self.registry_patch.start()
        self.client_context = TestClient(app, headers={"X-Requested-With": "SemixCRM"})
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.registry_patch.stop()
        self.environment_patch.stop()
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_settings_api_masks_key(self) -> None:
        saved = self.client.put(
            "/api/ai/settings",
            json={
                "api_key": "go-secret-1234",
                "model": "deepseek-v4-flash",
                "timeout": 45,
            },
        )

        self.assertEqual(200, saved.status_code)
        self.assertNotIn("go-secret-1234", saved.text)
        self.assertEqual("••••1234", saved.json()["api_key_hint"])
        loaded = self.client.get("/api/ai/settings")
        self.assertEqual(200, loaded.status_code)
        self.assertNotIn("go-secret-1234", loaded.text)

    def test_save_without_key_preserves_existing_secret(self) -> None:
        self.client.put(
            "/api/ai/settings",
            json={"api_key": "existing-key", "model": DEFAULT_MODEL, "timeout": 45},
        )

        response = self.client.put(
            "/api/ai/settings",
            json={"model": "glm-5.2", "timeout": 60},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("existing-key", load_settings().api_key)
        self.assertEqual("glm-5.2", response.json()["model"])

    def test_delete_key_disables_ai(self) -> None:
        self.client.put(
            "/api/ai/settings",
            json={"api_key": "existing-key", "model": DEFAULT_MODEL, "timeout": 45},
        )

        response = self.client.delete("/api/ai/settings/key")

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json()["removed"])
        self.assertFalse(response.json()["settings"]["enabled"])

    def test_invalid_model_and_timeout_are_rejected(self) -> None:
        invalid_model = self.client.put(
            "/api/ai/settings",
            json={"api_key": "key", "model": "qwen3-coder", "timeout": 45},
        )
        invalid_timeout = self.client.put(
            "/api/ai/settings",
            json={"api_key": "key", "model": DEFAULT_MODEL, "timeout": 2},
        )

        self.assertEqual(422, invalid_model.status_code)
        self.assertEqual(422, invalid_timeout.status_code)

    def test_connection_check_uses_unsaved_key_without_persisting_it(self) -> None:
        with patch("backend.main.AiClient.complete", return_value="OK") as complete:
            response = self.client.post(
                "/api/ai/settings/test",
                json={"api_key": "temporary-key", "model": DEFAULT_MODEL, "timeout": 45},
            )

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json()["ok"])
        complete.assert_called_once_with(
            "Ты проверяешь подключение к OpenCode Go.",
            "Ответь одним словом: OK",
            temperature=0,
            max_tokens=128,
        )
        self.assertFalse(self.client.get("/api/ai/settings").json()["api_key_configured"])

    def test_connection_check_maps_rejected_key(self) -> None:
        with patch(
            "backend.main.AiClient.complete",
            side_effect=AiError("Ключ OpenCode отклонён (401)"),
        ):
            response = self.client.post(
                "/api/ai/settings/test",
                json={"api_key": "bad-key", "model": DEFAULT_MODEL, "timeout": 45},
            )

        self.assertEqual(502, response.status_code)
        self.assertIn("401", response.json()["detail"])

    def test_connection_check_requires_a_key(self) -> None:
        response = self.client.post(
            "/api/ai/settings/test",
            json={"model": DEFAULT_MODEL, "timeout": 45},
        )

        self.assertEqual(400, response.status_code)
        self.assertIn("ключ", response.json()["detail"].lower())

    def test_working_profile_update_requires_the_crm_header(self) -> None:
        with TestClient(app) as bare_client:
            response = bare_client.put(
                "/api/ai/profile",
                json={"name": "Семён", "role": "Разрабатываю сайты"},
            )

        self.assertEqual(403, response.status_code)
        self.assertIn("X-Requested-With", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
