
import logging

import requests
from bs4 import BeautifulSoup

# Get a logger for this module.
# When this file is imported by app.py, logging is configured there.
# When run directly, we set up basic logging below in __main__.
logger = logging.getLogger(__name__)

# Map short currency codes to their full names
NAME_MAP = {
    "USD": "US DOLLAR", "GBP": "POUND STERLING", "EUR": "EURO",
    "AED": "UAE DIRHAM", "CAD": "CANADIAN DOLLAR", "CNY": "CHINESE YUAN",
    "CHF": "SWISS FRANC", "JPY": "JAPANESE YEN", "SAR": "SAUDI RIYAL",
    "SEK": "SWEDISH KRONER", "NOK": "NORWEGIAN KRONER", "DKK": "DANISH KRONER",
    "INR": "INDIAN RUPEE", "KES": "KENYAN SHILLING", "ZAR": "SOUTH AFRICAN RAND",
    "DJF": "DJIBOUTI FRANC", "AUD": "AUSTRALIAN DOLLAR",
}


def _parse_float(text):
    """Try to turn a string like '  57.32  ' into a float.
    Returns None if the conversion fails instead of crashing.
    """
    try:
        return float(text.strip())
    except ValueError:
        return None


def scrape_nib_rates() -> dict:
    """Scrape the current exchange rates from NIB Bank's website.

    Returns a dict keyed by currency code, e.g.:
        {"USD": {"currency_code": "USD", "name": "US DOLLAR", "buying": 57.0, "selling": 58.5}}

    On failure, returns a dict with a single "error" key so callers
    can check for errors without catching exceptions themselves.
    """
    url = "https://www.nibbanksc.com/exchange-rate/"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Referer": "https://www.nibbanksc.com/",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        logger.info("Fetching NIB Bank exchange rates...")
        response = requests.get(url, headers=headers, timeout=20)
        # Raises an HTTPError for 4xx/5xx responses
        response.raise_for_status()

    except requests.exceptions.ConnectionError:
        logger.error("Could not connect to NIB Bank website. Check your internet connection.")
        return {"error": "Connection failed - could not reach NIB Bank website"}
    except requests.exceptions.Timeout:
        logger.error("Request to NIB Bank timed out after 20 seconds.")
        return {"error": "Request timed out"}
    except requests.exceptions.HTTPError as e:
        logger.error("NIB Bank website returned an HTTP error: %s", e)
        return {"error": f"HTTP error: {e}"}
    except requests.exceptions.RequestException as e:
        logger.error("Something went wrong while requesting NIB Bank data: %s", e)
        return {"error": f"Request error: {e}"}

    try:
        soup = BeautifulSoup(response.text, "html.parser")

        # The page has multiple tables; index 1 is the cash rates table
        tables = soup.find_all("table", class_="ea-advanced-data-table")
        if len(tables) < 2:
            logger.error("Expected at least 2 tables on the NIB page but found %d", len(tables))
            return {"error": "Could not find exchange rate tables on the page"}

        cleaned_rates = {}
        cash_table = tables[1]

        for row in cash_table.find("tbody").find_all("tr"):
            cols = row.find_all("td")
            # We need at least 4 columns: flag, code, buying, selling
            if len(cols) < 4:
                continue

            code = cols[1].get_text(strip=True)
            if not code:
                continue

            buying = _parse_float(cols[2].get_text())
            selling = _parse_float(cols[3].get_text())

            cleaned_rates[code] = {
                "currency_code": code,
                "name": NAME_MAP.get(code, code),
                "buying": buying,
                "selling": selling,
            }

        logger.info("Successfully scraped %d currencies from NIB Bank", len(cleaned_rates))
        return cleaned_rates

    except Exception as e:
        logger.error("Failed to parse NIB Bank response: %s", e)
        return {"error": f"Failed to parse page: {e}"}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    rates = scrape_nib_rates()
    for code, r in rates.items():
        print(r)