import requests
from termcolor import colored

def get_exchange_rates(date: str = "2026-04-24") -> list[dict]:
    # First get the nonce from the page
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    })

    page = session.get("https://awashbank.com/exchange-historical/")
    
    # Extract nonce from page source
    import re
    nonce_match = re.search(r'"nonce"\s*:\s*"([a-f0-9]+)"', page.text)
    print(colored(f"Extracted nonce: {nonce_match.group(1) if nonce_match else 'Not found'}", "green"))
    nonce = nonce_match.group(1) if nonce_match else "df723e51c0"  # fallback

    # Hit the AJAX endpoint directly
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
        raise Exception("API returned failure")

    rates = data["data"]["rates"]

    return [
        {
            "currency_code": code,
            "currency_name": info["name"],
            "cash_buying": info["buying"] or "N/A",
            "cash_selling": info["selling"] or "N/A",
            "txn_buying": info["transaction_buying"] or "N/A",
            "txn_selling": info["transaction_selling"] or "N/A",
            "weighted_buying": info["weighted_buying_average"] or "N/A",
            "weighted_selling": info["weighted_selling_average"] or "N/A",
        }
        for code, info in rates.items()
    ]


if __name__ == "__main__":
    rates = get_exchange_rates("2026-04-23")
    for r in rates:
        print(r)