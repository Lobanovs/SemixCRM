from __future__ import annotations

import json
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

from backend import database, main, parser
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

    def test_parser_settings_persist_unlimited_and_large_limits(self) -> None:
        unlimited = database.save_parser_settings(
            "Новосибирск",
            ["стоматологии"],
            ["2gis"],
            0,
        )
        large = database.save_parser_settings(
            "Новосибирск",
            ["стоматологии"],
            ["2gis"],
            275,
        )

        self.assertEqual(0, unlimited["limit"])
        self.assertEqual(275, large["limit"])

    def test_api_models_accept_unlimited_limit(self) -> None:
        parse_request = main.ParseRequest(
            city="Новосибирск",
            niches=["стоматологии"],
            sources=["2gis"],
            limit=0,
        )
        settings_request = main.ParserSettingsRequest(
            city="Новосибирск",
            niches=["стоматологии"],
            sources=["2gis"],
            limit=0,
        )

        self.assertEqual(0, parse_request.limit)
        self.assertEqual(0, settings_request.limit)

    def test_collect_2gis_passes_selected_page_to_parser_command(self) -> None:
        captured: dict[str, list[str]] = {}

        def fake_run(command: list[str], *_: object) -> subprocess.CompletedProcess[str]:
            captured["command"] = command
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text('[{"name": "Тестовая компания"}]', encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="Готово")

        with (
            patch.object(parser, "OUTPUT_DIR", Path(self.temp_dir.name)),
            patch.object(parser, "ensure_parser2gis_command", return_value=["parser-2gis"], create=True),
            patch.object(parser, "resolve_parser2gis_city_code", return_value="novosibirsk"),
            patch.object(parser, "_run_parser_process", side_effect=fake_run),
        ):
            parser.collect_2gis("Новосибирск", "стоматологии", 10, start_page=4)

        self.assertEqual("parser-2gis", captured["command"][0])
        input_url = captured["command"][captured["command"].index("-i") + 1]
        self.assertIn("/page/4/filters/sort=name", input_url)

    def test_collect_2gis_unlimited_uses_upstream_ceiling_without_global_timeout(self) -> None:
        captured: dict[str, object] = {}

        def fake_run(
            command: list[str],
            _environment: dict[str, str],
            timeout: int | None,
        ) -> subprocess.CompletedProcess[str]:
            captured["command"] = command
            captured["timeout"] = timeout
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(
                json.dumps([{"name": f"Клиника {index}"} for index in range(75)], ensure_ascii=False),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, stdout="Готово")

        with (
            patch.object(parser, "OUTPUT_DIR", Path(self.temp_dir.name)),
            patch.object(parser, "ensure_parser2gis_command", return_value=["parser-2gis"]),
            patch.object(parser, "resolve_parser2gis_city_code", return_value="novosibirsk"),
            patch.object(parser, "_run_parser_process", side_effect=fake_run),
        ):
            leads = parser.collect_2gis("Новосибирск", "стоматологии", 0)

        command = captured["command"]
        self.assertIsInstance(command, list)
        max_records = int(command[command.index("--parser.max-records") + 1])
        self.assertEqual(parser.UPSTREAM_UNLIMITED_MAX_RECORDS, max_records)
        self.assertIsNone(captured["timeout"])
        self.assertEqual(75, len(leads))

    def test_collect_2gis_keeps_explicit_limit_above_fifty(self) -> None:
        captured: dict[str, list[str]] = {}

        def fake_run(command: list[str], *_: object) -> subprocess.CompletedProcess[str]:
            captured["command"] = command
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text('[{"name": "Тестовая компания"}]', encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="Готово")

        with (
            patch.object(parser, "OUTPUT_DIR", Path(self.temp_dir.name)),
            patch.object(parser, "ensure_parser2gis_command", return_value=["parser-2gis"]),
            patch.object(parser, "resolve_parser2gis_city_code", return_value="novosibirsk"),
            patch.object(parser, "_run_parser_process", side_effect=fake_run),
        ):
            parser.collect_2gis("Новосибирск", "стоматологии", 275)

        command = captured["command"]
        max_records = int(command[command.index("--parser.max-records") + 1])
        self.assertEqual(275, max_records)

    def test_collect_leads_does_not_slice_unlimited_results(self) -> None:
        cards = [
            {"source": "2GIS", "city": "Новосибирск", "name": f"Клиника {index}"}
            for index in range(75)
        ]

        with patch.object(parser, "collect_2gis", return_value=cards):
            leads = parser.collect_leads("Новосибирск", "стоматологии", ["2gis"], 0)

        self.assertEqual(75, len(leads))


if __name__ == "__main__":
    unittest.main()
