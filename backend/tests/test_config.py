from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.config import load_environment


class EnvironmentConfigTests(unittest.TestCase):
    def test_loads_local_env_without_overwriting_explicit_process_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "SEMIXCRM_TEST_FROM_FILE=loaded\nSEMIXCRM_TEST_EXPLICIT=from-file\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"SEMIXCRM_TEST_EXPLICIT": "from-shell"}, clear=False):
                os.environ.pop("SEMIXCRM_TEST_FROM_FILE", None)
                try:
                    loaded = load_environment(env_file)
                    self.assertTrue(loaded)
                    self.assertEqual("loaded", os.environ["SEMIXCRM_TEST_FROM_FILE"])
                    self.assertEqual("from-shell", os.environ["SEMIXCRM_TEST_EXPLICIT"])
                finally:
                    os.environ.pop("SEMIXCRM_TEST_FROM_FILE", None)


if __name__ == "__main__":
    unittest.main()
