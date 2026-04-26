import json
import logging
import re

from flask import Flask, request

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
    return scrape_coop_exchange_rates()


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


@api.route("/dashen-exchange-rates")
class DashenExchangeRatesResource(Resource):
    @api.doc(
        summary="Get Dashen Bank exchange rates",
        description="Returns latest rates scraped from Dashen Bank.",
        responses={200: "Rates returned successfully."},
    )
    @api.response(200, "Success", exchange_rates_response_model)
    def get(self):
        return get_dashen_exchange_rates()


@api.route("/boa-exchange-rates")
class BoaExchangeRatesResource(Resource):
    @api.doc(
        summary="Get Bank of Abyssinia exchange rates",
        description="Returns latest rates scraped from Bank of Abyssinia.",
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
            "If date is omitted, current date is used and upstream logic may fall back to previous day."
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
        description="Returns latest rates scraped from Cooperative Bank of Oromia.",
        responses={200: "Rates returned successfully."},
    )
    @api.response(200, "Success", exchange_rates_response_model)
    def get(self):
        return get_coop_exchange_rates()


@api.route("/hibret-exchange-rates")
class HibretExchangeRatesResource(Resource):
    @api.doc(
        summary="Get Hibret Bank exchange rates",
        description="Returns latest rates scraped from Hibret Bank.",
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
        description="Returns latest rates fetched from Wegagen Bank source API.",
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
            "If date is omitted, upstream default date behavior is applied."
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
        description="Returns latest rates scraped from NIB Bank.",
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
    return """
    <h1>Welcome to the Ethiopian Bank Exchange Rates API</h1>
    <p>Available endpoints:</p>
    <ul>
        <li><a href="/apidocs">/apidocs</a> - Swagger UI documentation</li>
        <li><a href="/cbe-exchange-rates">/cbe-exchange-rates</a> - Fetches exchange rates from CBE API</li>
        <li><a href="/cbe-exchange-rates?date=2026-04-24">/cbe-exchange-rates?date=YYYY-MM-DD</a> - Fetches CBE rates for a specific date</li>
        <li><a href="/boa-exchange-rates">/boa-exchange-rates</a> - Scrapes exchange rates from Bank of Abyssinia</li>
        <li><a href="/coop-exchange-rates">/coop-exchange-rates</a> - Scrapes exchange rates from Cooperative Bank of Oromia</li>
        <li><a href="/dashen-exchange-rates">/dashen-exchange-rates</a> - Scrapes exchange rates from Dashen Bank</li>
        <li><a href="/hibret-exchange-rates">/hibret-exchange-rates</a> - Scrapes exchange rates from Hibret Bank</li>
        <li><a href="/wegagen-exchange-rates">/wegagen-exchange-rates</a> - Fetches exchange rates from Wegagen</li>
        <li><a href="/awash-exchange-rates">/awash-exchange-rates</a> - Fetches exchange rates from Awash Bank</li>
        <li><a href="/awash-exchange-rates?date=2026-04-24">/awash-exchange-rates?date=YYYY-MM-DD</a> - Fetches Awash rates for a specific date</li>
        <li><a href="/nib-exchange-rates">/nib-exchange-rates</a> - Scrapes exchange rates from NIB Bank</li>
    </ul>
    """, 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
