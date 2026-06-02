import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import logging
logger = logging.getLogger(__name__)



def scrape_boa_exchange_rates():
    url = 'https://www.bankofabyssinia.com/exchange-rate-2/'
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    # Mapping to match CBE's "CurrencyName" field
    currency_map = {
        "USD": "US DOLLAR", "GBP": "POUND STERLING", "EUR": "EURO",
        "AED": "UAE DIRHAM", "CHF": "SWISS FRANC", "SEK": "SWEDISH KRONER",
        "NOK": "NORWEGIAN KRONER", "CAD": "CANADIAN DOLLAR", "SAR": "SAUDI RIYAL",
        "CNY": "CHINESE YUAN", "KWD": "KUWAITI DINAR", "INR": "INDIAN RUPEE",
        "JPY": "JAPANESE YEN", "ZAR": "SOUTH AFRICAN RAND", "DKK": "DANISH KRONER",
        "DJF": "DJIBOUTI FRANC", "KES": "KENYAN SHILLING", "AUD": "AUSTRALIAN DOLLAR"
    }

    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # 1. Safer Date Extraction
        date_header = soup.find('th', class_='column-1')
        if not date_header:
            # Fallback if class name changed
            date_header = soup.find('thead').find('th') if soup.find('thead') else None
        
        if date_header:
            date_str_raw = date_header.get_text(strip=True)
            try:
                date_obj = datetime.strptime(date_str_raw, "%B %d, %Y")
                formatted_date = date_obj.strftime("%Y-%m-%d")
            except ValueError:
                formatted_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        else:
            formatted_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # 2. Find the table
        table = soup.find('table', id='tablepress-15')
        if not table:
            # Try finding any table if ID failed
            table = soup.find('table')
            
        if not table:
            return {"error": "Could not find exchange rate table on page."}

        rows = table.find('tbody').find_all('tr') if table.find('tbody') else table.find_all('tr')
        
        exchange_rates = []
        seen_currencies = set() # To prevent duplicates

        for row in rows:
            cols = row.find_all(['td', 'th'])
            if len(cols) < 3:
                continue
            
            code = cols[0].get_text(strip=True).upper()
            
            # Validation: Only process 3-letter currency codes we haven't seen yet
            if len(code) != 3 or code in seen_currencies:
                continue

            try:
                # Clean numeric strings (remove commas if any)
                buying_str = cols[1].get_text(strip=True).replace(',', '')
                selling_str = cols[2].get_text(strip=True).replace(',', '')
                
                buying = float(buying_str)
                selling = float(selling_str)
                
                seen_currencies.add(code)

                rate_entry = {
                    "__component": "exchange-rate.exchange-rate",
                    "cashBuying": buying,
                    "cashSelling": selling,
                    "transactionalBuying": buying,
                    "transactionalSelling": selling,
                    "_id": f"boa_rate_{code.lower()}",
                    "weightedAverageBuying": None,
                    "weightedAverageSelling": None,
                    "__v": 0,
                    "currency": {
                        "show_on_home": True,
                        "_id": f"boa_curr_{code.lower()}",
                        "CurrencyCode": code,
                        "CurrencyName": currency_map.get(code, code),
                        "id": f"boa_curr_{code.lower()}"
                    },
                    "id": f"boa_rate_{code.lower()}"
                }
                exchange_rates.append(rate_entry)
            except ValueError:
                continue

        # 3. Construct cleaned rates dict
        cleaned_rates = {}
        for rate in exchange_rates:
            currency = rate['currency']
            code = currency['CurrencyCode']
            name = currency['CurrencyName']
            buying = rate['cashBuying']
            selling = rate['cashSelling']
            cleaned_rates[code] = {
                'currency_code': code,
                'name': name,
                'buying': buying,
                'selling': selling
            }
        return cleaned_rates

    except Exception as e:
        return {"error": f"Scraper failed: {str(e)}"}

if __name__ == "__main__":
    rates = scrape_boa_exchange_rates()
    print(json.dumps(rates, indent=2))
