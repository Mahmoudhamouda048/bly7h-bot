import os, time, hmac, hashlib, base64, json, threading
import requests

# ==== CONFIG - نفس اساميك ====
MASTER_KEY = os.getenv("BLY7H_MASTAR", "")
MASTER_SECRET = os.getenv("BLY7H_MASTAR_SECRET", "")
MASTER_PASSPHRASE = os.getenv("BLY7H_MASTAR_PASSPHRASE", "")
FOLLOWER_KEY = os.getenv("BLYTH_FOLLIWER") or os.getenv("BLYTH_FOLLIWER") or os.getenv("BLY7H_FOLLIWER") or os.getenv("BLY7H_FOLLIWER") or ""
FOLLOWER_SECRET = os.getenv("BLYTH_FOLLIWER_SECRET") or os.getenv("BLY7H_FOLLIWER_SECRET") or ""
FOLLOWER_PASSPHRASE = os.getenv("BLYTH_FOLLIWER_PASSPHRASE") or os.getenv("BLY7H_FOLLIWER_PASSPHRASE") or ""
COPY_RATIO = float(os.getenv("COPY_RATIO", "2"))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8891837911:AAHxxQ8EGwoFy567hzH1RrzeFxGfzZtS5hc")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")  # هيتملي اوتوماتيك اول رسالة

BASE_URL = "https://api-futures.kucoin.com"

def sign(secret, msg):
    return base64.b64encode(hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()).decode()

def kucoin_request(api_key, api_secret, passphrase, method, path, body=None):
    ts = str(int(time.time()*1000))
    body_str = json.dumps(body) if body else ""
    str_to_sign = ts + method + path + body_str
    headers = {
        "KC-API-KEY": api_key,
        "KC-API-SIGN": sign(api_secret, str_to_sign),
        "KC-API-TIMESTAMP": ts,
        "KC-API-PASSPHRASE": sign(api_secret, passphrase),
        "KC-API-KEY-VERSION": "2",
        "Content-Type": "application/json"
    }
    r = requests.request(method, BASE_URL+path, headers=headers, data=body_str if body else None, timeout=20)
    j = r.json()
    if j.get("code") != "200000":
        raise Exception(f"{j}")
    return j

def get_positions(api_key, secret, passphrase):
    try:
        data = kucoin_request(api_key, secret, passphrase, "GET", "/api/v1/positions")
        return [p for p in data.get("data", []) if float(p.get("currentQty", 0)) != 0]
    except Exception as e:
        return f"ERROR: {e}"

def copy_trade():
    if not MASTER_KEY or not FOLLOWER_KEY:
        return "❌ لسه محطتش مفاتيح KuCoin في المتغيرات"
    
    master = get_positions(MASTER_KEY, MASTER_SECRET, MASTER_PASSPHRASE)
    follower = get_positions(FOLLOWER_KEY, FOLLOWER_SECRET, FOLLOWER_PASSPHRASE)
    
    if isinstance(master, str): return f"Master Error: {master}"
    if isinstance(follower, str): return f"Follower Error: {follower}"
    
    logs = []
    # افتح اللي مش مفتوح
    for m in master:
        sym = m["symbol"]
        qty = float(m["currentQty"])
        if qty == 0: continue
        side = "buy" if qty > 0 else "sell"
        target = int(abs(qty)*COPY_RATIO)
        f_pos = next((x for x in follower if x["symbol"]==sym), None)
        if not f_pos:
            logs.append(f"🔵 OPEN {sym} {side} x{target}")
            try:
                kucoin_request(FOLLOWER_KEY, FOLLOWER_SECRET, FOLLOWER_PASSPHRASE, "POST", "/api/v1/orders", {"symbol": sym, "side": side, "size": str(target), "type": "market", "leverage": "5"})
            except Exception as e:
                logs.append(f"❌ {sym} error: {e}")
    
    # اقفل اللي الماستر قفله
    for f in follower:
        if not any(m["symbol"]==f["symbol"] and float(m["currentQty"])!=0 for m in master):
            logs.append(f"🔴 CLOSE {f['symbol']}")
            try:
                kucoin_request(FOLLOWER_KEY, FOLLOWER_SECRET, FOLLOWER_PASSPHRASE, "POST", "/api/v1/orders", {"symbol": f["symbol"], "closeOrder": True, "type": "market"})
            except Exception as e:
                logs.append(f"❌ close {f['symbol']}: {e}")
    
    if not logs:
        return f"✅ تمام - الماستر: {len(master)} صفقة - الفولور: {len(follower)} صفقة - كله متزامن"
    return "\n".join(logs)

# ===== TELEGRAM =====
def tg_send(text, chat_id=None):
    cid = chat_id or TELEGRAM_CHAT_ID
    if not cid: return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": cid, "text": text}, timeout=10)
    except: pass

def tg_poll():
    global TELEGRAM_CHAT_ID
    offset = 0
    print("Bot started... polling")
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=35).json()
            for upd in r.get("result", []):
                offset = upd["update_id"]+1
                msg = upd.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "")
                if not chat_id: continue
                TELEGRAM_CHAT_ID = str(chat_id)
                print(f"Chat: {chat_id} Text: {text}")
                if text in ["/start", "/help"]:
                    tg_send("👋 بوت Bly7h شغال\n\n/copy - انسخ دلوقتي\n/status - حالة الصفقات\n/balance - الرصيد\n/start - القائمة", chat_id)
                elif "/copy" in text:
                    tg_send("⏳ بنسخ...", chat_id)
                    res = copy_trade()
                    tg_send(res, chat_id)
                elif "/status" in text:
                    m = get_positions(MASTER_KEY, MASTER_SECRET, MASTER_PASSPHRASE)
                    f = get_positions(FOLLOWER_KEY, FOLLOWER_SECRET, FOLLOWER_PASSPHRASE)
                    tg_send(f"📊 Master: {m if isinstance(m,str) else len(m)} صفقة\n📊 Follower: {f if isinstance(f,str) else len(f)} صفقة", chat_id)
                elif "/balance" in text:
                    try:
                        bal_m = kucoin_request(MASTER_KEY, MASTER_SECRET, MASTER_PASSPHRASE, "GET", "/api/v1/account-overview?currency=USDT")
                        bal_f = kucoin_request(FOLLOWER_KEY, FOLLOWER_SECRET, FOLLOWER_PASSPHRASE, "GET", "/api/v1/account-overview?currency=USDT")
                        tg_send(f"💰 Master: {bal_m}\n💰 Follower: {bal_f}", chat_id)
                    except Exception as e:
                        tg_send(f"Balance error: {e}", chat_id)
                # رد على اي رسالة عادية
                if text and not text.startswith("/"):
                    tg_send("دوس /copy عشان انسخ دلوقتي", chat_id)
        except Exception as e:
            print(f"Poll error: {e}")
            time.sleep(5)

def auto_copy_loop():
    while True:
        time.sleep(60)  # كل دقيقة
        try:
            if TELEGRAM_CHAT_ID and MASTER_KEY and FOLLOWER_KEY:
                res = copy_trade()
                if "OPEN" in res or "CLOSE" in res:
                    tg_send(f"🤖 نسخ اوتوماتيك:\n{res}")
        except Exception as e:
            print(f"Auto copy error: {e}")

if __name__ == "__main__":
    threading.Thread(target=auto_copy_loop, daemon=True).start()
    tg_poll()
