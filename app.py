import requests
import json
from datetime import datetime
from bs4 import BeautifulSoup
from datetime import timezone
from flask import Flask, jsonify


app = Flask(__name__)


def fetch_cbe_exchange_rates(target_date=None):
    """
    Fetches daily exchange rates from CBE API.
    :param target_date: Date string in YYYY-MM-DD format. Defaults to today.
    """
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    url = "https://combanketh.et/cbeapi/daily-exchange-rates/"
    
    # Query parameters
    params = {
        '_limit': 1,
        'Date': target_date
    }

    # Headers from your curl command
    headers = {
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9,om;q=0.8,ru;q=0.7,am;q=0.6',
        'Connection': 'keep-alive',
        'Referer': 'https://combanketh.et/exchange-rates',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
        'api-key': 'Bearer sb_publishable_c9lt_SobLYwvlHO_qNHm2g_bRNh0dMJ',
        'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Linux"'
    }

    # Cookies from your curl command
    cookies = {
        '_ga': 'GA1.1.1333179547.1766772762',
        '_ga_NJXYC6GE1B': 'GS2.1.s1767029576$o2$g1$t1767029584$j52$l0$h0'
    }

    try:
        response = requests.get(url, headers=headers, params=params, cookies=cookies)
        response.raise_for_status()  # Raise exception for bad status codes
        
        data = response.json()

        if not data:
            print(f"No data available for {target_date}")
            return

        # Extract the main record (since _limit=1, it's the first item in the list)
        main_record = data[0]
        rates = main_record.get('ExchangeRate', [])

        print(f"CBE Daily Exchange Rates - Date: {main_record.get('Date')}")
        print("-" * 85)
        print(f"{'Currency Name':<25} | {'Code':<6} | {'Cash Buying':<12} | {'Cash Selling':<12}")
        print("-" * 85)
        cleaned_rates = {}
        for rate in rates:
            currency = rate.get('currency', {})
            name = currency.get('CurrencyName', 'N/A')
            code = currency.get('CurrencyCode', 'N/A')
            buying = rate.get('cashBuying', 0)
            selling = rate.get('cashSelling', 0)
            cleaned_rates[code] = {
                'currency_code': code,
              
                'name': name,
                'buying': buying,
                'selling': selling
            }

            print(f"{name:<25} | {code:<6} | {buying:<12.4f} | {selling:<12.4f}")
        return cleaned_rates

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
    except (KeyError, IndexError) as e:
        print(f"Error parsing JSON structure: {e}")

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
        "AED": "UAE DIRHAM", "CHF": "SWISS FRANK", "SEK": "SWEDISH KRONER",
        "NOK": "NORWEGIAN KRONER", "CAD": "CANADIAN DOLLAR", "SAR": "SAUDI RIYAL",
        "CNY": "CHINESE YUAN", "KWD": "KUWAITI DINAR", "INR": "INDIAN RUPEE",
        "JPY": "JAPANIS YEN", "ZAR": "SOUTH AFRICAN RAND", "DKK": "DANISH KRONER",
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

@app.route('/boa-exchange-rates', methods=['GET'])
def get_boa_exchange_rates():
    result = scrape_boa_exchange_rates()
    return jsonify(result)

@app.route('/cbe-exchange-rates', methods=['GET'])
def get_cbe_exchange_rates():
    result = fetch_cbe_exchange_rates()
    return jsonify(result)

@app.route('/')
def index():
    return "Welcome to the Exchange Rate API! Use /cbe-exchange-rates or /boa-exchange-rates to get data."

if __name__ == "__main__":
    # You can pass a specific date or leave it empty for today
   # fetch_cbe_exchange_rates()
    app.run(host='0.0.0.0', port=5000, debug=True)