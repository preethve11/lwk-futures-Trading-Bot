import { Activity, AlertTriangle, DollarSign, ShieldCheck, Wallet } from 'lucide-react';

import { Badge } from '../components/Badge';
import { MetricTile } from '../components/MetricTile';
import type { DashboardData } from '../hooks/useDashboardData';
import { formatCurrency, formatDateTime, formatNumber } from '../utils/format';

export function LiveStatus({ data }: { data: DashboardData }) {
  const session = data.latestSession;
  const position = data.currentPosition;
  const account = data.latestAccountSnapshot;
  const riskPaused =
    data.riskState?.kill_switch_enabled ||
    data.riskState?.manual_pause_enabled ||
    data.riskState?.daily_loss_locked ||
    data.riskState?.drawdown_locked;

  return (
    <div className="page-stack">
      <div className="metric-grid">
        <MetricTile
          label="Bot State"
          value={riskPaused ? 'Paused' : session?.status ?? 'No session'}
          detail={session ? `${session.symbol} ${session.timeframe}` : 'Awaiting API session'}
          tone={riskPaused ? 'danger' : session?.status === 'running' ? 'ok' : 'warn'}
          icon={<Activity size={20} />}
        />
        <MetricTile
          label="Account Equity"
          value={account ? formatCurrency(account.margin_balance) : 'No snapshot'}
          detail={account ? `${account.asset} wallet ${formatCurrency(account.wallet_balance)}` : 'Run account reconciliation'}
          tone={account ? 'ok' : 'warn'}
          icon={<Wallet size={20} />}
        />
        <MetricTile
          label="Realized PnL"
          value={formatCurrency(data.realizedPnl)}
          detail={`${data.trades.length} closed trades`}
          tone={data.realizedPnl >= 0 ? 'ok' : 'danger'}
          icon={<DollarSign size={20} />}
        />
        <MetricTile
          label="Open Position"
          value={position ? `${position.side} ${position.symbol}` : 'Flat'}
          detail={position ? `${formatNumber(position.quantity, 6)} @ ${formatCurrency(position.entry_price)}` : 'No open snapshot'}
          tone={position ? 'ok' : 'neutral'}
          icon={<ShieldCheck size={20} />}
        />
        <MetricTile
          label="Risk Items"
          value={String(data.openRiskItems)}
          detail={data.riskState?.reason || 'No operator reason'}
          tone={data.openRiskItems > 0 ? 'danger' : 'ok'}
          icon={<AlertTriangle size={20} />}
        />
      </div>

      <section className="panel">
        <div className="section-heading">
          <h2>Account Equity</h2>
          {account ? <Badge value={account.asset} /> : <Badge value="missing" />}
        </div>
        {account ? (
          <div className="facts-grid">
            <span>Wallet</span>
            <strong>{formatCurrency(account.wallet_balance)}</strong>
            <span>Margin Balance</span>
            <strong>{formatCurrency(account.margin_balance)}</strong>
            <span>Available</span>
            <strong>{formatCurrency(account.available_balance)}</strong>
            <span>Unrealized PnL</span>
            <strong className={account.unrealized_pnl >= 0 ? 'positive' : 'negative'}>
              {formatCurrency(account.unrealized_pnl)}
            </strong>
            <span>Updated</span>
            <strong>{formatDateTime(account.event_time)}</strong>
          </div>
        ) : (
          <div className="empty-state">No account equity snapshots</div>
        )}
      </section>

      <section className="panel">
        <div className="section-heading">
          <h2>Current Position</h2>
          {position ? <Badge value={position.status} /> : <Badge value="flat" />}
        </div>
        {position ? (
          <div className="facts-grid">
            <span>Symbol</span>
            <strong>{position.symbol}</strong>
            <span>Quantity</span>
            <strong>{formatNumber(position.quantity, 6)}</strong>
            <span>Entry</span>
            <strong>{formatCurrency(position.entry_price)}</strong>
            <span>Unrealized PnL</span>
            <strong className={position.unrealized_pnl >= 0 ? 'positive' : 'negative'}>{formatCurrency(position.unrealized_pnl)}</strong>
            <span>Leverage</span>
            <strong>{position.leverage}x</strong>
            <span>Opened</span>
            <strong>{formatDateTime(position.opened_at)}</strong>
          </div>
        ) : (
          <div className="empty-state">No persisted open position</div>
        )}
      </section>

      <section className="panel">
        <div className="section-heading">
          <h2>Recent Sessions</h2>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Mode</th>
                <th>Symbol</th>
                <th>Strategy</th>
                <th>Status</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {data.sessions.slice(0, 6).map((item) => (
                <tr key={item.id}>
                  <td>{item.mode}</td>
                  <td>{item.symbol}</td>
                  <td>{item.strategy_name}</td>
                  <td><Badge value={item.status} /></td>
                  <td>{formatDateTime(item.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
