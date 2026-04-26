# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project Snapshot

- Purpose: Flask API that aggregates Ethiopian bank foreign exchange rates.
- Entry points:
  - Local/dev: app.py
  - Passenger/WSGI hosting: passenger_wsgi.py
- Main structure:
  - banks/: bank-specific scrapers/fetchers (one module per bank)
  - app.py: Flask routes and some in-file bank integrations

## Quick Start Commands

- Create environment: python3 -m venv .venv && source .venv/bin/activate
- Install dependencies: pip install flask requests beautifulsoup4
- Run locally: python app.py
- Verify service: curl http://127.0.0.1:5000/

## API Endpoints in app.py

- /cbe-exchange-rates
- /boa-exchange-rates
- /coop-exchange-rates
- /dashen-exchange-rates
- /hibret-exchange-rates
- /wegagen-exchange-rates
- /awash-exchange-rates
- /nib-exchange-rates

## Conventions To Follow

- Keep return payloads consistent with existing shape in each scraper (typically keyed by currency code with buying/selling fields).
- Preserve route names and response contracts unless explicitly asked to change API behavior.
- Prefer adding/adjusting logic inside the relevant bank module in banks/ when possible.
- Keep scraping requests browser-like (headers/referer are often required by upstream sites).

## Known Pitfalls

- No test suite or lint config is present; validate by running app.py and hitting relevant endpoints.
- Upstream bank websites are volatile; HTML selectors can break unexpectedly.
- app.py currently includes duplicate import of banks.nib.scrape_nib_rates; avoid introducing more duplicated imports.
- Some functions in app.py still use print-based debugging and mixed return styles; avoid broad refactors unless requested.
- Hibret scraper disables SSL verification (verify=False); do not change security behavior unless requested because it may affect current connectivity.

## Change Workflow

- Make narrowly scoped changes for the requested bank/endpoint.
- After edits, run app.py and test only impacted endpoints first.
- If scraping fails, capture the failing selector or HTTP assumption and fix minimally.
