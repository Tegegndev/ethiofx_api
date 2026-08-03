import json
import logging

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Map short currency codes to their full names
CURRENCY_MAP = {
    "USD": "US DOLLAR", "GBP": "POUND STERLING", "EUR": "EURO",
    "AED": "UAE DIRHAM", "CHF": "SWISS FRANC", "SEK": "SWEDISH KRONER",
    "NOK": "NORWEGIAN KRONER", "CAD": "CANADIAN DOLLAR", "SAR": "SAUDI RIYAL",
    "CNY": "CHINESE YUAN", "KWD": "KUWAITI DINAR", "INR": "INDIAN RUPEE",
    "JPY": "JAPANESE YEN", "ZAR": "SOUTH AFRICAN RAND", "DKK": "DANISH KRONER",
    "DJF": "DJIBOUTI FRANC", "KES": "KENYAN SHILLING", "AUD": "AUSTRALIAN DOLLAR"
}


def _parse_float(text):
    """Extract a float value from text. Returns None if not parseable."""
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def scrape_boa_exchange_rates():
    """Scrape current exchange rates from Bank of Abyssinia's website.

    The page contains two tables in one: cash rates and transaction rates.
    Returns a dict keyed by currency code, preferring cash rates and falling
    back to transaction rates when cash is unavailable.
    """
    url = "https://www.bankofabyssinia.com/exchange-rate-2/"

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        logger.info("Fetching Bank of Abyssinia exchange rates...")
        # SSL verification is disabled because the bank's certificate chain
        # is incomplete and fails verification. The server is also slow,
        # so allow a generous timeout.
        response = requests.get(url, headers=headers, timeout=90, verify=False)
        response.raise_for_status()

    except requests.exceptions.ConnectionError:
        logger.error("Could not connect to Bank of Abyssinia website.")
        return {"error": "Connection failed - could not reach Bank of Abyssinia website"}
    except requests.exceptions.Timeout:
        logger.error("Request to Bank of Abyssinia timed out.")
        return {"error": "Request timed out"}
    except requests.exceptions.HTTPError as e:
        logger.error("Bank of Abyssinia website returned an HTTP error: %s", e)
        return {"error": f"HTTP error: {e}"}
    except requests.exceptions.RequestException as e:
        logger.error("Something went wrong while requesting Bank of Abyssinia data: %s", e)
        return {"error": f"Request error: {e}"}

    try:
        soup = BeautifulSoup(response.text, "html.parser")

        # The page uses a single tablepress table with two sections:
        # cash rates followed by transaction rates.
        table = soup.find("table", id="tablepress-15")
        if not table:
            table = soup.find("table")

        if not table:
            logger.error("Could not find an exchange rate table on the Bank of Abyssinia page")
            return {"error": "Could not find exchange rate table"}

        rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")

        cash_rates = {}
        txn_rates = {}
        section = None

        for row in rows:
            cols = row.find_all(["td", "th"])
            if len(cols) < 3:
                continue

            header_text = cols[0].get_text(strip=True).upper()
            if header_text in ("CASH RATES", "TRANSACTION RATES"):
                section = header_text
                continue
            if header_text == "CURRENCY TYPE":
                continue

            code = cols[0].get_text(strip=True).upper()
            if len(code) != 3 or not code.isalpha():
                continue

            buying = _parse_float(cols[1].get_text(strip=True))
            selling = _parse_float(cols[2].get_text(strip=True))
            if buying is None or selling is None:
                continue

            if section == "TRANSACTION RATES":
                txn_rates[code] = (buying, selling)
            else:
                cash_rates[code] = (buying, selling)

        if not cash_rates and not txn_rates:
            logger.error("No exchange rates parsed from Bank of Abyssinia page")
            return {"error": "No exchange rates found on page"}

        cleaned_rates = {}
        all_codes = set(cash_rates) | set(txn_rates)
        for code in all_codes:
            buying, selling = cash_rates.get(code, txn_rates.get(code))
            cleaned_rates[code] = {
                "currency_code": code,
                "name": CURRENCY_MAP.get(code, code),
                "buying": buying,
                "selling": selling,
            }

        logger.info("Successfully scraped %d currencies from Bank of Abyssinia", len(cleaned_rates))
        return cleaned_rates

    except Exception as e:
        logger.error("Failed to parse Bank of Abyssinia response: %s", e)
        return {"error": f"Failed to parse page: {e}"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(scrape_boa_exchange_rates(), indent=2))
