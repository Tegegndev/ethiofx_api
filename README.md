# Ethiopian Bank Exchange Rates API

A Flask-based API that aggregates Ethiopian bank FX rates into a unified response shape, with both machine-friendly JSON endpoints and a homepage UI.

## What this project does

- Fetches/scrapes exchange rates from multiple Ethiopian banks.
- Normalizes responses to a shared schema:
  - `currency_code`
  - `name`
  - `buying`
  - `selling`
- Provides:
  - bank-specific endpoints (e.g. `/cbe-exchange-rates`)
  - unified v1 endpoints (e.g. `/api/v1/rates/cbe/USD`)
  - interactive docs (`/apidocs`) and OpenAPI JSON (`/openapi.json`)
  - homepage + HTMX rates fragment (`/` and `/home/rates-fragment`)
  - request stats (`/request-stats`)

## Supported banks

The bank catalog is loaded from:

- `banks/catalog.json`

Current catalog short names:

- `cbe` (Commercial Bank of Ethiopia)
- `boa` (Bank of Abyssinia)
- `coop` (Cooperative Bank of Oromia)
- `dashen` (Dashen Bank)
- `hibret` (Hibret Bank)
- `wegagen` (Wegagen Bank)
- `awash` (Awash Bank)
- `nib` (NIB International Bank)

## Tech stack

- Python 3
- Flask
- Flask-RESTPlus / Flask-RESTX
- Requests
- BeautifulSoup4

Dependencies are defined in:

- `requirements.txt`

## Repository structure

```text
ethiofx_api/
├── app.py                  # Main Flask app, routes, OpenAPI, normalization orchestration
├── passenger_wsgi.py       # WSGI entrypoint
├── banks/
│   ├── awash.py
│   ├── boa.py
│   ├── cbe.py
│   ├── hibret.py
│   ├── nib.py
│   ├── wegagen.py
│   └── catalog.json
├── templates/
│   ├── index.html
│   └── partials/rates_fragment.html
├── tests/
│   ├── helpers.py
│   └── test_exchange_rates.py
└── temp/
    ├── homepage_banks_cache.json
    ├── request_stats.json
    └── restart.txt
```

## Local setup

1. **Clone**
   ```bash
   git clone https://github.com/Tegegndev/ethiofx_api.git
   cd ethiofx_api
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run**
   ```bash
   python app.py
   ```

5. **Open**
   - API docs: `http://127.0.0.1:5000/apidocs`
   - OpenAPI spec: `http://127.0.0.1:5000/openapi.json`
   - Homepage: `http://127.0.0.1:5000/`

## API overview

### Utility endpoints

- `GET /` — homepage
- `GET /apidocs` — Swagger UI (Flask-RESTPlus/RESTX docs)
- `GET /openapi.json` — raw OpenAPI schema
- `GET /home/rates-fragment` — HTMX-rendered rates fragment
- `GET /request-stats` — request counter snapshot

### Catalog endpoint

- `GET /api/v1/banks`
  - Returns list of banks with:
    - `short_name`
    - `full_name`
    - `logo_url`
    - `source`

### Unified lookup endpoints (recommended)

- `GET /api/v1/rates?bank=<short_name>&currency=<code>&date=YYYY-MM-DD`
  - `currency` may also be passed as `ccy`
  - `date` is optional

- `GET /api/v1/rates/<bank>?date=YYYY-MM-DD`
  - Returns all available rates for one bank

- `GET /api/v1/rates/<bank>/<currency>?date=YYYY-MM-DD`
  - Returns one normalized rate object

### Bank-specific endpoints

- `GET /cbe-exchange-rates?date=YYYY-MM-DD`
- `GET /awash-exchange-rates?date=YYYY-MM-DD`
- `GET /boa-exchange-rates`
- `GET /coop-exchange-rates`
- `GET /dashen-exchange-rates`
- `GET /hibret-exchange-rates`
- `GET /wegagen-exchange-rates`
- `GET /nib-exchange-rates`

## Response format

### Standard rates payload shape

```json
{
  "USD": {
    "currency_code": "USD",
    "name": "US DOLLAR",
    "buying": 56.12,
    "selling": 57.01
  }
}
```

### Single-rate lookup shape

```json
{
  "status": "success",
  "bank": "Commercial Bank of Ethiopia",
  "bank_short_name": "cbe",
  "bank_logo_url": "https://www.combanketh.et/assets/logo.png",
  "currency": "USD",
  "buying": 57.8,
  "selling": 58.94,
  "date": "2026-04-26",
  "source": "https://combanketh.et/exchange-rates"
}
```

### Error shape examples

```json
{
  "error": "Invalid date format. Use YYYY-MM-DD."
}
```

or

```json
{
  "status": "error",
  "message": "Unknown bank."
}
```

## Example usage (curl)

```bash
# All rates for CBE
curl "http://127.0.0.1:5000/api/v1/rates/cbe"

# One rate by bank and currency
curl "http://127.0.0.1:5000/api/v1/rates/cbe/USD"

# Date-filtered endpoint
curl "http://127.0.0.1:5000/cbe-exchange-rates?date=2026-04-24"
```

## Screenshots

### API response examples

<img src="https://github.com/user-attachments/assets/08f7dcf7-0b83-4b8b-99f9-f403d3a693c2" alt="API response screenshot 1" />

<img src="https://github.com/user-attachments/assets/509c5b04-9937-49ca-9841-96f497527a4a" alt="API response screenshot 2" />

<img src="https://github.com/user-attachments/assets/041d8be6-6eac-426c-94be-0fa2823024db" alt="API response screenshot 3" />

<img src="https://github.com/user-attachments/assets/a8fa6877-a3de-4f47-843b-1f45f370819a" alt="API response screenshot 4" />

## Testing

Run test suite:

```bash
python -m unittest discover -s tests -v
```

## Runtime data and caching

Generated files under `temp/`:

- `request_stats.json` — request counters per path + total
- `homepage_banks_cache.json` — cached homepage card data (default TTL: 300s)

## Deployment notes

- `passenger_wsgi.py` exposes `application` for WSGI hosting.
- App startup entrypoint is `app.py`.

## Known caveats

- The app imports `banks.coop` and `banks.dashen` from `app.py`; ensure those modules exist in your deployment branch/environment.
- Some upstream sources can change HTML/API formats and may temporarily break individual bank scrapers.
- ⚠️ **WARNING:** `hibret` scraper currently requests with `verify=False` (TLS verification disabled), which can expose traffic to man-in-the-middle attacks. Do not use this as-is in production; enforce proper certificate verification first.

## License

No license file is currently present in this repository. Add one if you plan to distribute or reuse the project broadly.
