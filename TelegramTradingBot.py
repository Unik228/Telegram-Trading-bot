from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")

message = "Bot démarré"  # exemple de message de log

with open("log.txt", "a") as f:
    f.write(f"{datetime.utcnow()} | {message}\n")

import time
import hmac
import hashlib
import requests
import json

from binance.client import Client
from binance.enums import *


# ========== CONFIGURATION ==========
import os
from dotenv import load_dotenv

load_dotenv()

binance_api_key = os.getenv("BINANCE_API_KEY")
binance_secret = os.getenv("BINANCE_SECRET_KEY")
bybit_api_key = os.getenv("BYBIT_API_KEY")
bybit_secret = os.getenv("BYBIT_SECRET_KEY")
telegram_token = os.getenv("TELEGRAM_TOKEN")


# Trading
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TAKE_PROFIT = 0.02
STOP_LOSS = -0.01
ORDER_SIZE = 10  # USD

# Fichiers
POSITIONS_FILE = "positions.json"
LOG_FILE = "log.txt"

# ========== OUTILS ==========
def log(message):
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.utcnow()} | {message}\n")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, data=data)

def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_positions(data):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(data, f)

# ========== BYBIT ==========
def sign_bybit(params):
    query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(BYBIT_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()

def get_bybit_price(symbol):
    r = requests.get(f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}").json()
    return float(r['result']['list'][0]['lastPrice'])

def order_bybit(symbol, side, qty):
    url = "https://api.bybit.com/v5/order/create"
    params = {
        "apiKey": BYBIT_API,
        "symbol": symbol,
        "category": "spot",
        "side": side,
        "orderType": "Market",
        "qty": qty,
        "timestamp": int(time.time() * 1000)
    }
    params["sign"] = sign_bybit(params)
    r = requests.post(url, json=params).json()
    return r

# ========== BINANCE ==========
def get_binance_price(symbol):
    ticker = binance_client.get_symbol_ticker(symbol=symbol)
    return float(ticker["price"])

def order_binance(symbol, side, qty):
    side_enum = SIDE_BUY if side == "Buy" else SIDE_SELL
    return binance_client.order_market(symbol=symbol, side=side_enum, quantity=qty)

# ========== LOGIQUE GÉNÉRALE ==========
def trading_cycle():
    positions = load_positions()

    for symbol in SYMBOLS:
        try:
            # Binance
            price_b = get_binance_price(symbol)
            qty_b = round(ORDER_SIZE / price_b, 5)

            # Bybit
            price_y = get_bybit_price(symbol)
            qty_y = round(ORDER_SIZE / price_y, 5)

            for exchange, price, qty, order_func in [
                ("binance", price_b, qty_b, order_binance),
                ("bybit", price_y, qty_y, order_bybit)
            ]:
                key = f"{exchange}_{symbol}"
                if key in positions:
                    entry = positions[key]
                    change = (price - entry['buy_price']) / entry['buy_price']
                    if change >= TAKE_PROFIT:
                        order_func(symbol, "Sell", entry['qty'])
                        send_telegram(f"✅ Vente {symbol} ({exchange}) à {price}")
                        log(f"Vente {symbol} {exchange} +2%")
                        del positions[key]
                    elif change <= STOP_LOSS:
                        order_func(symbol, "Sell", entry['qty'])
                        send_telegram(f"❌ Stop-Loss {symbol} ({exchange}) à {price}")
                        log(f"Stop-Loss {symbol} {exchange} -1%")
                        del positions[key]
                else:
                    order_func(symbol, "Buy", qty)
                    positions[key] = {"buy_price": price, "qty": qty}
                    send_telegram(f"🟢 Achat {symbol} ({exchange}) à {price}")
                    log(f"Achat {symbol} {exchange} à {price}")

        except Exception as e:
            msg = f"[{symbol}] Erreur : {str(e)}"
            send_telegram(msg)
            log(msg)

    save_positions(positions)

# ========== DÉMARRAGE ==========
if __name__ == "__main__":
    send_telegram("🤖 Bot Trading combiné Binance + Bybit lancé.")
    while True:
        trading_cycle()
        time.sleep(300)  # 05 minutes
