import os
import time
import hmac
import hashlib
import base64
import json
import requests
import logging
import threading
import schedule
import urllib.parse
from datetime import datetime, timedelta
from dotenv import load_dotenv

# === Config & Logs ===
load_dotenv()
logging.basicConfig(filename="bot.log", level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

# === Globals ===
BYBIT_API_KEY = os.getenv("BYBIT_API")
BYBIT_SECRET = os.getenv("BYBIT_SECRET")
OKX_API_KEY = os.getenv("OKX_API")
OKX_SECRET = os.getenv("OKX_SECRET")
OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE")
KRAKEN_API_KEY = os.getenv("KRAKEN_API")
KRAKEN_SECRET = os.getenv("KRAKEN_SECRET")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

RECV_WINDOW = "5000"
ORDER_SIZE = 10
SPREAD_THRESHOLD = 0.5  # in %
STARTING_CAPITAL = 100
LOOP_INTERVAL = 300  # seconds

capital = STARTING_CAPITAL
trades = []
running = True

# === Telegram ===
def send_telegram(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      data={"chat_id": TG_CHAT_ID, "text": msg}, timeout=5)
    except Exception as e:
        logging.error(f"Telegram error: {e}")

# === Bybit auth & call ===
def sign_bybit(method, path, params):
    ts = str(int(time.time()*1000))
    if method == "GET":
        qs = urllib.parse.urlencode(sorted(params.items()))
        pre = ts + BYBIT_API_KEY + RECV_WINDOW + qs
    else:
        pre = ts + BYBIT_API_KEY + RECV_WINDOW + json.dumps(params, separators=(',',':'))
    sign = hmac.new(BYBIT_SECRET.encode(), pre.encode(), hashlib.sha256).hexdigest()
    return ts, sign

def place_bybit_order(symbol, side, qty):
    path = "/v5/order/create"; method = "POST"
    body = {"category":"spot","symbol":symbol,"side":side,"orderType":"Market","qty":qty}
    ts, sign = sign_bybit(method, path, body)
    h = {"Content-Type":"application/json","X-BAPI-API-KEY":BYBIT_API_KEY,
         "X-BAPI-TIMESTAMP":ts,"X-BAPI-RECV-WINDOW":RECV_WINDOW,"X-BAPI-SIGN":sign}
    try:
        r = requests.post("https://api.bybit.com"+path, headers=h, json=body, timeout=10)
        r.raise_for_status()
        logging.info(f"Bybit {side} {symbol} {qty}")
        return r.json()
    except Exception as e:
        logging.error(f"Bybit order error: {e}")
        send_telegram(f"⚠️ Bybit order error: {e}")
        return None

def get_price_bybit(symbol):
    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers?category=spot", timeout=5)
        if r.status_code != 200 or not r.text.strip():
            raise Exception(f"HTTP {r.status_code}")
        for it in r.json()["result"]["list"]:
            if it["symbol"] == symbol:
                return float(it["lastPrice"])
    except Exception as e:
        logging.error(f"Bybit price {symbol} error: {e}")
    return 0

# === OKX auth & calls ===
def sign_okx(method, path, body=""):
    ts = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z')
    pre = ts + method + path + (json.dumps(body) if body else "")
    sig = base64.b64encode(hmac.new(OKX_SECRET.encode(), pre.encode(), hashlib.sha256).digest()).decode()
    return ts, sig

def get_price_okx(symbol):
    try:
        inst = symbol[:-4] + "-USDT"
        path = f"/api/v5/market/ticker?instId={inst}"
        r = requests.get("https://www.okx.com"+path, timeout=5)
        if r.status_code != 200: raise Exception(r.status_code)
        v = r.json().get("data", [])
        if v: return float(v[0]["last"])
    except Exception as e:
        logging.error(f"OKX price {symbol} error: {e}")
    return 0

# === Kraken auth & calls ===
def kraken_request(path, data):
    try:
        url = "https://api.kraken.com"+path
        nonce = str(int(time.time()*1000))
        d = {"nonce":nonce, **data}
        pd = urllib.parse.urlencode(d)
        msg = path.encode() + hashlib.sha256((nonce+pd).encode()).digest()
        sig = hmac.new(base64.b64decode(KRAKEN_SECRET), msg, hashlib.sha512).digest()
        h = {"API-Key":KRAKEN_API_KEY,"API-Sign":base64.b64encode(sig).decode()}
        r = requests.post(url, headers=h, data=d, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.error(f"Kraken call error: {e}")
    return None

def get_price_kraken(symbol):
    try:
        m = {"BTCUSDT":"XBTUSDT","ETHUSDT":"ETHUSDT","SOLUSDT":"SOLUSDT"}
        p = m.get(symbol)
        j = kraken_request("/0/public/Ticker", {"pair":p})
        if j: return float(list(j["result"].values())[0]["c"][0])
    except Exception as e:
        logging.error(f"Kraken price {symbol} error: {e}")
    return 0

# === Trading / arbitrage logic ===
def simulate(symbol, buy_ex, sell_ex, buy_p, sell_p):
    global capital
    qty = ORDER_SIZE / buy_p
    capital += (sell_p - buy_p) * qty
    trades.append((symbol, buy_ex, sell_ex, buy_p, sell_p))
    send_telegram(f"🎯 Trade: {symbol} | Buy {buy_ex} @ {buy_p:.2f} | Sell {sell_ex} @ {sell_p:.2f}")
    logging.info(f"Trade {symbol} profit: {(sell_p - buy_p)*qty:.2f}")

def cycle():
    global running
    syms = ["BTCUSDT","ETHUSDT","SOLUSDT"]
    for s in syms:
        if not running: break
        p3 = {"Bybit":get_price_bybit(s),"OKX":get_price_okx(s),"Kraken":get_price_kraken(s)}
        if any(p==0 for p in p3.values()): continue
        mn, mx = min(p3, key=p3.get), max(p3, key=p3.get)
        spread = (p3[mx]-p3[mn])/p3[mn]*100
        logging.info(f"{s} spread {spread:.2f}%")
        if spread>=SPREAD_THRESHOLD:
            simulate(s, mn, mx, p3[mn], p3[mx])
    time.sleep(LOOP_INTERVAL)

def run_loop():
    while True:
        if running: cycle()
        else: time.sleep(5)

# === Telegram commands listener ===
def handle_telegram():
    off = None
    while True:
        r = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates", params={"offset":off}, timeout=5).json()
        for u in r.get("result",[]):
            off = u["update_id"]+1
            txt = u["message"]["text"]
            if txt=="/stop": running_flag(False)
            elif txt=="/start": running_flag(True)
            elif txt=="/status": send_telegram("🟢 Running" if running else "🔴 Paused")
            elif txt=="/balance": send_telegram(f"Balance: {capital:.2f} USDT | Trades: {len(trades)}")
        time.sleep(2)

def running_flag(val):
    global running
    running = val
    send_telegram("▶️ Resumed" if val else "⛔ Paused")

# === Daily report ===
def daily_report():
    while True:
        now = datetime.utcnow()
        nxt = (now+timedelta(days=1)).replace(hour=0, minute=0, second=0)
        time.sleep((nxt-now).total_seconds())
        send_telegram(f"📊 Daily: capital={capital:.2f}, trades={len(trades)}")
        # reset trades?
        
# === Startup ===
if __name__=="__main__":
    send_telegram("🤖 Bot démarré multi-exch, arbitrage live")
    threading.Thread(target=run_loop, daemon=True).start()
    threading.Thread(target=handle_telegram, daemon=True).start()
    threading.Thread(target=daily_report, daemon=True).start()
    while True: time.sleep(60)
