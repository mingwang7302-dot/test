import React, { useCallback, useEffect, useState } from 'react';
import { Line } from 'react-chartjs-2';
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend } from 'chart.js';
import apiClient from './api';
import MarketDashboard from './MarketDashboard';
import './App.css';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

function StockValuation() {
  const [ticker, setTicker] = useState('2330.TW');
  const [activePeriod, setActivePeriod] = useState('1y');
  const [chartData, setChartData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const normalizedTicker = (value) => {
    const clean = value.trim().toUpperCase();
    return /^\d{4}$/.test(clean) ? `${clean}.TW` : clean;
  };

  const fetchChartData = useCallback(async () => {
    if (!ticker) return;
    setLoading(true); setError(null);
    try {
      const [prices, analyses] = await Promise.all([
        apiClient.get(`/stock_history/${ticker}?period=${activePeriod}`),
        apiClient.get(`/analysis_history/${ticker}`),
      ]);
      const labels = prices.data.map(row => row.Date);
      const latest = analyses.data.length ? analyses.data[0] : null;
      const lines = { cheap: [], hold: [], expensive: [] };
      labels.forEach(() => {
        Object.keys(lines).forEach(key => lines[key].push(latest ? latest[`${key}_price`] : null));
      });
      setChartData({ labels, datasets: [
        { label: `${ticker} 收盤價`, data: prices.data.map(row => row.Close), borderColor: '#26a69a' },
        { label: '便宜價', data: lines.cheap, borderColor: '#66bb6a', borderDash: [5, 5], pointRadius: 0 },
        { label: '合理價', data: lines.hold, borderColor: '#42a5f5', borderDash: [5, 5], pointRadius: 0 },
        { label: '昂貴價', data: lines.expensive, borderColor: '#ef5350', borderDash: [5, 5], pointRadius: 0 },
      ]});
    } catch (err) { setError(err.response?.data?.error || err.message); }
    finally { setLoading(false); }
  }, [ticker, activePeriod]);

  useEffect(() => { fetchChartData(); }, [fetchChartData]);
  const analyze = async () => {
    setLoading(true); setError(null);
    try { await apiClient.get(`/analyze/${ticker}`); await fetchChartData(); }
    catch (err) { setError(err.response?.data?.error || err.message); setLoading(false); }
  };

  return <section className="valuation-panel">
    <h2>個股估值</h2>
    <p className="section-intro">使用歷史本益比分位數與預估 EPS，作為輔助估值，不等同目標價。</p>
    <div className="controls">
      <input value={ticker} onChange={event => setTicker(event.target.value.toUpperCase())} onBlur={() => setTicker(normalizedTicker(ticker))} placeholder="例如 2330 或 2330.TW" />
      {['1M', '3M', '6M', 'YTD', '1Y', '5Y', 'MAX'].map(period => <button key={period} className={activePeriod.toUpperCase() === period ? 'active' : ''} onClick={() => setActivePeriod(period.toLowerCase())}>{period}</button>)}
      <button className="primary-btn" onClick={analyze} disabled={loading}>{loading ? '分析中…' : '執行估值'}</button>
    </div>
    {error && <p className="error">{error}</p>}
    <div className="stock-chart">{chartData && <Line data={chartData} options={{ responsive: true, maintainAspectRatio: false, plugins: { title: { display: true, text: `${ticker} 股價與估值區間` } } }} />}</div>
  </section>;
}

export default function App() {
  return <div className="App"><header><h1>台股籌碼與估值工作台</h1><p>期現貨、融資與價格確認集中判讀</p></header><main><MarketDashboard /><StockValuation /></main></div>;
}
