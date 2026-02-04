import pandas as pd # <- used for dataframe
import numpy as np # <- used for dataframe

#csv_file = r"imported_data\Performance.csv"

# ================================================================================
# CANDLE CHART CREATION
# Creates charts of trsdes using yahoo finance
# ================================================================================

import yfinance as yf
import mplfinance as mpf
from datetime import datetime, timedelta

def plot_trade_candlestick(symbol, bought_ts, sold_ts, save_path=None):
    """
    Generates a candlestick chart for a trade with entry and exit markers.
    
    :param symbol: e.g. 'AAPL'
    :param bought_ts: datetime object
    :param sold_ts: datetime object
    :param save_path: path to save the chart image, or None to show
    """
    
    # Extend the time window around the trade
    start = bought_ts - timedelta(hours=2)
    end = sold_ts + timedelta(hours=2)
    
    # Download intraday data (1m interval)
    df = yf.download(symbol, start=start, end=end, interval="1m")
    
    if df.empty:
        print("No data available for this period")
        return
    
    # Add entry/exit markers
    apds = [
        mpf.make_addplot([df.index.get_loc(bought_ts) * df['Close'].iloc[0]] * len(df), 
                         type='scatter', markersize=100, marker='^', color='green'),
        mpf.make_addplot([df.index.get_loc(sold_ts) * df['Close'].iloc[0]] * len(df), 
                         type='scatter', markersize=100, marker='v', color='red')
    ]
    
    # Plot
    mpf.plot(
        df,
        type='candle',
        style='yahoo',
        title=f"{symbol} Trade {bought_ts.strftime('%Y-%m-%d %H:%M')}",
        addplot=apds,
        volume=True,
        mav=(5, 20)
    )
    
    if save_path:
        mpf.plot(df, type='candle', style='yahoo', addplot=apds, savefig=save_path)
    else:
        mpf.show()
        

# Example usage
plot_trade_candlestick(
    symbol='AAPL',
    bought_ts=datetime(2025,12,16,15,33),
    sold_ts=datetime(2025,12,16,15,50)
)



#This function allows to handle the CSV format before pushing in the DB
def csv_handler(df_trade):
    # Read the CSV
    # df_trade = pd.read_csv(csv_file)


    # Clean the PnL column
    df_trade["pnl"] = (
        df_trade["pnl"]
        .str.replace("$", "", regex=False)
        .str.replace("(", "-", regex=False)
        .str.replace(")", "", regex=False)
        .astype(float)
    )

    # Convert timestamps to datetime
    df_trade["boughtTimestamp"] = pd.to_datetime(df_trade["boughtTimestamp"], format="%m/%d/%Y %H:%M:%S")
    df_trade["soldTimestamp"] = pd.to_datetime(df_trade["soldTimestamp"], format="%m/%d/%Y %H:%M:%S")

    # Group partial fills into full trades
    trade_cols = ["symbol", "boughtTimestamp", "buyPrice", "sellPrice"]

    df_trades = (
        df_trade
        .groupby(trade_cols, as_index=False)
        .agg(
            qty=("qty", "sum"),
            pnl=("pnl", "sum"),
            duration=("duration", "first"),
            soldTimestamp=("soldTimestamp", "first")
        )
    )

    # Adds the side of the trade
    df_trades["side"] = np.where(
        df_trades["boughtTimestamp"] > df_trades["soldTimestamp"],
        "short",
        "long"
    )

    # Reorder columns
    df_trades = df_trades[[symbol],[boughtTimestamp],[soldTimestamp],[buyPrice],[sellPrice],[duration],[side],[qty],[pnl]]

    # Print results
    #print("=== Reconstructed Trades ===")
    #print(df_trades)

    return df_trades

#csv_handler(csv_file)



