from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
CORS(app) # 允許所有來源的跨域請求

# Database Configuration
basedir = os.path.abspath(os.path.dirname(__file__))
# Ensure the instance folder exists
instance_path = os.path.join(basedir, 'instance')
os.makedirs(instance_path, exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_path, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Database Model ---
class Analysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    cheap_price = db.Column(db.Float, nullable=False)
    hold_price = db.Column(db.Float, nullable=False)
    expensive_price = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            'date': self.date.strftime('%Y-%m-%d'),
            'cheap_price': self.cheap_price,
            'hold_price': self.hold_price,
            'expensive_price': self.expensive_price
        }

@app.route('/api/stock_history/<ticker>')
def stock_history(ticker):
    """
    獲取指定股票的歷史股價。
    支持的期間參數 (period): 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
    """
    # 從 URL 查詢參數中獲取 'period'，如果不存在則預設為 '1y'
    period = request.args.get('period', '1y')

    stock = yf.Ticker(ticker)

    # 使用傳入的 period 參數獲取歷史數據
    hist = stock.history(period=period)

    if hist.empty:
        return jsonify({"error": "Ticker not found or no data available"}), 404

    # 將索引 (日期) 重設為一個欄位
    hist.reset_index(inplace=True)

    # 將日期格式化為 YYYY-MM-DD
    hist['Date'] = hist['Date'].dt.strftime('%Y-%m-%d')

    # 將數據轉換為字典列表，方便前端處理
    data = hist.to_dict("records")

    return jsonify(data)

def analyze_stock(ticker):
    """
    分析股票並提供基於本益比的估價。
    """
    stock = yf.Ticker(ticker)
    info = stock.info

    # 1. 獲取預估 EPS
    forward_eps = info.get('forwardEps')
    if not forward_eps:
        return {"error": "Forward EPS not available"}

    # 2. 獲取歷史數據來計算本益比區間
    # 獲取最長歷史數據
    hist = stock.history(period="10y")
    # 移除時區資訊，以避免比較錯誤
    hist.index = hist.index.tz_localize(None)

    # 獲取季度財報
    quarterly_financials = stock.quarterly_financials

    if quarterly_financials.empty or hist.empty:
        return {"error": "Not enough historical data to calculate P/E ratio"}

    # 提取 Basic EPS
    if 'Basic EPS' not in quarterly_financials.index:
        return {"error": "Basic EPS not available in financial data"}

    quarterly_eps = quarterly_financials.loc['Basic EPS']

    # 計算 TTM EPS (最近12個月)
    ttm_eps = quarterly_eps.rolling(window=4).sum()

    pe_ratios = []

    # 遍歷每個財報日期
    for date, ttm_eps_value in ttm_eps.dropna().items():
        if ttm_eps_value <= 0:
            continue

        # 找到財報日期後一個月的股價平均值，來代表當時的市場價格
        start_date = date
        end_date = date + pd.Timedelta(days=30)

        # 篩選出該區間的股價
        mask = (hist.index > start_date) & (hist.index <= end_date)
        price_period = hist.loc[mask]

        if not price_period.empty:
            avg_price = price_period['Close'].mean()
            pe_ratio = avg_price / ttm_eps_value
            pe_ratios.append(pe_ratio)

    if not pe_ratios:
        return {"error": "Could not calculate historical P/E ratios"}

    # 3. 計算本益比區間
    pe_min = np.min(pe_ratios)
    pe_mean = np.mean(pe_ratios)
    pe_max = np.max(pe_ratios)

    # 4. 計算估價
    cheap_price = forward_eps * pe_min
    hold_price = forward_eps * pe_mean
    expensive_price = forward_eps * pe_max

    current_price = info.get('currentPrice') or hist['Close'].iloc[-1]

    return {
        "ticker": ticker.upper(),
        "currentPrice": round(current_price, 2),
        "forwardEps": forward_eps,
        "historicalPeRatio": {
            "min": round(pe_min, 2),
            "mean": round(pe_mean, 2),
            "max": round(pe_max, 2)
        },
        "valuation": {
            "cheap": round(cheap_price, 2),
            "hold": round(hold_price, 2),
            "expensive": round(expensive_price, 2)
        }
    }

@app.route('/api/analyze/<ticker>')
def analyze(ticker):
    """
    接收股票代碼並回傳分析結果，並將結果儲存到數據庫
    """
    result = analyze_stock(ticker)
    if "error" in result:
        return jsonify(result), 404

    # --- Save to Database ---
    valuation = result['valuation']
    new_analysis = Analysis(
        ticker=result['ticker'],
        cheap_price=valuation['cheap'],
        hold_price=valuation['hold'],
        expensive_price=valuation['expensive']
    )
    db.session.add(new_analysis)
    db.session.commit()

    return jsonify(result)

@app.route('/api/analysis_history/<ticker>')
def analysis_history(ticker):
    """
    查詢指定股票的歷史分析紀錄
    """
    analyses = Analysis.query.filter_by(ticker=ticker.upper()).order_by(Analysis.date.desc()).all()
    return jsonify([analysis.to_dict() for analysis in analyses])

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)
