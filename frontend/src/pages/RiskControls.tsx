import { Power, RefreshCcw } from 'lucide-react';
import { useState } from 'react';

import { Toggle } from '../components/Toggle';
import type { DashboardData } from '../hooks/useDashboardData';
import { formatDateTime } from '../utils/format';

export function RiskControls({ data }: { data: DashboardData }) {
  const [pending, setPending] = useState(false);
  const riskState = data.riskState;
  const performanceGate = data.performanceGate;

  const update = async (payload: Parameters<typeof data.updateRiskState>[0]) => {
    setPending(true);
    try {
      await data.updateRiskState(payload);
    } finally {
      setPending(false);
    }
  };

  const setKillSwitch = async (enabled: boolean) => {
    setPending(true);
    try {
      await data.setKillSwitch(enabled, enabled ? 'dashboard kill switch' : 'dashboard release');
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="page-stack">
      <section className="panel risk-command">
        <div>
          <h2>Kill Switch</h2>
          <p className="muted">Last update: {formatDateTime(riskState?.updated_at ?? null)}</p>
        </div>
        <button
          className={`command-button ${riskState?.kill_switch_enabled ? 'danger-command' : 'ok-command'}`}
          type="button"
          onClick={() => void setKillSwitch(!(riskState?.kill_switch_enabled ?? false))}
          disabled={pending}
          title="Toggle kill switch"
        >
          <Power size={18} />
          {riskState?.kill_switch_enabled ? 'Disable' : 'Enable'}
        </button>
      </section>

      <section className="panel">
        <div className="section-heading">
          <h2>Risk Locks</h2>
          <button className="icon-button" type="button" onClick={() => void data.refresh()} title="Refresh risk state">
            <RefreshCcw size={17} />
          </button>
        </div>
        <div className="control-list">
          <Toggle
            label="Manual pause"
            checked={riskState?.manual_pause_enabled ?? false}
            onChange={(checked) => void update({ manual_pause_enabled: checked, reason: checked ? 'manual pause' : 'manual pause released' })}
          />
          <Toggle
            label="Daily loss lock"
            checked={riskState?.daily_loss_locked ?? false}
            onChange={(checked) => void update({ daily_loss_locked: checked, reason: checked ? 'daily loss lock' : 'daily loss lock released' })}
          />
          <Toggle
            label="Drawdown lock"
            checked={riskState?.drawdown_locked ?? false}
            onChange={(checked) => void update({ drawdown_locked: checked, reason: checked ? 'drawdown lock' : 'drawdown lock released' })}
          />
        </div>
        <div className="operator-note">
          <span>Reason</span>
          <strong>{riskState?.reason || 'No active operator note'}</strong>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <h2>Strategy Gate</h2>
          <span>{performanceGate?.allowed ? 'passed' : 'blocked'}</span>
        </div>
        {performanceGate ? (
          <div className="facts-grid">
            <span>Status</span>
            <strong className={performanceGate.allowed ? 'positive' : 'negative'}>{performanceGate.allowed ? 'Allowed' : 'Blocked'}</strong>
            <span>Reason</span>
            <strong>{performanceGate.reason}</strong>
            <span>Run</span>
            <strong>{performanceGate.backtest_run_id ?? 'No run'}</strong>
            <span>Profit Factor</span>
            <strong>{performanceGate.metrics.profit_factor ?? 'n/a'}</strong>
            <span>Trades</span>
            <strong>{performanceGate.metrics.total_trades ?? 0}</strong>
            <span>Max Drawdown</span>
            <strong>{performanceGate.metrics.max_drawdown_pct ?? 'n/a'}%</strong>
          </div>
        ) : (
          <div className="empty-state">No strategy gate result</div>
        )}
      </section>
    </div>
  );
}
