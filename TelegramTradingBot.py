# ========== Partie 1 : Imports, configuration et outils utilitaires ==========

import os
import json
import time
import hmac
import hashlib
import requests
import schedule
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from datetime import datetime
from dotenv import load_dotenv

# Chargement des variables d'environnement
load_dotenv()

# ========== Clés API ==========
BYBIT_API = os.getenv("BYBIT_API")
BYBIT_SECRET = os.getenv("BYBIT_SECRET")
OKX_API = os.getenv("OKX_API")
OKX_SECRET = os.getenv("OKX_SECRET")
OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE")
KRAKEN_API = os.getenv("KRAKEN_API")
KRAKEN_SECRET = os.getenv("KRAKEN_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ========== Paramètres ==========
CAPITAL = 100
TAKE_PROFIT = 0.03
STOP_LOSS = -0.015
SPREAD_THRESHOLD = 0.5  # 0.5% spread minimum pour arbitrage
ORDER_SIZE = 10  # USD

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]

POSITIONS_FILE = "positions.json"
LOG_FILE = "log.txt"

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.now().isoformat()} | {msg}\n")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=data)
    except:
        pass
# ========== Partie 2 : Connexion aux exchanges et récupération des prix ==========

def get_price_bybit(symbol):
    try:
        url = "https://api.bybit.com/v5/market/tickers?category=spot"
        res = requests.get(url)
        if res.status_code != 200 or not res.text.strip():
            log(f"❌ EMPTY or BAD RESPONSE from BYBIT for {symbol} → Status: {res.status_code}")
            return 0
        data = res.json()
        for ticker in data['result']['list']:
            if ticker['symbol'] == symbol:
                return float(ticker['lastPrice'])
        log(f"⚠️ Symbol {symbol} not found in BYBIT response")
        return 0
    except Exception as e:
        log(f"BYBIT error for {symbol}: {e}")
        return 0

def get_price_okx(symbol):
    try:
        url = f"https://www.okx.com/api/v5/market/ticker?instId={symbol}"
        res = requests.get(url)
        if res.status_code != 200 or not res.text.strip():
            log(f"❌ EMPTY or BAD RESPONSE from OKX for {symbol} → Status: {res.status_code}")
            return 0
        data = res.json()
        return float(data['data'][0]['last']) if 'data' in data and data['data'] else 0
    except Exception as e:
        log(f"OKX error for {symbol}: {e}")
        return 0

def get_price_kraken(symbol):
    try:
        if symbol == "BTCUSDT":
            symbol = "XBTUSDT"
        pair_code = symbol.replace("USDT", "ZUSD")
        url = f"https://api.kraken.com/0/public/Ticker?pair={pair_code}"
        res = requests.get(url)
        if res.status_code != 200 or not res.text.strip():
            log(f"❌ EMPTY or BAD RESPONSE from KRAKEN for {symbol} → Status: {res.status_code}")
            return 0
        data = res.json()
        pair = list(data['result'].keys())[0]
        return float(data['result'][pair]['c'][0])
    except Exception as e:
        log(f"KRAKEN error for {symbol}: {e}")
        return 0

# -------- Calcul Spread --------
def check_spread_and_decide(symbol):
    bybit_price = get_bybit_price(symbol)
    okx_price = get_okx_price(symbol)
    kraken_price = get_kraken_price(symbol)

    if not all([bybit_price, okx_price, kraken_price]):
        return

    prices = {"Bybit": bybit_price, "OKX": okx_price, "Kraken": kraken_price}
    max_exchange = max(prices, key=prices.get)
    min_exchange = min(prices, key=prices.get)

    spread = (prices[max_exchange] - prices[min_exchange]) / prices[min_exchange] * 100

    if spread >= SPREAD_THRESHOLD:
        send_telegram(f"📈 Spread détecté {spread:.2f}% sur {symbol} entre {min_exchange} et {max_exchange}")
        log(f"Spread {spread:.2f}% | Buy: {min_exchange} @ {prices[min_exchange]} | Sell: {max_exchange} @ {prices[max_exchange]}")
        # Ajoute ici : place_trade(min_exchange, max_exchange, symbol)
    else:
        log(f"Spread insuffisant ({spread:.2f}%) pour {symbol}")
        
# ========== Partie 3 : Trading simulé et reporting ==========

def get_signal(symbol):
    # Récupération des prix sur chaque exchange
    price_bybit = get_price_bybit(symbol)
    price_okx = get_price_okx(symbol.replace("USDT", "-USDT"))
    price_kraken = get_price_kraken(symbol)

    # Ajout de logs pour vérifier les valeurs
    log(f"[SIGNAL CHECK] {symbol} - Bybit: {price_bybit} | OKX: {price_okx} | Kraken: {price_kraken}")

    # Vérification des données valides
    if not all([price_bybit, price_okx, price_kraken]):
        log(f"❌ Données incomplètes ou incorrectes pour {symbol}.")
        return None

    prices = [price_bybit, price_okx, price_kraken]
    max_price = max(prices)
    min_price = min(prices)

    # Seuil de déclenchement d'arbitrage : 0.5% d'écart
    spread = (max_price - min_price) / min_price
    if spread >= 0.005:
        log(f"✅ Opportunité détectée sur {symbol} (Spread: {spread*100:.2f}%)")
        return {"symbol": symbol, "spread": spread, "buy": min_price, "sell": max_price}
    else:
        log(f"🔍 Pas d'opportunité significative sur {symbol} (Spread: {spread*100:.2f}%)")
        return None


# 🔍 TESTS RAPIDES POUR DEBUG
if __name__ == "__main__":
    test_symbol = "BTCUSDT"
    print("🧪 TEST DE RÉCUPÉRATION DES PRIX EN TEMPS RÉEL")
    print(f"Bybit ({test_symbol}): {get_price_bybit(test_symbol)}")
    print(f"OKX ({test_symbol.replace('USDT', '-USDT')}): {get_price_okx(test_symbol.replace('USDT', '-USDT'))}")
    print(f"Kraken ({test_symbol}): {get_price_kraken(test_symbol)}")

    print("\n🧪 TEST DE SIGNAL")
    signal = get_signal(test_symbol)
    if signal:
        print(f"📊 SIGNAL: {signal}")
    else:
        print("⚠️ Aucun signal généré.")

# ========== Partie 4 : Commandes Telegram ==========

@bot.message_handler(commands=['balance'])
def balance(msg):
    roi = (capital - STARTING_CAPITAL) / STARTING_CAPITAL * 100
    bot.reply_to(msg, f"💼 Capital actuel: {capital:.2f} USDT\n📊 ROI: {roi:.2f}%")

@bot.message_handler(commands=['status'])
def status(msg):
    state = "🟢 En marche" if is_running else "🔴 En pause"
    bot.reply_to(msg, f"🤖 Statut du bot : {state}")

@bot.message_handler(commands=['stop'])
def stop(msg):
    global is_running
    is_running = False
    bot.reply_to(msg, "⛔ Bot mis en pause.")

@bot.message_handler(commands=['start'])
def start(msg):
    global is_running
    is_running = True
    bot.reply_to(msg, "✅ Bot relancé.")

# Thread du bot Telegram
telegram_thread = threading.Thread(target=lambda: bot.infinity_polling(), daemon=True)
telegram_thread.start()

# Thread du rapport quotidien
report_thread = threading.Thread(target=schedule_daily_report, daemon=True)
report_thread.start()
# ========== Partie 4 : Boucle principale de trading ==========

MIN_SPREAD_PERCENT = 0.4  # seuil minimum de spread pour déclencher un trade
TRADE_INTERVAL = 300      # secondes entre chaque cycle de scan (5 minutes)

def get_all_symbols_bybit():
    try:
        url = "https://api.bybit.com/v5/market/instruments-info?category=spot"
        response = requests.get(url).json()
        return [s['symbol'] for s in response['result']['list']]
    except:
        return []

def get_all_symbols_okx():
    try:
        url = "https://www.okx.com/api/v5/public/instruments?instType=SPOT"
        response = requests.get(url).json()
        return [s['instId'] for s in response['data']]
    except:
        return []

def get_all_symbols_kraken():
    try:
        url = "https://api.kraken.com/0/public/AssetPairs"
        response = requests.get(url).json()
        return [k for k in response['result'].keys() if k.endswith("USDT")]
    except:
        return []

def loop_trading():
    global is_running

    while True:
        if not is_running:
            time.sleep(5)
            continue

        all_symbols = set(get_all_symbols_bybit()) | set(get_all_symbols_okx()) | set(get_all_symbols_kraken())

        for symbol in all_symbols:
            try:
                price_bybit = get_price_bybit(symbol)
                price_okx = get_price_okx(symbol)
                price_kraken = get_price_kraken(symbol)

                best_buy = min([p for p in [price_bybit, price_okx, price_kraken] if p > 0])
                best_sell = max([p for p in [price_bybit, price_okx, price_kraken] if p > 0])

                if best_buy == 0:
                    continue

                spread = ((best_sell - best_buy) / best_buy) * 100

                if spread >= MIN_SPREAD_PERCENT:
                    simulate_trade(symbol, buy_price=best_buy, sell_price=best_sell)

            except Exception as e:
                send_telegram(f"⚠️ Erreur sur {symbol}: {e}")
                log(f"Erreur {symbol}: {e}")
                continue

        time.sleep(TRADE_INTERVAL)

# Lancer la boucle principale
loop_trading()
