def is_hammer(open_price, high_price, low_price, close_price):
    body = abs(close_price - open_price)
    lower_wick = open_price - low_price if close_price > open_price else close_price - low_price
    upper_wick = high_price - close_price if close_price > open_price else high_price - open_price
    return lower_wick > 2 * body and upper_wick < body

def is_bullish_engulfing(prev_open, prev_close, open_price, close_price):
    return prev_close < prev_open and close_price > open_price and close_price > prev_open and open_price < prev_close

def is_bearish_engulfing(prev_open, prev_close, open_price, close_price):
    return prev_close > prev_open and close_price < open_price and close_price < prev_open and open_price > prev_close

def is_doji(open_price, close_price, threshold=0.1):
    return abs(close_price - open_price) <= threshold