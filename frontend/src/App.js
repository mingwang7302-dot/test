import React, { useState, useEffect, useCallback } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import apiClient from './api';
import './App.css';

// Register ChartJS components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

function App() {
  const [ticker, setTicker] = useState('AAPL');
  const [activePeriod, setActivePeriod] = useState('1y');
  const [chartData, setChartData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleTickerChange = (event) => {
    setTicker(event.target.value.toUpperCase());
  };

  const handlePeriodChange = (period) => {
    setActivePeriod(period.toLowerCase());
  };

  const fetchChartData = useCallback(async () => {
    if (!ticker) return;

    setLoading(true);
    setError(null);
    setChartData(null);

    try {
      const [historyRes, analysisHistoryRes] = await Promise.all([
        apiClient.get(`/stock_history/${ticker}?period=${activePeriod}`),
        apiClient.get(`/analysis_history/${ticker}`),
      ]);

      const stockHistory = historyRes.data;
      const analysisHistory = analysisHistoryRes.data;

      const labels = stockHistory.map(data => data.Date);
      const closePrices = stockHistory.map(data => data.Close);

      const analysisMap = new Map(analysisHistory.map(a => [a.date, a]));
      let lastAnalysis = null;

      const cheapLine = [], holdLine = [], expensiveLine = [];

      for (const date of labels) {
        if (analysisMap.has(date)) {
          lastAnalysis = analysisMap.get(date);
        }
        if (lastAnalysis) {
          cheapLine.push(lastAnalysis.cheap_price);
          holdLine.push(lastAnalysis.hold_price);
          expensiveLine.push(lastAnalysis.expensive_price);
        } else {
          cheapLine.push(null);
          holdLine.push(null);
          expensiveLine.push(null);
        }
      }

      setChartData({
        labels,
        datasets: [
          {
            label: `${ticker} 收盤價`,
            data: closePrices,
            borderColor: 'rgb(75, 192, 192)',
            yAxisID: 'y',
          },
          {
            label: '便宜價',
            data: cheapLine,
            borderColor: 'rgb(255, 99, 132)',
            borderDash: [5, 5],
            pointRadius: 0,
            yAxisID: 'y',
          },
          {
            label: '合理價',
            data: holdLine,
            borderColor: 'rgb(54, 162, 235)',
            borderDash: [5, 5],
            pointRadius: 0,
            yAxisID: 'y',
          },
          {
            label: '昂貴價',
            data: expensiveLine,
            borderColor: 'rgb(255, 206, 86)',
            borderDash: [5, 5],
            pointRadius: 0,
            yAxisID: 'y',
          },
        ],
      });

    } catch (err) {
      setError(`資料獲取失敗: ${err.response ? err.response.data.error : err.message}`);
    } finally {
      setLoading(false);
    }
  }, [ticker, activePeriod]);

  const handleRunAnalysis = async () => {
    setLoading(true);
    setError(null);
    try {
      // First, trigger a new analysis.
      await apiClient.get(`/analyze/${ticker}`);
      // After the new analysis is saved, fetch all data to update the chart.
      await fetchChartData();
    } catch (err) {
      setError(`執行新分析失敗: ${err.response ? err.response.data.error : err.message}`);
      setLoading(false);
    }
  };

  // Fetch data on initial load or when ticker/period changes.
  useEffect(() => {
    fetchChartData();
  }, [fetchChartData]);

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: { position: 'top' },
      title: {
        display: true,
        text: `${ticker} 股價與 AI 估值分析 (${activePeriod.toUpperCase()})`,
      },
    },
    scales: {
      y: {
        type: 'linear',
        display: true,
        position: 'left',
        title: {
          display: true,
          text: '價格 (USD)',
        },
      },
    },
  };

  const periods = ['1M', '3M', '6M', 'YTD', '1Y', '5Y', 'MAX'];

  return (
    <div className="App">
      <header className="App-header">
        <h1>AI 股價分析與估值工具</h1>
      </header>
      <div className="container">
        <div className="controls">
          <input
            type="text"
            value={ticker}
            onChange={handleTickerChange}
            placeholder="輸入股票代碼 (例如 AAPL)"
            className="ticker-input"
          />
          <div className="period-buttons">
            {periods.map((period) => (
              <button
                key={period}
                className={`period-btn ${activePeriod.toUpperCase() === period ? 'active' : ''}`}
                onClick={() => handlePeriodChange(period)}
              >
                {period}
              </button>
            ))}
          </div>
          <button onClick={handleRunAnalysis} className="analyze-btn" disabled={loading}>
            {loading ? '分析中...' : '執行新分析'}
          </button>
        </div>
        <div className="chart-container">
          {loading && <p>載入圖表數據中...</p>}
          {error && <p className="error">{error}</p>}
          {chartData && <Line options={chartOptions} data={chartData} />}
        </div>
      </div>
    </div>
  );
}

export default App;
