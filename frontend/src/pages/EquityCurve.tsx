import { LineChart } from '../components/LineChart';
import type { DashboardData } from '../hooks/useDashboardData';
import { formatCurrency, formatPercent } from '../utils/format';

function buildEquityCurve(initialCapital: number, pnls: number[]) {
  return pnls.reduce<number[]>((curve, pnl) => [...curve, curve[curve.length - 1] + pnl], [initialCapital]);
}

function buildDrawdown(equity: number[]) {
  let peak = equity[0] ?? 0;
  return equity.map((value) => {
    peak = Math.max(peak, value);
    return peak === 0 ? 0 : ((value - peak) / peak) * 100;
  });
}

export function EquityCurve({ data }: { data: DashboardData }) {
  const initialCapital = data.backtests[0]?.initial_capital ?? 10000;
  const equity = buildEquityCurve(initialCapital, [...data.trades].reverse().map((trade) => trade.pnl));
  const drawdown = buildDrawdown(equity);
  const current = equity[equity.length - 1] ?? initialCapital;
  const maxDrawdown = Math.min(...drawdown, 0);

  return (
    <div className="page-stack">
      <section className="panel">
        <div className="section-heading">
          <h2>Equity Curve</h2>
          <strong>{formatCurrency(current)}</strong>
        </div>
        <LineChart values={equity} />
      </section>

      <section className="panel">
        <div className="section-heading">
          <h2>Drawdown</h2>
          <strong className="negative">{formatPercent(maxDrawdown)}</strong>
        </div>
        <LineChart values={drawdown} tone="drawdown" />
      </section>
    </div>
  );
}
