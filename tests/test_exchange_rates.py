import json
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from tests.helpers import import_modules


class FakeCell:
    def __init__(self, text="", attrs=None, image=None):
        self.text = text
        self.attrs = attrs or {}
        self.image = image

    def get_text(self, strip=False):
        return self.text.strip() if strip else self.text

    def find(self, name, **_kwargs):
        if name == "img":
            return self.image
        return None

    def get(self, key, default=None):
        return self.attrs.get(key, default)

    def __getitem__(self, key):
        return self.attrs[key]


class FakeRow:
    def __init__(self, cells):
        self.cells = cells

    def find_all(self, name):
        if name in ("td", ["td"]):
            return self.cells
        if isinstance(name, list) and "td" in name:
            return self.cells
        return []


class FakeBody:
    def __init__(self, rows):
        self.rows = rows

    def find_all(self, name):
        return self.rows if name == "tr" else []


class FakeTable:
    def __init__(self, rows):
        self.body = FakeBody(rows)

    def find(self, name, **_kwargs):
        if name == "tbody":
            return self.body
        return None

    def find_all(self, name, **_kwargs):
        if name == "tr":
            return self.body.find_all("tr")
        return []


class FakeNibSoup:
    def __init__(self):
        self.tables = [
            FakeTable([]),
            FakeTable(
                [
                    FakeRow(
                        [
                            FakeCell("1"),
                            FakeCell("USD"),
                            FakeCell("56.10"),
                            FakeCell("57.22"),
                        ]
                    ),
                    FakeRow(
                        [
                            FakeCell("2"),
                            FakeCell("EUR"),
                            FakeCell("not-a-number"),
                            FakeCell("61.00"),
                        ]
                    ),
                ]
            ),
        ]

    def find_all(self, name, **kwargs):
        if name == "table" and kwargs.get("class_") == "ea-advanced-data-table":
            return self.tables
        return []


class FakeHibretSoup:
    def __init__(self):
        self.table = FakeTable(
            [
                FakeRow(
                    [
                        FakeCell(image=FakeCell(attrs={"alt": "usd"})),
                        FakeCell("USD (US Dollar)"),
                        FakeCell(""),
                        FakeCell(""),
                        FakeCell("56.70"),
                        FakeCell("57.40"),
                    ]
                ),
                FakeRow(
                    [
                        FakeCell(),
                        FakeCell("EUR (Euro)"),
                        FakeCell("60.10"),
                        FakeCell("61.20"),
                        FakeCell(""),
                        FakeCell(""),
                    ]
                ),
            ]
        )

    def find(self, name, **_kwargs):
        if name == "table":
            return self.table
        return None


class FakeDashenContent:
    def __init__(self, table):
        self.table = table

    def find(self, name, **_kwargs):
        if name == "table":
            return self.table
        return None


class FakeDashenSoup:
    def __init__(self):
        self.content = FakeDashenContent(
            FakeTable(
                [
                    FakeRow(
                        [
                            FakeCell("USD"),
                            FakeCell("US Dollar"),
                            FakeCell("56.50"),
                            FakeCell("57.60"),
                        ]
                    ),
                    FakeRow(
                        [
                            FakeCell("EUR"),
                            FakeCell("Euro"),
                            FakeCell("invalid"),
                            FakeCell("62.00"),
                        ]
                    ),
                ]
            )
        )

    def find(self, name, **kwargs):
        if name == "div" and kwargs.get("class_") == "et_pb_tab_content":
            return self.content
        return None


class ExchangeRateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        modules = import_modules()
        cls.app = modules["app"]
        cls.awash = modules["banks.awash"]
        cls.nib = modules["banks.nib"]
        cls.hibret = modules["banks.hibret"]
        cls.wegagen = modules["banks.wegagen"]
        cls.dashen = modules["banks.dashen"]

    def test_fetch_cbe_exchange_rates_normalizes_response(self):
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                "Date": "2026-04-24",
                "ExchangeRate": [
                    {
                        "currency": {
                            "CurrencyName": "US DOLLAR",
                            "CurrencyCode": "USD",
                        },
                        "cashBuying": 56.12,
                        "cashSelling": 57.01,
                    }
                ],
            }
        ]
        mock_response.raise_for_status.return_value = None

        with patch.object(self.app.requests, "get", return_value=mock_response):
            result = self.app.fetch_cbe_exchange_rates("2026-04-24")

        self.assertEqual(
            result,
            {
                "USD": {
                    "currency_code": "USD",
                    "name": "US DOLLAR",
                    "buying": 56.12,
                    "selling": 57.01,
                }
            },
        )

    def test_fetch_dashen_exchange_rates_skips_invalid_rows(self):
        mock_response = Mock(text="<html></html>")
        mock_response.raise_for_status.return_value = None

        with patch.object(self.dashen.requests, "get", return_value=mock_response), patch.object(
            self.dashen, "BeautifulSoup", return_value=FakeDashenSoup()
        ):
            result = json.loads(self.app.fetch_dashen_exchange_rates())

        self.assertEqual(
            result,
            {
                "USD": {
                    "buying": 56.5,
                    "currency_code": "USD",
                    "name": "US DOLLAR",
                    "selling": 57.6,
                }
            },
        )

    def test_awash_rates_use_transaction_values_as_fallback(self):
        session = Mock()
        session.get.return_value = Mock(text='{"nonce":"abc123"}')
        session.post.return_value = Mock(
            json=Mock(
                return_value={
                    "success": True,
                    "data": {
                        "rates": {
                            "USD": {
                                "buying": None,
                                "selling": None,
                                "transaction_buying": "56.10",
                                "transaction_selling": "57.20",
                                "name": "US Dollar",
                            }
                        }
                    },
                }
            )
        )

        with patch.object(self.awash.requests, "Session", return_value=session):
            result = self.awash.get_awash_rates("2026-04-24")

        self.assertEqual(result["USD"]["buying"], 56.10)
        self.assertEqual(result["USD"]["selling"], 57.20)
        self.assertEqual(result["USD"]["name"], "US DOLLAR")

    def test_nib_rates_parse_cash_table(self):
        mock_response = Mock(text="<html></html>")
        mock_response.raise_for_status.return_value = None

        with patch.object(self.nib.requests, "get", return_value=mock_response), patch.object(
            self.nib, "BeautifulSoup", return_value=FakeNibSoup()
        ):
            result = self.nib.scrape_nib_rates()

        self.assertEqual(result["USD"]["buying"], 56.10)
        self.assertEqual(result["USD"]["selling"], 57.22)
        self.assertIsNone(result["EUR"]["buying"])

    def test_hibret_rates_fallback_to_transaction_values(self):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None

        with patch.object(self.hibret.requests, "get", return_value=mock_response), patch.object(
            self.hibret, "BeautifulSoup", return_value=FakeHibretSoup()
        ):
            result = self.hibret.scrape_hibret_exchange_rates()

        self.assertEqual(result["USD"]["buying"], 56.70)
        self.assertEqual(result["USD"]["selling"], 57.40)
        self.assertEqual(result["EUR"]["buying"], 60.10)
        self.assertEqual(result["EUR"]["name"], "EURO")

    def test_wegagen_rates_map_json_payload(self):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "data": [
                {"attributes": {"code": "usd", "buying": 55.9, "selling": 56.8}}
            ]
        }

        with patch.object(self.wegagen.requests, "get", return_value=mock_response):
            result = self.wegagen.get_wegagen_rates()

        self.assertEqual(
            result["USD"],
            {
                "currency_code": "USD",
                "name": "US DOLLAR",
                "buying": 55.9,
                "selling": 56.8,
            },
        )

    def test_awash_returns_error_dict_on_http_failure(self):
        session = Mock()
        session.get.return_value = Mock()
        session.get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")

        with patch.object(self.awash.requests, "Session", return_value=session):
            result = self.awash.get_awash_rates("2026-04-24")

        self.assertEqual(result, {"error": "HTTP error: boom"})

    def test_nib_returns_error_dict_when_tables_missing(self):
        mock_response = Mock(text="<html></html>")
        mock_response.raise_for_status.return_value = None

        class EmptySoup:
            def find_all(self, *_args, **_kwargs):
                return []

        with patch.object(self.nib.requests, "get", return_value=mock_response), patch.object(
            self.nib, "BeautifulSoup", return_value=EmptySoup()
        ):
            result = self.nib.scrape_nib_rates()

        self.assertEqual(result, {"error": "Could not find exchange rate tables on the page"})

    def test_hibret_returns_error_dict_on_timeout(self):
        with patch.object(
            self.hibret.requests,
            "get",
            side_effect=requests.exceptions.Timeout(),
        ):
            result = self.hibret.scrape_hibret_exchange_rates()

        self.assertEqual(result, {"error": "Request timed out"})

    def test_wegagen_returns_error_dict_on_parse_failure(self):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"data": [{}]}

        with patch.object(self.wegagen.requests, "get", return_value=mock_response):
            result = self.wegagen.get_wegagen_rates()

        self.assertEqual(result, {"error": "Failed to parse response: 'attributes'"})

    def test_route_functions_delegate_to_scrapers(self):
        with patch.object(self.app, "fetch_cbe_exchange_rates", return_value={"USD": {"buying": 1}}):
            self.assertEqual(self.app.get_cbe_exchange_rates(), {"USD": {"buying": 1}})

        with patch.object(self.app, "scrape_boa_exchange_rates", return_value={"USD": {"buying": 2}}):
            self.assertEqual(self.app.get_boa_exchange_rates(), {"USD": {"buying": 2}})

        with patch.object(self.app, "scrape_coop_exchange_rates", return_value={"USD": {"buying": 3}}):
            self.assertEqual(self.app.get_coop_exchange_rates(), {"USD": {"buying": 3}})

        with patch.object(self.app, "scrape_hibret_exchange_rates", return_value={"USD": {"buying": 4}}):
            self.assertEqual(self.app.get_hibret_exchange_rates(), {"USD": {"buying": 4}})

        with patch.object(self.app, "get_wegagen_rates", return_value={"USD": {"buying": 5}}):
            self.assertEqual(self.app.get_wegagen_exchange_rates(), {"USD": {"buying": 5}})

        with patch.object(self.app, "get_awash_rates", return_value={"USD": {"buying": 6}}):
            self.assertEqual(self.app.get_awash_exchange_rates(), {"USD": {"buying": 6}})

        with patch.object(self.app, "scrape_nib_rates", return_value={"USD": {"buying": 7}}):
            self.assertEqual(self.app.get_nib_exchange_rates(), {"USD": {"buying": 7}})

    def test_coop_wrapper_payload_is_normalized_to_standard_schema(self):
        wrapped_payload = [
            {
                "ExchangeRate": [
                    {
                        "cashBuying": 153.1701,
                        "cashSelling": 156.2335,
                        "currency": {
                            "CurrencyCode": "USD",
                            "CurrencyName": "US DOLLAR",
                        },
                    },
                    {
                        "cashBuying": 209.3762,
                        "cashSelling": 213.5637,
                        "currency": {
                            "CurrencyCode": "GBP",
                            "CurrencyName": "POUND STERLING",
                        },
                    },
                ]
            }
        ]

        with patch.object(self.app, "scrape_coop_exchange_rates", return_value=json.dumps(wrapped_payload)):
            result = self.app.get_coop_exchange_rates()

        self.assertEqual(
            result,
            {
                "USD": {
                    "currency_code": "USD",
                    "name": "US DOLLAR",
                    "buying": 153.1701,
                    "selling": 156.2335,
                },
                "GBP": {
                    "currency_code": "GBP",
                    "name": "POUND STERLING",
                    "buying": 209.3762,
                    "selling": 213.5637,
                },
            },
        )

    def test_coop_wrapper_payload_with_no_rates_returns_500_error(self):
        with patch.object(self.app, "scrape_coop_exchange_rates", return_value=json.dumps([{"ExchangeRate": []}])):
            result = self.app.get_coop_exchange_rates()

        self.assertEqual(
            result,
            ({"error": "Failed to parse Cooperative Bank exchange rates"}, 500),
        )

    def test_error_routes_return_500_payload(self):
        with patch.object(self.app, "scrape_hibret_exchange_rates", return_value={"error": "upstream"}):
            self.assertEqual(
                self.app.get_hibret_exchange_rates(),
                ({"error": "Failed to fetch Hibret Bank exchange rates"}, 500),
            )

        with patch.object(self.app, "get_wegagen_rates", return_value={"error": "upstream"}):
            self.assertEqual(
                self.app.get_wegagen_exchange_rates(),
                ({"error": "Failed to fetch Wegagen Bank exchange rates"}, 500),
            )

        with patch.object(self.app, "get_awash_rates", return_value={"error": "upstream"}):
            self.assertEqual(
                self.app.get_awash_exchange_rates(),
                ({"error": "Failed to fetch Awash Bank exchange rates"}, 500),
            )

        with patch.object(self.app, "scrape_nib_rates", return_value={"error": "upstream"}):
            self.assertEqual(
                self.app.get_nib_exchange_rates(),
                ({"error": "Failed to fetch NIB Bank exchange rates"}, 500),
            )

    def test_swagger_docs_and_openapi_spec_are_exposed(self):
        docs_html = self.app.swagger_ui()
        spec = self.app.openapi_json()
        index_page = self.app.index()

        self.assertIn("SwaggerUIBundle", docs_html)
        self.assertEqual(spec["info"]["title"], "Ethiopian Bank Exchange Rates API")
        self.assertIn("/cbe-exchange-rates", spec["paths"])
        self.assertIn("/apidocs", index_page[0])

    def test_request_stats_file_counter_persists(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            stats_file = self.app.Path(tmp_dir) / "request_stats.json"

            with patch.object(self.app, "REQUEST_STATS_FILE", stats_file):
                self.assertEqual(self.app.get_request_stats()["total_requests"], 0)
                self.app._increment_request_stats("/cbe-exchange-rates")
                self.app._increment_request_stats("/cbe-exchange-rates")
                self.app._increment_request_stats("/boa-exchange-rates")

                stats = self.app.get_request_stats()

        self.assertEqual(stats["total_requests"], 3)
        self.assertEqual(stats["by_path"]["/cbe-exchange-rates"], 2)
        self.assertEqual(stats["by_path"]["/boa-exchange-rates"], 1)
        self.assertTrue(stats["updated_at"].endswith("Z"))

    def test_request_stats_endpoint_delegates_to_stats_reader(self):
        with patch.object(
            self.app,
            "get_request_stats",
            return_value={"total_requests": 9, "updated_at": None, "by_path": {}},
        ):
            result = self.app.request_stats_endpoint()

        self.assertEqual(result["total_requests"], 9)


if __name__ == "__main__":
    unittest.main()
