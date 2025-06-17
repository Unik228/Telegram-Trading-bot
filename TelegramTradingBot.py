import os
import time
import json
import hmac
import hashlib
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from threading import Thread

load_dotenv()

# ========== CONFIGURATION ==========
BYBIT_API = os.getenv("BYBIT_API")
BYBIT_SECRET = os.getenv("BYBIT_SECRET")
OKX_API = os.getenv("OKX_API")
OKX_SECRET = os.getenv("OKX_SECRET")
OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE")
KRAKEN_API = os.getenv("KRAKEN_API")
KRAKEN_SECRET = os.getenv("KRAKEN_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ORDER_SIZE = 10
TAKE_PROFIT = 0.02
STOP_LOSS = -0.01
SPREAD_MIN = 0.5  # %

POSITIONS_FILE = "positions.json"
STATS_FILE = "stats.json"
RUNNING = True

# ========== OUTILS ==========
def log(msg):
    with open("log.txt", "a") as f:
        f.write(f"{datetime.now(timezone.utc)} | {msg}\n")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_positions(data):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(data, f)

def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            return json.load(f)
    return {"trades": 0, "profit": 0.0}

def save_stats(data):
    with open(STATS_FILE, "w") as f:
        json.dump(data, f)

# ========== PRIX ==========
def get_bybit_price(symbol):
    r = requests.get(f"https://api.bybit.com/v5/market/tickers?category=spot").json()
    for coin in r['result']['list']:
        if coin['symbol'] == symbol:
            return float(coin['lastPrice'])
    return None

def get_kraken_price(symbol):
    symbol_map = {"BTCUSDT": "XBTUSDT", "ETHUSDT": "ETHUSDT"}
    pair = symbol_map.get(symbol, symbol)
    r = requests.get(f"https://api.kraken.com/0/public/Ticker?pair={pair}").json()
    result = r.get("result", {})
    for data in result.values():
        return float(data["c"][0])
    return None

def get_okx_price(symbol):
    r = requests.get(f"https://www.okx.com/api/v5/market/ticker?instId={symbol}").json()
    return float(r["data"][0]["last"]) if r["data"] else None

# ========== ORDRES SIMULÉS ==========
def fake_order(exchange, symbol, side, qty, price):
    msg = f"{side} {symbol} sur {exchange} à {price}"
    log(msg)
    send_telegram(msg)
    return True

# ========== STRATÉGIE ==========
def trade_cycle():
    global RUNNING
    positions = load_positions()
    stats = load_stats()

    SYMBOLS = ["BTCUSDT", "ETHUSDT"]

    for symbol in SYMBOLS:
        if not RUNNING:
            break

        try:
            price_bybit = get_bybit_price(symbol)
            price_kraken = get_kraken_price(symbol)
            price_okx = get_okx_price(symbol)

            prices = {
                "bybit": price_bybit,
                "kraken": price_kraken,
                "okx": price_okx,
            }

            # Stratégie d'achat sur la plateforme la moins chère
            best_buy = min(prices.items(), key=lambda x: x[1] if x[1] else float('inf'))
            best_sell = max(prices.items(), key=lambda x: x[1] if x[1] else float('-inf'))

            spread = ((best_sell[1] - best_buy[1]) / best_buy[1]) * 100
            if spread < SPREAD_MIN:
                continue  # Pas de spread suffisant

            key = f"{symbol}"
            if key not in positions:
                qty = round(ORDER_SIZE / best_buy[1], 5)
                fake_order(best_buy[0], symbol, "BUY", qty, best_buy[1])
                positions[key] = {
                    "buy_price": best_buy[1],
                    "qty": qty,
                    "buy_exchange": best_buy[0],
                    "sell_exchange": best_sell[0],
                }
            else:
                change = (best_sell[1] - positions[key]['buy_price']) / positions[key]['buy_price']
                if change >= TAKE_PROFIT or change <= STOP_LOSS:
                    fake_order(positions[key]['sell_exchange'], symbol, "SELL", positions[key]["qty"], best_sell[1])
                    profit = (best_sell[1] - positions[key]['buy_price']) * positions[key]['qty']
                    stats["trades"] += 1
                    stats["profit"] += profit
                    del positions[key]

        except Exception as e:
            log(f"{symbol} erreur: {str(e)}")
            send_telegram(f"⚠️ Erreur sur {symbol}: {str(e)}")

    save_positions(positions)
    save_stats(stats)

# ========== TÂCHES ==========

def loop_trading():
    while True:
        if RUNNING:
            trade_cycle()
        time.sleep(300)  # 5 min

def daily_report():
    while True:
        now = datetime.now()
        next_run = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        time.sleep((next_run - now).seconds)
        stats = load_stats()
        msg = f"📊 Rapport quotidien :\nTrades: {stats['trades']}\nProfit net: {stats['profit']:.2f} USD"
        send_telegram(msg)
        save_stats({"trades": 0, "profit": 0.0})

# ========== COMMANDES TELEGRAM ==========
def telegram_commands():
    global RUNNING
    offset = None
    while True:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        if offset:
            url += f"?offset={offset}"
        res = requests.get(url).json()
        for update in res.get("result", []):
            offset = update["update_id"] + 1
            cmd = update["message"]["text"]
            if cmd == "/start":
                RUNNING = True
                send_telegram("▶️ Trading relancé.")
            elif cmd == "/stop":
                RUNNING = False
                send_telegram("⏸️ Trading en pause.")
            elif cmd == "/status":
                send_telegram("✅ Le bot fonctionne." if RUNNING else "⛔ Le bot est en pause.")
            elif cmd == "/balance":
                stats = load_stats()
                send_telegram(f"💼 Profit: {stats['profit']:.2f} USD | Trades: {stats['trades']}")
        time.sleep(5)

# ========== MAIN ==========
if __name__ == "__main__":
    send_telegram("🤖 Bot multi-exchange lancé.")
    Thread(target=loop_trading).start()
    Thread(target=daily_report).start()
    Thread(target=telegram_commands).start()
