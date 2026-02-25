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

    # Adds the side of the trade
    df_trade["side"] = np.where(
        df_trade["boughtTimestamp"] > df_trade["soldTimestamp"],
        "short",
        "long"
    )
    # Adds entry time columns
    df_trade["entryTimestamp"] = np.where(
        df_trade["boughtTimestamp"] < df_trade["soldTimestamp"],
        df_trade["boughtTimestamp"],
        df_trade["soldTimestamp"]
    )
    # Adds exit time columns
    df_trade["exitTimestamp"] = np.where(
        df_trade["boughtTimestamp"] > df_trade["soldTimestamp"],
        df_trade["boughtTimestamp"],
        df_trade["soldTimestamp"]
    )

    # Adds entry price columns
    df_trade["entryPrice"] = np.where(
        df_trade["boughtTimestamp"] < df_trade["soldTimestamp"],
        df_trade["buyPrice"],
        df_trade["sellPrice"]
    )
    # Adds exit price columns
    df_trade["exitPrice"] = np.where(
        df_trade["boughtTimestamp"] > df_trade["soldTimestamp"],
        df_trade["buyPrice"],
        df_trade["sellPrice"]
    )

        # Group partial fills into full trades
    trade_cols = ["symbol", "entryTimestamp", "entryPrice"]

    df_trades = (
        df_trade
        .groupby(trade_cols, as_index=False)
        .agg(
            qty=("qty", "sum"),
            pnl=("pnl", "sum"),
            duration=("duration", "last"),
            entryTimestamp=("entryTimestamp", "first"),
            exitPrice=("exitPrice","last"),
            exitTimestamp=("exitTimestamp","last"),
            side=("side","first")
        )
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

    return df_trades


# ================================================================================
# DATA FILTER
# This function filters the displayed data per account
# ================================================================================


from datetime import datetime

def filter_trades(
    trades,
    account_id=None,
    date_from=None,
    date_to=None,
    strategy_id=None,
    setup_ids=None,
):
    result = []

    # normalize dates once
    from_dt = datetime.fromisoformat(date_from) if date_from else None
    to_dt = datetime.fromisoformat(date_to) if date_to else None
    if to_dt:
        to_dt = to_dt.replace(hour=23, minute=59, second=59)

    setup_ids = set(map(int, setup_ids)) if setup_ids else set()

    for t in trades:
        # ---- account ----
        if account_id and str(t.get("key_trading_accounts")) != str(account_id):
            continue

        # ---- date ----
        entry_ts = datetime.fromisoformat(t["entryTimestamp"])
        if from_dt and entry_ts < from_dt:
            continue
        if to_dt and entry_ts > to_dt:
            continue

        # ---- strategy ----
        if strategy_id and str(t.get("key_strategies_id")) != str(strategy_id):
            continue

        # ---- setups ----
        if setup_ids and not setup_ids.intersection(set(t.get("setups", []))):
            continue

        result.append(t)

    return result