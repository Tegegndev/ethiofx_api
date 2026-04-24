import re

from bs4 import BeautifulSoup
import requests


def scrape_hibret_exchange_rates() -> dict:
    response = requests.get(
        "https://www.hibretbank.com.et/about/exchange-rate/",
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Referer": "https://www.hibretbank.com.et/",
        },
        verify=False  # Disable SSL verification if needed (not recommended for production
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table")
    if not table:
        return {"error": "Could not find exchange rate table"}

    rows = table.find("tbody").find_all("tr")

    # Normalize currency name like the rest of your scrapers
    name_map = {
        "USD": "US DOLLAR", "GBP": "POUND STERLING", "EUR": "EURO",
        "AED": "UAE DIRHAM", "CAD": "CANADIAN DOLLAR", "CNY": "CHINESE YUAN",
        "CHF": "SWISS FRANK", "JPY": "JAPANESE YEN", "SAR": "SAUDI RIYAL",
    }

    cleaned_rates = {}

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 6:
            continue

        currency_text = cols[1].get_text(strip=True)
        if not currency_text or currency_text in ("CURRENCY",):
            continue

        # Extract code from alt attribute of flag img
        img = cols[0].find("img")
        code = img["alt"].upper() if img and img.get("alt") else None

        # Fallback: parse code from text like "USD (US Dollar)"
        if not code or len(code) > 4:
            match = re.match(r'^([A-Z]{2,4})', currency_text)
            code = match.group(1) if match else None

        if not code:
            continue

        def val(col):
            text = col.get_text(strip=True)
            try:
                return float(text.replace(",", ""))
            except ValueError:
                return None

        buying = val(cols[2])
        selling = val(cols[3])
        txn_buying = val(cols[4])
        txn_selling = val(cols[5])

        # Use transaction rates as fallback if cash is None
        cleaned_rates[code] = {
            "currency_code": code,
            "name": name_map.get(code, currency_text.upper()),
            "buying": buying or txn_buying,
            "selling": selling or txn_selling,
        }

    return cleaned_rates


if __name__ == "__main__":
    rates = scrape_hibret_exchange_rates()
    print(rates)