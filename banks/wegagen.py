import requests

def get_wegagen_rates() -> dict:
    response = requests.get(
        "https://weg.back.strapi.wegagen.com/api/exchange-rates?populate=*",
        headers={
            "Accept": "application/json",
            "Origin": "https://wegagen.com",
            "Referer": "https://wegagen.com/",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        }
    )
    response.raise_for_status()
    data = response.json()

    name_map = {
        "USD": "US DOLLAR", "GBP": "POUND STERLING", "EUR": "EURO",
        "AED": "UAE DIRHAM", "CAD": "CANADIAN DOLLAR", "CNY": "CHINESE YUAN",
        "CHF": "SWISS FRANK", "JPY": "JAPANESE YEN", "SAR": "SAUDI RIYAL",
        "SEK": "SWEDISH KRONER", "NOK": "NORWEGIAN KRONER", "DKK": "DANISH KRONER",
        "INR": "INDIAN RUPEE", "KES": "KENYAN SHILLING", "ZAR": "SOUTH AFRICAN RAND",
        "DJF": "DJIBOUTI FRANC", "AUD": "AUSTRALIAN DOLLAR",
    }

    cleaned_rates = {}
    for item in data["data"]:
        attr = item["attributes"]
        code = attr["code"].upper()
        cleaned_rates[code] = {
            "currency_code": code,
            "name": name_map.get(code, code),
            "buying": attr["buying"],
            "selling": attr["selling"],
        }

    return cleaned_rates




if __name__ == "__main__":
    rates = get_wegagen_rates()
    for code, r in rates.items():
        print(r)