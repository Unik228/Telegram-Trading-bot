import os
import json
import time
import hmac
import hashlib
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from threading import Thread, Event

load_dotenv()

# ========== CLÉS ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_SECRET = os.getenv("BYBIT_API_SECRET")

# ========== PARAMÈTRES ==========
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
ORDER_SIZE = 10  # USD
TAKE_PROFIT = 0.02
STOP_LOSS = -0.01
SPREAD_MINIMUM = 0.005  # 0.5 %
POSITIONS_FILE = "positions_bybit.json"
LOG_FILE = "log_bybit.txt"
CAPITAL_INITIAL = 100

running = True
total_profit = 0
trade_count = 0

# ========== OUTILS ==========
def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.utcnow()} | {msg}\n")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})

def sign_bybit(params):
    query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(BYBIT_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()

def get_price(symbol):
    url = f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}"
    r = requests.get(url).json()
    return float(r['result']['list'][0]['lastPrice'])

def place_order(symbol, side, qty):
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

def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_positions(data):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(data, f)

# ========== FONCTIONS ==========
def trading_cycle():
    global trade_count, total_profit
    positions = load_positions()

    for symbol in SYMBOLS:
        try:
            price = get_price(symbol)
            qty = round(ORDER_SIZE / price, 5)
            key = symbol

            if key in positions:
                entry = positions[key]
                change = (price - entry["buy_price"]) / entry["buy_price"]
                if change >= TAKE_PROFIT:
                    place_order(symbol, "Sell", entry["qty"])
                    profit = change * ORDER_SIZE
                    total_profit += profit
                    trade_count += 1
                    send_telegram(f"✅ Vente {symbol} à {price} (+{change*100:.2f}%)")
                    log(f"TP {symbol} : +{change*100:.2f}%")
                    del positions[key]
                elif change <= STOP_LOSS:
                    place_order(symbol, "Sell", entry["qty"])
                    profit = change * ORDER_SIZE
                    total_profit += profit
                    trade_count += 1
                    send_telegram(f"❌ Stop-Loss {symbol} à {price} ({change*100:.2f}%)")
                    log(f"SL {symbol} : {change*100:.2f}%")
                    del positions[key]
            else:
                spread = (price - price * 0.998) / price
                if spread >= SPREAD_MINIMUM:
                    place_order(symbol, "Buy", qty)
                    positions[key] = {"buy_price": price, "qty": qty}
                    send_telegram(f"🟢 Achat {symbol} à {price}")
                    log(f"Achat {symbol} : {price}")

        except Exception as e:
            send_telegram(f"[{symbol}] Erreur : {str(e)}")
            log(f"Erreur {symbol} : {str(e)}")

    save_positions(positions)

def send_daily_report():
    global total_profit, trade_count
    roi = (total_profit / CAPITAL_INITIAL) * 100
    msg = (
        f"📊 Rapport quotidien\n"
        f"💰 Profit total : {total_profit:.2f} $\n"
        f"📈 Trades : {trade_count}\n"
        f"📊 ROI : {roi:.2f} %"
    )
    send_telegram(msg)
    log(msg)
    total_profit = 0
    trade_count = 0

def wait_until_midnight():
    while True:
        now = datetime.now()
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0)
        time.sleep((midnight - now).total_seconds())
        send_daily_report()

def handle_telegram_commands():
    global running
    last_update_id = None
    while True:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        r = requests.get(url).json()
        updates = r.get("result", [])

        for update in updates:
            if last_update_id is None or update["update_id"] > last_update_id:
                last_update_id = update["update_id"]
                msg = update.get("message", {}).get("text", "")
                chat_id = update.get("message", {}).get("chat", {}).get("id")

                if msg == "/stop":
                    running = False
                    send_telegram("⏹ Bot arrêté.")
                elif msg == "/start":
                    running = True
                    send_telegram("▶️ Bot relancé.")
                elif msg == "/balance":
                    send_telegram(f"💼 Capital initial : {CAPITAL_INITIAL}$")
                elif msg == "/status":
                    send_telegram(f"⏱ Statut du bot : {'✅ En marche' if running else '⛔️ Arrêté'}")

        time.sleep(5)

# ========== DÉMARRAGE ==========
if __name__ == "__main__":
    send_telegram("🤖 Bot Trading Bybit lancé.")
    Thread(target=wait_until_midnight, daemon=True).start()
    Thread(target=handle_telegram_commands, daemon=True).start()

    while True:
        if running:
            trading_cycle()
        time.sleep(300)
