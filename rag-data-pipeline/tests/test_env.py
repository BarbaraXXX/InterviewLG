from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from rag_data_pipeline.env import load_deepseek_settings


class EnvTest(unittest.TestCase):
    def test_load_deepseek_settings_from_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text(
                "DEEPSEEK_API_KEY=test-key\nDEEPSEEK_MODEL=deepseek-chat\n",
                encoding="utf-8",
            )
            old_key = os.environ.pop("DEEPSEEK_API_KEY", None)
            try:
                settings = load_deepseek_settings(root)
            finally:
                if old_key is not None:
                    os.environ["DEEPSEEK_API_KEY"] = old_key

        self.assertEqual(settings.api_key, "test-key")
        self.assertEqual(settings.base_url, "https://api.deepseek.com")
        self.assertEqual(settings.model, "deepseek-chat")

    def test_load_deepseek_settings_requires_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_key = os.environ.pop("DEEPSEEK_API_KEY", None)
            try:
                with self.assertRaises(RuntimeError):
                    load_deepseek_settings(Path(tmp))
            finally:
                if old_key is not None:
                    os.environ["DEEPSEEK_API_KEY"] = old_key


if __name__ == "__main__":
    unittest.main()

