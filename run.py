from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from datetime import datetime, timedelta
from utils.functions import csv_handler, filter_trades
from zoneinfo import ZoneInfo
import os
import io, base64
import pandas as pd
from supabase import create_client, Client
import requests
import mplfinance as mpf
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me-in-production")

# ===== CONFIG =====
UPLOAD_FOLDER = "imported_data"
ALLOWED_EXTENSIONS = {"csv"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ===== SUPABASE =====
SUPABASE_URL         = os.environ.get("SUPABASE_URL")
SUPABASE_KEY         = os.environ.get("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

supabase      : Client = create_client(SUPABASE_URL, SUPABASE_KEY)
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ===== HELPERS =====
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def load_user_settings_into_session(user_id):
    res = (
        supabase_admin.table("settings")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )

    if res.data:
        settings = res.data[0]
        session["timezone"] = settings.get("timezone", "Europe/Paris")
        session["settings"] = settings

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def get_user_trade_ids(user_id):
    """Return all trade IDs belonging to the current user."""
    accounts_res = (
        supabase_admin.table("trading_accounts")
        .select("id")
        .eq("user_id", user_id)
        .execute()
    )
    account_ids = [a["id"] for a in (accounts_res.data or [])]
    if not account_ids:
        return []
    trades_res = (
        supabase_admin.table("trades")
        .select("id")
        .in_("key_trading_accounts", account_ids)
        .execute()
    )
    return [t["id"] for t in (trades_res.data or [])]

# ===== AUTH =====
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            # ✅ API should return JSON, not HTML
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

@app.post("/auth/session")
def auth_session():
    data = request.json
    access_token = data.get("access_token")

    if not access_token:
        return jsonify({"error": "No token"}), 400

    try:
        user = supabase.auth.get_user(access_token)

        session["user"] = {
            "id": user.user.id,
            "email": user.user.email
        }

        # load settings AFTER auth success
        load_user_settings_into_session(user.user.id)

        return jsonify({"ok": True})

    except Exception as e:
        return jsonify({"error": str(e)}), 401

# ── Fake left-panel data for login page ────────────────────────────────────
import calendar as _cal

_FAKE_CALENDAR = {
    "2026-04-01": {"pnl": -320, "trades": 3},
    "2026-04-02": {"pnl":  510, "trades": 5},
    "2026-04-03": {"pnl":  210, "trades": 2},
    "2026-04-04": {"pnl":  -80, "trades": 4},
    "2026-04-07": {"pnl":  640, "trades": 6},
    "2026-04-08": {"pnl":  190, "trades": 3},
    "2026-04-09": {"pnl": -450, "trades": 4},
    "2026-04-10": {"pnl":  720, "trades": 7},
    "2026-04-11": {"pnl":  380, "trades": 4},
    "2026-04-14": {"pnl":  230, "trades": 3},
    "2026-04-15": {"pnl": -160, "trades": 2},
    "2026-04-16": {"pnl":  890, "trades": 8},
    "2026-04-17": {"pnl":  310, "trades": 4},
    "2026-04-18": {"pnl": -120, "trades": 3},
}

_FAKE_RECENT_TRADES = [
    {"symbol": "ES",  "entry_time": "09:32", "side": "Long",  "qty": 2, "pnl":  720},
    {"symbol": "NQ",  "entry_time": "10:15", "side": "Short", "qty": 1, "pnl": -450},
    {"symbol": "ES",  "entry_time": "11:04", "side": "Long",  "qty": 3, "pnl":  890},
    {"symbol": "MES", "entry_time": "13:47", "side": "Short", "qty": 5, "pnl": -120},
]

def _login_context():
    year, month, today_day = 2026, 4, 12
    first_weekday, days_in_month = _cal.monthrange(year, month)
    offset = first_weekday if first_weekday < 5 else 0
    cells  = [{"empty": True}] * offset
    for day in range(1, days_in_month + 1):
        from datetime import date
        if date(year, month, day).weekday() >= 5:
            continue
        iso  = f"{year}-{month:02d}-{day:02d}"
        data = _FAKE_CALENDAR.get(iso, {"pnl": 0.0, "trades": 0})
        pnl  = data["pnl"]
        cells.append({
            "empty": False, "day": day,
            "today": day == today_day, "future": day > today_day,
            "pnl": pnl,
            "pnl_display": f"{abs(pnl):.0f}" if abs(pnl) < 1000 else f"{abs(pnl)/1000:.1f}k",
            "trades": data["trades"],
        })
    mtd = 3241.50
    return {
        "current_month":   "April",
        "current_year":    2026,
        "mtd_pnl_display": f"+${mtd/1000:.1f}k",
        "calendar_cells":  cells,
        "recent_trades":   _FAKE_RECENT_TRADES,
    }

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email    = request.form["email"]
        password = request.form["password"]

        try:
            res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            # set session user
            session["user"] = {
                "id": res.user.id,
                "email": res.user.email
            }

            # load settings AFTER login
            load_user_settings_into_session(res.user.id)

            return redirect(url_for("dashboard"))

        except Exception:
            return render_template(
                "login.html",
                error="Invalid credentials",
                **_login_context()
            )

    return render_template("login.html", **_login_context())

@app.route("/auth/google")
def auth_google():
    res = supabase.auth.sign_in_with_oauth({
        "provider": "google",
        "options": {"redirect_to": "https://journal-51c7.onrender.com/auth/callback"}
    })
    return redirect(res.url)

@app.route("/auth/callback")
def auth_callback():
    code = request.args.get("code")

    if not code:
        return redirect(url_for("login"))

    try:
        res = supabase.auth.exchange_code_for_session({"auth_code": code})

        # set session user
        session["user"] = {
            "id": res.user.id,
            "email": res.user.email
        }

        # load user settings (timezone, chart settings, etc.)
        load_user_settings_into_session(res.user.id)

        return redirect(url_for("dashboard"))

    except Exception as e:
        print("Auth callback error:", e)
        return redirect(url_for("login"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ===== CHART GENERATION =====
def generate_chart_base64(symbol, entry_time, exit_time, entry_price, exit_price, side, user_id, timeframe="5m", fills=None):
    try:
        # ── Timeframe → Yahoo interval mapping ──────────────────────────
        TIMEFRAME_TO_YAHOO = {
            "1m": "1m", "2m": "2m", "3m": "2m",
            "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "60m", "4h": "60m", "D": "1d",
        }
        YAHOO_LOOKBACK_DAYS = {
            "1m": 1, "2m": 5, "5m": 5,
            "15m": 10, "30m": 15, "60m": 30, "1d": 90,
        }
        CONTEXT_HOURS = {
            "1m":  (2, 3),   "2m":  (2, 3),   "3m":  (3, 4),
            "5m":  (4, 5),   "15m": (8, 10),   "30m": (16, 20),
            "1h":  (24, 48), "4h":  (72, 120), "D":   (720, 1440),
        }
        yahoo_interval        = TIMEFRAME_TO_YAHOO.get(timeframe, "5m")
        lookback              = YAHOO_LOOKBACK_DAYS.get(yahoo_interval, 5)
        ctx_before, ctx_after = CONTEXT_HOURS.get(timeframe, (3, 4))

        yahoo_symbol = symbol if symbol.endswith("=F") else f"{symbol}=F"
        trade_date   = entry_time.date()

        period1 = int((datetime.combine(trade_date, datetime.min.time()) - timedelta(days=lookback)).timestamp())
        period2 = int((datetime.combine(trade_date, datetime.min.time()) + timedelta(days=2)).timestamp())

        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
            f"?interval={yahoo_interval}&period1={period1}&period2={period2}"
        )

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept":     "application/json",
            "Referer":    "https://finance.yahoo.com",
        }

        r = requests.get(url, headers=headers, timeout=10)
        if not r.ok:
            print(f"Yahoo returned {r.status_code} for {yahoo_symbol}: {r.text[:300]}")
            return None

        data   = r.json()
        result = data.get("chart", {}).get("result")
        if not result:
            print(f"No result in Yahoo response for {yahoo_symbol}: {data.get('chart', {}).get('error')}")
            return None

        result     = result[0]
        timestamps = result["timestamp"]
        quote      = result["indicators"]["quote"][0]

        settings_res = (
            supabase_admin.table("settings")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        settings = settings_res.data[0] if settings_res.data else {}

        user_timezone = settings.get("timezone", "Europe/Paris")

        df = pd.DataFrame({
            "Open":   quote["open"],
            "High":   quote["high"],
            "Low":    quote["low"],
            "Close":  quote["close"],
            "Volume": quote.get("volume", [0] * len(timestamps))
        }, index=pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(user_timezone))

        df = df.dropna(subset=["Open", "High", "Low", "Close"])

        if len(df) < 5:
            print(f"Insufficient candles for {yahoo_symbol}: {len(df)}")
            return None

        # ── Localize trade-level entry/exit (used for chart window) ─────
        entry_ts = pd.Timestamp(entry_time)
        exit_ts  = pd.Timestamp(exit_time)

        if entry_ts.tzinfo is None:
            entry_ts = entry_ts.tz_localize(user_timezone)
        else:
            entry_ts = entry_ts.tz_convert(user_timezone)

        if exit_ts.tzinfo is None:
            exit_ts = exit_ts.tz_localize(user_timezone)
        else:
            exit_ts = exit_ts.tz_convert(user_timezone)

        def to_bool(v):
            return v in [True, "true", "True", 1, "1"]

        def to_int(v):
            try:
                return int(float(v)) if v is not None else None
            except:
                return None

        MA_TYPE_MAP = {1: "SMA", 2: "EMA"}

        # ── 1. Compute MAs on FULL df (needs max history) ───────────────
        ma_configs = [
            {"enabled": to_bool(settings.get("MA1_activ")), "type": to_int(settings.get("MA1_type")), "value": to_int(settings.get("MA1_value"))},
            {"enabled": to_bool(settings.get("MA2_activ")), "type": to_int(settings.get("MA2_type")), "value": to_int(settings.get("MA2_value"))},
        ]

        for ma in ma_configs:
            if not ma["enabled"] or not ma["value"] or ma["value"] <= 0:
                continue
            ma_type     = MA_TYPE_MAP.get(ma["type"], "EMA")
            column_name = f"{ma_type}_{ma['value']}"
            if ma_type == "SMA":
                df[column_name] = df["Close"].rolling(ma["value"]).mean()
            else:
                df[column_name] = df["Close"].ewm(span=ma["value"], adjust=False).mean()

        # ── 2. Compute VWAP on FULL df ───────────────────────────────────
        if to_bool(settings.get("VWAP_activ")):
            typical_price     = (df["High"] + df["Low"] + df["Close"]) / 3
            df["_tp_vol"]     = typical_price * df["Volume"]
            df["_date"]       = df.index.date
            df["_cum_tp_vol"] = df.groupby("_date")["_tp_vol"].cumsum()
            df["_cum_vol"]    = df.groupby("_date")["Volume"].cumsum().replace(0, float("nan"))
            df["VWAP"]        = (df["_cum_tp_vol"] / df["_cum_vol"]).ffill()
            df.drop(columns=["_tp_vol", "_date", "_cum_tp_vol", "_cum_vol"], inplace=True)

        # ── 3. Trim to trade window ──────────────────────────────────────
        df = df[
            (df.index >= entry_ts - timedelta(hours=ctx_before)) &
            (df.index <= exit_ts  + timedelta(hours=ctx_after))
        ]

        if df.empty or len(df) < 5:
            print(f"No candles in trade window for {yahoo_symbol}")
            return None

        is_long     = str(side).lower() == "long"
        entry_color = "#26a666" if is_long else "#ef5350"
        exit_color  = "#ef5350" if is_long else "#26a666"

        # ── 4. Build addplots AFTER trim ─────────────────────────────────
        apds = []

        for ma in ma_configs:
            if not ma["enabled"] or not ma["value"] or ma["value"] <= 0:
                continue
            col = f"{MA_TYPE_MAP.get(ma['type'], 'EMA')}_{ma['value']}"
            if col in df.columns:
                apds.append(mpf.make_addplot(df[col], width=1.2))

        if "VWAP" in df.columns:
            apds.append(mpf.make_addplot(df["VWAP"], width=1.2, color="#d47bfd"))

        # ── 5. Per-fill markers ──────────────────────────────────────────
        # Collect all entry/exit prices for hlines
        all_entry_prices = set()
        all_exit_prices  = set()

        def parse_fill_ts(raw):
            ts = pd.Timestamp(str(raw).split(".")[0])  # strip microseconds, treat as naive local time
            if ts.tzinfo is None:
                ts = ts.tz_localize(user_timezone)
            else:
                ts = ts.tz_convert(user_timezone)
            return ts

        if fills:
            for fill in fills:
                try:
                    # Resolve which timestamp/price is entry vs exit per side
                    if is_long:
                        fe_ts = parse_fill_ts(fill["bought_timestamp"])
                        fx_ts = parse_fill_ts(fill["sold_timestamp"])
                        fe_px = float(fill["buy_price"])
                        fx_px = float(fill["sell_price"])
                    else:
                        fe_ts = parse_fill_ts(fill["sold_timestamp"])
                        fx_ts = parse_fill_ts(fill["bought_timestamp"])
                        fe_px = float(fill["sell_price"])
                        fx_px = float(fill["buy_price"])

                    fe_idx = df.index.get_indexer([fe_ts], method="nearest")[0]
                    fx_idx = df.index.get_indexer([fx_ts], method="nearest")[0]

                    # Entry marker
                    apds.append(mpf.make_addplot(
                        [fe_px if i == fe_idx else float("nan") for i in range(len(df))],
                        type="scatter", markersize=90,
                        marker="^" if is_long else "v", color=entry_color
                    ))
                    # Exit marker
                    apds.append(mpf.make_addplot(
                        [fx_px if i == fx_idx else float("nan") for i in range(len(df))],
                        type="scatter", markersize=90,
                        marker="v" if is_long else "^", color=exit_color
                    ))

                    all_entry_prices.add(fe_px)
                    all_exit_prices.add(fx_px)

                except Exception as e:
                    print(f"Marker error for fill: {e}")
                    continue

        else:
            # ── Fallback: single marker for legacy trades without fills ──
            entry_idx = df.index.get_indexer([entry_ts], method="nearest")[0]
            exit_idx  = df.index.get_indexer([exit_ts],  method="nearest")[0]

            apds.append(mpf.make_addplot(
                [entry_price if i == entry_idx else float("nan") for i in range(len(df))],
                type="scatter", markersize=120,
                marker="^" if is_long else "v", color=entry_color
            ))
            apds.append(mpf.make_addplot(
                [exit_price if i == exit_idx else float("nan") for i in range(len(df))],
                type="scatter", markersize=120,
                marker="v" if is_long else "^", color=exit_color
            ))

            all_entry_prices.add(entry_price)
            all_exit_prices.add(exit_price)

        # ── 6. Hlines: one per unique price level ────────────────────────
        hline_prices = list(all_entry_prices) + list(all_exit_prices)
        hline_colors = [entry_color] * len(all_entry_prices) + [exit_color] * len(all_exit_prices)

        hlines = dict(
            hlines=hline_prices,
            colors=hline_colors,
            linestyle="--", linewidths=0.8
        )

        # ── 7. Custom candle style ───────────────────────────────────────
        custom_style = mpf.make_mpf_style(
            base_mpf_style="charles",
            marketcolors=mpf.make_marketcolors(
                up   = "#D1D1D1",
                down = "#7E838C",
                edge = {"up": "#7E838C", "down": "#7E838C"},
                wick = {"up": "#7E838C", "down": "#7E838C"},
                ohlc = "inherit",
                volume = {"up": "#D1D1D1", "down": "#7E838C"},
            ),
            facecolor = "#ffffff",
            figcolor  = "#ffffff",
            gridcolor = "#e0e0e0",
            gridstyle = "--",
            gridaxis  = "both",
        )

        fig, axes = mpf.plot(
            df,
            type="candle",
            style=custom_style,
            addplot=apds,
            hlines=hlines,
            tight_layout=True,
            figsize=(10, 5),
            returnfig=True
        )

        # ── 8. Watermark ─────────────────────────────────────────────────
        axes[0].text(
            0.02, 0.02,
            timeframe,
            transform=axes[0].transAxes,
            fontsize=18,
            color="#b0b0b0",
            alpha=0.6,
            ha="left",
            va="bottom",
            fontweight="bold"
        )

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100)
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")

    except Exception as e:
        import traceback
        print(f"Chart generation failed for {symbol}")
        print(traceback.format_exc())
        return None
# ===== PAGE ROUTES =====
@app.get("/api/fills/<int:trade_id>")
@login_required
def get_fills(trade_id):
    try:
        # Security: verify the trade belongs to this user
        trade_res = (
            supabase_admin.table("trades")
            .select("key_trading_accounts")
            .eq("id", trade_id)
            .execute()
        )
        if not trade_res.data:
            return jsonify({"error": "Trade not found"}), 404

        accounts_res = (
            supabase_admin.table("trading_accounts")
            .select("id")
            .eq("user_id", session["user"]["id"])
            .execute()
        )
        user_account_ids = [a["id"] for a in (accounts_res.data or [])]
        if trade_res.data[0]["key_trading_accounts"] not in user_account_ids:
            return jsonify({"error": "Unauthorized"}), 403

        fills_res = (
            supabase_admin.table("fills")
            .select("*")
            .eq("trade_id", trade_id)
            .order("bought_timestamp")
            .execute()
        )
        return jsonify(fills_res.data or [])

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")

@app.route("/journal")
@login_required
def journal():
    return render_template("journal.html")

@app.route("/charts")
@login_required
def charts():
    return render_template("charts.html")

@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload_file():
    if request.method == "GET":
        return render_template("upload.html")
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if not file.filename.lower().endswith(".csv"):
            return jsonify({"error": "Only CSV files allowed"}), 400

        account_id = request.form.get("account_id")
        if not account_id:
            return jsonify({"error": "No account selected"}), 400

        df = pd.read_csv(file)

        user_id = session["user"]["id"]
        fees_res = (
            supabase_admin.table("fees")
            .select("symbol, fees")
            .eq("user_id", user_id)
            .execute()
        )
        df_fees = pd.DataFrame(fees_res.data or [])

        df_fills = csv_handler(df, df_fees)

        # tag each fill with account_id for later use in confirm
        df_fills["key_trading_accounts"] = account_id

        session["preview_fills"]  = df_fills.to_dict(orient="records")
        session["chart_timeframe"] = request.form.get("chart_timeframe", "5m")

        # send preview without account_id column
        preview = df_fills.drop(columns=["key_trading_accounts", "fees"])

        return jsonify({
            "rows":    preview.to_dict(orient="records"),
            "columns": list(preview.columns)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/confirm_upload", methods=["POST"])
@login_required
def confirm_upload():
    try:
        data   = request.json
        # groups: [{ fillIndices: [0,2,3], label: "Trade 1" }, ...]
        groups = data.get("groups", [])
        fills  = session.get("preview_fills", [])

        if not fills:
            return jsonify({"error": "No fills in session"}), 400
        if not groups:
            return jsonify({"error": "No groups defined"}), 400

        user_id        = session["user"]["id"]
        chart_timeframe = session.get("chart_timeframe", "5m")
        failed_charts  = []
        inserted_trades = []

        for group in groups:
            indices      = group.get("fillIndices", [])
            group_fills  = [fills[i] for i in indices if i < len(fills)]
            if not group_fills:
                continue

            # ── Compute trade-level aggregates ──────────────────────────
            symbol    = group_fills[0]["symbol"]
            account   = group_fills[0]["key_trading_accounts"]
            total_qty = sum(f["qty"] for f in group_fills)
            total_pnl = round(sum(f["pnl"] for f in group_fills), 2)
            total_fees = round(sum(f.get("fees", 0) for f in group_fills), 2)
            gross_pnl = round(total_pnl + total_fees, 2)

            # Determine side: if boughtTimestamp < soldTimestamp → long
            first_fill = group_fills[0]
            side = "long" if first_fill["boughtTimestamp"] < first_fill["soldTimestamp"] else "short"

            # Entry = earliest bought (long) or sold (short) timestamp
            if side == "long":
                timestamps_entry = [f["boughtTimestamp"] for f in group_fills]
                timestamps_exit  = [f["soldTimestamp"]   for f in group_fills]
                prices_entry     = [f["buyPrice"]        for f in group_fills]
                prices_exit      = [f["sellPrice"]       for f in group_fills]
            else:
                timestamps_entry = [f["soldTimestamp"]   for f in group_fills]
                timestamps_exit  = [f["boughtTimestamp"] for f in group_fills]
                prices_entry     = [f["sellPrice"]       for f in group_fills]
                prices_exit      = [f["buyPrice"]        for f in group_fills]

            entry_timestamp = min(timestamps_entry)
            exit_timestamp  = max(timestamps_exit)

            # Weighted average entry/exit price
            avg_entry = round(
                sum(p * f["qty"] for p, f in zip(prices_entry, group_fills)) / total_qty, 4
            )
            avg_exit = round(
                sum(p * f["qty"] for p, f in zip(prices_exit, group_fills)) / total_qty, 4
            )

            # Duration: first entry → last exit
            from datetime import datetime as dt
            entry_dt   = dt.fromisoformat(entry_timestamp)
            exit_dt    = dt.fromisoformat(exit_timestamp)
            delta      = exit_dt - entry_dt
            total_secs = int(delta.total_seconds())
            hours, rem = divmod(total_secs, 3600)
            mins, secs = divmod(rem, 60)
            if hours:
                duration = f"{hours}h {mins}min {secs}sec"
            elif mins:
                duration = f"{mins}min {secs}sec"
            else:
                duration = f"{secs}sec"

            # ── Insert trade ─────────────────────────────────────────────
            trade_row = {
                "symbol":               symbol,
                "entryTimestamp":       entry_timestamp,
                "exitTimestamp":        exit_timestamp,
                "entryPrice":           avg_entry,
                "exitPrice":            avg_exit,
                "qty":                  total_qty,
                "pnl":                  total_pnl,
                "gross_pnl":            gross_pnl,
                "fees":                 total_fees,
                "duration":             duration,
                "side":                 side,
                "key_trading_accounts": account,
            }

            trade_res = supabase_admin.table("trades").insert(trade_row).execute()
            trade     = trade_res.data[0]
            trade_id  = trade["id"]

            # ── Insert fills linked to this trade ────────────────────────
            fill_rows = []
            for f in group_fills:
                fill_rows.append({
                    "trade_id":        trade_id,
                    "buy_fill_id":     f.get("buyFillId"),
                    "sell_fill_id":    f.get("sellFillId"),
                    "qty":             f["qty"],
                    "buy_price":       f["buyPrice"],
                    "sell_price":      f["sellPrice"],
                    "pnl":             f["pnl"],
                    "bought_timestamp": f["boughtTimestamp"],
                    "sold_timestamp":   f["soldTimestamp"],
                    "duration":        f.get("duration"),
                })
            supabase_admin.table("fills").insert(fill_rows).execute()

            # ── Generate chart ───────────────────────────────────────────
            try:
                chart_b64 = generate_chart_base64(
                    symbol      = symbol,
                    entry_time  = entry_dt,
                    exit_time   = exit_dt,
                    entry_price = avg_entry,
                    exit_price  = avg_exit,
                    side        = side,
                    user_id     = user_id,
                    timeframe   = chart_timeframe,
                )
                if chart_b64:
                    supabase_admin.table("trades") \
                        .update({"chart_image": chart_b64}) \
                        .eq("id", trade_id) \
                        .execute()
            except Exception as e:
                print(f"Chart error for trade {trade_id}: {e}")
                failed_charts.append(trade_id)

            inserted_trades.append(trade_id)

        session.pop("preview_fills", None)
        return jsonify({
            "ok":           True,
            "inserted":     len(inserted_trades),
            "failed_charts": failed_charts,
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route("/accounts")
@login_required
def settings():
    return render_template("settings.html")

# ===== API ROUTES =====

@app.get("/api/trades")
@login_required
def api_trades():
    try:
        user_id     = session["user"]["id"]
        account_id  = request.args.get("account")
        date_from   = request.args.get("from")
        date_to     = request.args.get("to")
        strategy_id = request.args.get("strategy")
        setup_ids   = request.args.getlist("setups")

        # ===== GET USER ACCOUNTS =====
        accounts_res = (
            supabase_admin.table("trading_accounts")
            .select("id")
            .eq("user_id", user_id)
            .execute()
        )
        user_account_ids = [a["id"] for a in (accounts_res.data or [])]

        if not user_account_ids:
            return jsonify([])

        # ===== BUILD BASE QUERY =====
        query = (
            supabase_admin.table("trades")
            .select("*")
            .in_("key_trading_accounts", user_account_ids)
        )

        # 🔥 APPLY ACCOUNT FILTER DIRECTLY IN DB
        if account_id:
            query = query.eq("key_trading_accounts", account_id)

        trades_res = query.execute()
        trades = trades_res.data or []

        if not trades:
            return jsonify([])

        trade_ids = [t["id"] for t in trades]

        # ===== FETCH SETUPS (ONLY IF NEEDED) =====
        links_res = (
            supabase_admin.table("trade_setup")
            .select("key_trade_id, key_setup_id")
            .in_("key_trade_id", trade_ids)
            .execute()
        )
        links = links_res.data or []

        setups_by_trade = {}
        for l in links:
            setups_by_trade.setdefault(l["key_trade_id"], []).append(l["key_setup_id"])

        # ===== FETCH EMOTIONS =====
        emotions_res = (
            supabase_admin.table("emotions_trades")
            .select("trade_id, emotions_id")
            .in_("trade_id", trade_ids)
            .execute()
        )
        emotion_links = emotions_res.data or []

        emotions_by_trade = {}
        for e in emotion_links:
            emotions_by_trade.setdefault(e["trade_id"], []).append(e["emotions_id"])

        # ===== MERGE DATA =====
        for t in trades:
            t["setups"]   = setups_by_trade.get(t["id"], [])
            t["emotions"] = emotions_by_trade.get(t["id"], [])

        # ===== FINAL FILTERING (date, strategy, setups) =====
        trades = filter_trades(
            trades,
            date_from=date_from,
            date_to=date_to,
            strategy_id=strategy_id,
            setup_ids=setup_ids,
        )

        return jsonify(trades)

    except Exception as e:
        print("api/trades error:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/yahoo/<symbol>")
@login_required
def fetch_yahoo(symbol):
    try:
        yahoo_symbol = symbol if symbol.endswith("=F") else f"{symbol}=F"
        date_str     = request.args.get("date")
        interval     = request.args.get("interval", "5m")
        range_param  = request.args.get("range", None)

        if date_str:
            trade_date = datetime.strptime(date_str, "%Y-%m-%d")
            period1    = int((trade_date - timedelta(days=1)).timestamp())
            period2    = int((trade_date + timedelta(days=1)).timestamp())
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
                f"?interval={interval}&period1={period1}&period2={period2}"
            )
        else:
            r = range_param or "1d"
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
                f"?interval={interval}&range={r}"
            )

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept":     "application/json",
            "Referer":    "https://finance.yahoo.com",
        }

        r = requests.get(url, headers=headers, timeout=10)
        if not r.ok:
            return jsonify({"error": r.status_code, "body": r.text[:500]}), 502

        return jsonify(r.json())

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.delete("/api/trades")
@login_required
def delete_trades():
    data = request.json
    ids  = data.get("ids", [])

    if not ids:
        return {"error": "No IDs provided"}, 400

    # Cascade delete junction tables first
    supabase_admin.table("emotions_trades").delete().in_("trade_id", ids).execute()
    supabase_admin.table("trade_setup").delete().in_("key_trade_id", ids).execute()
    supabase_admin.table("trades").delete().in_("id", ids).execute()
    return {"deleted": len(ids)}

@app.get("/api/accounts")
@login_required
def get_accounts():
    user_id  = session["user"]["id"]
    response = (
        supabase_admin.table("trading_accounts")
        .select("id, name")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )
    return jsonify(response.data or [])

@app.post("/api/accounts")
@login_required
def add_account():
    data            = request.json
    data["user_id"] = session["user"]["id"]
    supabase_admin.table("trading_accounts").insert(data).execute()
    return {"ok": True}

@app.patch("/api/accounts/<id>")
@login_required
def update_account(id):
    supabase_admin.table("trading_accounts").update(request.json).eq("id", id).execute()
    return {"ok": True}

@app.delete("/api/accounts/<id>")
@login_required
def delete_account(id):
    user_id = session["user"]["id"]

    # 1. Get all trades linked to this account
    trades_res = (
        supabase_admin.table("trades")
        .select("id")
        .eq("key_trading_accounts", id)
        .execute()
    )
    trade_ids = [t["id"] for t in (trades_res.data or [])]

    # 2. Cascade delete junction tables first
    if trade_ids:
        supabase_admin.table("emotions_trades").delete().in_("trade_id", trade_ids).execute()
        supabase_admin.table("trade_setup").delete().in_("key_trade_id", trade_ids).execute()
        supabase_admin.table("trades").delete().in_("id", trade_ids).execute()

    # 3. Now safe to delete the account
    supabase_admin.table("trading_accounts").delete().eq("id", id).eq("user_id", user_id).execute()
    return {"ok": True}

@app.patch("/api/trades/<id>")
@login_required
def update_trade(id):
    data     = request.json
    response = supabase_admin.table("trades").update(data).eq("id", id).execute()

    if response.data is None:
        return {"error": "Update failed"}, 400
    return {"ok": True}

# ===== STRATEGIES =====

@app.get("/api/strategies")
@login_required
def get_strategies():
    try:
        user_id  = session["user"]["id"]
        response = (
            supabase_admin.table("strategies")
            .select("id, strategy_name, color")
            .eq("user_id", user_id)
            .order("strategy_name")
            .execute()
        )
        return jsonify(response.data or [])
    except Exception as e:
        print("Supabase /api/strategies error:", e)
        return jsonify({"error": str(e)}), 500

@app.post("/api/strategies")
@login_required
def add_strategy():
    data = request.json
    data["user_id"] = session["user"]["id"]
    supabase_admin.table("strategies").insert(data).execute()
    return {"ok": True}

@app.patch("/api/strategies/<id>")
@login_required
def update_strategy(id):
    supabase_admin.table("strategies").update(request.json).eq("id", id).execute()
    return {"ok": True}

@app.delete("/api/strategies/<id>")
@login_required
def delete_strategy(id):
    supabase_admin.table("strategies").delete().eq("id", id).execute()
    return {"ok": True}

@app.post("/api/trades/bulk-strategy")
@login_required
def bulk_strategy():
    data = request.json

    ids = data.get("ids", [])
    strategy_id = data.get("strategy_id")

    supabase_admin.table("trades") \
        .update({"key_strategies_id": strategy_id}) \
        .in_("id", ids) \
        .execute()

    return {"ok": True}

# ===== SETUPS =====

@app.get("/api/setups")
@login_required
def get_setups():
    user_id  = session["user"]["id"]
    response = (
        supabase_admin.table("setups")
        .select("id, setup_name, color")
        .eq("user_id", user_id)
        .order("setup_name")
        .execute()
    )
    return jsonify(response.data or [])

@app.post("/api/setups")
@login_required
def add_setup():
    data = request.json
    data["user_id"] = session["user"]["id"]
    response = supabase_admin.table("setups").insert(data).execute()
    return jsonify(response.data[0])

@app.patch("/api/setups/<id>")
@login_required
def update_setup(id):
    supabase_admin.table("setups") \
        .update(request.json) \
        .eq("id", id) \
        .eq("user_id", session["user"]["id"]) \
        .execute()
    return {"ok": True}

@app.delete("/api/setups/<id>")
@login_required
def delete_setup(id):
    supabase_admin.table("setups") \
        .delete() \
        .eq("id", id) \
        .eq("user_id", session["user"]["id"]) \
        .execute()
    return {"ok": True}

@app.post("/api/trades/bulk-setups")
@login_required
def bulk_setups():
    data = request.json

    ids = data.get("ids", [])
    add = data.get("add", [])
    remove = data.get("remove", [])

    inserts = []

    for trade_id in ids:
        for setup_id in add:
            inserts.append({
                "key_trade_id": trade_id,
                "key_setup_id": setup_id
            })

    if inserts:
        supabase_admin.table("trade_setup") \
            .upsert(inserts) \
            .execute()

    for setup_id in remove:
        supabase_admin.table("trade_setup") \
            .delete() \
            .in_("key_trade_id", ids) \
            .eq("key_setup_id", setup_id) \
            .execute()

    return {"ok": True}

# ===== TRADE SETUPS (junction) =====

@app.post("/api/trade_setups")
@login_required
def add_trade_setup():
    data     = request.json
    response = supabase_admin.table("trade_setup").insert({
        "key_trade_id": data["key_trade_id"],
        "key_setup_id": data["key_setup_id"]
    }).execute()
    return jsonify(response.data[0])

@app.get("/api/trade_setups")
@login_required
def get_trade_setups():
    try:
        user_id = session["user"]["id"]

        # get user's trades
        trade_ids = get_user_trade_ids(user_id)
        if not trade_ids:
            return jsonify([])

        res = (
            supabase_admin.table("trade_setup")
            .select("*")
            .in_("key_trade_id", trade_ids)
            .execute()
        )

        return jsonify(res.data or [])
    except Exception as e:
        print("GET /api/trade_setups error:", e)
        return jsonify({"error": str(e)}), 500

@app.delete("/api/trade_setups")
@login_required
def delete_trade_setup():
    data     = request.json
    trade_id = data.get("trade_id")
    setup_id = data.get("setup_id")

    if not trade_id or not setup_id:
        return {"error": "Missing trade_id or setup_id"}, 400

    supabase_admin.table("trade_setup").delete().eq("key_trade_id", trade_id).eq("key_setup_id", setup_id).execute()
    return {"ok": True}

# ===== EMOTIONS =====
@app.get("/api/emotions")
@login_required
def get_emotions():
    try:
        user_id  = session["user"]["id"]
        response = (
            supabase_admin.table("emotions")
            .select("id, emotion, color")
            .eq("user_id", user_id)
            .order("emotion")
            .execute()
        )
        return jsonify(response.data or [])
    except Exception as e:
        print("Supabase /api/emotions error:", e)
        return jsonify({"error": str(e)}), 500

@app.post("/api/emotions")
@login_required
def add_emotion():
    try:
        data = request.json
        data["user_id"] = session["user"]["id"]
        response = supabase_admin.table("emotions").insert(data).execute()
        return jsonify(response.data[0])
    except Exception as e:
        print("Supabase POST /api/emotions error:", e)
        return jsonify({"error": str(e)}), 500

@app.patch("/api/emotions/<id>")
@login_required
def update_emotion(id):
    try:
        supabase_admin.table("emotions") \
            .update(request.json) \
            .eq("id", id) \
            .eq("user_id", session["user"]["id"]) \
            .execute()
        return {"ok": True}
    except Exception as e:
        print(f"Supabase PATCH /api/emotions/{id} error:", e)
        return jsonify({"error": str(e)}), 500

@app.delete("/api/emotions/<id>")
@login_required
def delete_emotion(id):
    try:
        supabase_admin.table("emotions") \
            .delete() \
            .eq("id", id) \
            .eq("user_id", session["user"]["id"]) \
            .execute()
        return {"ok": True}
    except Exception as e:
        print(f"Supabase DELETE /api/emotions/{id} error:", e)
        return jsonify({"error": str(e)}), 500

@app.post("/api/trades/bulk-emotions")
@login_required
def bulk_emotions():
    data = request.json

    ids = data.get("ids", [])
    add = data.get("add", [])
    remove = data.get("remove", [])

    inserts = []

    for trade_id in ids:
        for emotion_id in add:
            inserts.append({
                "trade_id": trade_id,
                "emotions_id": emotion_id
            })

    if inserts:
        supabase_admin.table("emotions_trades") \
            .upsert(inserts) \
            .execute()

    for emotion_id in remove:
        supabase_admin.table("emotions_trades") \
            .delete() \
            .in_("trade_id", ids) \
            .eq("emotions_id", emotion_id) \
            .execute()

    return {"ok": True}

# ===== EMOTIONS TRADES (junction) =====

@app.post("/api/emotions_trades")
@login_required
def add_emotion_trade():
    data     = request.json
    response = supabase_admin.table("emotions_trades").insert({
        "trade_id":    data["trade_id"],
        "emotions_id": data["emotions_id"]
    }).execute()
    return jsonify(response.data[0])

@app.get("/api/emotions_trades")
@login_required
def get_emotions_trades():
    try:
        user_id = session["user"]["id"]

        trade_ids = get_user_trade_ids(user_id)
        if not trade_ids:
            return jsonify([])

        res = (
            supabase_admin.table("emotions_trades")
            .select("*")
            .in_("trade_id", trade_ids)
            .execute()
        )

        return jsonify(res.data or [])
    except Exception as e:
        print("GET /api/emotions_trades error:", e)
        return jsonify({"error": str(e)}), 500

@app.delete("/api/emotions_trades")
@login_required
def delete_emotion_trade():
    data       = request.json
    trade_id   = data.get("trade_id")
    emotion_id = data.get("emotions_id")

    if not trade_id or not emotion_id:
        return {"error": "Missing trade_id or emotions_id"}, 400

    supabase_admin.table("emotions_trades") \
        .delete() \
        .eq("trade_id", trade_id) \
        .eq("emotions_id", emotion_id) \
        .execute()
    return {"ok": True}

# ============== check if timezone and account created =================== #
@app.get("/api/onboarding-status")
@login_required
def onboarding_status():
    user_id = session["user"]["id"]

    accounts_res = (
        supabase_admin.table("trading_accounts")
        .select("id")
        .eq("user_id", user_id)
        .execute()
    )

    settings_res = (
        supabase_admin.table("settings")
        .select("timezone")
        .eq("user_id", user_id)
        .execute()
    )

    has_account = len(accounts_res.data or []) > 0

    timezone = None
    if settings_res.data:
        timezone = settings_res.data[0].get("timezone")

    return jsonify({
        "has_account": has_account,
        "has_timezone": bool(timezone),
        "timezone": timezone
    })

# ===== FEES =====

@app.get("/api/fees")
@login_required
def get_fees():
    try:
        user_id = session["user"]["id"]
        response = (
            supabase_admin.table("fees")
            .select("*")
            .eq("user_id", user_id)
            .order("id")
            .execute()
        )
        return jsonify(response.data or [])
    except Exception as e:
        print("Supabase /api/fees error:", e)
        return jsonify({"error": str(e)}), 500

@app.post("/api/fees")
@login_required
def add_fee():
    try:
        data = request.json
        data["user_id"] = session["user"]["id"]
        response = supabase_admin.table("fees").insert(data).execute()
        return jsonify(response.data[0])
    except Exception as e:
        print("Supabase POST /api/fees error:", e)
        return jsonify({"error": str(e)}), 500

@app.patch("/api/fees/<id>")
@login_required
def update_fee(id):
    try:
        supabase_admin.table("fees") \
            .update(request.json) \
            .eq("id", id) \
            .eq("user_id", session["user"]["id"]) \
            .execute()
        return {"ok": True}
    except Exception as e:
        print(f"Supabase PATCH /api/fees/{id} error:", e)
        return jsonify({"error": str(e)}), 500

@app.delete("/api/fees/<id>")
@login_required
def delete_fee(id):
    try:
        supabase_admin.table("fees") \
            .delete() \
            .eq("id", id) \
            .eq("user_id", session["user"]["id"]) \
            .execute()
        return {"ok": True}
    except Exception as e:
        print(f"Supabase DELETE /api/fees/{id} error:", e)
        return jsonify({"error": str(e)}), 500

@app.post("/api/trades/apply-fees")
@login_required
def apply_fees_bulk():
    try:
        data = request.json
        ids  = data.get("ids", [])

        if not ids:
            return jsonify({"error": "No IDs provided"}), 400

        user_id = session["user"]["id"]

        # ===== GET USER FEES =====
        fees_res = (
            supabase_admin.table("fees")
            .select("symbol, fees")
            .eq("user_id", user_id)
            .execute()
        )
        fees_map = {f["symbol"]: f["fees"] for f in (fees_res.data or [])}

        # ===== GET TRADES =====
        trades_res = (
            supabase_admin.table("trades")
            .select("*")
            .in_("id", ids)
            .execute()
        )

        trades = trades_res.data or []
        updated = []

        for t in trades:
            symbol = t["symbol"]
            fee    = fees_map.get(symbol, 0)

            qty = float(t.get("qty") or 1)

            # fees table = round-trip per contract
            new_fees = fee

            gross_pnl = float(t.get("gross_pnl") or 0)

            # ✅ recompute from source of truth
            pnl = gross_pnl - (qty * new_fees)

            supabase_admin.table("trades").update({
                "fees": new_fees,
                "pnl": pnl
            }).eq("id", t["id"]).execute()

            updated.append({
                "id": t["id"],
                "fees": new_fees,
                "pnl": pnl
            })

        return jsonify(updated)

    except Exception as e:
        print("apply fees error:", e)
        return jsonify({"error": str(e)}), 500

# ===== SETTINGS =====

@app.get("/api/settings")
@login_required
def get_settings():
    try:
        user_id  = session["user"]["id"]
        response = (
            supabase_admin.table("settings")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        data = response.data
        return jsonify(data[0] if data else {})
    except Exception as e:
        print("Supabase GET /api/settings error:", e)
        return jsonify({}), 200

@app.patch("/api/settings")
@login_required
def update_settings():
    try:
        user_id = session["user"]["id"]
        data    = request.json

        # 1. check if settings exist
        existing = (
            supabase_admin.table("settings")
            .select("id")
            .eq("user_id", user_id)
            .execute()
        )

        if existing.data:
            supabase_admin.table("settings") \
                .update(data) \
                .eq("user_id", user_id) \
                .execute()
        else:
            data["user_id"] = user_id
            supabase_admin.table("settings") \
                .insert(data) \
                .execute()

        # 2. IMPORTANT: sync timezone into session immediately
        if "timezone" in data:
            session["timezone"] = data["timezone"]

        return jsonify({"ok": True})

    except Exception as e:
        print("Supabase PATCH /api/settings error:", e)
        return jsonify({"error": str(e)}), 500

# ===== SIGNUP =====
# Add this route to app.py, right after the /login route.

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("user"):
        return redirect(url_for("dashboard"))

    error   = None
    success = None
    prefill_email = None

    if request.method == "POST":
        email            = request.form.get("email", "").strip()
        password         = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        prefill_email    = email

        # ── Client-side validation ──────────────────────────────────────
        if not email or not password:
            error = "Email and password are required."
        elif password != confirm_password:
            error = "Passwords do not match."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        else:
            try:
                res = supabase.auth.sign_up({"email": email, "password": password})

                # Supabase returns a user even when email confirmation is
                # required — check whether the session is already active.
                if res.session:
                    # Email confirmation disabled → log straight in
                    session["user"] = {
                        "id":    res.user.id,
                        "email": res.user.email,
                    }
                    return redirect(url_for("dashboard"))
                else:
                    # Email confirmation enabled → tell the user to check inbox
                    success = f"Account created! Check {email} for a confirmation link."

            except Exception as e:
                msg = str(e).lower()
                if "already registered" in msg or "already exists" in msg:
                    error = "An account with this email already exists."
                else:
                    error = "Could not create account. Please try again."

    return render_template(
        "signup.html",
        error=error,
        success=success,
        prefill_email=prefill_email,
    )

@app.post("/api/trades/generate-charts")
@login_required
def generate_charts():
    try:
        data      = request.json
        ids       = data.get("ids", [])
        timeframe = data.get("timeframe", "5m")

        if not ids:
            return jsonify({"error": "No trade IDs"}), 400

        trades_res = (
            supabase_admin.table("trades")
            .select("*")
            .in_("id", ids)
            .execute()
        )

        trades = trades_res.data or []

        # Fetch ALL fills for these trades in one query
        fills_res = (
            supabase_admin.table("fills")
            .select("trade_id, buy_price, sell_price, bought_timestamp, sold_timestamp")
            .in_("trade_id", ids)
            .execute()
        )

        # Group fills by trade_id
        fills_by_trade = {}
        for f in (fills_res.data or []):
            tid = f["trade_id"]
            fills_by_trade.setdefault(tid, []).append(f)

        failed  = []
        updated = []
        user_id = session["user"]["id"]

        for trade in trades:
            try:
                trade_fills = fills_by_trade.get(trade["id"]) or None

                chart_b64 = generate_chart_base64(
                    symbol      = trade["symbol"],
                    entry_time  = datetime.fromisoformat(trade["entryTimestamp"]),
                    exit_time   = datetime.fromisoformat(trade["exitTimestamp"]),
                    entry_price = float(trade["entryPrice"]),
                    exit_price  = float(trade["exitPrice"]),
                    side        = trade["side"],
                    user_id     = user_id,
                    timeframe   = timeframe,
                    fills       = trade_fills,   # None for legacy trades → single marker fallback
                )

                if chart_b64:
                    supabase_admin.table("trades") \
                        .update({"chart_image": chart_b64}) \
                        .eq("id", trade["id"]) \
                        .execute()
                    updated.append(trade["id"])
                else:
                    failed.append(trade["id"])

            except Exception as e:
                print(f"Chart error {trade['id']}: {e}")
                failed.append(trade["id"])

        return jsonify({
            "ok":      True,
            "updated": updated,
            "failed":  failed,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/logs")
@login_required
def logs():
    return render_template("logs.html")

@app.get("/api/logs")
@login_required
def get_logs():
    try:
        user_id = session["user"]["id"]
        year    = request.args.get("year")
        month   = request.args.get("month")

        query = (
            supabase_admin.table("trading_logs")
            .select("*")
            .eq("user_id", user_id)
        )

        if year and month:
            # filter by month: date >= YYYY-MM-01 and date < next month
            from datetime import date
            y, m = int(year), int(month)
            date_from = f"{y}-{m:02d}-01"
            if m == 12:
                date_to = f"{y+1}-01-01"
            else:
                date_to = f"{y}-{m+1:02d}-01"
            query = query.gte("date", date_from).lt("date", date_to)

        res = query.order("date").execute()
        return jsonify(res.data or [])

    except Exception as e:
        print("GET /api/logs error:", e)
        return jsonify({"error": str(e)}), 500


@app.post("/api/logs")
@login_required
def create_log():
    try:
        data            = request.json
        data["user_id"] = session["user"]["id"]
        res = supabase_admin.table("trading_logs").insert(data).execute()
        return jsonify(res.data[0])
    except Exception as e:
        print("POST /api/logs error:", e)
        return jsonify({"error": str(e)}), 500


@app.patch("/api/logs/<id>")
@login_required
def update_log(id):
    try:
        user_id = session["user"]["id"]
        res = (
            supabase_admin.table("trading_logs")
            .update(request.json)
            .eq("id", id)
            .eq("user_id", user_id)   # ensures users can only edit their own
            .execute()
        )
        return jsonify({"ok": True})
    except Exception as e:
        print(f"PATCH /api/logs/{id} error:", e)
        return jsonify({"error": str(e)}), 500


@app.get("/api/trades/summary")
@login_required
def trades_summary():
    """Returns [{date, trades, pnl}] for a given month — used by the logs page footer."""
    try:
        user_id = session["user"]["id"]
        year    = request.args.get("year")
        month   = request.args.get("month")

        # get all account IDs for this user
        accounts_res = (
            supabase_admin.table("trading_accounts")
            .select("id")
            .eq("user_id", user_id)
            .execute()
        )
        account_ids = [a["id"] for a in (accounts_res.data or [])]
        if not account_ids:
            return jsonify([])

        query = (
            supabase_admin.table("trades")
            .select("entryTimestamp, pnl")
            .in_("key_trading_accounts", account_ids)
        )

        if year and month:
            from datetime import date
            y, m = int(year), int(month)
            date_from = f"{y}-{m:02d}-01"
            date_to   = f"{y+1}-01-01" if m == 12 else f"{y}-{m+1:02d}-01"
            query = query.gte("entryTimestamp", date_from).lt("entryTimestamp", date_to)

        res    = query.execute()
        trades = res.data or []

        # group by date
        from collections import defaultdict
        by_date = defaultdict(lambda: {"trades": 0, "pnl": 0.0})
        for t in trades:
            # entryTimestamp is "YYYY-MM-DD HH:MM:SS" or ISO string
            date_str = str(t["entryTimestamp"])[:10]
            by_date[date_str]["trades"] += 1
            by_date[date_str]["pnl"]    += float(t["pnl"] or 0)

        result = [
            {"date": d, "trades": v["trades"], "pnl": round(v["pnl"], 2)}
            for d, v in sorted(by_date.items())
        ]
        return jsonify(result)

    except Exception as e:
        print("GET /api/trades/summary error:", e)
        return jsonify({"error": str(e)}), 500

# ===== ENTRY POINT =====
if __name__ == "__main__":
    app.run(debug=True)