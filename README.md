# PubChem bulk data retrieval client

A command-line client designed to query and retrieve chemical data from PubChem in bulk. Optimized for Windows, it features system proxy detection, automatic rate-limit compliance, double-track exponential-backoff retries, local caching, and data preservation during interrupts. The client aligns output rows with the input spreadsheet.

---

## Core features

* **Automatic type inference**
  The client automatically detects the identifier type using regular expressions:
  - Pure Numeric -> `cid`
  - Starts with `InChI=` -> `inchi`
  - 27-character with double hyphens (for example, `XXXXX-XXXXX-X`) -> `inchikey`
  - Contains chemical symbols and elements, excluding proxy letters -> `smiles`
  - Others (common lowercase names, commercial terms) -> `name`
  It uses a lowercase alphabetical check to avoid collisions between common names (such as `aspirin`) and short SMILES strings.

* **Excel multi-sheet processing**
  The client supports Excel files with multiple worksheets:
  - **Global de-duplication**: Aggregates all identifiers across all worksheets and filters out duplicates and cached entries. It only queries PubChem for unique, uncached identifiers, reducing network requests.
  - **Preservation of structure**: Processes worksheets sequentially to output data matching the original sheet names, row counts, and physical order.
  - **CSV fallback**: Merges all worksheets vertically if you choose to export to CSV.

* **Automatic retries and proxy support**
  - **System proxy detection**: Automatically detects system proxy configurations in Windows registries and applies them to the current process.
  - **SSL patch**: Dynamically patches Python's `ssl.create_default_context` to allow unverified SSL connections. This helps avoid SSL errors, such as `ssl.SSLEOFError`, caused by local proxies under Python 3.13.
  - **Network connection retries**: Retries indefinitely using exponential backoff with random jitter when encountering socket timeouts, connection resets, or SSL handshake failures.
  - **HTTP error retries**: Retries up to 5 times when receiving 503 (Server Busy) or 504 (Gateway Timeout) status codes, then falls back to a 404 response.
  - **Rate limit compliance**: Introduces a 0.25-second delay between requests to comply with the PubChem rate limit (maximum of 5 requests per second).

* **Local caching**
  The client persists cache data to `cache/pubchem_cache.json`.
  - Uses the `InChIKey` (a 27-character hash of the chemical structure) as the primary key to store detailed compound properties.
  - Uses a secondary index (`query_index`) to map query aliases—including synonyms, CIDs, SMILES, InChIs, and IUPAC names—to their unique InChIKey. This allows subsequent searches with different identifiers to hit the local cache.
  - **Negative caching**: Caches failed queries and non-existent chemical terms as `"404 Not Found"` to avoid repeated queries.
  - **Atomic writing**: Writes data to a temporary file before renaming it to prevent file corruption during sudden interruptions.

* **Row alignment and interrupt protection**
  - Extracts identifiers from the first column of the input spreadsheet (supports automatic header detection).
  - Ensures that the output file has the same number of rows and physical order as the input file.
  - Populates output cells with `"404 Not Found"` for missing or non-matching terms to prevent row shifting.
  - **Interrupt protection**: Captures keyboard interrupts (`Ctrl+C`), writes currently retrieved and cached data to the output file, fills unretrieved rows with `"404 Not Found"`, and exits.

* **Chinese logs and error messages**
  Error messages, CLI validation warnings, and logging outputs are printed in Chinese to facilitate local debugging.

* **Interactive CLI display**
  Uses the `rich` library to display banners, progress bars, and execution summary tables.

---

## Installation

Requires Python 3.8 or later. To install the dependencies, run:

```bash
pip install -r requirements.txt
```

---

## Usage

Run the tool using the command line:

```bash
python app.py --input <input_path> [--scope <selected_scopes>] [--output <output_path>] [--batch <batch_size>] [--header <header_strategy>]
```

### CLI arguments
| Argument | Default | Description (Error messages are output in Chinese) |
| :--- | :--- | :--- |
| `--input` | **Required** | Path to the input file (.csv, .xlsx, or .xls format). |
| `--scope` | `cid name smiles weight` | Space-separated list of compound properties to export (see table below). |
| `--output` | `output.csv` | Output file path. The file extension determines the format (.csv or .xlsx). |
| `--batch` | `100` | Batch size for queries (applies only to pure numeric CIDs). |
| `--header` | `auto` | Header detection strategy: `auto` (automatically detect headers), `yes` (skip the first row), `no` (treat the first row as data). |

---

## Examples

### 1. Default run
Run with default settings (outputs to `output.csv`):
```bash
python app.py --input my_compounds.xlsx
```

### 2. Run with custom options
Query custom properties, specify a batch size, and output to an Excel file:
```bash
python app.py --input dataset.xlsx --scope cid name smiles weight formula xlogp tpsa --output result.xlsx --batch 50
```

---

## Run tests

The project includes a suite of unit tests located in the `tests/` directory. To run the tests:

```bash
python -m pytest -v
```

---

## Project structure

The project structure is organized as follows:

```
pubchem-scrabber/
│
├── app.py                      # Main entrypoint, console UI layout, and global error catches
├── requirements.txt            # Third-party dependency configurations
├── README.md                   # English User Guide (This file)
├── README.zh_CN.md             # Chinese User Guide
│
├── lib/                        # Core service logic
│   ├── cli_parser.py           # CLI parser, CSV/Excel loaders, and auto-header parser
│   ├── network_engine.py       # Proxy sniffing, SSL unverified patches, and smart retries
│   ├── cache_manager.py        # Double-core reverse cache databases and negative caching
│   └── batch_dispatcher.py     # Batch scheduling dispatcher and row alignment
│
└── tests/                      # Testing package suites
    ├── test_cli_parser.py
    ├── test_network_engine.py
    ├── test_cache_manager.py
    └── test_batch_dispatcher.py
```
