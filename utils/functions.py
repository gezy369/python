import pandas as pd
import numpy as np
from datetime import datetime

def csv_handler(df_trade, df_fees=None):
    df_trade["pnl"] = (
        df_trade["pnl"]
        .astype(str)
        .str.replace("$", "", regex=False)
        .str.replace("(", "-", regex=False)
        .str.replace(")", "", regex=False)
        .astype(float)
    )

    df_trade["boughtTimestamp"] = pd.to_datetime(df_trade["boughtTimestamp"], format="%m/%d/%Y %H:%M:%S")
    df_trade["soldTimestamp"]   = pd.to_datetime(df_trade["soldTimestamp"],   format="%m/%d/%Y %H:%M:%S")

    df_trade["symbol"] = df_trade["symbol"].str[:-2]

    # ===== FEES =====
    if df_fees is not None and not df_fees.empty:
        df_fees["symbol"]  = df_fees["symbol"].str.upper()
        df_trade["symbol"] = df_trade["symbol"].str.upper()
        df_trade = df_trade.merge(df_fees, on="symbol", how="left")
        df_trade["fees"] = df_trade["fees"].fillna(0) * df_trade["qty"]
        df_trade["pnl"]  = df_trade["pnl"] - df_trade["fees"]
    else:
        df_trade["fees"] = 0

    df_trade["pnl"] = round(df_trade["pnl"], 2)

    df_trade["boughtTimestamp"] = df_trade["boughtTimestamp"].astype(str)
    df_trade["soldTimestamp"]   = df_trade["soldTimestamp"].astype(str)

    return df_trade[[
        "symbol", "buyFillId", "sellFillId",
        "qty", "buyPrice", "sellPrice",
        "pnl", "fees", "boughtTimestamp", "soldTimestamp", "duration"
    ]]

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