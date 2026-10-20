"""Tests for organiser.py. Every test works in a temporary folder, never the real Downloads."""

import ctypes
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from organiser import (Move, apply_moves, categorise, find_last_run, load_config,
                       plan_moves, scan, skip_reason, undo_run, unique_destination)

FILE_ATTRIBUTE_HIDDEN = 0x2


class OrganiserTestCase(unittest.TestCase):
    """Gives each test an empty folder to organise and a separate log folder."""

    def setUp(self):
        self.config = load_config()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.folder = root / "Downloads"
        self.folder.mkdir()
        self.log_dir = root / "logs"

    def make(self, relative: str, content: str | None = None) -> Path:
        path = self.folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if content is not None else relative, encoding="utf-8")
        return path

    def organise(self) -> tuple[Path, list[tuple[Move, str]]]:
        moves = plan_moves(self.folder, scan(self.folder, self.config))
        return apply_moves(self.folder, moves, log_dir=self.log_dir)

    def contents(self) -> dict[str, str]:
        """Every file under the folder, as relative path -> text."""
        return {str(p.relative_to(self.folder)): p.read_text(encoding="utf-8")
                for p in self.folder.rglob("*") if p.is_file()}

    def folders(self) -> set[str]:
        return {str(p.relative_to(self.folder)) for p in self.folder.rglob("*") if p.is_dir()}


class CategoriseTests(OrganiserTestCase):

    def test_known_extensions(self):
        self.assertEqual(categorise(Path("a.pdf"), self.config), "Documents")
        self.assertEqual(categorise(Path("a.msi"), self.config), "Installers")
        self.assertEqual(categorise(Path("a.jpeg"), self.config), "Images")
        self.assertEqual(categorise(Path("a.7z"), self.config), "Archives")
        self.assertEqual(categorise(Path("a.mp3"), self.config), "Media")

    def test_extension_case_is_ignored(self):
        self.assertEqual(categorise(Path("PHOTO.PNG"), self.config), "Images")

    def test_unknown_or_missing_extension_goes_to_other(self):
        self.assertEqual(categorise(Path("notes.xyz"), self.config), "Other")
        self.assertEqual(categorise(Path("README"), self.config), "Other")


class SkipTests(OrganiserTestCase):

    def test_system_files(self):
        self.assertEqual(skip_reason(self.make("desktop.ini"), self.config), "system file")
        self.assertEqual(skip_reason(self.make("Thumbs.db"), self.config), "system file")

    def test_partial_downloads(self):
        for name in ("big.zip.crdownload", "film.mp4.part", "setup.tmp"):
            with self.subTest(name=name):
                self.assertEqual(skip_reason(self.make(name), self.config), "partial download")

    def test_dot_files(self):
        self.assertEqual(skip_reason(self.make(".secret"), self.config), "hidden file")

    def test_hidden_attribute(self):
        path = self.make("hidden.pdf")
        ctypes.windll.kernel32.SetFileAttributesW(str(path), FILE_ATTRIBUTE_HIDDEN)
        self.assertEqual(skip_reason(path, self.config), "hidden file")

    def test_ordinary_file_is_not_skipped(self):
        self.assertIsNone(skip_reason(self.make("report.pdf"), self.config))


class ScanTests(OrganiserTestCase):

    def test_lists_top_level_files_only_sorted_by_name(self):
        self.make("b.pdf")
        self.make("A.exe")
        self.make("Documents/already-sorted.pdf")
        names = [f.path.name for f in scan(self.folder, self.config)]
        self.assertEqual(names, ["A.exe", "b.pdf"])

    def test_records_size_category_and_skip_reason(self):
        self.make("report.pdf", "12345")
        self.make("desktop.ini")
        desktop, report = scan(self.folder, self.config)
        self.assertEqual((report.category, report.size, report.skip_reason), ("Documents", 5, None))
        self.assertEqual(desktop.skip_reason, "system file")


class PlanTests(OrganiserTestCase):

    def test_plans_moves_into_category_folders(self):
        self.make("report.pdf")
        self.make("setup.exe")
        moves = plan_moves(self.folder, scan(self.folder, self.config))
        self.assertEqual([m.destination.relative_to(self.folder) for m in moves],
                         [Path("Documents/report.pdf"), Path("Installers/setup.exe")])

    def test_skipped_files_are_not_planned(self):
        self.make("desktop.ini")
        self.make("big.zip.crdownload")
        self.assertEqual(plan_moves(self.folder, scan(self.folder, self.config)), [])

    def test_planning_moves_nothing(self):
        self.make("report.pdf")
        before = self.contents()
        plan_moves(self.folder, scan(self.folder, self.config))
        self.assertEqual(self.contents(), before)
        self.assertEqual(self.folders(), set())

    def test_clash_with_existing_file_is_renamed(self):
        self.make("Documents/report.pdf")
        self.make("Documents/report (1).pdf")
        self.make("report.pdf")
        [move] = plan_moves(self.folder, scan(self.folder, self.config))
        self.assertEqual(move.destination.name, "report (2).pdf")
        self.assertTrue(move.renamed)

    def test_clash_check_ignores_case(self):
        # Windows treats Report.PDF and report.pdf as the same file.
        self.make("Documents/report.pdf")
        self.make("Report.PDF")
        [move] = plan_moves(self.folder, scan(self.folder, self.config))
        self.assertEqual(move.destination.name, "Report (1).PDF")

    def test_unique_destination_avoids_names_already_planned(self):
        target = self.folder / "Documents" / "a.pdf"
        taken = {target, target.with_name("a (1).pdf")}
        self.assertEqual(unique_destination(target, taken).name, "a (2).pdf")


class ApplyTests(OrganiserTestCase):

    def test_moves_files_and_keeps_their_contents(self):
        self.make("report.pdf", "report contents")
        self.make("photo.PNG", "photo contents")
        self.make("desktop.ini", "ini contents")
        _, failures = self.organise()
        self.assertEqual(failures, [])
        self.assertEqual(self.contents(), {
            "desktop.ini": "ini contents",
            r"Documents\report.pdf": "report contents",
            r"Images\photo.PNG": "photo contents",
        })

    def test_never_overwrites_an_existing_file(self):
        self.make("Documents/report.pdf", "already there")
        self.make("report.pdf", "incoming")
        self.organise()
        self.assertEqual(self.contents(), {
            r"Documents\report.pdf": "already there",
            r"Documents\report (1).pdf": "incoming",
        })

    def test_writes_a_log_of_each_move_and_created_folder(self):
        self.make("Documents/old.pdf")
        self.make("report.pdf")
        self.make("setup.exe")
        log_path, _ = self.organise()
        record = json.loads(log_path.read_text(encoding="utf-8"))
        self.assertEqual(record["folder"], str(self.folder.resolve()))
        self.assertEqual(len(record["moves"]), 2)
        # Documents already existed, so only Installers counts as created.
        self.assertEqual(record["created_folders"], [str(self.folder / "Installers")])

    def test_file_appearing_at_destination_after_planning_is_left_alone(self):
        self.make("report.pdf", "incoming")
        moves = plan_moves(self.folder, scan(self.folder, self.config))
        self.make("Documents/report.pdf", "arrived after planning")
        log_path, failures = apply_moves(self.folder, moves, log_dir=self.log_dir)
        self.assertEqual([reason for _, reason in failures], ["destination already exists"])
        self.assertEqual(self.contents(), {
            "report.pdf": "incoming",
            r"Documents\report.pdf": "arrived after planning",
        })
        self.assertEqual(json.loads(log_path.read_text(encoding="utf-8"))["moves"], [])

    def test_missing_source_is_reported_and_the_rest_still_move(self):
        self.make("a.pdf")
        self.make("b.pdf")
        moves = plan_moves(self.folder, scan(self.folder, self.config))
        (self.folder / "a.pdf").unlink()
        _, failures = apply_moves(self.folder, moves, log_dir=self.log_dir)
        self.assertEqual([m.source.name for m, _ in failures], ["a.pdf"])
        self.assertEqual(set(self.contents()), {r"Documents\b.pdf"})

    def test_runs_in_the_same_second_get_separate_logs(self):
        self.make("a.pdf")
        first, _ = self.organise()
        self.make("b.pdf")
        second, _ = self.organise()
        self.assertNotEqual(first, second)
        self.assertEqual(len(list(self.log_dir.glob("moves-*.json"))), 2)


class UndoTests(OrganiserTestCase):

    def test_round_trip_restores_the_folder_exactly(self):
        self.make("report.pdf", "r")
        self.make("song.mp3", "s")
        self.make("desktop.ini", "d")
        before = self.contents()
        log_path, _ = self.organise()
        undone, failures = undo_run(log_path)
        self.assertEqual((len(undone), failures), (2, []))
        self.assertEqual(self.contents(), before)
        self.assertEqual(self.folders(), set())

    def test_renamed_file_goes_back_under_its_original_name(self):
        self.make("Documents/report.pdf", "already there")
        self.make("report.pdf", "incoming")
        log_path, _ = self.organise()
        undo_run(log_path)
        self.assertEqual(self.contents(), {
            "report.pdf": "incoming",
            r"Documents\report.pdf": "already there",
        })

    def test_created_folder_is_kept_if_something_else_is_in_it(self):
        self.make("report.pdf")
        log_path, _ = self.organise()
        self.make("Documents/added-later.pdf")
        undo_run(log_path)
        self.assertEqual(self.folders(), {"Documents"})
        self.assertIn(r"Documents\added-later.pdf", self.contents())

    def test_blocked_file_is_left_and_retried_on_the_next_undo(self):
        self.make("a.pdf", "original")
        self.make("b.zip")
        log_path, _ = self.organise()
        self.make("a.pdf", "new file in the way")

        undone, failures = undo_run(log_path)
        self.assertEqual([m.source.name for m in undone], ["b.zip"])
        self.assertEqual([reason for _, reason in failures],
                         ["a file with the original name is already there"])
        self.assertEqual(self.contents()["a.pdf"], "new file in the way")
        self.assertEqual(self.contents()[r"Documents\a.pdf"], "original")

        (self.folder / "a.pdf").unlink()
        undone, failures = undo_run(log_path)
        self.assertEqual(([m.source.name for m in undone], failures), (["a.pdf"], []))
        self.assertEqual(self.contents(), {"a.pdf": "original", "b.zip": "b.zip"})

    def test_file_removed_since_the_move_is_reported(self):
        self.make("a.pdf")
        log_path, _ = self.organise()
        (self.folder / "Documents" / "a.pdf").unlink()
        _, failures = undo_run(log_path)
        self.assertEqual([reason for _, reason in failures],
                         ["file is no longer where it was moved to"])


class FindLastRunTests(OrganiserTestCase):

    def test_nothing_to_undo_without_logs(self):
        self.log_dir.mkdir()
        self.assertIsNone(find_last_run(self.folder, self.log_dir))

    def test_picks_the_most_recent_run_and_steps_back_after_each_undo(self):
        self.make("a.pdf")
        first, _ = self.organise()
        self.make("b.pdf")
        second, _ = self.organise()
        self.assertEqual(find_last_run(self.folder, self.log_dir), second)
        undo_run(second)
        self.assertEqual(find_last_run(self.folder, self.log_dir), first)
        undo_run(first)
        self.assertIsNone(find_last_run(self.folder, self.log_dir))

    def test_ignores_runs_on_other_folders(self):
        other = self.folder.parent / "Other folder"
        other.mkdir()
        (other / "a.pdf").write_text("a")
        apply_moves(other, plan_moves(other, scan(other, self.config)), log_dir=self.log_dir)
        self.assertIsNone(find_last_run(self.folder, self.log_dir))

    def test_matches_the_folder_however_its_path_is_written(self):
        self.make("a.pdf")
        log_path, _ = self.organise()
        spelt_differently = Path(str(self.folder).upper() + "\\")
        self.assertEqual(find_last_run(spelt_differently, self.log_dir), log_path)

    def test_partly_undone_run_is_still_offered(self):
        self.make("a.pdf")
        self.make("b.zip")
        log_path, _ = self.organise()
        self.make("a.pdf", "in the way")
        undo_run(log_path)
        self.assertEqual(find_last_run(self.folder, self.log_dir), log_path)


if __name__ == "__main__":
    unittest.main()
