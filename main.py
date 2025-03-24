import os
import time
from dotenv import load_dotenv
from bot.telegram import send_telegram_message
from bot.trader import get_binance_client, analyze_and_trade, calculate_quantity

load_dotenv()

api_key = os.getenv("BINANCE_API_KEY")
secret_key = os.getenv("BINANCE_SECRET_KEY")
symbol = os.getenv("SYMBOL", "DOGEUSDT")  # Troque aqui para o par que desejar
trade_value_usdt = float(os.getenv("TRADE_VALUE_USDT", "1"))
use_testnet = os.getenv("USE_TESTNET", "False").lower() == "true"

client = get_binance_client(api_key, secret_key, use_testnet)

def validate_symbol(client, symbol):
    try:
        info = client.get_symbol_info(symbol)
        if info is None:
            raise ValueError(f"⚠️ Símbolo '{symbol}' não encontrado na Binance.")
        print(f"✅ Símbolo '{symbol}' verificado com sucesso!")
    except Exception as e:
        print(f"Erro ao validar símbolo: {e}")
        exit(1)

validate_symbol(client, symbol)

print(f"🚀 Iniciando o bot para {symbol} | Valor por trade: {trade_value_usdt} USDT")
send_telegram_message(f"🤖 Bot iniciado para o par {symbol} com {trade_value_usdt} USDT por operação no modo {'REAL' if not use_testnet else 'TESTNET'}")

if __name__ == "__main__":
    while True:
        try:
            quantity = calculate_quantity(client, symbol, trade_value_usdt)
            print(f"🔁 Quantidade calculada para {symbol}: {quantity}")
            analyze_and_trade(client, symbol, quantity)
            time.sleep(60)  # Espera 1 minuto antes de verificar novamente
        except Exception as e:
            print("Erro no loop principal:", e)
            send_telegram_message(f"⚠️ Erro no loop principal: {e}")
            time.sleep(10)
