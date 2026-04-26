import logging

import requests

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


def get_wegagen_rates() -> dict:
    """Fetch current exchange rates from Wegagen Bank's API.

    Returns a dict keyed by currency code on success, or a dict with
    an "error" key if something goes wrong.
    """
    url = "https://weg.back.strapi.wegagen.com/api/exchange-rates?populate=*"
    headers = {
        "Accept": "application/json",
        "Origin": "https://wegagen.com",
        "Referer": "https://wegagen.com/",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    }

    try:
        logger.info("Fetching Wegagen Bank exchange rates...")
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        data = response.json()

        cleaned_rates = {}
        for item in data["data"]:
            attr = item["attributes"]
            code = attr["code"].upper()
            cleaned_rates[code] = {
                "currency_code": code,
                "name": NAME_MAP.get(code, code),
                "buying": attr["buying"],
                "selling": attr["selling"],
            }

        logger.info("Successfully fetched %d currencies from Wegagen Bank", len(cleaned_rates))
        return cleaned_rates

    except requests.exceptions.ConnectionError:
        logger.error("Could not connect to Wegagen Bank API. Check your internet connection.")
        return {"error": "Connection failed - could not reach Wegagen Bank API"}
    except requests.exceptions.Timeout:
        logger.error("Request to Wegagen Bank timed out.")
        return {"error": "Request timed out"}
    except requests.exceptions.HTTPError as e:
        logger.error("Wegagen Bank API returned an HTTP error: %s", e)
        return {"error": f"HTTP error: {e}"}
    except (KeyError, ValueError) as e:
        logger.error("Failed to parse Wegagen Bank response data: %s", e)
        return {"error": f"Failed to parse response: {e}"}
    except Exception as e:
        logger.error("An unexpected error occurred while fetching Wegagen Bank rates: %s", e)
        return {"error": f"Unexpected error: {e}"}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    rates = get_wegagen_rates()
    for code, r in rates.items():
        print(r)