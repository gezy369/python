import pandas as pd

def csv_handler():
    # Read the CSV
    df_trade = pd.read_csv(r"PYTHON CODING\Performance.csv")
    print(df_trade)

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
    trade_cols = ["symbol", "boughtTimestamp", "soldTimestamp", "buyPrice", "sellPrice"]

    df_trades = (
        df_trade
        .groupby(trade_cols, as_index=False)
        .agg(
            qty=("qty", "sum"),
            pnl=("pnl", "sum"),
            duration=("duration", "first")
        )
    )

    # Optional: compute daily PnL
    df_trades["buy_date"] = df_trades["boughtTimestamp"].dt.date

    daily_pnl = (
        df_trades
        .groupby("buy_date", as_index=False)["pnl"]
        .sum()
    )

    # Print results
    print("=== Reconstructed Trades ===")
    print(df_trades)

    print("\n=== Daily PnL ===")
    print(daily_pnl)

return df_trades
