import pandas as pd # <- used for dataframe
import numpy as np # <- used for dataframe

#csv_file = r"imported_data\Performance.csv"

# ================================================================================
# CSV HANDLER
# This function allows to handle the CSV format before pushing in the DB
# ================================================================================

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
    # Adds entry time columns
    df_trades["entryTimestamp"] = np.where(
        df_trades["boughtTimestamp"] < df_trades["soldTimestamp"],
        df_trades["boughtTimestamp"],
        df_trades["soldTimestamp"]
    )
    # Adds exit time columns
    df_trades["exitTimestamp"] = np.where(
        df_trades["boughtTimestamp"] > df_trades["soldTimestamp"],
        df_trades["boughtTimestamp"],
        df_trades["soldTimestamp"]
    )

    # Adds entry price columns
    df_trades["entryPrice"] = np.where(
        df_trades["boughtTimestamp"] < df_trades["soldTimestamp"],
        df_trades["buyPrice"],
        df_trades["sellPrice"]
    )
    # Adds exit price columns
    df_trades["exitPrice"] = np.where(
        df_trades["boughtTimestamp"] > df_trades["soldTimestamp"],
        df_trades["buyPrice"],
        df_trades["sellPrice"]
    )

    # Formats symbols
    df_trades["symbol"] = df_trades["symbol"].str[:-2] 

    # Reorder columns
    df_trades = df_trades[[
        "symbol",
        "entryTimestamp",
        "exitTimestamp",
        "entryPrice",
        "exitPrice",
        "duration",
        "side",
        "qty",
        "pnl"
    ]]  

    # Print results
    #print("=== Reconstructed Trades ===")
    #print(df_trades)

    return df_trades

#csv_handler(csv_file)



