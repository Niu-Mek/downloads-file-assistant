"""Scan, plan and move logic for the Downloads file assistant."""

import json
import os
import shutil
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("config.json")
LOG_DIR = Path(__file__).with_name("logs")


@dataclass
class FileInfo:
    path: Path
    category: str
    size: int
    modified: datetime
    skip_reason: str | None = None


@dataclass
class Move:
    source: Path
    destination: Path

    @property
    def renamed(self) -> bool:
        return self.source.name != self.destination.name


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    # Build a lower-case extension -> category lookup once.
    config["extension_map"] = {
        ext.lower(): category
        for category, extensions in config["categories"].items()
        for ext in extensions
    }
    return config


def categorise(path: Path, config: dict) -> str:
    return config["extension_map"].get(path.suffix.lower(), config["fallback_category"])


def skip_reason(path: Path, config: dict) -> str | None:
    """Return why a file should be left alone, or None if it can be organised."""
    if path.name.lower() in (name.lower() for name in config["skip_names"]):
        return "system file"
    if path.suffix.lower() in config["skip_extensions"]:
        return "partial download"
    if path.name.startswith("."):
        return "hidden file"
    attributes = getattr(path.stat(), "st_file_attributes", 0)
    if attributes & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM):
        return "hidden file"
    return None


def scan(folder: Path, config: dict) -> list[FileInfo]:
    """List the files directly inside folder. Subfolders are not entered."""
    files = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file():
            continue
        info = path.stat()
        files.append(FileInfo(
            path=path,
            category=categorise(path, config),
            size=info.st_size,
            modified=datetime.fromtimestamp(info.st_mtime),
            skip_reason=skip_reason(path, config),
        ))
    return files


def unique_destination(target: Path, taken: set[Path]) -> Path:
    """Return target, or 'name (1).ext', 'name (2).ext'... if it is already used."""
    candidate = target
    counter = 1
    while candidate.exists() or candidate in taken:
        candidate = target.with_name(f"{target.stem} ({counter}){target.suffix}")
        counter += 1
    return candidate


def plan_moves(folder: Path, files: list[FileInfo]) -> list[Move]:
    """Work out where each file should go. Nothing is moved here."""
    moves = []
    taken: set[Path] = set()
    for f in files:
        if f.skip_reason:
            continue
        destination = unique_destination(folder / f.category / f.path.name, taken)
        taken.add(destination)
        moves.append(Move(f.path, destination))
    return moves


def read_log(log_path: Path) -> dict:
    with open(log_path, encoding="utf-8") as f:
        return json.load(f)


def write_log(log_path: Path, record: dict) -> None:
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)


def folder_key(folder: Path | str) -> str:
    """Normalise a folder path so the same folder always compares equal on Windows."""
    return os.path.normcase(str(Path(folder).resolve()))


def apply_moves(folder: Path, moves: list[Move],
                log_dir: Path = LOG_DIR) -> tuple[Path, list[tuple[Move, str]]]:
    """Carry out the moves, logging each one as it happens so undo always matches
    what was actually done. Returns the log path and any moves that failed."""
    log_dir.mkdir(exist_ok=True)
    log_path = unique_destination(log_dir / f"moves-{datetime.now():%Y%m%d-%H%M%S}.json", set())
    record = {
        "folder": str(folder.resolve()),
        "started": datetime.now().isoformat(),
        "created_folders": [],
        "moves": [],
    }
    write_log(log_path, record)

    failures = []
    for move in moves:
        # Check again just before moving: never overwrite, even if the folder
        # changed since the plan was made.
        if move.destination.exists():
            failures.append((move, "destination already exists"))
            continue
        try:
            if not move.destination.parent.exists():
                move.destination.parent.mkdir()
                record["created_folders"].append(str(move.destination.parent))
            shutil.move(move.source, move.destination)
        except OSError as error:
            failures.append((move, error.strerror or str(error)))
            continue
        record["moves"].append({"source": str(move.source),
                                "destination": str(move.destination)})
        write_log(log_path, record)
    return log_path, failures


def find_last_run(folder: Path, log_dir: Path = LOG_DIR) -> Path | None:
    """Return the log of the most recent run on folder that still has moves to undo."""
    target = folder_key(folder)
    candidates = []
    for log_path in log_dir.glob("moves-*.json"):
        record = read_log(log_path)
        if folder_key(record["folder"]) != target:
            continue
        if any(not entry.get("undone") for entry in record["moves"]):
            candidates.append((record["started"], log_path))
    return max(candidates)[1] if candidates else None


def undo_run(log_path: Path) -> tuple[list[Move], list[tuple[Move, str]]]:
    """Move files back to where they came from, newest move first. Each move is
    marked as undone in the log, so running undo again only retries what failed."""
    record = read_log(log_path)
    undone = []
    failures = []
    for entry in reversed(record["moves"]):
        if entry.get("undone"):
            continue
        move = Move(Path(entry["source"]), Path(entry["destination"]))
        if move.source.exists():
            failures.append((move, "a file with the original name is already there"))
            continue
        if not move.destination.exists():
            failures.append((move, "file is no longer where it was moved to"))
            continue
        try:
            shutil.move(move.destination, move.source)
        except OSError as error:
            failures.append((move, error.strerror or str(error)))
            continue
        entry["undone"] = True
        undone.append(move)
        write_log(log_path, record)

    # Tidy up category folders this run created, but only if they are now empty:
    # rmdir refuses to remove a folder that still holds anything.
    for created in record.get("created_folders", []):
        try:
            Path(created).rmdir()
        except OSError:
            pass
    return undone, failures
