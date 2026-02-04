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

    # Reorder columns
    df_trades = df_trades[[symbol],[boughtTimestamp],[soldTimestamp],[buyPrice],[sellPrice],[duration],[side],[qty],[pnl]]

    # Print results
    #print("=== Reconstructed Trades ===")
    #print(df_trades)

    return df_trades

#csv_handler(csv_file)



