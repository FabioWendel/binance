import os
import time
import math
import threading
from bot.logger import log_trade
from bot.telegram import send_telegram_message
from binance.client import Client
import pandas as pd
from bot.candle_patterns import is_bearish_engulfing, is_bullish_engulfing, is_doji, is_hammer
from binance.client import Client



def get_binance_client(api_key, api_secret, testnet=False):
    client = Client(api_key, api_secret, tld='com')
    client.API_URL = 'https://testnet.binance.vision/api' if testnet else 'https://api.binance.com/api'
    client.REQUEST_TIMEOUT = 10

    # ⚠️ Corrige o erro de timestamp
    client._timestamp_offset = int(client.get_server_time()['serverTime']) - int(time.time() * 1000)
    
    return client


def get_klines(client, symbol, interval='1m', limit=5):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'qav', 'trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
    ])
    df['open'] = df['open'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)
    return df


def analyze_and_trade(client, symbol, quantity):
    if is_in_position():
        print("⏸️ Já estamos em uma posição. Aguardando TP/SL.")
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

    signal = None
    action = None

    if is_hammer(open_price, high, low, close_price) or is_bullish_engulfing(prev_open, prev_close, open_price, close_price):
        signal = "📈 COMPRA"
        action = "BUY"
    elif is_bearish_engulfing(prev_open, prev_close, open_price, close_price):
        signal = "📉 VENDA A DESCOBERTO"
        action = "SELL"
    elif is_doji(open_price, close_price):
        signal = "⚖️ Doji detectado (neutro)"
        send_telegram_message(signal)
        print(signal)
        return
    else:
        print("Nenhum padrão detectado.")
        return

    mode = os.getenv("MODE", "spot")
    send_telegram_message(f"{signal} detectado! Enviando ordem {action} para {symbol} ({mode.upper()}).")

    try:
        order = place_order(client, symbol, quantity, side=action, mode=mode)

        if "fills" in order:
            entry_price = float(order['fills'][0]['price'])  # Spot
        else:
            entry_price = float(order.get("avgFillPrice") or order.get("price"))  # Futures

        # Marca como posição aberta
        set_position(True)

        log_trade(action, symbol, entry_price, quantity, signal)

        # MONITORA EM BACKGROUND USANDO THREAD
        threading.Thread(
            target=monitor_position_threaded,
            args=(client, symbol, entry_price, quantity, action, mode, signal)
        ).start()

    except Exception as e:
        set_position(False)
        send_telegram_message(f"❌ Erro ao enviar ordem: {e}")
        print("Erro ao executar a ordem:", e)


def monitor_position_threaded(client, symbol, entry_price, quantity, action, mode, signal):
    result = monitor_position(client, symbol, entry_price, quantity, action, mode)
    log_trade("CLOSE", symbol, result["exit_price"], quantity, signal, result["status"])
    set_position(False)


def monitor_position(client, symbol, entry_price, quantity, action, mode):
    tp_percent = float(os.getenv("TAKE_PROFIT_PERCENT", "0.5")) / 100
    sl_percent = float(os.getenv("STOP_LOSS_PERCENT", "0.3")) / 100

    if action == "BUY":
        tp = entry_price * (1 + tp_percent)
        sl = entry_price * (1 - sl_percent)
    else:
        tp = entry_price * (1 - tp_percent)
        sl = entry_price * (1 + sl_percent)

    print(f"🎯 TP: {tp:.2f} | 🛑 SL: {sl:.2f}")

    while True:
        try:
            price = float(client.get_symbol_ticker(symbol=symbol)['price'])

            if (action == "BUY" and price >= tp) or (action == "SELL" and price <= tp):
                send_telegram_message(f"✅ Take Profit atingido ({price:.2f})! Encerrando posição.")
                place_order(client, symbol, quantity, side="SELL" if action == "BUY" else "BUY", mode=mode)
                return {"status": "TP", "exit_price": price}

            elif (action == "BUY" and price <= sl) or (action == "SELL" and price >= sl):
                send_telegram_message(f"❌ Stop Loss atingido ({price:.2f})! Encerrando posição.")
                place_order(client, symbol, quantity, side="SELL" if action == "BUY" else "BUY", mode=mode)
                return {"status": "SL", "exit_price": price}

            time.sleep(3)

        except Exception as e:
            send_telegram_message(f"⚠️ Erro ao monitorar posição: {e}")
            print("Erro monitorando posição:", e)
            return {"status": "ERROR", "exit_price": entry_price}


def place_order(client, symbol, quantity, side, mode="spot"):
    if mode == "futures":
        if side == "BUY":
            return client.futures_create_order(symbol=symbol, side="BUY", type="MARKET", quantity=quantity)
        else:
            return client.futures_create_order(symbol=symbol, side="SELL", type="MARKET", quantity=quantity)
    else:
        if side == "BUY":
            return client.order_market_buy(symbol=symbol, quantity=quantity)
        else:
            return client.order_market_sell(symbol=symbol, quantity=quantity)


def is_in_position():
    return os.path.exists("position.lock")


def set_position(active: bool):
    if active:
        with open("position.lock", "w") as f:
            f.write("1")
    else:
        if os.path.exists("position.lock"):
            os.remove("position.lock")


def calculate_quantity(client, symbol, trade_value_usdt):
    price = float(client.get_symbol_ticker(symbol=symbol)['price'])

    # Obter stepSize
    info = client.get_symbol_info(symbol)
    step_size = 1e-6
    min_notional = 1  # valor mínimo da ordem

    for f in info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            step_size = float(f['stepSize'])
        elif f['filterType'] == 'MIN_NOTIONAL':
            min_notional = float(f['minNotional'])

    quantity = trade_value_usdt / price
    quantity = round_step_size(quantity, step_size)

    # Recalcular o valor final
    order_value = quantity * price
    if order_value < min_notional:
        raise ValueError(f"❌ Valor da ordem ({order_value:.2f} USDT) está abaixo do mínimo permitido ({min_notional} USDT).")

    return quantity



def round_step_size(quantity, step_size):
    precision = int(round(-math.log(step_size, 10), 0))
    return round(quantity, precision)


def get_lot_size_info(client, symbol):
    info = client.get_symbol_info(symbol)
    for f in info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            return {
                'minQty': float(f['minQty']),
                'stepSize': float(f['stepSize']),
                'maxQty': float(f['maxQty'])
            }
