"""Downloads file assistant: command-line entry point."""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from organiser import apply_moves, find_last_run, load_config, plan_moves, scan, undo_run

DEFAULT_FOLDER = Path.home() / "Downloads"


def format_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def fit(name: str, width: int = 50) -> str:
    """Shorten long names with an ellipsis so the columns stay aligned."""
    return name if len(name) <= width else name[:width - 3] + "..."


def cmd_scan(folder: Path) -> None:
    files = scan(folder, load_config())
    if not files:
        print(f"No files found in {folder}")
        return

    by_category = defaultdict(list)
    skipped = []
    for f in files:
        (skipped if f.skip_reason else by_category[f.category]).append(f)

    print(f"Scanned {folder}: {plural(len(files), 'file')}\n")
    for category in sorted(by_category):
        group = by_category[category]
        total = sum(f.size for f in group)
        print(f"{category} ({plural(len(group), 'file')}, {format_size(total)})")
        for f in group:
            print(f"  {fit(f.path.name):<50} {format_size(f.size):>10}  {f.modified:%Y-%m-%d}")
        print()

    if skipped:
        print(f"Skipped ({plural(len(skipped), 'file')})")
        for f in skipped:
            print(f"  {fit(f.path.name):<50} {f.skip_reason}")


def cmd_organise(folder: Path, apply: bool) -> None:
    files = scan(folder, load_config())
    moves = plan_moves(folder, files)
    if not moves:
        print(f"Nothing to organise in {folder}")
        return

    heading = "Moving" if apply else "Dry run:"
    verb = "" if apply else " would be moved"
    print(f"{heading} {plural(len(moves), 'file')}{verb} in {folder}\n")
    for move in moves:
        target = move.destination.relative_to(folder)
        note = "  (renamed to avoid a clash)" if move.renamed else ""
        print(f"  {fit(move.source.name):<50} -> {target}{note}")

    skipped = sum(1 for f in files if f.skip_reason)
    if skipped:
        print(f"\n{plural(skipped, 'file')} left alone (see 'scan' for details)")

    if not apply:
        print("\nNo files were moved. Add --apply to carry out these moves.")
        return

    log_path, failures = apply_moves(folder, moves)
    moved = len(moves) - len(failures)
    print(f"\nMoved {plural(moved, 'file')}. Log saved to {log_path}")
    if failures:
        was = "was" if len(failures) == 1 else "were"
        print(f"\n{plural(len(failures), 'file')} could not be moved and {was} left in place:")
        for move, reason in failures:
            print(f"  {fit(move.source.name):<50} {reason}")
    if moved:
        print("\nRun 'undo' to put them back.")


def cmd_undo(folder: Path) -> None:
    log_path = find_last_run(folder)
    if log_path is None:
        print(f"Nothing to undo for {folder}")
        return

    print(f"Undoing the run logged in {log_path}\n")
    undone, failures = undo_run(log_path)
    for move in undone:
        print(f"  {move.destination.relative_to(folder)} -> {move.source.name}")
    print(f"\nPut back {plural(len(undone), 'file')}.")
    if failures:
        was = "was" if len(failures) == 1 else "were"
        print(f"\n{plural(len(failures), 'file')} could not be put back and {was} not moved:")
        for move, reason in failures:
            print(f"  {fit(str(move.destination.relative_to(folder))):<50} {reason}")
        print("\nRun 'undo' again after sorting these out to retry them.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tidy up your Downloads folder.")
    parser.add_argument("--path", type=Path, default=DEFAULT_FOLDER,
                        help=f"folder to work on (default: {DEFAULT_FOLDER})")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("scan", help="report what's in the folder")
    organise = commands.add_parser("organise", help="sort files into category folders")
    organise.add_argument("--apply", action="store_true",
                          help="actually move the files (without this, only show the plan)")
    commands.add_parser("undo", help="put back the files moved by the last run on this folder")

    args = parser.parse_args()
    if not args.path.is_dir():
        sys.exit(f"Folder not found: {args.path}")

    if args.command == "scan":
        cmd_scan(args.path)
    elif args.command == "organise":
        cmd_organise(args.path, args.apply)
    elif args.command == "undo":
        cmd_undo(args.path)


if __name__ == "__main__":
    main()
