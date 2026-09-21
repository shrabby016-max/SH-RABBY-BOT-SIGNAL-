SH RABBY BOT SIGNAL

Build:
  pip install -r requirements.txt

Run:
  python bot.py

Environment variables:
  TELEGRAM_BOT_TOKEN
  TWELVE_DATA_API_KEY
  CHAT_ID

Trading schedule:
  - Real Forex pair: EUR/USD
  - Signal scan: every 5 minutes
  - Signal is sent 2 minutes before the trade start time
  - Trade duration / expiry: 60 seconds
  - Result is sent immediately after the 60-second trade ends
  - Bangladesh time: Asia/Dhaka
  - Real Forex weekends: no signals
  - OTC is NOT included; Twelve Data is not treated as an OTC source

Signal conditions:
  - EMA(9) / EMA(21)
  - RSI(14)
  - Recent candle direction
  - Minimum 4/5 confirmation

Note:
  A signal is only sent when the strategy produces a valid signal. Therefore,
  there can be a gap longer than 5 minutes when market conditions do not meet
  the confirmation rules.
