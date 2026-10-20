# Downloads File Assistant

A small Python command-line tool that tidies your Windows Downloads folder. It sorts files into category folders by type, always shows you the plan before touching anything, and can undo every move.

## Features

- **Scan** the folder and list files by category, size and date.
- **Organise** files into category folders (`Documents`, `Installers`, `Images`, `Archives`, `Media`, `Other`).
- **Dry run by default:** nothing moves until you add `--apply`.
- **Never overwrites:** if `report.pdf` already exists, the incoming file becomes `report (1).pdf`.
- **Undo:** every run is logged, and `undo` puts the files back.
- **Leaves some files alone:** system files (`desktop.ini`, `thumbs.db`), partial downloads (`.crdownload`, `.part`, `.tmp`) and hidden files.

## Requirements

- Windows
- Python 3.12 or later

It uses the standard library only, so there is nothing to `pip install`.

## Usage

```
python file_assistant.py scan                 # report what's in Downloads
python file_assistant.py organise             # dry run: show the planned moves
python file_assistant.py organise --apply     # carry out the moves
python file_assistant.py undo                 # put back the files from the last run
```

Every command works on `%USERPROFILE%\Downloads` by default. Use `--path` to work on another folder, for example a test copy:

```
python file_assistant.py --path "C:\Temp\Downloads copy" organise
```

`--path` goes before the command name.

### Example dry run

```
Dry run: 3 files would be moved in C:\Users\you\Downloads

  notes.xyz                                          -> Other\notes.xyz
  photo.PNG                                          -> Images\photo.PNG
  report.pdf                                         -> Documents\report (1).pdf  (renamed to avoid a clash)

1 file left alone (see 'scan' for details)

No files were moved. Add --apply to carry out these moves.
```

## Categories

Categories are set in `config.json`, so you can change them without touching the code:

| Folder       | Extensions                          |
|--------------|-------------------------------------|
| `Documents`  | pdf, docx, xlsx, pptx, txt, csv     |
| `Installers` | exe, msi                            |
| `Images`     | jpg, jpeg, png, gif, svg            |
| `Archives`   | zip, rar, 7z                        |
| `Media`      | mp4, mp3, wav                       |
| `Other`      | anything not listed above           |

Extensions are matched case-insensitively. Only files directly inside the folder are sorted; existing subfolders are not entered.

## How undo works

- Each `organise --apply` run writes a log to `logs\moves-<date>-<time>.json`, recording each move as it happens.
- `undo` reverses the most recent run on the folder you point it at. Runs on other folders are ignored, so undoing a test copy never affects your real Downloads.
- Running `undo` again steps back through earlier runs.
- If a file cannot be put back (for example a new file with the same name is now in its place), it is left where it is and reported. Run `undo` again once you have sorted it out, and only the remaining files are retried.
- Category folders created by the run are removed afterwards, but only if they are empty.

## Safety rules

- Nothing moves without `--apply`.
- No file is ever deleted or overwritten.
- Every move is logged and can be undone.

## Running the tests

```
python -m unittest discover -s tests
```

The tests use the standard library's `unittest` and run in temporary folders, so they never touch your real Downloads or the `logs\` folder.

## Project layout

```
file_assistant.py        # command-line entry point
organiser.py             # scan, plan, move and undo logic
config.json              # category-to-extension rules
tests\test_organiser.py  # automated tests
logs\                    # move logs used by undo (not committed)
PLAN.md                  # design plan and approved decisions
```

## Status

Version 1 is complete: scan, organise, apply and undo all work, are covered by automated tests, and have been rehearsed end to end on a copy of a real Downloads folder.

Ideas for later versions include sorting by date, finding duplicates by content hash, watching the folder for new downloads, and a simple GUI or scheduled task.
