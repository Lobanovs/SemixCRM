from __future__ import annotations

import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

from backend import database, parser
from backend.parser import build_2gis_search_url


class ParserStartPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.db_patch = patch.object(database, "DB_PATH", self.db_path)
        self.db_patch.start()
        database.init_db()

    def tearDown(self) -> None:
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_builds_page_four_url_for_novosibirsk_dentistry(self) -> None:
        url = build_2gis_search_url("novosibirsk", "стоматологии", 4)

        self.assertEqual(
            "https://2gis.ru/novosibirsk/search/%D1%81%D1%82%D0%BE%D0%BC%D0%B0%D1%82%D0%BE%D0%BB%D0%BE%D0%B3%D0%B8%D0%B8/page/4/filters/sort=name",
            url,
        )

    def test_first_page_keeps_canonical_search_url(self) -> None:
        url = build_2gis_search_url("novosibirsk", "стоматологии", 1)

        self.assertNotIn("/page/1", url)
        self.assertTrue(url.endswith("/filters/sort=name"))

    def test_parser_settings_persist_start_page(self) -> None:
        saved = database.save_parser_settings(
            "Новосибирск",
            ["стоматологии"],
            ["2gis"],
            20,
            start_page=4,
        )

        self.assertEqual(4, saved["start_page"])
        self.assertEqual(4, database.get_parser_settings()["start_page"])

    def test_collect_2gis_passes_selected_page_to_parser_command(self) -> None:
        captured: dict[str, list[str]] = {}

        def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            captured["command"] = command
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text('{"items": []}', encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="Готово")

        with patch.object(parser, "OUTPUT_DIR", Path(self.temp_dir.name)), patch.object(parser.subprocess, "run", side_effect=fake_run):
            parser.collect_2gis("Новосибирск", "стоматологии", 10, start_page=4)

        input_url = captured["command"][captured["command"].index("-i") + 1]
        self.assertIn("/page/4/filters/sort=name", input_url)


if __name__ == "__main__":
    unittest.main()
