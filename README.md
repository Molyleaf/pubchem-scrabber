# PubChem Bulk Automatic Client 🧪

An enterprise-grade, high-resilience **PubChem Chemical Data Bulk Scraper & Aligning Client** deeply optimized for the Windows operating system. This client integrates official API compliance throttling, dual-track exponential-backoff retries, multi-dimensional local reverse caching, and a keyboard interrupt data-safeguard gateway to guarantee 100% physical row alignment and robust data retrieval under complex network conditions.

---

## 🌟 Core Features & Architecture Highlights

* **Smart Type Inference Engine**
  Equipped with a regex-driven lexical inference parser, the program intelligently identifies and routes the query namespaces automatically:
  - Pure Numeric -> `cid`
  - Starts with `InChI=` -> `inchi`
  - 27-character with double hyphens (e.g. `XXXXX-XXXXX-X`) -> `inchikey`
  - Contains chemical symbols and elements, excluding proxy letters -> `smiles`
  - Others (common lowercase names, commercial terms) -> `name`
  Fully optimized with a "lowercase alphabetic分流" strategy to completely resolve type collision between English trivial names (e.g. `aspirin`) and simple SMILES strings.

* **Excel Multi-Sheets Processing (Sequential Multi-Sheets Support)**
  Fully supports Excel files containing multiple worksheets:
  - **Global De-duplicated Querying**: Aggregates all identifiers from all worksheets at the entry stage and filters out duplicate/cached keys. Only queries the official PubChem database for unique pending queries, saving up to 60%+ network quota.
  - **Original Name and Order Preservation**: Employs `pd.ExcelWriter` to sequentially parse and align each worksheet, returning the exact structure, sheet name, and order into a single output file.
  - **CSV Concat Down-gradibility**: Automatically merges all worksheets vertically via Concat if the output format is specified as `.csv`.

* **High-Resilience Network Gateway & Dual-Track Retry (Smart Retry & SSL Monkey Patch)**
  - **Proxy Auto-Sniffing**: Automatically fetches global Windows registry proxy configurations (Clash / HTTP / HTTPS system proxies) and injects them into the current running process at startup.
  - **SSL Tunnel Penetration**: Directly monkey-patches Python's `ssl.create_default_context` at runtime. This forces unverified SSL handshake contexts and completely bypasses the frequent `ssl.SSLEOFError` connection termination caused by local proxy decryptions under Python 3.13.
  - **Infinite Jittered Retries**: Catches underlying socket time-outs, connection resets (WinError 10054), and SSL handshake failures, triggering infinite exponential-backoff retries with randomized jitter.
  - **5-HTTP Retry Limit**: Targets 503 Server Busy or 504 Gateway Timeout responses from overloaded PubChem servers, limiting retries to 5 times before falling back to a safe 404 response.
  - **Compliance Rate Limiter**: Enforces a strict global `time.sleep(0.25)` throttling lock between requests to stay fully compliant with the official PubChem rate-limit redline (max 5 requests per second).

* **Double-Core Local Cache & Negative Caching**
  Persistent caching is located at `cache/pubchem_cache.json` using an atomic-write strategy.
  - Utilizes standard `InChIKey` (27-char structural hash) as the global absolute primary key to store detailed compound properties (`compounds` detail table).
  - Uses `query_index` mapping indexes: once fetched, all associated tags (`query`, `cid`, `iupac_name`, `smiles`, `inchi`, `inchikey`) in lowercase are mapped directly to their unique InChIKey. **Retrieve once, hit instantly next time using any synonyms or IDs!**
  - **Negative Caching**: Associates failed queries or non-existent chemical terms to a `"404 Not Found"` record in the local cache, preventing repeated useless network roundtrips.
  - **Atomic File Writing**: Writes database modifications to a temporary `.tmp` file and performs an atomic rename. This fully guards against cache file corruption even during sudden system power losses.

* **Strict 100% Row-Alignment & Safeguard Gateway**
  - Reads the input spreadsheet and extracts identifiers from the first column (supporting automatic header detection).
  - Guarantees the output row counts and physical order are **100% strictly aligned** with the input spreadsheet.
  - Returns `"404 Not Found"` in all chosen scope columns for any missing or non-matching terms, avoiding any row shifts.
  - **Data Safeguard Gateway**: Catches keyboard interrupts (`Ctrl+C`), aligning and flushing all currently processed and cached data safely to the disk and filling remaining items with `404 Not Found` before gracefully exiting.

* **Chinese Localized Errors**
  To perfectly fit local debug workflows, all caught critical errors, CLI violations, rate overload logs, and raw Python traceback details are strictly printed in **Chinese**.

* **Rich Terminal User Experience**
  Utilizes the `rich` library to construct a beautiful neon console UI, complete with neon banners, smooth task progress bars, and a clean statistics table upon completion.

---

## 🛠 Installation

Requirements: Python $\ge$ 3.8. Execute the following command to install all third-party dependencies:

```bash
pip install -r requirements.txt
```

---

## 🚀 Usage & CLI Parameters

Run the client via the command line:

```bash
python app.py --input <input_path> [--scope <selected_scopes>] [--output <output_path>] [--batch <batch_size>] [--header <header_strategy>]
```

### Argument Details
| Argument | Default | Description (All error messages are output in Chinese) |
| :--- | :--- | :--- |
| `--input` | **Required** | Path to the input dataset file, supporting `.csv`, `.xlsx`, and `.xls` formats. |
| `--scope` | `cid name smiles weight` | Space-separated list of compound properties to export (see table below). |
| `--output` | `output.csv` | Output file path. **Defaults to `output.csv` if omitted**. Ext-name decides output format automatically. |
| `--batch` | `100` | Chunk size of numeric CIDs queried simultaneously in one HTTP request. |
| `--header` | `auto` | Header strategy: `auto` (auto-detects if first row is column name), `yes` (skips the first row), `no` (reads first row as data). |

---

## 💡 Running Examples

### 1. Minimal Default Multi-Sheets Run (Outputs directly to `output.csv` in the root folder)
```bash
python app.py --input my_compounds.xlsx
```

### 2. Export Properties sequentially to Excel with a Batch size of 50
```bash
python app.py --input dataset.xlsx --scope cid name smiles weight formula xlogp tpsa --output result.xlsx --batch 50
```

---

## 🧪 Automated Testing

A robust, mock-isolated test suite is prepared in the `tests/` directory. Sleep delays are fully patched so you can run the whole suite in less than 0.5 seconds!

### Run All Tests:
```bash
python -m pytest -v
```

---

## 📂 Project Structure

Core business services are modularized under the `lib/` folder to maintain absolute separation of concerns:

```
pubchem-scrabber/
│
├── app.py                      # Main entrypoint, console UI layout, and global error catches
├── requirements.txt            # Third-party dependency configurations
├── README.md                   # English User Guide (This file)
├── README.zh_CN.md             # Chinese User Guide
│
├── lib/                        # Core service logic
│   ├── cli_parser.py           # CLI parser, CSV/Excel loaders, and auto-header parser (Multi-Sheets sequential load)
│   ├── network_engine.py       # Proxy sniffing, SSL unverified patches, and smart retries
│   ├── cache_manager.py        # Double-core reverse cache databases and negative caching
│   └── batch_dispatcher.py     # Batch scheduling dispatcher and strict 100% row alignment (Multi-Sheets sequential write)
│
└── tests/                      # Testing package suites
    ├── test_cli_parser.py
    ├── test_network_engine.py
    ├── test_cache_manager.py
    └── test_batch_dispatcher.py
```
