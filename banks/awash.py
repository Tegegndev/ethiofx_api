import logging
import re
from termcolor import colored
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


def get_awash_rates(date: str = "2026-04-24") -> dict:
    """Fetch exchange rates from Awash Bank for the given date.

    Returns a dict keyed by currency code on success, or a dict with
    an "error" key if something goes wrong.
    """
    try:
        logger.info("Fetching Awash Bank exchange rates for date: %s", date)

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        })

        # First, load the page to grab the security nonce WordPress uses
        page = session.get("https://awashbank.com/exchange-historical/", timeout=20)
        page.raise_for_status()

        nonce_match = re.search(r'"nonce"\s*:\s*"([a-f0-9]+)"', page.text)
        if nonce_match:
            nonce = nonce_match.group(1)
            logger.info("Found nonce in page source")
        else:
            # Fall back to a known nonce if we can't extract one
            nonce = "df723e51c0"
            logger.warning("Could not find nonce in page source, using fallback nonce")

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
            },
            timeout=20,
        )
        response.raise_for_status()

        data = response.json()
        if not data.get("success"):
            logger.error("Awash Bank API responded but reported failure: %s", data)
            return {"error": "Awash Bank API returned a failure response"}

        cleaned_rates = {}
        for code, info in data["data"]["rates"].items():
            # Use cash rates first; fall back to transaction rates if cash is missing
            buying = info.get("buying") or info.get("transaction_buying") or None
            selling = info.get("selling") or info.get("transaction_selling") or None

            cleaned_rates[code] = {
                "currency_code": code,
                "name": NAME_MAP.get(code, info.get("name", code).upper()),
                "buying": float(buying) if buying else None,
                "selling": float(selling) if selling else None,
            }

        logger.info("Successfully fetched %d currencies from Awash Bank", len(cleaned_rates))
        return cleaned_rates

    except requests.exceptions.ConnectionError:
        logger.error("Could not connect to Awash Bank website. Check your internet connection.")
        return {"error": "Connection failed - could not reach Awash Bank website"}
    except requests.exceptions.Timeout:
        logger.error("Request to Awash Bank timed out.")
        return {"error": "Request timed out"}
    except requests.exceptions.HTTPError as e:
        logger.error("Awash Bank website returned an HTTP error: %s", e)
        return {"error": f"HTTP error: {e}"}
    except (KeyError, ValueError) as e:
        logger.error("Failed to parse Awash Bank response data: %s", e)
        return {"error": f"Failed to parse response: {e}"}
    except Exception as e:
        logger.error("An unexpected error occurred while fetching Awash Bank rates: %s", e)
        return {"error": f"Unexpected error: {e}"}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    rates = get_awash_rates("2026-04-24")
    for code, r in rates.items():
        print(r)

    print(colored("COnfigure Nonce security for awash bank", "red"))