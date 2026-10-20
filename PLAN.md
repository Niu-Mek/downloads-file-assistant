# Plan: Downloads File Manager Assistant (Pilot_P1)

**Status:** Approved, 20 October 2026
**Author:** Mekere Manasi

## Goal

A Python command-line assistant that tidies `C:\Users\IT-Admin\Downloads`. It creates category folders, moves files into them by type, and can undo every move. It always shows what it plans to do before it touches anything.

## Starting point

At planning time the Downloads folder held 10 files (6 PDFs, 3 installers and a `desktop.ini`) and no subfolders. Python was not installed.

## Scope for version 1

**What it will do:**

1. **Scan** the Downloads folder and list the files by category, size and date.
2. **Sort by type** into category folders:

   | Folder       | Extensions                          |
   |--------------|-------------------------------------|
   | `Documents`  | pdf, docx, xlsx, pptx, txt, csv     |
   | `Installers` | exe, msi                            |
   | `Images`     | jpg, png, gif, svg                  |
   | `Archives`   | zip, rar, 7z                        |
   | `Media`      | mp4, mp3, wav                       |
   | `Other`      | anything not listed above           |

3. **Dry run by default:** it prints the plan and only moves files when you add `--apply`.
4. **Handle name clashes safely:** it never overwrites a file. If `report.pdf` already exists, the new one becomes `report (1).pdf`.
5. **Undo:** every run writes a log of the moves, and `undo` reverses the most recent run.
6. **Skip some files:** system files (`desktop.ini`), partial downloads (`.crdownload`, `.part`, `.tmp`) and hidden files are left alone.

**Left for later:**

- Sorting by date (for example `Documents\2026-10`)
- Finding duplicates by content hash
- Watching the folder and sorting new downloads automatically
- A simple GUI or a scheduled task

## Project layout

```
Pilot_P1\
├── file_assistant.py     # entry point and command-line commands
├── organiser.py          # scan, plan and move logic
├── config.json           # category-to-extension rules (editable, no code changes)
├── logs\                 # move logs used by undo
├── tests\
│   └── test_organiser.py # runs against a temporary folder, never the real Downloads
├── PLAN.md
└── README.md
```

## Commands

```
python file_assistant.py scan            # report what's there
python file_assistant.py organise        # dry run: show the planned moves
python file_assistant.py organise --apply
python file_assistant.py undo            # reverse the last run
python file_assistant.py mkdir <name>    # create a folder in Downloads
```

## Technical choices

- Standard library only (`pathlib`, `shutil`, `argparse`, `json`, `logging`), so there's nothing to `pip install`.
- Python 3.12 or later.
- A target folder option (`--path`) so we can test on a copy before using the real Downloads.

## Build steps

1. Install Python: `winget install Python.Python.3.12`, or the python.org installer with "Add to PATH" ticked.
2. Write `config.json` and the `scan` command.
3. Add the dry-run `organise` command and check its output against the real Downloads.
4. Add `--apply` with safe moving and logging.
5. Add `undo`.
6. Write the tests, then do a final test on a copy of Downloads before the real run.

## Safety rules

- Nothing moves without `--apply`.
- Nothing is ever deleted or overwritten.
- Every move is logged and can be undone.

## Approved decisions

| Decision            | Outcome                                                        |
|---------------------|----------------------------------------------------------------|
| Python installation | Python 3.12 via `winget` or python.org, added to PATH           |
| Categories          | As listed in the table above                                   |
| Installers          | `.exe` and `.msi` files move into `Installers`                 |
