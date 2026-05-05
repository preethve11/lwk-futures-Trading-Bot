import type { ReactNode } from 'react';

interface MetricTileProps {
  label: string;
  value: string;
  detail?: string;
  tone?: 'ok' | 'warn' | 'danger' | 'neutral';
  icon: ReactNode;
}

export function MetricTile({ label, value, detail, tone = 'neutral', icon }: MetricTileProps) {
  return (
    <section className={`metric-tile metric-${tone}`}>
      <div className="metric-icon" aria-hidden="true">
        {icon}
      </div>
      <div>
        <p className="metric-label">{label}</p>
        <strong className="metric-value">{value}</strong>
        {detail ? <span className="metric-detail">{detail}</span> : null}
      </div>
    </section>
  );
}
