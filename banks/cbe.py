import json
import logging
from datetime import datetime, timezone, timedelta
import requests
logger = logging.getLogger(__name__)


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
        logger.info("Fetching CBE exchange rates for date: %s", target_date)
        response = requests.get(url, headers=headers, params=params, cookies=cookies)
        response.raise_for_status()  # Raise exception for bad status codes
        
        data = response.json()

        if not data:
            print(f"Current day exchange rates not available for {target_date}, trying previous day.")
            previous_date = (datetime.strptime(target_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
            return fetch_cbe_exchange_rates(previous_date)

        # Extract the main record (since _limit=1, it's the first item in the list)
        main_record = data[0]
        rates = main_record.get('ExchangeRate', [])

        logger.info("CBE Daily Exchange Rates - Date: %s", main_record.get('Date'))
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

        if not cleaned_rates:
            print(f"Current day exchange rates not available for {target_date}, trying previous day.")
            previous_date = (datetime.strptime(target_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
            return fetch_cbe_exchange_rates(previous_date)

        logger.info("Successfully fetched %d currencies from CBE", len(cleaned_rates))
        return cleaned_rates

    except requests.exceptions.RequestException as e:
        logger.error("Error fetching CBE data: %s", e)
    except (KeyError, IndexError) as e:
        logger.error("Error parsing CBE JSON structure: %s", e)

if __name__ == "__main__":
    rates = fetch_cbe_exchange_rates()
    print(json.dumps(rates, indent=2))