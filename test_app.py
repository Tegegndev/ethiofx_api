import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the workspace directory to the Python path so we can import app.py
sys.path.insert(0, '/workspace')

import app
from datetime import datetime


class TestFetchCBEExchangeRates(unittest.TestCase):
    """Test cases for the fetch_cbe_exchange_rates function"""

    @patch('app.requests.get')
    def test_fetch_cbe_exchange_rates_success(self, mock_get):
        """Test successful fetching of CBE exchange rates"""
        # Mock response data
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "ExchangeRate": [
                    {
                        "currency": {"CurrencyName": "US DOLLAR", "CurrencyCode": "USD"},
                        "cashBuying": 50.0,
                        "cashSelling": 52.0
                    }
                ],
                "Date": "2023-01-01"
            }
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Call the function
        result = app.fetch_cbe_exchange_rates("2023-01-01")

        # Assertions
        self.assertIsNotNone(result)
        self.assertIn("USD", result)
        self.assertEqual(result["USD"]["name"], "US DOLLAR")
        self.assertEqual(result["USD"]["buying"], 50.0)
        self.assertEqual(result["USD"]["selling"], 52.0)

    @patch('app.requests.get')
    def test_fetch_cbe_exchange_rates_request_exception(self, mock_get):
        """Test handling of request exceptions"""
        mock_get.side_effect = [Exception("Network error")]

        result = app.fetch_cbe_exchange_rates("2023-01-01")
        
        self.assertIsNone(result)

    @patch('app.requests.get')
    def test_fetch_cbe_exchange_rates_empty_response(self, mock_get):
        """Test handling of empty response"""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = app.fetch_cbe_exchange_rates("2023-01-01")
        
        self.assertIsNone(result)


class TestScrapeBOAExchangeRates(unittest.TestCase):
    """Test cases for the scrape_boa_exchange_rates function"""

    @patch('app.requests.get')
    @patch('app.BeautifulSoup')
    def test_scrape_boa_exchange_rates_success(self, mock_bs, mock_get):
        """Test successful scraping of BOA exchange rates"""
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.text = """
        <html>
          <head>
            <title>Bank of Abyssinia - Exchange Rates</title>
          </head>
          <body>
            <table id="tablepress-15">
              <thead>
                <tr>
                  <th class="column-1">January 01, 2023</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>USD</td>
                  <td>51.0</td>
                  <td>53.0</td>
                </tr>
              </tbody>
            </table>
          </body>
        </html>
        """
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Set up BeautifulSoup mocks
        mock_th = MagicMock()
        mock_th.get_text.return_value = "January 01, 2023"
        mock_table = MagicMock()
        mock_row = MagicMock()
        mock_col1 = MagicMock()
        mock_col1.get_text.return_value = "USD"
        mock_col2 = MagicMock()
        mock_col2.get_text.return_value = "51.0"
        mock_col3 = MagicMock()
        mock_col3.get_text.return_value = "53.0"
        mock_row.find_all.return_value = [mock_col1, mock_col2, mock_col3]
        mock_tbody = MagicMock()
        mock_tbody.find_all.return_value = [mock_row]
        mock_table.find.return_value = mock_tbody
        mock_bs.return_value.find.return_value = mock_table
        mock_bs.return_value.find.side_effect = lambda tag, **kwargs: mock_th if tag == 'th' and kwargs.get('class_') == 'column-1' else mock_table

        result = app.scrape_boa_exchange_rates()

        self.assertIsNotNone(result)
        self.assertIn("USD", result)
        self.assertEqual(result["USD"]["buying"], 51.0)
        self.assertEqual(result["USD"]["selling"], 53.0)

    @patch('app.requests.get')
    def test_scrape_boa_exchange_rates_request_exception(self, mock_get):
        """Test handling of request exceptions in BOA scraper"""
        mock_get.side_effect = Exception("Network error")

        result = app.scrape_boa_exchange_rates()
        
        self.assertIsNotNone(result)
        self.assertIn("error", result)


class TestScrapeCoopExchangeRates(unittest.TestCase):
    """Test cases for the scrape_coop_exchange_rates function"""

    @patch('app.requests.get')
    @patch('app.BeautifulSoup')
    @patch('app.re.search')
    def test_scrape_coop_exchange_rates_success(self, mock_re_search, mock_bs, mock_get):
        """Test successful scraping of Coop Bank exchange rates"""
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.text = "<html></html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Mock regex search to return a match
        mock_match = MagicMock()
        mock_match.group.return_value = '{"USD": {"buying": "50.5", "selling": "52.5", "name": "US Dollar"}}'
        mock_re_search.return_value = mock_match

        # Mock BeautifulSoup
        mock_script = MagicMock()
        mock_script.text = "exchangeRates = {\"USD\": {\"buying\": \"50.5\", \"selling\": \"52.5\", \"name\": \"US Dollar\"}}"
        mock_bs.return_value.find_all.return_value = [mock_script]
        
        # Mock table finding to return None (so script strategy is used)
        mock_bs.return_value.find.return_value = None

        result = app.scrape_coop_exchange_rates()

        self.assertIsNotNone(result)
        self.assertIn("USD", result)
        self.assertEqual(result["USD"]["buying"], 50.5)
        self.assertEqual(result["USD"]["selling"], 52.5)

    @patch('app.requests.get')
    def test_scrape_coop_exchange_rates_exception(self, mock_get):
        """Test handling of exceptions in Coop Bank scraper"""
        mock_get.side_effect = Exception("Network error")

        result = app.scrape_coop_exchange_rates()
        
        self.assertIsNotNone(result)
        self.assertIn("error", result)


class TestFetchDashenExchangeRates(unittest.TestCase):
    """Test cases for the fetch_dashen_exchange_rates function"""

    @patch('app.requests.get')
    @patch('app.BeautifulSoup')
    def test_fetch_dashen_exchange_rates_success(self, mock_bs, mock_get):
        """Test successful fetching of Dashen Bank exchange rates"""
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.text = "<html></html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Mock BeautifulSoup parsing
        mock_table = MagicMock()
        mock_row = MagicMock()
        mock_cols = [
            MagicMock(**{"get_text.return_value": "USD"}),
            MagicMock(**{"get_text.return_value": "US Dollar"}),
            MagicMock(**{"get_text.return_value": "50.0"}),
            MagicMock(**{"get_text.return_value": "52.0"})
        ]
        mock_row.find_all.return_value = mock_cols
        mock_body = MagicMock()
        mock_body.find_all.return_value = [mock_row]
        mock_table.find.return_value = mock_body
        mock_content_div = MagicMock()
        mock_content_div.find.return_value = mock_table
        mock_bs.return_value.find.return_value = mock_content_div

        result = app.fetch_dashen_exchange_rates()

        # Since this function returns JSON string, parse it back
        import json
        parsed_result = json.loads(result)
        
        self.assertIsNotNone(parsed_result)
        self.assertIn("USD", parsed_result)
        self.assertEqual(parsed_result["USD"]["buying"], 50.0)
        self.assertEqual(parsed_result["USD"]["selling"], 52.0)

    @patch('app.requests.get')
    def test_fetch_dashen_exchange_rates_exception(self, mock_get):
        """Test handling of exceptions in Dashen Bank fetcher"""
        mock_get.side_effect = Exception("Network error")

        result = app.fetch_dashen_exchange_rates()

        import json
        parsed_result = json.loads(result)
        
        self.assertIsNotNone(parsed_result)
        self.assertIn("error", parsed_result)


class TestAppRoutes(unittest.TestCase):
    """Test cases for Flask routes"""

    def setUp(self):
        """Set up test client"""
        app.app.config['TESTING'] = True
        self.client = app.app.test_client()

    def test_index_route(self):
        """Test the index route"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Welcome to the Exchange Rate API", response.data)


if __name__ == '__main__':
    unittest.main()