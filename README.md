# Clair Stockage

A visual local storage explorer for Windows — **version 0.6.0**.

**Understand what takes up space on your PC without opening file contents or deleting anything.**

Clair Stockage scans selected folders, calculates their sizes, and presents the results as a list or a visual map. It helps you locate used storage while keeping measured data, partial results, and AI interpretations clearly distinguishable.

## Features

- **Explore storage by folder:** compare sizes, extensions, and files, then navigate through the directory tree.
- **Find large items:** use the sortable list and color-coded map to identify large folders.
- **Control each scan:** no scan starts automatically. Choose a drive or folder, follow progress, and stop the scan when needed.
- **Check scan coverage:** access errors and interrupted scans are reported; partial sizes are identified as incomplete.
- **Request an optional explanation:** a local AI report interprets metadata and technical clues alongside the measured results.

Clair Stockage is a read-only exploration tool: it does not delete, move, or modify the files being scanned.

## Installation and launch

### Requirements

- Windows
- Python 3.11 or 3.12 with Tcl/Tk, included in the standard Windows Python installation
- No additional Python packages required

### Start the application

Download or clone the repository, then run `Launch-Admin.cmd` and accept the Windows UAC prompt. The application opens without starting a scan. Select a drive, your home folder (**Dossier personnel**), or **Choisir un dossier** to begin.

The launcher requests administrator privileges to improve access to protected folders. Some folders may still remain inaccessible.

You can also start the application from the repository root in PowerShell without elevation:

```powershell
py -3.12 -m clair_storage
```

In this case, access depends on your account permissions. Neither launch method changes file permissions or ownership.

The application interface is currently in French.

## Explore your storage

- **List (Liste):** sort items by name or size, search within the current folder, and double-click folders to navigate.
- **Map (Carte):** view items in proportion to their size. Colors indicate size ranges.
- **Access and coverage (Accès et couverture):** inspect errors, skipped items, and incomplete results.
- **Stop scan (Arrêter le scan):** stop scanning and retain the available results as partial measurements.

Full scans have no automatic time or item limit. Scanning a large volume may take time and consume significant memory.

## Optional local AI report

The measured report works without AI. To request an interpretation, install [Ollama](https://ollama.com/) separately and download a local model, for example:

```powershell
ollama pull qwen3:8b
```

Open **Bilan IA**, check the Ollama connection with **Tester Ollama**, select an available model, and click **Analyser ce dossier**. The application uses a local Ollama instance and does not install software or download models on your behalf.

The AI report:

- Uses metadata, names, and technical clues without reading file contents.
- Examines a limited sample of folders rather than the entire directory tree.
- Separates measured findings from generated interpretations, which require review.
- Takes no action on files.

The option to include file names and technical markers is enabled by default. Disabling it excludes individual file names and marker discovery, while retaining folder names.

Use **Voir les données envoyées** to inspect the metadata prepared for the report. **Exporter le bilan** saves a JSON file that may include this metadata and intermediate AI notes.

## Privacy and measurement limitations

- The scanner reads metadata needed for measurement, including names, sizes, and directory information. It does not open file contents.
- Individual file names and technical markers are sent to local Ollama only when the corresponding option is enabled and you request an AI report. Folder names and other relevant report metadata remain included.
- Displayed sizes are **logical sizes** and may differ from physical disk usage. Accessible links are followed, external targets may contribute to logical totals, and file hard links are not deduplicated.
- Inaccessible folders, system errors, and interrupted scans can produce partial results. Running as administrator may improve access but does not guarantee complete coverage.
- Results reflect observations made during the scan. Files may change while scanning is in progress.

## Tests

The automated tests use the Python standard library:

```powershell
py -3.12 -m unittest discover -s tests -v
```

See [docs/VALIDATION.md](./docs/VALIDATION.md) for test coverage and outstanding manual checks. That document is currently in French.
