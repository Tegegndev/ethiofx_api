
import requests

from bs4 import BeautifulSoup

def scrape_nib_rates() -> dict:
    response = requests.get(
        "https://www.nibbanksc.com/exchange-rate/",
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Referer": "https://www.nibbanksc.com/",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    tables = soup.find_all("table", class_="ea-advanced-data-table")
    if len(tables) < 2:
        return {"error": "Could not find exchange rate tables"}

    name_map = {
        "USD": "US DOLLAR", "GBP": "POUND STERLING", "EUR": "EURO",
        "AED": "UAE DIRHAM", "CAD": "CANADIAN DOLLAR", "CNY": "CHINESE YUAN",
        "CHF": "SWISS FRANK", "JPY": "JAPANESE YEN", "SAR": "SAUDI RIYAL",
        "SEK": "SWEDISH KRONER", "NOK": "NORWEGIAN KRONER", "DKK": "DANISH KRONER",
        "INR": "INDIAN RUPEE", "KES": "KENYAN SHILLING", "ZAR": "SOUTH AFRICAN RAND",
        "DJF": "DJIBOUTI FRANC", "AUD": "AUSTRALIAN DOLLAR",
    }

    def parse_val(text):
        try:
            return float(text.strip())
        except ValueError:
            return None

    cleaned_rates = {}

    # table[0] = unknown, table[1] = cash rates (6 cols), table[2] = weighted avg (4 cols)
    cash_table = tables[1]
    for row in cash_table.find("tbody").find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 4:
            continue
        code = cols[1].get_text(strip=True)
        if not code:
            continue
        cleaned_rates[code] = {
            "currency_code": code,
            "name": name_map.get(code, code),
            "buying": parse_val(cols[2].get_text()),
            "selling": parse_val(cols[3].get_text()),
        }

    return cleaned_rates


if __name__ == "__main__":
    rates = scrape_nib_rates()
    for code, r in rates.items():
        print(r)