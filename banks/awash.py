import requests
import re

def get_awash_rates(date: str = "2026-04-24") -> dict:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    })

    page = session.get("https://awashbank.com/exchange-historical/")
    nonce_match = re.search(r'"nonce"\s*:\s*"([a-f0-9]+)"', page.text)
    nonce = nonce_match.group(1) if nonce_match else "df723e51c0"

    response = session.post(
        "https://awashbank.com/wp-admin/admin-ajax.php",
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://awashbank.com/exchange-historical/",
        },
        data={
            "action": "get_exchange_rates",
            "nonce": nonce,
            "shortcode_type": "exchange_rates",
            "is_user_selected": "true",
            "date": date,
        }
    )

    data = response.json()
    if not data.get("success"):
        raise Exception("Awash API returned failure")

    name_map = {
        "USD": "US DOLLAR", "GBP": "POUND STERLING", "EUR": "EURO",
        "AED": "UAE DIRHAM", "CAD": "CANADIAN DOLLAR", "CNY": "CHINESE YUAN",
        "CHF": "SWISS FRANK", "JPY": "JAPANESE YEN", "SAR": "SAUDI RIYAL",
        "SEK": "SWEDISH KRONER", "NOK": "NORWEGIAN KRONER", "DKK": "DANISH KRONER",
        "INR": "INDIAN RUPEE", "KES": "KENYAN SHILLING", "ZAR": "SOUTH AFRICAN RAND",
        "DJF": "DJIBOUTI FRANC", "AUD": "AUSTRALIAN DOLLAR",
    }

    cleaned_rates = {}
    for code, info in data["data"]["rates"].items():
        buying = info["buying"] or info["transaction_buying"] or None
        selling = info["selling"] or info["transaction_selling"] or None

        cleaned_rates[code] = {
            "currency_code": code,
            "name": name_map.get(code, info["name"].upper()),
            "buying": float(buying) if buying else None,
            "selling": float(selling) if selling else None,
        }

    return cleaned_rates


if __name__ == "__main__":
    rates = get_awash_rates("2026-04-24")
    for code, r in rates.items():
        print(r)