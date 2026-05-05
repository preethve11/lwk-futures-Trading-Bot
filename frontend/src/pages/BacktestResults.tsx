import { LineChart } from '../components/LineChart';
import { MetricTile } from '../components/MetricTile';
import type { DashboardData } from '../hooks/useDashboardData';
import { formatCurrency, formatNumber, formatPercent } from '../utils/format';
import { BarChart3, Gauge, Percent, TrendingUp } from 'lucide-react';

export function BacktestResults({ data }: { data: DashboardData }) {
  const latest = data.backtests[0];
  const series = [...data.backtests]
    .reverse()
    .map((run) => run.final_capital);

  if (!latest) {
    return <section className="panel page-fill"><div className="empty-state">No persisted backtest results</div></section>;
  }

  return (
    <div className="page-stack">
      <div className="metric-grid">
        <MetricTile label="Total Return" value={formatPercent(latest.total_return_pct)} detail={latest.symbol} tone={latest.total_return_pct >= 0 ? 'ok' : 'danger'} icon={<TrendingUp size={20} />} />
        <MetricTile label="Sharpe" value={formatNumber(latest.sharpe_ratio)} detail="risk-adjusted return" icon={<Gauge size={20} />} />
        <MetricTile label="Win Rate" value={formatPercent(latest.win_rate * 100)} detail={`${latest.total_trades} trades`} icon={<Percent size={20} />} />
        <MetricTile label="Profit Factor" value={formatNumber(latest.profit_factor)} detail="gross profit/loss" icon={<BarChart3 size={20} />} />
      </div>
      <section className="panel">
        <div className="section-heading">
          <h2>Backtest Equity</h2>
          <strong>{formatCurrency(latest.final_capital)}</strong>
        </div>
        <LineChart values={series} />
      </section>
      <section className="panel">
        <div className="section-heading">
          <h2>Recent Runs</h2>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Timeframe</th>
                <th>Trades</th>
                <th>Return</th>
                <th>Max DD</th>
                <th>Expectancy</th>
              </tr>
            </thead>
            <tbody>
              {data.backtests.map((run) => (
                <tr key={run.id}>
                  <td>{run.symbol}</td>
                  <td>{run.timeframe}</td>
                  <td>{run.total_trades}</td>
                  <td className={run.total_return_pct >= 0 ? 'positive' : 'negative'}>{formatPercent(run.total_return_pct)}</td>
                  <td className="negative">{formatPercent(run.max_drawdown_pct)}</td>
                  <td>{formatCurrency(run.expectancy)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
