from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

from market_data import MarketDataError, collect_snapshot, evaluate_regime

app = Flask(__name__)
CORS(app)

basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, "instance")
os.makedirs(instance_path, exist_ok=True)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(instance_path, "database.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class Analysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    cheap_price = db.Column(db.Float, nullable=False)
    hold_price = db.Column(db.Float, nullable=False)
    expensive_price = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            "date": self.date.strftime("%Y-%m-%d"),
            "cheap_price": self.cheap_price,
            "hold_price": self.hold_price,
            "expensive_price": self.expensive_price,
        }


class MarketSnapshot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trading_date = db.Column(db.String(8), nullable=False, unique=True, index=True)
    collected_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    foreign_spot_net_twd = db.Column(db.Float, nullable=False)
    foreign_futures_long = db.Column(db.Integer, nullable=False)
    foreign_futures_short = db.Column(db.Integer, nullable=False)
    foreign_futures_net = db.Column(db.Integer, nullable=False)
    margin_balance_twd = db.Column(db.Float, nullable=False)
    taiex_close = db.Column(db.Float, nullable=False)
    taiex_ma20 = db.Column(db.Float, nullable=False)
    taiex_new_20d_low = db.Column(db.Boolean, nullable=False)

    def to_dict(self):
        return {
            "date": self.trading_date,
            "collected_at": self.collected_at.isoformat() + "Z",
            "foreign_spot_net_twd": self.foreign_spot_net_twd,
            "foreign_futures_long": self.foreign_futures_long,
            "foreign_futures_short": self.foreign_futures_short,
            "foreign_futures_net": self.foreign_futures_net,
            "margin_balance_twd": self.margin_balance_twd,
            "taiex_close": self.taiex_close,
            "taiex_ma20": self.taiex_ma20,
            "taiex_new_20d_low": self.taiex_new_20d_low,
        }


def _market_history(limit=60, before_date=None):
    query = MarketSnapshot.query
    if before_date:
        query = query.filter(MarketSnapshot.trading_date < before_date)
    rows = query.order_by(MarketSnapshot.trading_date.desc()).limit(limit).all()
    return list(reversed(rows))


def _dashboard_payload(latest, days=60):
    previous = _market_history(limit=5, before_date=latest.trading_date)
    history = _market_history(limit=days)
    return {
        "latest": latest.to_dict(),
        "signal": evaluate_regime(latest, previous),
        "history": [row.to_dict() for row in history],
        "sources": {
            "foreign_spot": "TWSE BFI82U",
            "margin": "TWSE MI_MARGN",
            "foreign_futures": "TAIFEX institutional futures contracts",
            "taiex": "Yahoo Finance ^TWII (price confirmation only)",
        },
        "rules_version": "tw-market-regime-v1",
    }


@app.route("/api/market/dashboard")
def market_dashboard():
    days = min(max(request.args.get("days", 60, type=int), 5), 120)
    latest = MarketSnapshot.query.order_by(MarketSnapshot.trading_date.desc()).first()
    if latest is None:
        return jsonify({"error": "尚無市場資料，請先執行更新"}), 404
    return jsonify(_dashboard_payload(latest, days))


@app.route("/api/market/refresh", methods=["POST"])
def refresh_market():
    try:
        data = collect_snapshot()
    except MarketDataError as exc:
        return jsonify({"error": str(exc)}), 502

    row = MarketSnapshot.query.filter_by(trading_date=data["date"]).first()
    if row is None:
        row = MarketSnapshot(trading_date=data["date"])
        db.session.add(row)
    for field in (
        "foreign_spot_net_twd", "foreign_futures_long", "foreign_futures_short",
        "foreign_futures_net", "margin_balance_twd", "taiex_close", "taiex_ma20",
        "taiex_new_20d_low",
    ):
        setattr(row, field, data[field])
    row.collected_at = datetime.utcnow()
    db.session.commit()
    return jsonify(_dashboard_payload(row))


@app.route("/api/stock_history/<ticker>")
def stock_history(ticker):
    period = request.args.get("period", "1y")
    hist = yf.Ticker(ticker).history(period=period)
    if hist.empty:
        return jsonify({"error": "Ticker not found or no data available"}), 404
    hist.reset_index(inplace=True)
    hist["Date"] = hist["Date"].dt.strftime("%Y-%m-%d")
    return jsonify(hist.to_dict("records"))


def analyze_stock(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info
    forward_eps = info.get("forwardEps")
    if not forward_eps:
        return {"error": "Forward EPS not available"}
    hist = stock.history(period="10y")
    hist.index = hist.index.tz_localize(None)
    quarterly_financials = stock.quarterly_financials
    if quarterly_financials.empty or hist.empty:
        return {"error": "Not enough historical data to calculate P/E ratio"}
    if "Basic EPS" not in quarterly_financials.index:
        return {"error": "Basic EPS not available in financial data"}

    # yfinance usually returns newest quarter first; sort oldest-to-newest before TTM rolling.
    quarterly_eps = quarterly_financials.loc["Basic EPS"].sort_index()
    ttm_eps = quarterly_eps.rolling(window=4).sum()
    pe_ratios = []
    for date, ttm_eps_value in ttm_eps.dropna().items():
        if ttm_eps_value <= 0:
            continue
        price_period = hist.loc[(hist.index > date) & (hist.index <= date + pd.Timedelta(days=30))]
        if not price_period.empty:
            pe_ratios.append(price_period["Close"].mean() / ttm_eps_value)
    if not pe_ratios:
        return {"error": "Could not calculate historical P/E ratios"}

    # Percentiles reduce the effect of one-off extreme valuations.
    pe_low, pe_mid, pe_high = np.percentile(pe_ratios, [20, 50, 80])
    current_price = info.get("currentPrice") or hist["Close"].iloc[-1]
    return {
        "ticker": ticker.upper(),
        "currentPrice": round(current_price, 2),
        "forwardEps": forward_eps,
        "historicalPeRatio": {
            "min": round(pe_low, 2), "mean": round(pe_mid, 2), "max": round(pe_high, 2)
        },
        "valuation": {
            "cheap": round(forward_eps * pe_low, 2),
            "hold": round(forward_eps * pe_mid, 2),
            "expensive": round(forward_eps * pe_high, 2),
        },
    }


@app.route("/api/analyze/<ticker>")
def analyze(ticker):
    result = analyze_stock(ticker)
    if "error" in result:
        return jsonify(result), 404
    valuation = result["valuation"]
    db.session.add(Analysis(
        ticker=result["ticker"], cheap_price=valuation["cheap"],
        hold_price=valuation["hold"], expensive_price=valuation["expensive"],
    ))
    db.session.commit()
    return jsonify(result)


@app.route("/api/analysis_history/<ticker>")
def analysis_history(ticker):
    analyses = Analysis.query.filter_by(ticker=ticker.upper()).order_by(Analysis.date.desc()).all()
    return jsonify([analysis.to_dict() for analysis in analyses])


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=int(os.getenv("PORT", "5001")))
