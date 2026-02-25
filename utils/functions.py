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

def filter_trades(trades, account_id=None, date_from=None, date_to=None, strategy_id=None, setup_ids=None,):
    """
    trades: list of trade dicts
    """

    result = trades

    # ---------- ACCOUNT ----------
    if account_id:
        result = [
            t for t in result
            if str(t.get("key_trading_accounts")) == str(account_id)
        ]

    # ---------- DATE RANGE ----------
    if date_from:
        date_from = datetime.fromisoformat(date_from)
        result = [
            t for t in result
            if datetime.fromisoformat(t["entryTimestamp"]) >= date_from
        ]

    if date_to:
        date_to = datetime.fromisoformat(date_to)
        result = [
            t for t in result
            if datetime.fromisoformat(t["entryTimestamp"]) <= date_to
        ]

    # ---------- STRATEGY ----------
    if strategy_id:
        result = [
            t for t in result
            if t.get("key_strategies_id") == int(strategy_id)
        ]

    # ---------- SETUPS ----------
    if setup_ids:
        setup_ids = set(map(int, setup_ids))
        result = [
            t for t in result
            if setup_ids.intersection(t.get("setups", []))
        ]

    return result