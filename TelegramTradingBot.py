# main.py

import os, time, hmac, hashlib, base64, json, logging, threading, urllib.parse, requests
from datetime import datetime, timedelta
from collections import deque
from dotenv import load_dotenv

# ─ Setup
load_dotenv()
logging.basicConfig(filename="bot.log", level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s")

BYBIT_KEY, BYBIT_SECRET = os.getenv("BYBIT_API"), os.getenv("BYBIT_SECRET")
OKX_KEY, OKX_SECRET, OKX_PASSPHRASE = os.getenv("OKX_API"), os.getenv("OKX_SECRET"), os.getenv("OKX_PASSPHRASE")
KRAKEN_KEY, KRAKEN_SECRET = os.getenv("KRAKEN_API"), os.getenv("KRAKEN_SECRET")
TG_TOKEN, TG_CHAT = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")

ORDER_SIZE = 10
SPREAD_THRESHOLD = 0.5
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
LOOP_INTERVAL = 300

price_hist = {"BTCUSDT": deque(maxlen=MACD_SLOW + MACD_SIGNAL)}
capital = 100
trades = []
running = True

# ─ Telegram
def send_telegram(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      data={"chat_id": TG_CHAT, "text": msg}, timeout=5)
    except Exception as e:
        logging.error(f"Telegram: {e}")

# ─ Bybit price & trade
def sign_bybit(method, path, params):
    ts = str(int(time.time()*1000))
    prefix = ts + BYBIT_KEY + "5000" + (urllib.parse.urlencode(sorted(params.items())) if method=="GET" else json.dumps(params, separators=(",",":")))
    sig = hmac.new(BYBIT_SECRET.encode(), prefix.encode(), hashlib.sha256).hexdigest()
    return ts, sig

def price_bybit(sym):
    try:
        resp = requests.get("https://api.bybit.com/v5/market/tickers?category=spot", timeout=5)
        for it in resp.json().get("result", {}).get("list", []):
            if it["symbol"] == sym: return float(it["lastPrice"])
    except Exception as e:
        logging.error(f"Bybit price: {e}")
    return 0

def place_bybit(sym, side, qty):
    path, method = "/v5/order/create", "POST"
    body = {"category":"spot","symbol":sym,"side":side,"orderType":"Market","qty":qty}
    ts, sig = sign_bybit(method, path, body)
    h = {"Content-Type":"application/json","X-BAPI-API-KEY":BYBIT_KEY,"X-BAPI-TIMESTAMP":ts,
         "X-BAPI-RECV-WINDOW":"5000","X-BAPI-SIGN":sig}
    try:
        r = requests.post("https://api.bybit.com"+path, headers=h, json=body, timeout=10)
        r.raise_for_status()
        send_telegram(f"✅ Bybit executed {side} {sym} qty={qty}")
    except Exception as e:
        logging.error(f"Bybit trade: {e}")

# ─ OKX price & trade
def sign_okx(method, path, body=""):
    ts = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z')
    pre = ts + method + path + (json.dumps(body) if body else "")
    sig = base64.b64encode(hmac.new(OKX_SECRET.encode(), pre.encode(), hashlib.sha256).digest()).decode()
    return ts, sig

def price_okx(sym):
    try:
        inst = sym[:-4] + "-USDT"
        r = requests.get(f"https://www.okx.com/api/v5/market/ticker?instId={inst}", timeout=5).json()
        return float(r["data"][0]["last"])
    except Exception as e:
        logging.error(f"OKX price: {e}")
    return 0

def place_okx(sym, side, sz):
    path, method = "/api/v5/trade/order", "POST"
    body = {"instId":sym[:-4]+"-USDT","tdMode":"cash","side":side,"ordType":"market","sz":str(sz)}
    ts, sig = sign_okx(method, path, body)
    h = {"Content-Type":"application/json","OK-ACCESS-KEY":OKX_KEY,
         "OK-ACCESS-SIGN":sig,"OK-ACCESS-TIMESTAMP":ts,"OK-ACCESS-PASSPHRASE":OKX_PASSPHRASE}
    try:
        r = requests.post("https://www.okx.com"+path, headers=h, json=body, timeout=10)
        r.raise_for_status()
        send_telegram(f"✅ OKX executed {side} {body['instId']} sz={sz}")
    except Exception as e:
        logging.error(f"OKX trade: {e}")

# ─ Kraken price (no execution here)
def kraken_request(path, data):
    try:
        url = "https://api.kraken.com"+path
        nonce = str(int(time.time()*1000))
        d = {"nonce":nonce, **data}
        post = urllib.parse.urlencode(d)
        sig = hmac.new(base64.b64decode(KRAKEN_SECRET),
                       path.encode()+hashlib.sha256((nonce+post).encode()).digest(),
                       hashlib.sha512).digest()
        h = {"API-Key":KRAKEN_KEY,"API-Sign":base64.b64encode(sig).decode()}
        r = requests.post(url, headers=h, data=d, timeout=5)
        return r.json()
    except Exception as e:
        logging.error(f"Kraken req: {e}")
    return {}

def price_kraken(sym):
    mapping = {"BTCUSDT":"XBTUSDT","ETHUSDT":"ETHUSDT","SOLUSDT":"SOLUSDT"}
    pair = mapping.get(sym)
    if not pair: return 0
    r = kraken_request("/0/public/Ticker", {"pair":pair})
    try:
        return float(list(r.get("result", {}).values())[0]["c"][0])
    except:
        return 0

# ─ Indicators
def compute_rsi(prices):
    gains = sum(max(prices[i]-prices[i-1],0) for i in range(1,len(prices)))
    losses = sum(max(prices[i-1]-prices[i],0) for i in range(1,len(prices)))
    avg_gain = gains/(len(prices)-1)
    avg_loss = losses/(len(prices)-1)
    if avg_loss==0: return 100
    rs = avg_gain/avg_loss
    return 100 - (100/(1+rs))

def compute_macd(prices):
    def ema(p,n):
        k = 2/(n+1)
        e = p[0]
        for price in p[1:]: e = price*k + e*(1-k)
        return e
    fast = ema(prices, MACD_FAST)
    slow = ema(prices, MACD_SLOW)
    macd_line = fast - slow
    signal = ema([macd_line], MACD_SIGNAL)
    return macd_line, signal

# ─ Strategy
def try_trade(symbol):
    prices = {"Bybit":price_bybit(symbol),"OKX":price_okx(symbol),"Kraken":price_kraken(symbol)}
    if 0 in prices.values(): return
    buy_ex = min(prices, key=prices.get); sell_ex = max(prices, key=prices.get)
    spread = (prices[sell_ex]-prices[buy_ex])/prices[buy_ex]*100
    price_hist[symbol].append(prices[buy_ex])
    if spread>=SPREAD_THRESHOLD and len(price_hist[symbol])>=RSI_PERIOD:
        rsi = compute_rsi(list(price_hist[symbol]))
        macd_line, macd_signal = compute_macd(list(price_hist[symbol]))
        if rsi<30 and macd_line>macd_signal:
            send_telegram(f"🔥 SIGNAL {symbol}: BUY on {buy_ex} at {prices[buy_ex]:.2f}, SELL on {sell_ex} at {prices[sell_ex]:.2f}")
            qty = ORDER_SIZE/prices[buy_ex]
            if buy_ex=="Bybit": place_bybit(symbol,"Buy",round(qty,6))
            if buy_ex=="OKX": place_okx(symbol,"buy",qty)

# ─ Main loop
def run_loop():
    while True:
        if running: try_trade("BTCUSDT")
        time.sleep(LOOP_INTERVAL)

# ─ Telegram listener
def tg_loop():
    off=None
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",params={"offset":off},timeout=5).json()
            for u in r.get("result",[]):
                off=u["update_id"]+1
                t = u["message"]["text"]
                if t=="/start": set_running(True)
                if t=="/stop": set_running(False)
                if t=="/status": send_telegram("🟢 Running" if running else "🔴 Paused")
                if t=="/balance": send_telegram(f"💰 Balance: {capital:.2f} | Trades executed")
        except Exception as e:
            logging.error(f"TG loop: {e}")
        time.sleep(2)

def set_running(val):
    global running
    running=val
    send_telegram("▶️ Bot resumed" if val else "⛔ Bot paused")

# ─ Daily report
def daily_report():
    while True:
        now = datetime.utcnow()
        nxt = (now+timedelta(days=1)).replace(hour=0,minute=0,second=0)
        time.sleep((nxt-now).total_seconds())
        send_telegram(f"📊 Daily report executed")

# ─ Start
if __name__=="__main__":
    send_telegram("🤖 CryptoSentinel Signal+Trade Bot started")
    threading.Thread(target=run_loop,daemon=True).start()
    threading.Thread(target=tg_loop,daemon=True).start()
    threading.Thread(target=daily_report,daemon=True).start()
    while True: time.sleep(60)
