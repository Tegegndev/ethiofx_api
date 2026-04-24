import requests

def get_wegagen_rates() -> list[dict]:
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

    return [
        {
            "currency_code": item["attributes"]["code"],
            "date": item["attributes"]["date"],
            "buying": item["attributes"]["buying"],
            "selling": item["attributes"]["selling"],
            "tra_buying": item["attributes"]["tra_buying"],
            "tra_selling": item["attributes"]["tra_selling"],
        }
        for item in data["data"]
    ]


if __name__ == "__main__":
    rates = get_wegagen_rates()
    for r in rates:
        print(r)