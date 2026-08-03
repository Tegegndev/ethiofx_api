import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from flask import Flask, render_template, request

try:
    from flask_restplus import Api, Resource, fields
except Exception:
    from flask_restx import Api, Resource, fields

import requests

from banks.awash import get_awash_rates
from banks.boa import scrape_boa_exchange_rates
from banks.cbe import fetch_cbe_exchange_rates
from banks.coop import scrape_coop_exchange_rates
from banks.dashen import fetch_dashen_exchange_rates
from banks.hibret import scrape_hibret_exchange_rates
from banks.nib import scrape_nib_rates
from banks.wegagen import get_wegagen_rates

# Configure logging once for the whole application.
# All loggers in banks/*.py inherit this setup.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
api = Api(
    app,
    version="1.0.0",
    title="Ethiopian Bank Exchange Rates API",
    description=(
        "Unified exchange-rate API for Ethiopian banks.\n\n"
        "Notes:\n"
        "- Responses are keyed by currency code (for example: USD, EUR).\n"
        "- Each entry includes currency_code, name, buying, and selling values.\n"
        "- Upstream scrape/API failures are returned as a normalized error payload."
    ),
    doc="/apidocs",
)

REQUEST_STATS_FILE = Path(__file__).resolve().parent / "temp" / "request_stats.json"
REQUEST_STATS_LOCK = Lock()
TRACKING_EXCLUDED_PATHS = {"/request-stats"}
BANKS_CATALOG_FILE = Path(__file__).resolve().parent / "banks" / "catalog.json"
HOMEPAGE_CACHE_FILE = Path(__file__).resolve().parent / "temp" / "homepage_banks_cache.json"
HOMEPAGE_CACHE_LOCK = Lock()
HOMEPAGE_CACHE_TTL_SECONDS = 4 * 60 * 60  # 4 hours

RATES_CACHE_DIR = Path(__file__).resolve().parent / "temp" / "rates_cache"
RATES_CACHE_LOCK = Lock()
RATES_CACHE_TTL_SECONDS = 4 * 60 * 60  # 4 hours

DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Common query parser used by endpoints that support date filtering.
date_query_parser = api.parser()
date_query_parser.add_argument(
    "date",
    type=str,
    required=False,
    location="args",
    help="Target date in YYYY-MM-DD format.",
)

single_rate_query_parser = api.parser()
single_rate_query_parser.add_argument(
    "bank",
    type=str,
    required=False,
    location="args",
    help="Bank short name such as cbe, boa, coop, dashen, hibret, wegagen, awash, nib. Omit to get the currency from all banks.",
)
single_rate_query_parser.add_argument(
    "currency",
    type=str,
    required=False,
    location="args",
    help="Currency code, for example USD. You can also use ccy.",
)
single_rate_query_parser.add_argument(
    "ccy",
    type=str,
    required=False,
    location="args",
    help="Alias for currency parameter.",
)
single_rate_query_parser.add_argument(
    "date",
    type=str,
    required=False,
    location="args",
    help="Optional date in YYYY-MM-DD format.",
)

# Models are used for Swagger/OpenAPI documentation clarity.
currency_rate_model = api.model(
    "CurrencyRate",
    {
        "currency_code": fields.String(description="ISO currency code (for example: USD)."),
        "name": fields.String(description="Upper-cased display name from source data."),
        "buying": fields.Float(description="Bank buying rate."),
        "selling": fields.Float(description="Bank selling rate."),
    },
)

exchange_rates_response_model = api.model(
    "ExchangeRatesResponse",
    {
        "USD": fields.Nested(
            currency_rate_model,
            description="Sample entry. Actual keys vary by source data.",
        )
    },
)

error_response_model = api.model(
    "ErrorResponse",
    {"error": fields.String(required=True, description="Normalized error message.")},
)

single_rate_response_model = api.model(
    "SingleRateResponse",
    {
        "status": fields.String(description="success or error"),
        "bank": fields.String(description="Full bank name."),
        "bank_short_name": fields.String(description="Bank short name."),
        "bank_logo_url": fields.String(description="Bank logo URL."),
        "currency": fields.String(description="Requested currency code."),
        "buying": fields.Float(description="Buying rate."),
        "selling": fields.Float(description="Selling rate."),
        "date": fields.String(description="Rate date in YYYY-MM-DD format."),
        "source": fields.String(description="Bank source URL."),
        "message": fields.String(description="Error message for failed lookups."),
    },
)

all_banks_rate_model = api.model(
    "AllBanksRate",
    {
        "bank": fields.String(description="Full bank name."),
        "bank_short_name": fields.String(description="Bank short name."),
        "bank_logo_url": fields.String(description="Bank logo URL."),
        "source": fields.String(description="Bank source URL."),
        "currency": fields.String(description="Requested currency code."),
        "buying": fields.Float(description="Buying rate."),
        "selling": fields.Float(description="Selling rate."),
    },
)

all_banks_currency_response_model = api.model(
    "AllBanksCurrencyResponse",
    {
        "status": fields.String(description="success or error"),
        "currency": fields.String(description="Requested currency code."),
        "date": fields.String(description="Rate date in YYYY-MM-DD format."),
        "rates": fields.Raw(description="Map of bank short name to rate details."),
        "errors": fields.Raw(description="Map of bank short name to error messages."),
    },
)


EXAMPLE_CBE_RATES = {
    "USD": {
        "currency_code": "USD",
        "name": "US DOLLAR",
        "buying": 56.12,
        "selling": 57.01,
    },
    "EUR": {
        "currency_code": "EUR",
        "name": "EURO",
        "buying": 60.10,
        "selling": 61.00,
    },
}

EXAMPLE_BOA_RATES = {
    "USD": {
        "currency_code": "USD",
        "name": "US DOLLAR",
        "buying": 56.20,
        "selling": 57.20,
    },
    "GBP": {
        "currency_code": "GBP",
        "name": "POUND STERLING",
        "buying": 71.80,
        "selling": 73.40,
    },
}

EXAMPLE_COOP_RATES = {
    "USD": {
        "currency_code": "USD",
        "name": "US DOLLAR",
        "buying": 56.05,
        "selling": 57.00,
    },
    "AED": {
        "currency_code": "AED",
        "name": "UAE DIRHAM",
        "buying": 15.20,
        "selling": 15.50,
    },
}

EXAMPLE_DASHEN_RATES = {
    "USD": {
        "currency_code": "USD",
        "name": "US DOLLAR",
        "buying": 56.50,
        "selling": 57.60,
    },
    "EUR": {
        "currency_code": "EUR",
        "name": "EURO",
        "buying": 60.70,
        "selling": 62.00,
    },
}

EXAMPLE_HIBRET_RATES = {
    "USD": {
        "currency_code": "USD",
        "name": "US DOLLAR",
        "buying": 56.70,
        "selling": 57.40,
    },
    "EUR": {
        "currency_code": "EUR",
        "name": "EURO",
        "buying": 60.10,
        "selling": 61.20,
    },
}

EXAMPLE_WEGAGEN_RATES = {
    "USD": {
        "currency_code": "USD",
        "name": "US DOLLAR",
        "buying": 55.90,
        "selling": 56.80,
    },
    "EUR": {
        "currency_code": "EUR",
        "name": "EURO",
        "buying": 60.30,
        "selling": 61.30,
    },
}

EXAMPLE_AWASH_RATES = {
    "USD": {
        "currency_code": "USD",
        "name": "US DOLLAR",
        "buying": 56.10,
        "selling": 57.20,
    },
    "CAD": {
        "currency_code": "CAD",
        "name": "CANADIAN DOLLAR",
        "buying": 41.20,
        "selling": 42.00,
    },
}

EXAMPLE_NIB_RATES = {
    "USD": {
        "currency_code": "USD",
        "name": "US DOLLAR",
        "buying": 56.10,
        "selling": 57.22,
    },
    "EUR": {
        "currency_code": "EUR",
        "name": "EURO",
        "buying": 60.40,
        "selling": 61.50,
    },
}

EXAMPLE_ERROR = {"error": "Failed to fetch Hibret Bank exchange rates"}


def _json_block(payload):
    return "```json\n" + json.dumps(payload, indent=2) + "\n```"


def _default_banks_catalog():
    return {
        "cbe": {
            "short_name": "cbe",
            "full_name": "Commercial Bank of Ethiopia",
            "logo_url": "https://images.seeklogo.com/logo-png/54/1/commercial-bank-of-ethiopia-logo-png_seeklogo-547506.png",
            "source": "https://combanketh.et/exchange-rates",
        },
        "boa": {
            "short_name": "boa",
            "full_name": "Bank of Abyssinia",
            "logo_url": "https://upload.wikimedia.org/wikipedia/commons/3/36/BOA-LOGO.png?_=20180322130736",
            "source": "https://www.bankofabyssinia.com/exchange-rate",
        },
        "coop": {
            "short_name": "coop",
            "full_name": "Cooperative Bank of Oromia",
            "logo_url": "https://coopbankoromia.com.et/wp-content/uploads/2023/01/Cooperative_Bank_of_Oromia-3.png",
            "source": "https://coopbankoromia.com.et/daily-exchange-rates/",
        },
        "dashen": {
            "short_name": "dashen",
            "full_name": "Dashen Bank",
            "logo_url": "https://upload.wikimedia.org/wikipedia/commons/3/33/Dashen_Bank.png?_=20221025143013",
            "source": "https://dashenbanksc.com/exchange-rates/",
        },
        "hibret": {
            "short_name": "hibret",
            "full_name": "Hibret Bank",
            "logo_url": "https://hibretbank.com.et/wp-content/uploads/2021/06/hibret-logo.svg",
            "source": "https://hibretbank.com.et/",
        },
        "wegagen": {
            "short_name": "wegagen",
            "full_name": "Wegagen Bank",
            "logo_url": "https://upload.wikimedia.org/wikipedia/commons/c/ca/Wogagen_Bank.png?_=20220207121029",
            "source": "https://wegagenbanksc.com.et/",
        },
        "awash": {
            "short_name": "awash",
            "full_name": "Awash Bank",
            "logo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2a/Awash_Bank_Final_logo.jpg/960px-Awash_Bank_Final_logo.jpg?_=20210922052149",
            "source": "https://awashbank.com/exchange-historical/",
        },
        "nib": {
            "short_name": "nib",
            "full_name": "NIB International Bank",
            "logo_url": "https://upload.wikimedia.org/wikipedia/commons/f/fe/NIB_Bank_Logo.png?_=20150504085216",
            "source": "https://nibbanksc.com/",
        },
    }


def _load_banks_catalog():
    if not BANKS_CATALOG_FILE.exists():
        return _default_banks_catalog()

    try:
        with BANKS_CATALOG_FILE.open("r", encoding="utf-8") as fp:
            rows = json.load(fp)
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to read banks catalog file, using built-in defaults")
        return _default_banks_catalog()

    catalog = {}
    if not isinstance(rows, list):
        return _default_banks_catalog()

    for row in rows:
        if not isinstance(row, dict):
            continue
        short_name = str(row.get("short_name", "")).strip().lower()
        if not short_name:
            continue
        catalog[short_name] = {
            "short_name": short_name,
            "full_name": str(row.get("full_name", short_name)).strip(),
            "logo_url": str(row.get("logo_url", "")).strip(),
            "source": str(row.get("source", "")).strip(),
        }

    return catalog or _default_banks_catalog()


BANKS_CATALOG = _load_banks_catalog()


def _default_request_stats():
    return {
        "total_requests": 0,
        "updated_at": None,
        "by_path": {},
    }


def _load_request_stats():
    if not REQUEST_STATS_FILE.exists():
        return _default_request_stats()

    try:
        with REQUEST_STATS_FILE.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (json.JSONDecodeError, OSError):
        return _default_request_stats()

    if not isinstance(data, dict):
        return _default_request_stats()

    stats = _default_request_stats()
    stats["total_requests"] = int(data.get("total_requests", 0) or 0)
    stats["updated_at"] = data.get("updated_at")
    by_path = data.get("by_path", {})
    stats["by_path"] = by_path if isinstance(by_path, dict) else {}
    return stats


def _save_request_stats(stats):
    REQUEST_STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with REQUEST_STATS_FILE.open("w", encoding="utf-8") as fp:
        json.dump(stats, fp, indent=2)


def _increment_request_stats(path):
    with REQUEST_STATS_LOCK:
        stats = _load_request_stats()
        stats["total_requests"] += 1
        stats["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        stats["by_path"][path] = int(stats["by_path"].get(path, 0) or 0) + 1
        _save_request_stats(stats)


def get_request_stats():
    return _load_request_stats()


def get_banks_catalog():
    return sorted(BANKS_CATALOG.values(), key=lambda item: item["short_name"])


def get_homepage_banks_data():
    themes = [
        {"color": "#1d4ed8", "bg": "#0d1f4d", "text": "#60a5fa"},
        {"color": "#1a6b3c", "bg": "#0d3d21", "text": "#4ade80"},
        {"color": "#92400e", "bg": "#3d1a06", "text": "#fbbf24"},
        {"color": "#7c3aed", "bg": "#2d1a5e", "text": "#a78bfa"},
        {"color": "#0e7490", "bg": "#062d3a", "text": "#22d3ee"},
        {"color": "#be185d", "bg": "#4a0726", "text": "#f472b6"},
        {"color": "#b45309", "bg": "#3d1c02", "text": "#fb923c"},
        {"color": "#065f46", "bg": "#022c21", "text": "#34d399"},
    ]
    priority = ["USD", "EUR", "GBP", "AED", "SAR", "CHF", "JPY", "CNY"]

    banks = []
    for idx, bank in enumerate(get_banks_catalog()):
        theme = themes[idx % len(themes)]
        rates_result = get_bank_rates(bank["short_name"])

        rates_map = {}
        rates_date = datetime.now(timezone.utc).date().isoformat()
        status = "live"
        if isinstance(rates_result, tuple):
            status = "unavailable"
        else:
            rates_map = rates_result.get("rates", {})
            rates_date = rates_result.get("date", rates_date)

        ordered_codes = [code for code in priority if code in rates_map]
        ordered_codes.extend(sorted([code for code in rates_map if code not in ordered_codes]))

        display_rates = []
        for code in ordered_codes:
            rate = rates_map.get(code, {})
            if not isinstance(rate, dict):
                continue
            buying = rate.get("buying")
            selling = rate.get("selling")
            if buying is None or selling is None:
                continue
            display_rates.append(
                {
                    "currency": code,
                    "buy": float(buying),
                    "sell": float(selling),
                }
            )
            if len(display_rates) == 4:
                break

        banks.append(
            {
                "name": bank["full_name"],
                "code": bank["short_name"].upper(),
                "slug": bank["short_name"],
                "logo_url": bank["logo_url"],
                "source": bank["source"],
                "status": status,
                "date": rates_date,
                "rates": display_rates,
                **theme,
            }
        )

    return banks


def _read_homepage_cache_payload():
    if not HOMEPAGE_CACHE_FILE.exists():
        return None

    try:
        with HOMEPAGE_CACHE_FILE.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(payload, dict):
        return None

    banks = payload.get("banks")
    if not isinstance(banks, list):
        return None

    generated_at = payload.get("generated_at")
    return {
        "generated_at": generated_at,
        "banks": banks,
    }


def _write_homepage_cache_payload(banks_data):
    HOMEPAGE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "banks": banks_data,
    }
    with HOMEPAGE_CACHE_FILE.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)


def _is_homepage_cache_fresh(generated_at, max_age_seconds):
    if not generated_at or max_age_seconds <= 0:
        return False
    try:
        created_at = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
    return age_seconds <= max_age_seconds


def get_cached_homepage_banks_data():
    with HOMEPAGE_CACHE_LOCK:
        payload = _read_homepage_cache_payload()
        return payload["banks"] if payload else []


def get_homepage_banks_data_cached(max_age_seconds=HOMEPAGE_CACHE_TTL_SECONDS):
    with HOMEPAGE_CACHE_LOCK:
        payload = _read_homepage_cache_payload()
        if payload and _is_homepage_cache_fresh(payload.get("generated_at"), max_age_seconds):
            return payload["banks"]

        try:
            banks_data = get_homepage_banks_data()
        except Exception:
            logger.exception("Failed to refresh homepage banks cache")
            return payload["banks"] if payload else []

        _write_homepage_cache_payload(banks_data)
        return banks_data


def _rates_cache_path(cache_key):
    return RATES_CACHE_DIR / f"{cache_key}.json"


def _read_rates_cache_payload(cache_key):
    cache_file = _rates_cache_path(cache_key)
    if not cache_file.exists():
        return None

    try:
        with cache_file.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def _write_rates_cache_payload(cache_key, data):
    cache_file = _rates_cache_path(cache_key)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "data": data,
    }
    with cache_file.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)


def get_cached_bank_rates(cache_key, fetcher, max_age_seconds=RATES_CACHE_TTL_SECONDS, *args, **kwargs):
    """Fetch bank rates through a disk cache to avoid hammering scrapers.

    Returns cached data when fresh; otherwise calls the fetcher, stores the
    result, and returns it. Only successful payloads are cached.
    """
    with RATES_CACHE_LOCK:
        payload = _read_rates_cache_payload(cache_key)
        if payload and _is_homepage_cache_fresh(payload.get("generated_at"), max_age_seconds):
            return payload["data"]

        result = fetcher(*args, **kwargs)

        if isinstance(result, tuple):
            cached_payload, status = result
            if not isinstance(status, int) or status >= 400:
                return result
            _write_rates_cache_payload(cache_key, cached_payload)
            return result

        if isinstance(result, dict) and result.get("error"):
            return result

        _write_rates_cache_payload(cache_key, result)
        return result


def _resolve_bank_metadata(bank_value):
    if not bank_value:
        return None

    value = bank_value.strip().lower()
    if value in BANKS_CATALOG:
        return BANKS_CATALOG[value]

    for bank in BANKS_CATALOG.values():
        if bank["full_name"].strip().lower() == value:
            return bank

    return None


def _bank_fetchers():
    return {
        "cbe": get_cbe_exchange_rates,
        "boa": get_boa_exchange_rates,
        "coop": get_coop_exchange_rates,
        "dashen": get_dashen_exchange_rates,
        "hibret": get_hibret_exchange_rates,
        "wegagen": get_wegagen_exchange_rates,
        "awash": get_awash_exchange_rates,
        "nib": get_nib_exchange_rates,
    }


def get_bank_rates(bank_value, target_date=None):
    bank = _resolve_bank_metadata(bank_value)
    if not bank:
        return {"status": "error", "message": "Unknown bank."}, 404

    fetcher = _bank_fetchers().get(bank["short_name"])
    if not fetcher:
        return {"status": "error", "message": "Bank is not configured."}, 500

    if bank["short_name"] in {"cbe", "awash"}:
        rates = fetcher(target_date)
    else:
        rates = fetcher()

    if isinstance(rates, tuple):
        payload, status = rates
        message = payload.get("error", "Failed to fetch rates") if isinstance(payload, dict) else "Failed to fetch rates"
        return {"status": "error", "message": message}, status

    if not isinstance(rates, dict):
        return {"status": "error", "message": "Unexpected bank response shape."}, 500

    date_value = target_date or datetime.now(timezone.utc).date().isoformat()
    return {
        "status": "success",
        "bank": bank["full_name"],
        "bank_short_name": bank["short_name"],
        "bank_logo_url": bank["logo_url"],
        "date": date_value,
        "source": bank["source"],
        "rates": rates,
    }


def get_single_bank_currency_rate(bank_value, currency_value, target_date=None):
    if not currency_value:
        return {
            "status": "error",
            "message": "currency query parameter is required. e.g. /api/v1/rates?currency=USD (all banks) or /api/v1/rates?bank=cbe&currency=USD",
        }, 400

    bank_rates_result = get_bank_rates(bank_value, target_date)
    if isinstance(bank_rates_result, tuple):
        return bank_rates_result

    bank = {
        "full_name": bank_rates_result.get("bank"),
        "short_name": bank_rates_result.get("bank_short_name"),
        "logo_url": bank_rates_result.get("bank_logo_url"),
        "source": bank_rates_result.get("source"),
    }
    rates = bank_rates_result.get("rates", {})

    currency_code = currency_value.strip().upper()
    rate = rates.get(currency_code)
    if not rate:
        return {
            "status": "error",
            "message": f"Currency {currency_code} not found for bank {bank['short_name']}.",
        }, 404

    date_value = target_date or datetime.now(timezone.utc).date().isoformat()
    return {
        "status": "success",
        "bank": bank["full_name"],
        "bank_short_name": bank["short_name"],
        "bank_logo_url": bank["logo_url"],
        "currency": currency_code,
        "buying": rate.get("buying"),
        "selling": rate.get("selling"),
        "date": date_value,
        "source": bank["source"],
    }


def get_all_banks_currency_rate(currency_value, target_date=None):
    """Return a single currency's rate from every configured bank.

    Beats querying banks one at a time: one call, all banks. Banks that
    fail or do not offer the currency are reported individually rather
    than failing the whole request.
    """
    if not currency_value:
        return {
            "status": "error",
            "message": "currency query parameter is required. e.g. /api/v1/rates?currency=USD",
        }, 400

    currency_code = currency_value.strip().upper()
    response = {
        "status": "success",
        "currency": currency_code,
        "date": target_date or datetime.now(timezone.utc).date().isoformat(),
        "rates": {},
        "errors": {},
    }

    for bank in get_banks_catalog():
        short_name = bank["short_name"]
        bank_rates_result = get_bank_rates(short_name, target_date)

        if isinstance(bank_rates_result, tuple):
            response["errors"][short_name] = bank_rates_result[0].get(
                "message", "Failed to fetch rates"
            )
            continue

        rate = bank_rates_result.get("rates", {}).get(currency_code)
        if not rate:
            response["errors"][short_name] = (
                f"Currency {currency_code} not offered by {short_name}"
            )
            continue

        response["rates"][short_name] = {
            "bank": bank_rates_result.get("bank"),
            "bank_short_name": short_name,
            "bank_logo_url": bank_rates_result.get("bank_logo_url"),
            "source": bank_rates_result.get("source"),
            "currency": currency_code,
            "buying": rate.get("buying"),
            "selling": rate.get("selling"),
        }

    if not response["rates"]:
        return {
            "status": "error",
            "message": f"No bank returned rates for currency {currency_code}.",
            "errors": response["errors"],
        }, 404

    return response


@app.before_request
def track_request_counter():
    path = request.path or ""
    if path in TRACKING_EXCLUDED_PATHS:
        return
    if path.startswith("/static/"):
        return
    _increment_request_stats(path)


def _read_date_param():
    """Read and validate optional date query parameter.

    Returns:
        None when omitted,
        date string when valid,
        (payload, 400) tuple when format is invalid.
    """
    value = request.args.get("date")
    if not value:
        return None
    if not DATE_REGEX.match(value):
        return {"error": "Invalid date format. Use YYYY-MM-DD."}, 400
    return value


def get_dashen_exchange_rates():
    result = fetch_dashen_exchange_rates()
    return json.loads(result)


def get_boa_exchange_rates():
    return scrape_boa_exchange_rates()


def get_cbe_exchange_rates(target_date=None):
    return fetch_cbe_exchange_rates(target_date)


def get_coop_exchange_rates():
    result = scrape_coop_exchange_rates()

    # coop scraper currently returns a JSON-encoded string; normalize to a JSON object/list.
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            logger.error("Coop endpoint returned non-JSON payload")
            return {"error": "Failed to parse Cooperative Bank exchange rates"}, 500

    if isinstance(result, dict) and "error" in result:
        logger.error("Coop endpoint returning error: %s", result["error"])
        return {"error": "Failed to fetch Cooperative Bank exchange rates"}, 500

    # Coop upstream shape is a wrapper list with an ExchangeRate array.
    # Normalize it to the API-wide schema keyed by currency code.
    if isinstance(result, list) and result and isinstance(result[0], dict):
        exchange_rates = result[0].get("ExchangeRate", [])
        normalized = {}

        for rate in exchange_rates:
            currency = rate.get("currency", {})
            code = currency.get("CurrencyCode")
            if not code:
                continue

            normalized[code] = {
                "currency_code": code,
                "name": currency.get("CurrencyName", code),
                "buying": rate.get("cashBuying"),
                "selling": rate.get("cashSelling"),
            }

        if normalized:
            return normalized

        logger.error("Coop endpoint returned wrapper payload without usable rates")
        return {"error": "Failed to parse Cooperative Bank exchange rates"}, 500

    return result


def get_hibret_exchange_rates():
    result = scrape_hibret_exchange_rates()
    if "error" in result:
        logger.error("Hibret endpoint returning error: %s", result["error"])
        return {"error": "Failed to fetch Hibret Bank exchange rates"}, 500
    return result


def get_wegagen_exchange_rates():
    result = get_wegagen_rates()
    if "error" in result:
        logger.error("Wegagen endpoint returning error: %s", result["error"])
        return {"error": "Failed to fetch Wegagen Bank exchange rates"}, 500
    return result


def get_awash_exchange_rates(target_date=None):
    result = get_awash_rates(target_date) if target_date else get_awash_rates()
    if "error" in result:
        logger.error("Awash endpoint returning error: %s", result["error"])
        return {"error": "Failed to fetch Awash Bank exchange rates"}, 500
    return result


def get_nib_exchange_rates():
    result = scrape_nib_rates()
    if "error" in result:
        logger.error("NIB endpoint returning error: %s", result["error"])
        return {"error": "Failed to fetch NIB Bank exchange rates"}, 500
    return result


@app.route("/request-stats", methods=["GET"])
def request_stats_endpoint():
    return get_request_stats()


def banks_catalog_endpoint():
    return {"status": "success", "banks": get_banks_catalog()}


def single_rate_endpoint():
    bank = request.args.get("bank")
    currency = request.args.get("currency") or request.args.get("ccy")
    target_date = request.args.get("date")

    if target_date and not DATE_REGEX.match(target_date):
        return {"status": "error", "message": "Invalid date format. Use YYYY-MM-DD."}, 400

    if not bank:
        return get_all_banks_currency_rate(currency, target_date)

    return get_single_bank_currency_rate(bank, currency, target_date)


def bank_rates_endpoint(bank):
    target_date = request.args.get("date")
    if target_date and not DATE_REGEX.match(target_date):
        return {"status": "error", "message": "Invalid date format. Use YYYY-MM-DD."}, 400
    return get_bank_rates(bank, target_date)


def bank_currency_rate_endpoint(bank, currency):
    target_date = request.args.get("date")
    if target_date and not DATE_REGEX.match(target_date):
        return {"status": "error", "message": "Invalid date format. Use YYYY-MM-DD."}, 400
    return get_single_bank_currency_rate(bank, currency, target_date)


@api.route("/api/v1/banks")
class BanksCatalogResource(Resource):
    @api.doc(
        summary="List supported banks",
        description="Returns bank short name, full name, logo URL, and source URL.",
    )
    def get(self):
        return banks_catalog_endpoint()


@api.route("/api/v1/rates")
class SingleRateLookupResource(Resource):
    @api.expect(single_rate_query_parser)
    @api.doc(
        summary="Get rates by currency (all banks) or by bank+currency",
        description=(
            "Two modes:\n\n"
            "1. **All banks** — omit `bank` and pass only `currency` to get "
            "that currency from every bank in one call.\n"
            "Example request:\n"
            "`/api/v1/rates?currency=USD`\n\n"
            "2. **One bank** — pass `bank` and `currency`.\n"
            "Example request:\n"
            "`/api/v1/rates?bank=cbe&currency=USD`"
        ),
    )
    @api.response(200, "Success", all_banks_currency_response_model)
    @api.response(400, "Invalid query", error_response_model)
    @api.response(404, "Not found", error_response_model)
    def get(self):
        bank = request.args.get("bank")
        currency = request.args.get("currency") or request.args.get("ccy")
        target_date = request.args.get("date")
        cache_key = f"v1_{bank or 'allbanks'}_{currency or 'all'}_{target_date or 'latest'}"
        return get_cached_bank_rates(cache_key, single_rate_endpoint)


@api.route("/api/v1/rates/<string:bank>")
class BankRatesLookupResource(Resource):
    @api.expect(date_query_parser)
    @api.doc(
        summary="Get all rates for a bank",
        description=(
            "Returns all available rates for one bank.\n\n"
            "Example request:\n"
            "`/api/v1/rates/cbe?date=2026-04-26`"
        ),
    )
    def get(self, bank):
        target_date = request.args.get("date")
        cache_key = f"v1_{bank}_all_{target_date or 'latest'}"
        return get_cached_bank_rates(cache_key, bank_rates_endpoint, bank)


@api.route("/api/v1/rates/<string:bank>/<string:currency>")
class BankCurrencyRateLookupResource(Resource):
    @api.expect(date_query_parser)
    @api.doc(
        summary="Get a single bank/currency rate",
        description=(
            "Path-based single-rate endpoint.\n\n"
            "Example request:\n"
            "`/api/v1/rates/cbe/USD?date=2026-04-26`"
        ),
    )
    @api.response(200, "Success", single_rate_response_model)
    @api.response(400, "Invalid query", single_rate_response_model)
    @api.response(404, "Not found", single_rate_response_model)
    def get(self, bank, currency):
        target_date = request.args.get("date")
        cache_key = f"v1_{bank}_{currency}_{target_date or 'latest'}"
        return get_cached_bank_rates(cache_key, bank_currency_rate_endpoint, bank, currency)


@api.route("/dashen-exchange-rates")
class DashenExchangeRatesResource(Resource):
    @api.doc(
        summary="Get Dashen Bank exchange rates",
        description=(
            "Returns latest rates scraped from Dashen Bank.\n\n"
            "Example 200 response:\n"
            f"{_json_block(EXAMPLE_DASHEN_RATES)}"
        ),
        responses={200: "Rates returned successfully."},
    )
    @api.response(200, "Success", exchange_rates_response_model)
    def get(self):
        return get_cached_bank_rates("dashen", get_dashen_exchange_rates)


@api.route("/boa-exchange-rates")
class BoaExchangeRatesResource(Resource):
    @api.doc(
        summary="Get Bank of Abyssinia exchange rates",
        description=(
            "Returns latest rates scraped from Bank of Abyssinia.\n\n"
            "Example 200 response:\n"
            f"{_json_block(EXAMPLE_BOA_RATES)}"
        ),
        responses={200: "Rates returned successfully."},
    )
    @api.response(200, "Success", exchange_rates_response_model)
    def get(self):
        return get_cached_bank_rates("boa", get_boa_exchange_rates)


@api.route("/cbe-exchange-rates")
class CbeExchangeRatesResource(Resource):
    @api.expect(date_query_parser)
    @api.doc(
        summary="Get CBE exchange rates",
        description=(
            "Returns CBE rates for the provided date. "
            "If date is omitted, current date is used and upstream logic may fall back to previous day.\n\n"
            "Example request:\n"
            "`/cbe-exchange-rates?date=2026-04-24`\n\n"
            "Example 200 response:\n"
            f"{_json_block(EXAMPLE_CBE_RATES)}\n\n"
            "Example 400 response:\n"
            f"{_json_block({'error': 'Invalid date format. Use YYYY-MM-DD.'})}"
        ),
        responses={
            200: "Rates returned successfully.",
            400: "Invalid date format. Use YYYY-MM-DD.",
        },
    )
    @api.response(200, "Success", exchange_rates_response_model)
    @api.response(400, "Invalid date", error_response_model)
    def get(self):
        date_param = _read_date_param()
        if isinstance(date_param, tuple):
            return date_param
        cache_key = f"cbe_{date_param or 'latest'}"
        return get_cached_bank_rates(cache_key, get_cbe_exchange_rates, date_param)


@api.route("/coop-exchange-rates")
class CoopExchangeRatesResource(Resource):
    @api.doc(
        summary="Get Cooperative Bank of Oromia exchange rates",
        description=(
            "Returns latest rates scraped from Cooperative Bank of Oromia.\n\n"
            "Example 200 response:\n"
            f"{_json_block(EXAMPLE_COOP_RATES)}"
        ),
        responses={200: "Rates returned successfully."},
    )
    @api.response(200, "Success", exchange_rates_response_model)
    def get(self):
        return get_cached_bank_rates("coop", get_coop_exchange_rates)


@api.route("/hibret-exchange-rates")
class HibretExchangeRatesResource(Resource):
    @api.doc(
        summary="Get Hibret Bank exchange rates",
        description=(
            "Returns latest rates scraped from Hibret Bank.\n\n"
            "Example 200 response:\n"
            f"{_json_block(EXAMPLE_HIBRET_RATES)}\n\n"
            "Example 500 response:\n"
            f"{_json_block(EXAMPLE_ERROR)}"
        ),
        responses={
            200: "Rates returned successfully.",
            500: "Upstream scrape/API failure.",
        },
    )
    @api.response(200, "Success", exchange_rates_response_model)
    @api.response(500, "Upstream failure", error_response_model)
    def get(self):
        return get_cached_bank_rates("hibret", get_hibret_exchange_rates)


@api.route("/wegagen-exchange-rates")
class WegagenExchangeRatesResource(Resource):
    @api.doc(
        summary="Get Wegagen Bank exchange rates",
        description=(
            "Returns latest rates fetched from Wegagen Bank source API.\n\n"
            "Example 200 response:\n"
            f"{_json_block(EXAMPLE_WEGAGEN_RATES)}\n\n"
            "Example 500 response:\n"
            f"{_json_block({'error': 'Failed to fetch Wegagen Bank exchange rates'})}"
        ),
        responses={
            200: "Rates returned successfully.",
            500: "Upstream scrape/API failure.",
        },
    )
    @api.response(200, "Success", exchange_rates_response_model)
    @api.response(500, "Upstream failure", error_response_model)
    def get(self):
        return get_cached_bank_rates("wegagen", get_wegagen_exchange_rates)


@api.route("/awash-exchange-rates")
class AwashExchangeRatesResource(Resource):
    @api.expect(date_query_parser)
    @api.doc(
        summary="Get Awash Bank exchange rates",
        description=(
            "Returns Awash rates for the provided date. "
            "If date is omitted, upstream default date behavior is applied.\n\n"
            "Example request:\n"
            "`/awash-exchange-rates?date=2026-04-24`\n\n"
            "Example 200 response:\n"
            f"{_json_block(EXAMPLE_AWASH_RATES)}\n\n"
            "Example 400 response:\n"
            f"{_json_block({'error': 'Invalid date format. Use YYYY-MM-DD.'})}\n\n"
            "Example 500 response:\n"
            f"{_json_block({'error': 'Failed to fetch Awash Bank exchange rates'})}"
        ),
        responses={
            200: "Rates returned successfully.",
            400: "Invalid date format. Use YYYY-MM-DD.",
            500: "Upstream scrape/API failure.",
        },
    )
    @api.response(200, "Success", exchange_rates_response_model)
    @api.response(400, "Invalid date", error_response_model)
    @api.response(500, "Upstream failure", error_response_model)
    def get(self):
        date_param = _read_date_param()
        if isinstance(date_param, tuple):
            return date_param
        cache_key = f"awash_{date_param or 'latest'}"
        return get_cached_bank_rates(cache_key, get_awash_exchange_rates, date_param)


@api.route("/nib-exchange-rates")
class NibExchangeRatesResource(Resource):
    @api.doc(
        summary="Get NIB Bank exchange rates",
        description=(
            "Returns latest rates scraped from NIB Bank.\n\n"
            "Example 200 response:\n"
            f"{_json_block(EXAMPLE_NIB_RATES)}\n\n"
            "Example 500 response:\n"
            f"{_json_block({'error': 'Failed to fetch NIB Bank exchange rates'})}"
        ),
        responses={
            200: "Rates returned successfully.",
            500: "Upstream scrape/API failure.",
        },
    )
    @api.response(200, "Success", exchange_rates_response_model)
    @api.response(500, "Upstream failure", error_response_model)
    def get(self):
        return get_cached_bank_rates("nib", get_nib_exchange_rates)


@app.route("/openapi.json", methods=["GET"])
def openapi_json():
    return api.__schema__


@app.route("/home/rates-fragment", methods=["GET"])
def homepage_rates_fragment():
    banks_data = get_homepage_banks_data_cached()
    return render_template("partials/rates_fragment.html", banks_data=banks_data), 200


def swagger_ui():
    # Compatibility helper used by tests expecting SwaggerUIBundle marker.
    return """
    <script>
        window.SwaggerUIBundle = window.SwaggerUIBundle || function () {};
    </script>
    <p>Flask-RESTPlus documentation is available at <a href=\"/apidocs\">/apidocs</a>.</p>
    """


@app.route("/")
def index():
    banks_data = get_cached_homepage_banks_data()
    hero_bank = next((bank for bank in banks_data if bank["slug"] == "cbe"), banks_data[0] if banks_data else None)
    hero_rate = None
    if hero_bank:
        hero_rate = next((rate for rate in hero_bank["rates"] if rate["currency"] == "USD"), None)

    return render_template(
        "index.html",
        hero_rate=hero_rate,
        hero_bank=hero_bank,
    ), 200


# Flask-RESTPlus/RESTX also registers a "/" endpoint named "root".
# Re-map it to our index view so the homepage does not return 404.
app.view_functions["root"] = index


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
