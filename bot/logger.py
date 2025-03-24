import csv
import os
from datetime import datetime

LOG_FILE = "logs/trades.csv"

def log_trade(action, symbol, price, quantity, pattern, result=None):
    file_exists = os.path.isfile(LOG_FILE)

    with open(LOG_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["timestamp", "action", "symbol", "price", "quantity", "pattern", "result"])
        
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            action,
            symbol,
            f"{price:.2f}",
            quantity,
            pattern,
            result or ""
        ])
