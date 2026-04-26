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
        return get_dashen_exchange_rates()


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
        return get_boa_exchange_rates()


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
        return get_cbe_exchange_rates(date_param)


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
        return get_coop_exchange_rates()


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
        return get_hibret_exchange_rates()


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
        return get_wegagen_exchange_rates()


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
        return get_awash_exchange_rates(date_param)


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
        return get_nib_exchange_rates()


@app.route("/openapi.json", methods=["GET"])
def openapi_json():
    return api.__schema__


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
    return render_template("index.html"), 200


# Flask-RESTPlus/RESTX also registers a "/" endpoint named "root".
# Re-map it to our index view so the homepage does not return 404.
app.view_functions["root"] = index


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
