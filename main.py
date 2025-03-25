
import os
import time
from dotenv import load_dotenv
from bot.trader import (
    get_klines,
    analyze_and_trade,
    calculate_quantity,
    get_binance_client,
    is_in_position
)
from bot.telegram import send_telegram_message

load_dotenv()

# Carrega configurações do .env
api_key = os.getenv("BINANCE_API_KEY")
secret_key = os.getenv("BINANCE_SECRET_KEY")
symbols = os.getenv("SYMBOLS", "DOGEUSDT").split(",")
trade_value_usdt = float(os.getenv("TRADE_VALUE_USDT", "1"))
use_testnet = os.getenv("USE_TESTNET", "False").lower() == "true"

# Inicia cliente Binance
client = get_binance_client(api_key, secret_key, use_testnet)

# Mostra informações iniciais
print(f"🚀 Bot ativo para os pares: {', '.join(symbols)} | Valor por operação: {trade_value_usdt} USDT")
send_telegram_message(f"🤖 Bot iniciado para {', '.join(symbols)} | Modo: {'Testnet' if use_testnet else 'REAL'}")

# ================================
# 🔁 LOOP PRINCIPAL DO BOT
# ================================

if __name__ == "__main__":
    while True:
        for symbol in symbols:
            try:
                if not is_in_position(symbol):
                    quantity = calculate_quantity(client, symbol, trade_value_usdt)
                    print(f"🔎 {symbol} | Quantidade: {quantity}")
                    analyze_and_trade(client, symbol, quantity)
                else:
                    print(f"🔒 Já em posição no par {symbol}. Aguardando TP/SL.")
            except Exception as e:
                print(f"⚠️ Erro com {symbol}: {e}")
                send_telegram_message(f"⚠️ Erro com {symbol}: {e}")

        time.sleep(60)