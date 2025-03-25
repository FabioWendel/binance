
import os
import time
import math
import threading
import json
from datetime import datetime
import pandas as pd
from binance.exceptions import BinanceAPIException
from bot.telegram import send_telegram_message
from binance.client import Client


# =========================
# 📦 UTILITÁRIOS
# =========================

def round_step_size(quantity, step_size):
    precision = int(round(-math.log(step_size, 10), 0))
    return round(quantity, precision)

def get_klines(client, symbol, interval='5m', limit=10):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'num_trades',
        'taker_buy_base', 'taker_buy_quote', 'ignore'
    ])
    df['open'] = df['open'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)
    return df

def get_position_file(symbol):
    return f"{symbol}_lock"

def is_in_position(symbol):
    return os.path.exists(get_position_file(symbol))

def set_position(symbol, active=True):
    path = get_position_file(symbol)
    if active:
        with open(path, "w") as f:
            f.write("1")
    else:
        if os.path.exists(path):
            os.remove(path)

# =========================
# 💡 PADRÕES DE VELA
# =========================

def is_hammer(open_p, high, low, close):
    body = abs(close - open_p)
    lower_shadow = open_p - low if open_p < close else close - low
    upper_shadow = high - close if open_p < close else high - open_p
    return lower_shadow > 2 * body and upper_shadow < body

def is_bullish_engulfing(prev_open, prev_close, open_p, close):
    return prev_close < prev_open and close > open_p and close > prev_open and open_p < prev_close

def is_bearish_engulfing(prev_open, prev_close, open_p, close):
    return prev_open < prev_close and open_p > close and open_p > prev_close and close < prev_open

def is_doji(open_p, close):
    return abs(close - open_p) <= 0.001

# =========================
# 💰 OPERAÇÕES
# =========================

def place_order(client, symbol, quantity, side, mode="spot"):
    try:
        if mode == "futures":
            return client.futures_create_order(symbol=symbol, side=side, type="MARKET", quantity=quantity)
        else:
            if side == "BUY":
                return client.order_market_buy(symbol=symbol, quantity=quantity)
            else:
                return client.order_market_sell(symbol=symbol, quantity=quantity)
    except BinanceAPIException as e:
        print("❌ Erro na Binance API:", e)
        send_telegram_message(f"❌ Erro na Binance API: {e}")
        return None

def save_position_to_json(symbol, side, entry_price, quantity, tp, sl):
    position = {
        "symbol": symbol,
        "side": side,
        "entry_price": entry_price,
        "quantity": quantity,
        "tp": tp,
        "sl": sl,
        "status": "open",
        "timestamp": datetime.now().isoformat()
    }
    try:
        with open("positions.json", "r") as file:
            positions = json.load(file)
    except:
        positions = []
    positions.append(position)
    with open("positions.json", "w") as file:
        json.dump(positions, file, indent=4)

def close_position_in_json(symbol, status, exit_price):
    try:
        with open("positions.json", "r") as file:
            positions = json.load(file)
        for p in positions:
            if p["symbol"] == symbol and p["status"] == "open":
                p["status"] = status
                p["exit_price"] = exit_price
                p["exit_time"] = datetime.now().isoformat()
                break
        with open("positions.json", "w") as file:
            json.dump(positions, file, indent=4)
    except:
        pass

def monitor_position(client, symbol, entry_price, quantity, action, mode, tp, sl):
    print(f"🎯 TP: {tp:.4f} | 🛑 SL: {sl:.4f}")
    while True:
        try:
            price = float(client.get_symbol_ticker(symbol=symbol)['price'])

            if (action == "BUY" and price >= tp) or (action == "SELL" and price <= tp):
                place_order(client, symbol, quantity, "SELL" if action == "BUY" else "BUY", mode)
                send_telegram_message(f"✅ {symbol} atingiu o Take Profit a {price:.4f}")
                close_position_in_json(symbol, "tp", price)
                set_position(symbol, False)
                break

            elif (action == "BUY" and price <= sl) or (action == "SELL" and price >= sl):
                place_order(client, symbol, quantity, "SELL" if action == "BUY" else "BUY", mode)
                send_telegram_message(f"❌ {symbol} atingiu o Stop Loss a {price:.4f}")
                close_position_in_json(symbol, "sl", price)
                set_position(symbol, False)
                break

            time.sleep(3)

        except Exception as e:
            print("Erro no monitoramento:", e)
            break

def analyze_and_trade(client, symbol, quantity):
    if is_in_position(symbol):
        print(f"⏸️ Já existe uma posição aberta em {symbol}.")
        return

    df = get_klines(client, symbol, limit=10)
    last = df.iloc[-2]
    prev = df.iloc[-3]

    open_price = last['open']
    close_price = last['close']
    high = last['high']
    low = last['low']
    prev_open = prev['open']
    prev_close = prev['close']

    action = None
    signal = None

    if is_hammer(open_price, high, low, close_price) or is_bullish_engulfing(prev_open, prev_close, open_price, close_price):
        action = "BUY"
        signal = "📈 COMPRA"
    elif is_bearish_engulfing(prev_open, prev_close, open_price, close_price):
        action = "SELL"
        signal = "📉 VENDA"
    elif is_doji(open_price, close_price):
        print("⚖️ Doji detectado. Nenhuma ação.")
        return

    if action:
        order = place_order(client, symbol, quantity, action)
        if order is None:
            return

        price = float(order['fills'][0]['price']) if "fills" in order else float(order.get("avgFillPrice") or order.get("price"))
        tp_percent = float(os.getenv("TAKE_PROFIT_PERCENT", "0.5")) / 100
        sl_percent = float(os.getenv("STOP_LOSS_PERCENT", "0.3")) / 100

        tp = price * (1 + tp_percent) if action == "BUY" else price * (1 - tp_percent)
        sl = price * (1 - sl_percent) if action == "BUY" else price * (1 + sl_percent)

        save_position_to_json(symbol, action, price, quantity, tp, sl)
        set_position(symbol, True)

        send_telegram_message(f"{signal} enviada em {symbol} por {price:.4f}")
        threading.Thread(target=monitor_position, args=(client, symbol, price, quantity, action, "spot", tp, sl)).start()

def get_binance_client(api_key, secret_key, testnet=False):
    client = Client(api_key, secret_key)
    if testnet:
        client.API_URL = "https://testnet.binance.vision/api"
    try:
        # Corrige o horário caso haja diferença com o servidor da Binance
        server_time = client.get_server_time()['serverTime']
        local_time = int(time.time() * 1000)
        offset = server_time - local_time
        client._timestamp_offset = offset
    except:
        pass
    return client

def calculate_quantity(client, symbol, trade_value_usdt):
    price = float(client.get_symbol_ticker(symbol=symbol)['price'])

    # Obter stepSize para arredondar
    info = client.get_symbol_info(symbol)
    step_size = 1e-6

    for f in info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            step_size = float(f['stepSize'])
            break

    quantity = trade_value_usdt / price
    precision = int(round(-1 * math.log(step_size, 10), 0))
    return round(quantity, precision)