import json
import logging
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify

from banks.awash import get_awash_rates
from banks.boa import scrape_boa_exchange_rates
from banks.cbe import fetch_cbe_exchange_rates
from banks.coop import scrape_coop_exchange_rates
from banks.dashen import fetch_dashen_exchange_rates
from banks.hibret import scrape_hibret_exchange_rates
from banks.nib import scrape_nib_rates
from banks.wegagen import get_wegagen_rates

# Configure logging once here for the whole application.
# All loggers in sub-modules (banks/*.py) will inherit this config.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)



@app.route('/dashen-exchange-rates', methods=['GET'])
def get_dashen_exchange_rates():
    result = fetch_dashen_exchange_rates()
    return json.loads(result)

@app.route('/boa-exchange-rates', methods=['GET'])
def get_boa_exchange_rates():
    result = scrape_boa_exchange_rates()
    return result

@app.route('/cbe-exchange-rates', methods=['GET'])
def get_cbe_exchange_rates():
    result = fetch_cbe_exchange_rates()
    return result

@app.route('/coop-exchange-rates', methods=['GET'])
def get_coop_exchange_rates():
    result = scrape_coop_exchange_rates()
    return result

@app.route('/hibret-exchange-rates', methods=['GET'])
def get_hibret_exchange_rates():
    result = scrape_hibret_exchange_rates()
    if "error" in result:
        logger.error("Hibret endpoint returning error: %s", result["error"])
        return {"error": "Failed to fetch Hibret Bank exchange rates"}, 500
    return result

@app.route('/wegagen-exchange-rates', methods=['GET'])
def get_wegagen_exchange_rates():
    result = get_wegagen_rates()
    if "error" in result:
        logger.error("Wegagen endpoint returning error: %s", result["error"])
        return {"error": "Failed to fetch Wegagen Bank exchange rates"}, 500
    return result

# awash
@app.route('/awash-exchange-rates', methods=['GET'])
def get_awash_exchange_rates():
    result = get_awash_rates()
    if "error" in result:
        logger.error("Awash endpoint returning error: %s", result["error"])
        return {"error": "Failed to fetch Awash Bank exchange rates"}, 500
    return result

@app.route('/nib-exchange-rates', methods=['GET'])
def get_nib_exchange_rates():
    result = scrape_nib_rates()
    if "error" in result:
        logger.error("NIB endpoint returning error: %s", result["error"])
        return {"error": "Failed to fetch NIB Bank exchange rates"}, 500
    return result

@app.route('/')
def index():
    return """
    <h1>Welcome to the Ethiopian Bank Exchange Rates API</h1>
    <p>Available endpoints:</p>
    <ul>
        <li><a href="/cbe-exchange-rates">/cbe-exchange-rates</a> - Fetches exchange rates from CBE API</li>
        <li><a href="/boa-exchange-rates">/boa-exchange-rates</a> - Scrapes exchange rates from Bank of Abyssinia</li>
        <li><a href="/coop-exchange-rates">/coop-exchange-rates</a> - Scrapes exchange rates from Cooperative Bank of Oromia</li>
        <li><a href="/dashen-exchange-rates">/dashen-exchange-rates</a> - Scrapes exchange rates from Dashen Bank</li>
        <li><a href="/hibret-exchange-rates">/hibret-exchange-rates</a> - Scrapes exchange rates from Hibret Bank</li>
        <li><a href="/wegagen-exchange-rates">/wegagen-exchange-rates</a> - Fetches exchange rates from Wegagen</li>
        <li><a href="/awash-exchange-rates">/awash-exchange-rates</a> - Fetches exchange rates from Awash Bank</li>
        <li><a href="/nib-exchange-rates">/nib-exchange-rates</a> - Scrapes exchange rates from NIB Bank</li>
    </ul>
    """, 200

if __name__ == "__main__":
    # You can pass a specific date or leave it empty for today
   # fetch_cbe_exchange_rates()
    app.run(host='0.0.0.0', port=5000, debug=True)