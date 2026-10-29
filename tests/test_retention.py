import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from core.config import Config
from core.engine import backup_all, backup_source
from cli.commands import cmd_run


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "report.txt"
        self.source.write_text("latest content", encoding="utf-8")
        self.dest = self.root / "backups"
        self.folder = self.dest / "report备份"
        self.folder.mkdir(parents=True)

    def old_backups(self, count, name="report.txt"):
        paths = []
        for index in range(count):
            path = self.folder / f"{name}_20260101_{index:06d}.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(name, "old content")
            paths.append(path)
        return paths

    def test_old_config_defaults_and_persists_limit(self):
        path = self.root / "config.json"
        path.write_text(json.dumps({"destination": "existing"}), encoding="utf-8")
        config = Config(str(path))
        self.assertEqual(config.max_backups, 50)
        config.max_backups = 3
        reloaded = Config(str(path))
        self.assertEqual(reloaded.max_backups, 3)
        self.assertEqual(reloaded.destination, "existing")
        for invalid in (0, -1, True, "5"):
            with self.assertRaises(ValueError):
                config.max_backups = invalid

    def test_keeps_newest_and_ignores_other_files(self):
        old = self.old_backups(4)
        other = self.old_backups(1, "report.csv")[0]
        unrelated = self.folder / "report.txt_manual.zip"
        unrelated.write_text("keep", encoding="utf-8")
        directory = self.folder / "report.txt_20250101_000000.zip"
        directory.mkdir()
        # Retention follows backup timestamps even if old files were touched later.
        os.utime(old[0], (2000000000, 2000000000))
        current, skipped = backup_source(str(self.source), str(self.dest), max_backups=2)
        self.assertEqual(skipped, [])
        self.assertTrue(Path(current).exists())
        self.assertTrue(old[-1].exists())
        self.assertTrue(all(not path.exists() for path in old[:-1]))
        self.assertTrue(other.exists())
        self.assertTrue(unrelated.exists())
        self.assertTrue(directory.is_dir())
        with zipfile.ZipFile(current) as archive:
            self.assertEqual(archive.read("report.txt"), b"latest content")

    def test_default_limit_is_50(self):
        old = self.old_backups(51)
        backup_source(str(self.source), str(self.dest))
        self.assertEqual(len(list(self.folder.glob("*.zip"))), 50)
        self.assertFalse(old[0].exists())
        self.assertFalse(old[1].exists())
        self.assertTrue(old[2].exists())

    def test_repeated_backups_in_same_second_are_distinct(self):
        from datetime import datetime
        with patch("core.engine.datetime") as clock:
            clock.now.side_effect = [datetime(2026, 1, 2, 12),
                                    datetime(2026, 1, 2, 12),
                                    datetime(2026, 1, 2, 12, 0, 0, 1)]
            first, _ = backup_source(str(self.source), str(self.dest))
            second, _ = backup_source(str(self.source), str(self.dest))
        self.assertNotEqual(first, second)
        self.assertTrue(Path(first).exists())
        self.assertTrue(Path(second).exists())

    def test_partial_or_failed_backup_does_not_prune(self):
        old = self.old_backups(3)
        with patch("core.engine.zipfile.ZipFile.write", side_effect=PermissionError("locked")):
            _, skipped = backup_source(str(self.source), str(self.dest), max_backups=1)
        self.assertEqual(skipped, [str(self.source)])
        self.assertTrue(all(path.exists() for path in old))
        with patch("core.engine.zipfile.ZipFile", side_effect=OSError("disk full")):
            result = backup_all([{"path": str(self.source)}], str(self.dest), max_backups=1)
        self.assertFalse(result[0]["success"])
        self.assertTrue(all(path.exists() for path in old))

    def test_folder_backup_uses_configured_limit(self):
        source = self.root / "project"
        source.mkdir()
        (source / "data.txt").write_text("data", encoding="utf-8")
        for _ in range(3):
            result = backup_all([{"path": str(source)}], str(self.dest), max_backups=1)
            self.assertTrue(result[0]["success"])
        self.assertEqual(len(list((self.dest / "project备份").glob("*.zip"))), 1)

    def test_invalid_limit_does_not_create_or_remove_backups(self):
        old = self.old_backups(2)
        for invalid in (0, -1, True, "5"):
            with self.assertRaises(ValueError):
                backup_source(str(self.source), str(self.dest), max_backups=invalid)
        self.assertEqual(set(self.folder.iterdir()), set(old))

    def test_cli_applies_saved_limit(self):
        old = self.old_backups(3)
        config = Config(str(self.root / "config.json"))
        config.destination = str(self.dest)
        config.sources = [{"path": str(self.source), "enabled": True}]
        config.max_backups = 2
        with patch("cli.commands.Config", return_value=config), \
                patch("cli.commands.BackupLogger"), patch("builtins.print"):
            cmd_run(None)
        self.assertEqual(len(list(self.folder.glob("*.zip"))), 2)
        self.assertFalse(old[0].exists())
        self.assertTrue(old[-1].exists())


if __name__ == "__main__":
    unittest.main()
