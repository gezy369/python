import pandas as pd
import numpy as np
from datetime import datetime

def csv_handler(df_trade, df_fees=None):
    df_trade["pnl"] = (
        df_trade["pnl"]
        .str.replace("$", "", regex=False)
        .str.replace("(", "-", regex=False)
        .str.replace(")", "", regex=False)
        .astype(float)
    )

    df_trade["boughtTimestamp"] = pd.to_datetime(df_trade["boughtTimestamp"], format="%m/%d/%Y %H:%M:%S")
    df_trade["soldTimestamp"]   = pd.to_datetime(df_trade["soldTimestamp"],   format="%m/%d/%Y %H:%M:%S")

    df_trade["side"] = np.where(
        df_trade["boughtTimestamp"] > df_trade["soldTimestamp"], "short", "long"
    )

    df_trade["entryTimestamp"] = np.where(
        df_trade["boughtTimestamp"] < df_trade["soldTimestamp"],
        df_trade["boughtTimestamp"], df_trade["soldTimestamp"]
    )

    df_trade["exitTimestamp"] = np.where(
        df_trade["boughtTimestamp"] > df_trade["soldTimestamp"],
        df_trade["boughtTimestamp"], df_trade["soldTimestamp"]
    )

    df_trade["entryPrice"] = np.where(
        df_trade["boughtTimestamp"] < df_trade["soldTimestamp"],
        df_trade["buyPrice"], df_trade["sellPrice"]
    )

    df_trade["exitPrice"] = np.where(
        df_trade["boughtTimestamp"] > df_trade["soldTimestamp"],
        df_trade["buyPrice"], df_trade["sellPrice"]
    )

    # ===== GROUP =====
    trade_cols = ["symbol", "entryTimestamp", "entryPrice"]

    df_trades = (
        df_trade
        .groupby(trade_cols, as_index=False)
        .agg(
            qty=("qty", "sum"),
            pnl=("pnl", "sum"),
            duration=("duration", "last"),
            entryTimestamp=("entryTimestamp", "first"),
            exitPrice=("exitPrice", "last"),
            exitTimestamp=("exitTimestamp", "last"),
            side=("side", "first")
        )
    )

    # Normalize symbol
    df_trades["symbol"] = df_trades["symbol"].str[:-2]

    # Adds gross pnl
    df_trades["gross_pnl"] = df_trades["pnl"]
    # ===== FEES =====
    if df_fees is not None and not df_fees.empty:
        # Ensure same format
        df_fees["symbol"] = df_fees["symbol"].str.upper()
        df_trades["symbol"] = df_trades["symbol"].str.upper()

        # Merge fees
        df_trades = df_trades.merge(df_fees, on="symbol", how="left")

        # Fill missing fees with 0
        df_trades["fee"] = df_trades["fee"].fillna(0)

        # Compute total fees (round turn * qty)
        df_trades["fees"] = df_trades["fee"] * df_trades["qty"]

        # Net PnL
        df_trades["pnl"] = df_trades["pnl"] - df_trades["fees"]

        # Optional: drop fee column if you don’t want it stored
        # df_trades.drop(columns=["fee"], inplace=True)
    else:
        df_trades["fees"] = 0

    # ===== FINAL FORMAT =====
    df_trades = df_trades[[
        "symbol", "entryTimestamp", "exitTimestamp",
        "entryPrice", "exitPrice", "duration",
        "side", "qty", "pnl", "fees"
    ]]

    return df_trades


def filter_trades(trades, account_id=None, date_from=None, date_to=None, strategy_id=None, setup_ids=None):
    result = []

    from_dt = datetime.fromisoformat(date_from) if date_from else None
    to_dt   = datetime.fromisoformat(date_to)   if date_to   else None
    if to_dt:
        to_dt = to_dt.replace(hour=23, minute=59, second=59)

    setup_ids = set(map(int, setup_ids)) if setup_ids else set()

    for t in trades:
        if account_id and str(t.get("key_trading_accounts")) != str(account_id):
            continue

        entry_ts = datetime.fromisoformat(t["entryTimestamp"])
        if from_dt and entry_ts < from_dt:
            continue
        if to_dt and entry_ts > to_dt:
            continue

        if strategy_id and str(t.get("key_strategies_id")) != str(strategy_id):
            continue

        if setup_ids and not setup_ids.intersection(set(t.get("setups", []))):
            continue

        result.append(t)

    return result