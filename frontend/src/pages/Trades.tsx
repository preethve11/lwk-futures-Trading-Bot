import { Badge } from '../components/Badge';
import type { DashboardData } from '../hooks/useDashboardData';
import { formatCurrency, formatDateTime, formatNumber } from '../utils/format';

export function Trades({ data }: { data: DashboardData }) {
  const signalById = new Map(data.signals.map((signal) => [signal.id, signal]));

  return (
    <section className="panel page-fill">
      <div className="section-heading">
        <h2>Trades</h2>
        <span>{data.trades.length} records</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Side</th>
              <th>Quantity</th>
              <th>Entry</th>
              <th>Exit</th>
              <th>PnL</th>
              <th>Reason</th>
              <th>Closed</th>
            </tr>
          </thead>
          <tbody>
            {data.trades.map((trade) => {
              const signal = trade.signal_id ? signalById.get(trade.signal_id) : undefined;
              return (
                <tr key={trade.id}>
                  <td>{trade.symbol}</td>
                  <td><Badge value={trade.side} /></td>
                  <td>{formatNumber(trade.quantity, 6)}</td>
                  <td>{formatCurrency(trade.entry_price)}</td>
                  <td>{formatCurrency(trade.exit_price)}</td>
                  <td className={trade.pnl >= 0 ? 'positive' : 'negative'}>{formatCurrency(trade.pnl)}</td>
                  <td>{signal?.reason ?? trade.exit_reason}</td>
                  <td>{formatDateTime(trade.exit_time)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
