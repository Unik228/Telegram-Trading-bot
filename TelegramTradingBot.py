import os
import json
import time
import hmac
import hashlib
import requests
from datetime import datetime
from threading import Thread
from dotenv import load_dotenv
from binance.client import Client
from binance.enums import *

# ===== CONFIGURATION =====
load_dotenv()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")

binance_client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
binance_client.API_URL = 'https://testnet.binance.vision/api'


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TAKE_PROFIT = 0.02
STOP_LOSS = -0.01
ORDER_SIZE = 10
SPREAD_THRESHOLD = 0.005  # 0.5%
POSITIONS_FILE = "positions.json"
LOG_FILE = "log.txt"
STATE_FILE = "bot_state.json"

capital = 100.0  # capital simulé

# ===== OUTILS =====
def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.utcnow()} | {msg}\n")

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

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"active": True}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# ===== API BYBIT =====
def sign_bybit(params):
    query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(BYBIT_API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()

def get_bybit_price(symbol):
    r = requests.get(f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}").json()
    return float(r['result']['list'][0]['lastPrice'])

def order_bybit(symbol, side, qty):
    url = "https://api.bybit.com/v5/order/create"
    params = {
        "apiKey": BYBIT_API_KEY,
        "symbol": symbol,
        "category": "spot",
        "side": side,
        "orderType": "Market",
        "qty": qty,
        "timestamp": int(time.time() * 1000)
    }
    params["sign"] = sign_bybit(params)
    return requests.post(url, json=params).json()

# ===== API BINANCE =====
def get_binance_price(symbol):
    ticker = binance_client.get_symbol_ticker(symbol=symbol)
    return float(ticker["price"])

def order_binance(symbol, side, qty):
    side_enum = SIDE_BUY if side == "Buy" else SIDE_SELL
    return binance_client.order_market(symbol=symbol, side=side_enum, quantity=qty)

# ===== CYCLE DE TRADING =====
def trading_cycle():
    global capital
    positions = load_positions()

    for symbol in SYMBOLS:
        try:
            price_b = get_binance_price(symbol)
            price_y = get_bybit_price(symbol)
            spread = abs(price_b - price_y) / ((price_b + price_y) / 2)

            if spread < SPREAD_THRESHOLD:
                continue

            qty_b = round(ORDER_SIZE / price_b, 5)
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
                        capital += ORDER_SIZE * TAKE_PROFIT
                        del positions[key]
                    elif change <= STOP_LOSS:
                        order_func(symbol, "Sell", entry['qty'])
                        send_telegram(f"❌ Stop-Loss {symbol} ({exchange}) à {price}")
                        log(f"Stop-Loss {symbol} {exchange} -1%")
                        capital += ORDER_SIZE * STOP_LOSS
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

# ===== RAPPORT QUOTIDIEN =====
def daily_report():
    while True:
        now = datetime.utcnow()
        if now.hour == 0 and now.minute == 0:
            positions = load_positions()
            report = f"📊 Rapport Quotidien\n\nCapital: ${capital:.2f}\nPositions actives: {len(positions)}\nHeure UTC: {now.strftime('%Y-%m-%d %H:%M')}"
            send_telegram(report)
            log("Rapport quotidien envoyé.")
            time.sleep(60)
        else:
            time.sleep(30)

# ===== COMMANDES TELEGRAM =====
def telegram_listener():
    offset = None
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            if offset:
                url += f"?offset={offset + 1}"
            response = requests.get(url).json()

            for update in response.get("result", []):
                offset = update["update_id"]
                msg = update["message"]["text"].strip().lower()

                state = load_state()

                if msg == "/stop":
                    state["active"] = False
                    send_telegram("⛔ Bot arrêté.")
                elif msg == "/start":
                    state["active"] = True
                    send_telegram("▶️ Bot redémarré.")
                elif msg == "/balance":
                    send_telegram(f"💼 Capital simulé : ${capital:.2f}")
                elif msg == "/status":
                    active = "Actif ✅" if state["active"] else "Inactif ⛔"
                    send_telegram(f"📟 Statut : {active}")

                save_state(state)
        except Exception as e:
            log(f"Erreur Telegram Listener: {e}")
        time.sleep(5)

# ===== MAIN =====
if __name__ == "__main__":
    send_telegram("🤖 Bot Trading combiné Binance + Bybit LANCÉ.")
    Thread(target=telegram_listener, daemon=True).start()
    Thread(target=daily_report, daemon=True).start()

    while True:
        state = load_state()
        if state.get("active"):
            trading_cycle()
        time.sleep(300)
