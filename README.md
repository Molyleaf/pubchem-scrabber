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

* **Rich Terminal User Experience**
  Utilizes the `rich` library to construct a beautiful neon console UI, complete with neon banners, smooth task progress bars, and a clean statistics table upon completion. All system error and traceback outputs are localized in Chinese.

---

## 🛠 Installation

Requirements: Python $\ge$ 3.8. Execute the following command to install all third-party dependencies:

```bash
pip install -r requirements.txt
```

### Dependency List
* `pubchempy>=1.0.5` (Official PubChem SDK)
* `pandas>=2.3.3` (Data spreadsheet parsing)
* `openpyxl>=3.1.5` (Excel `.xlsx` reader and writer support)
* `rich>=14.2.0` (Technical console UI elements)
* `pytest>=9.0.3` (Automated testing runner)

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

### Available Scope Mappings
| Scope | Column Name | Compound Property |
| :--- | :--- | :--- |
| `cid` | `cid` | PubChem Compound ID (numeric) |
| `name` | `name` | IUPAC International Standard Name |
| `smiles` | `smiles` | Isomeric SMILES string |
| `inchi` | `inchi` | Standard International Chemical Identifier (InChI) |
| `inchikey` | `inchikey` | 27-character structural InChIKey hash |
| `weight` | `weight` | Molecular Weight (g/mol) |
| `formula` | `formula` | Molecular Formula |
| `xlogp` | `xlogp` | Octanol-Water Partition Coefficient (XLogP) |
| `tpsa` | `tpsa` | Topological Polar Surface Area (TPSA) |
| `charge` | `charge` | Formal Molecular Charge |

---

## 💡 Running Examples

### 1. Minimal Default Run (Outputs directly to `output.csv` in the root folder)
```bash
python app.py --input my_compounds.csv
```

### 2. Export Properties to Excel with a Batch size of 50
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
│   ├── cli_parser.py           # CLI parser, CSV/Excel loaders, and auto-header parser
│   ├── network_engine.py       # Proxy sniffing, SSL unverified patches, and smart retries
│   ├── cache_manager.py        # Double-core reverse cache databases and negative caching
│   └── batch_dispatcher.py     # Batch scheduling dispatcher and strict 100% row alignment
│
└── tests/                      # Testing package suites
    ├── test_cli_parser.py
    ├── test_network_engine.py
    ├── test_cache_manager.py
    └── test_batch_dispatcher.py
```
