# === IMPORTS ET CONFIGURATION ===
from dotenv import load_dotenv
import os, time, hmac, hashlib, json, threading
from datetime import datetime, timedelta
import requests
from binance.client import Client
from binance.enums import *

load_dotenv()

# === VARIABLES D'ENVIRONNEMENT ===
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === CONFIGURATION CLIENT BINANCE TESTNET ===
binance_client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
binance_client.API_URL = 'https://testnet.binance.vision/api'  # Utilisation du testnet Binance

# === CONSTANTES DE STRATÉGIE ===
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
ORDER_SIZE = 10  # montant en USDT à investir par ordre
TAKE_PROFIT = 0.02  # 2 %
STOP_LOSS = -0.01   # -1 %
SPREAD_THRESHOLD = 0.003  # 0.3 %
POSITIONS_FILE = "positions.json"
LOG_FILE = "log.txt"

# === VARIABLES GLOBALES ===
bot_active = True
total_profit = 0
total_trades = 0

# === OUTILS ===
def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.utcnow()} | {msg}\n")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        requests.post(url, data=data)
    except Exception as e:
        log(f"Erreur Telegram: {e}")

def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_positions(data):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(data, f)

# === BYBIT ===
def sign_bybit(params):
    query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(BYBIT_API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()

def get_bybit_price(symbol):
    try:
        r = requests.get(f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}").json()
        return float(r['result']['list'][0]['lastPrice'])
    except Exception as e:
        log(f"Erreur get_bybit_price {symbol}: {e}")
        return None

def order_bybit(symbol, side, qty):
    url = "https://api.bybit.com/v5/order/create"
    params = {
        "apiKey": BYBIT_API_KEY,
        "symbol": symbol,
        "category": "spot",
        "side": side.upper(),
        "orderType": "Market",
        "qty": qty,
        "timestamp": int(time.time() * 1000)
    }
    params["sign"] = sign_bybit(params)
    try:
        r = requests.post(url, json=params)
        return r.json()
    except Exception as e:
        log(f"Erreur order_bybit {symbol} {side}: {e}")
        return None

# === BINANCE ===
def get_binance_price(symbol):
    try:
        return float(binance_client.get_symbol_ticker(symbol=symbol)["price"])
    except Exception as e:
        log(f"Erreur get_binance_price {symbol}: {e}")
        return None

def order_binance(symbol, side, qty):
    try:
        side_enum = SIDE_BUY if side.lower() == "buy" else SIDE_SELL
        return binance_client.order_market(symbol=symbol, side=side_enum, quantity=qty)
    except Exception as e:
        log(f"Erreur order_binance {symbol} {side}: {e}")
        return None

# === STRATÉGIE ===
def trading_cycle():
    global total_profit, total_trades
    positions = load_positions()

    for symbol in SYMBOLS:
        try:
            price_binance = get_binance_price(symbol)
            price_bybit = get_bybit_price(symbol)

            if price_binance is None or price_bybit is None:
                continue  # Skip if we can't get prices

            spread = abs(price_binance - price_bybit) / min(price_binance, price_bybit)

            if spread < SPREAD_THRESHOLD:
                continue  # Skip if spread too low

            qty_b = round(ORDER_SIZE / price_binance, 5)
            qty_y = round(ORDER_SIZE / price_bybit, 5)

            # Passer les ordres et gérer les positions sur chaque plateforme
            for exchange, price, qty, order_func in [
                ("binance", price_binance, qty_b, order_binance),
                ("bybit", price_bybit, qty_y, order_bybit)
            ]:
                key = f"{exchange}_{symbol}"
                if key in positions:
                    entry = positions[key]
                    change = (price - entry['buy_price']) / entry['buy_price']
                    if change >= TAKE_PROFIT:
                        order_func(symbol, "Sell", entry['qty'])
                        send_telegram(f"✅ Vente {symbol} ({exchange}) à {price}")
                        profit = (price - entry['buy_price']) * entry['qty']
                        total_profit += profit
                        total_trades += 1
                        del positions[key]
                    elif change <= STOP_LOSS:
                        order_func(symbol, "Sell", entry['qty'])
                        send_telegram(f"❌ Stop-Loss {symbol} ({exchange}) à {price}")
                        loss = (price - entry['buy_price']) * entry['qty']
                        total_profit += loss
                        total_trades += 1
                        del positions[key]
                else:
                    order_func(symbol, "Buy", qty)
                    positions[key] = {"buy_price": price, "qty": qty}
                    send_telegram(f"🟢 Achat {symbol} ({exchange}) à {price}")

        except Exception as e:
            send_telegram(f"[{symbol}] ⚠️ Erreur : {e}")
            log(f"{symbol} error: {e}")

    save_positions(positions)

# === RAPPORT QUOTIDIEN ===
def daily_report():
    global total_profit, total_trades
    while True:
        now = datetime.now()
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        time.sleep((midnight - now).seconds)
        roi = (total_profit / 100) * 100 if total_trades > 0 else 0
        send_telegram(f"📊 Rapport quotidien\nTrades: {total_trades}\nProfit: {total_profit:.2f} USDT\nROI: {roi:.2f}%")
        total_profit = 0
        total_trades = 0

# === COMMANDES TELEGRAM ===
def listen_telegram():
    global bot_active
    offset = None
    while True:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        if offset:
            url += f"?offset={offset}"
        try:
            resp = requests.get(url).json()
            for update in resp.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message", {}).get("text", "").lower()
                if msg == "/stop":
                    bot_active = False
                    send_telegram("⛔ Bot arrêté.")
                elif msg == "/start":
                    bot_active = True
                    send_telegram("▶️ Bot redémarré.")
                elif msg == "/status":
                    send_telegram(f"🤖 Status: {'Actif' if bot_active else 'Inactif'}\nTrades: {total_trades}\nProfit: {total_profit:.2f} USDT")
                elif msg == "/balance":
                    bal = binance_client.get_asset_balance(asset="USDT")
                    send_telegram(f"💰 Solde Binance (USDT): {bal['free']}")
        except Exception as e:
            log(f"Erreur Telegram listen: {e}")
        time.sleep(5)

# === DÉMARRAGE ===
if __name__ == "__main__":
    send_telegram("🚀 Bot Binance+Bybit (Testnet) lancé avec succès.")
    threading.Thread(target=daily_report, daemon=True).start()
    threading.Thread(target=listen_telegram, daemon=True).start()

    while True:
        if bot_active:
            trading_cycle()
        time.sleep(300)
