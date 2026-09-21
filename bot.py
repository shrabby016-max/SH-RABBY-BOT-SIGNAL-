import os
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import aiohttp
from telegram import Bot

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")
CHAT_ID = os.getenv("CHAT_ID")
SYMBOL = "EUR/USD"
BD_TZ = ZoneInfo("Asia/Dhaka")
TRADE_DURATION_SECONDS = 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("SH_RABBY_BOT")

if not TELEGRAM_BOT_TOKEN: raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")
if not TWELVE_DATA_API_KEY: raise RuntimeError("TWELVE_DATA_API_KEY is missing")
if not CHAT_ID: raise RuntimeError("CHAT_ID is missing")

bot = Bot(token=TELEGRAM_BOT_TOKEN)

def bd_now():
    return datetime.now(BD_TZ)

def fmt(dt):
    return dt.strftime("%H:%M:%S")

async def candles(session, limit=50):
    try:
        async with session.get(
            "https://api.twelvedata.com/time_series",
            params={"symbol": SYMBOL, "interval": "1min", "outputsize": limit,
                    "apikey": TWELVE_DATA_API_KEY, "timezone": "Asia/Dhaka"},
            timeout=20) as r:
            data = await r.json()
            if "values" not in data:
                logger.error("Market API error: %s", data)
                return []
            return [{
                "open": float(x["open"]), "high": float(x["high"]),
                "low": float(x["low"]), "close": float(x["close"])
            } for x in reversed(data["values"])]
    except Exception:
        logger.exception("Market data error")
        return []

def ema(v, p):
    if len(v) < p: return None
    k = 2 / (p + 1)
    e = v[0]
    for x in v[1:]: e = (x - e) * k + e
    return e

def rsi(v, p=14):
    if len(v) < p + 1: return None
    gains, losses = [], []
    for i in range(1, len(v)):
        d = v[i] - v[i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag, al = sum(gains[:p])/p, sum(losses[:p])/p
    for i in range(p, len(gains)):
        ag = ((ag*(p-1))+gains[i])/p
        al = ((al*(p-1))+losses[i])/p
    if al == 0: return 100.0
    return 100 - 100/(1 + ag/al)

def signal(cs):
    if len(cs) < 30: return None
    v = [x["close"] for x in cs]
    a, b = ema(v, 9), ema(v, 21)
    r = rsi(v, 14)
    if a is None or b is None or r is None: return None
    up = down = 0
    if a > b: up += 1
    elif a < b: down += 1
    if v[-1] > a: up += 1
    elif v[-1] < a: down += 1
    if r >= 55: up += 1
    elif r <= 45: down += 1
    if cs[-1]["close"] > cs[-1]["open"]: up += 1
    elif cs[-1]["close"] < cs[-1]["open"]: down += 1
    if cs[-2]["close"] > cs[-2]["open"]: up += 1
    elif cs[-2]["close"] < cs[-2]["open"]: down += 1
    if up >= 4 and up > down: return {"direction":"BUY","option":"CALL","confirmation":up}
    if down >= 4 and down > up: return {"direction":"SELL","option":"PUT","confirmation":down}
    return None

def signal_text(s, start):
    side = "🟢 𝗕𝗨𝗬  ➜  🎯 𝗖𝗔𝗟𝗟 🟢" if s["direction"]=="BUY" else "🔴 𝗦𝗘𝗟𝗟  ➜  🎯 𝗣𝗨𝗧 🔴"
    return (f"╔══════════════════════════════╗\n"
            f"🔥 𝗦𝗛 𝗥𝗔𝗕𝗕𝗬 𝗕𝗢𝗧 𝗦𝗜𝗚𝗡𝗔𝗟 🔥\n"
            f"╚══════════════════════════════╝\n\n"
            f"📊 𝗣𝗔𝗜𝗥: {SYMBOL}\n"
            f"🕐 𝗧𝗜𝗠𝗘: {fmt(start)}\n"
            f"⏳ 𝗘𝗫𝗣𝗜𝗥𝗬: 60 𝗦𝗘𝗖𝗢𝗡𝗗𝗦\n\n{side}\n\n"
            f"🔎 𝗖𝗢𝗡𝗙𝗜𝗥𝗠𝗔𝗧𝗜𝗢𝗡: {s['confirmation']}/5")

def result_text(s, result):
    icon = {"WIN":"🟢 𝗪𝗜𝗡","LOSS":"🔴 𝗟𝗢𝗦𝗦","DRAW":"⚪ 𝗗𝗥𝗔𝗪"}[result]
    return (f"╔══════════════════════════════╗\n🔥 𝗦𝗛 𝗥𝗔𝗕𝗕𝗬 𝗕𝗢𝗧 𝗥𝗘𝗦𝗨𝗟𝗧 🔥\n"
            f"╚══════════════════════════════╝\n\n📊 𝗣𝗔𝗜𝗥: {SYMBOL}\n\n"
            f"📌 𝗦𝗜𝗚𝗡𝗔𝗟: {s['direction']} ➜ {s['option']}\n\n🏁 𝗥𝗘𝗦𝗨𝗟𝗧: {icon}")

async def price(session):
    try:
        async with session.get("https://api.twelvedata.com/quote",
            params={"symbol":SYMBOL,"apikey":TWELVE_DATA_API_KEY}, timeout=15) as r:
            d = await r.json()
            return float(d["close"]) if d.get("close") is not None else None
    except Exception:
        logger.exception("Price error")
        return None

def next_slot():
    # Check for a new signal every 5 minutes.
    # The signal is sent at this slot and the trade starts 2 minutes later.
    now = bd_now()
    next_minute = ((now.minute // 5) + 1) * 5
    if next_minute >= 60:
        return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return now.replace(minute=next_minute, second=0, microsecond=0)

async def main():
    logger.info("SH RABBY BOT STARTED | Asia/Dhaka | %s | 5-min scan | 2-min advance | 1-min expiry", SYMBOL)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                check = next_slot()
                start = check + timedelta(minutes=2)
                wait = (check - bd_now()).total_seconds()
                if wait > 0: await asyncio.sleep(wait)

                if bd_now().weekday() >= 5:
                    logger.info("Weekend: real Forex closed. No signal.")
                    await asyncio.sleep(60); continue

                s = signal(await candles(session))
                if not s:
                    logger.info("No valid signal at %s", fmt(check)); continue

                await bot.send_message(chat_id=CHAT_ID, text=signal_text(s, start))
                logger.info("Signal sent: %s", s)

                while (start - bd_now()).total_seconds() > 0: await asyncio.sleep(1)
                entry = await price(session)
                if entry is None: continue

                expiry = start + timedelta(seconds=TRADE_DURATION_SECONDS)
                while (expiry - bd_now()).total_seconds() > 0: await asyncio.sleep(1)
                final = await price(session)
                if final is None: continue

                if s["direction"] == "BUY":
                    result = "WIN" if final > entry else "LOSS" if final < entry else "DRAW"
                else:
                    result = "WIN" if final < entry else "LOSS" if final > entry else "DRAW"

                await bot.send_message(chat_id=CHAT_ID, text=result_text(s, result))
                logger.info("Result: %s", result)
            except Exception:
                logger.exception("MAIN LOOP ERROR")
                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
