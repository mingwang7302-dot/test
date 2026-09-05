import React, { useEffect, useState } from 'react';
import { Line } from 'react-chartjs-2';
import apiClient from './api';

const billion = (value) => `${(value / 100000000).toLocaleString('zh-TW', { maximumFractionDigits: 1 })} 億`;

export default function MarketDashboard() {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      const response = await apiClient.get('/market/dashboard');
      setDashboard(response.data);
    } catch (err) {
      if (err.response?.status !== 404) setError(err.response?.data?.error || err.message);
    }
  };

  useEffect(() => { load(); }, []);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.post('/market/refresh');
      setDashboard(response.data);
    } catch (err) {
      setError(err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  };

  if (!dashboard) return (
    <section className="market-panel empty-panel">
      <h2>台股每日市場狀態</h2>
      <p>尚無快照。第一次更新會從官方來源建立基準，連續累積後才會啟用3日及5日確認。</p>
      <button className="primary-btn" onClick={refresh} disabled={loading}>{loading ? '更新中…' : '取得最新盤後資料'}</button>
      {error && <p className="error">{error}</p>}
    </section>
  );

  const { latest, signal, history } = dashboard;
  const chartData = {
    labels: history.map(row => row.date),
    datasets: [
      { label: '外資現貨（億元）', data: history.map(row => row.foreign_spot_net_twd / 1e8), borderColor: '#ef5350', yAxisID: 'cash' },
      { label: '外資期貨淨部位（口）', data: history.map(row => row.foreign_futures_net), borderColor: '#42a5f5', yAxisID: 'contracts' },
    ],
  };
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      cash: { position: 'left', title: { display: true, text: '億元' } },
      contracts: { position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: '口' } },
    },
  };

  return (
    <section className="market-panel">
      <div className="panel-heading">
        <div><span className="eyebrow">{latest.date} 盤後</span><h2>台股每日市場狀態</h2></div>
        <button className="primary-btn" onClick={refresh} disabled={loading}>{loading ? '更新中…' : '更新資料'}</button>
      </div>
      {error && <p className="error">{error}</p>}
      <div className={`regime regime-${signal.regime}`}><span>目前判定</span><strong>{signal.regime}</strong><small>綜合分數 {signal.score}</small></div>
      <div className="metric-grid">
        <article><span>外資現貨</span><strong>{billion(latest.foreign_spot_net_twd)}</strong><small>TWSE 買賣差額</small></article>
        <article><span>外資台指期</span><strong>{latest.foreign_futures_net.toLocaleString()} 口</strong><small>多 {latest.foreign_futures_long.toLocaleString()}／空 {latest.foreign_futures_short.toLocaleString()}</small></article>
        <article><span>融資餘額</span><strong>{billion(latest.margin_balance_twd)}</strong><small>TWSE 集中市場</small></article>
        <article><span>加權指數</span><strong>{latest.taiex_close.toLocaleString()}</strong><small>MA20 {latest.taiex_ma20.toLocaleString(undefined, { maximumFractionDigits: 0 })}</small></article>
      </div>
      <div className="market-details">
        <div><h3>判定依據</h3><ul>{signal.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></div>
        <div><h3>下一步觀察</h3><ul>{signal.watch.length ? signal.watch.map(item => <li key={item}>{item}</li>) : <li>目前確認條件完整，觀察是否出現反轉警戒。</li>}</ul></div>
      </div>
      <div className="market-chart"><Line data={chartData} options={chartOptions} /></div>
      <p className="source-note">資料：TWSE、TAIFEX；價格確認：^TWII。所有判定均顯示計算基礎，不代表投資建議。</p>
    </section>
  );
}
