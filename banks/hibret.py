import logging
import re

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Map short currency codes to their full names
NAME_MAP = {
    "USD": "US DOLLAR", "GBP": "POUND STERLING", "EUR": "EURO",
    "AED": "UAE DIRHAM", "CAD": "CANADIAN DOLLAR", "CNY": "CHINESE YUAN",
    "CHF": "SWISS FRANC", "JPY": "JAPANESE YEN", "SAR": "SAUDI RIYAL",
}


def _parse_float(col):
    """Extract a float value from a BeautifulSoup table cell.
    Returns None if the text can't be converted to a number.
    """
    text = col.get_text(strip=True)
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def scrape_hibret_exchange_rates() -> dict:
    """Scrape current exchange rates from Hibret Bank's website.

    Returns a dict keyed by currency code on success, or a dict with
    an "error" key if something goes wrong.
    """
    url = "https://www.hibretbank.com.et/about/exchange-rate/"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Referer": "https://www.hibretbank.com.et/",
    }

    try:
        logger.info("Fetching Hibret Bank exchange rates...")
        # SSL verification is disabled because Hibret Bank's certificate
        # can cause issues in some environments. Not ideal for production.
        response = requests.get(url, headers=headers, timeout=20, verify=False)
        response.raise_for_status()

    except requests.exceptions.ConnectionError:
        logger.error("Could not connect to Hibret Bank website. Check your internet connection.")
        return {"error": "Connection failed - could not reach Hibret Bank website"}
    except requests.exceptions.Timeout:
        logger.error("Request to Hibret Bank timed out.")
        return {"error": "Request timed out"}
    except requests.exceptions.HTTPError as e:
        logger.error("Hibret Bank website returned an HTTP error: %s", e)
        return {"error": f"HTTP error: {e}"}
    except requests.exceptions.RequestException as e:
        logger.error("Something went wrong while requesting Hibret Bank data: %s", e)
        return {"error": f"Request error: {e}"}

    try:
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table")
        if not table:
            logger.error("Could not find an exchange rate table on the Hibret Bank page")
            return {"error": "Could not find exchange rate table"}

        rows = table.find("tbody").find_all("tr")
        cleaned_rates = {}

        for row in rows:
            cols = row.find_all("td")
            # We need at least 6 columns: flag, currency, buying, selling, txn buying, txn selling
            if len(cols) < 6:
                continue

            currency_text = cols[1].get_text(strip=True)
            if not currency_text or currency_text in ("CURRENCY",):
                continue

            # Try to get the currency code from the flag image's alt text first
            img = cols[0].find("img")
            code = img["alt"].upper() if img and img.get("alt") else None

            # Fall back to parsing the code from the currency text (e.g. "USD (US Dollar)")
            if not code or len(code) > 4:
                match = re.match(r'^([A-Z]{2,4})', currency_text)
                code = match.group(1) if match else None

            if not code:
                continue

            buying = _parse_float(cols[2])
            selling = _parse_float(cols[3])
            txn_buying = _parse_float(cols[4])
            txn_selling = _parse_float(cols[5])

            # Prefer cash rates; fall back to transaction rates if cash is missing
            cleaned_rates[code] = {
                "currency_code": code,
                "name": NAME_MAP.get(code, currency_text.upper()),
                "buying": buying or txn_buying,
                "selling": selling or txn_selling,
            }

        logger.info("Successfully scraped %d currencies from Hibret Bank", len(cleaned_rates))
        return cleaned_rates

    except Exception as e:
        logger.error("Failed to parse Hibret Bank response: %s", e)
        return {"error": f"Failed to parse page: {e}"}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    rates = scrape_hibret_exchange_rates()
    print(rates)