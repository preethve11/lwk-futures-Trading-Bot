import {
  Activity,
  BarChart3,
  ClipboardList,
  Gauge,
  LineChart,
  RefreshCcw,
  ShieldAlert,
  Table2
} from 'lucide-react';
import { useMemo, useState } from 'react';

import { BacktestResults } from './pages/BacktestResults';
import { EquityCurve } from './pages/EquityCurve';
import { EventViewer } from './pages/EventViewer';
import { LiveStatus } from './pages/LiveStatus';
import { RiskControls } from './pages/RiskControls';
import { Trades } from './pages/Trades';
import { useDashboardData } from './hooks/useDashboardData';
import { Badge } from './components/Badge';

type PageId = 'live' | 'equity' | 'trades' | 'backtests' | 'risk' | 'events';

const pages = [
  { id: 'live' as const, label: 'Live Status', icon: Activity },
  { id: 'equity' as const, label: 'Equity Curve', icon: LineChart },
  { id: 'trades' as const, label: 'Trades', icon: Table2 },
  { id: 'backtests' as const, label: 'Backtests', icon: BarChart3 },
  { id: 'risk' as const, label: 'Risk Controls', icon: ShieldAlert },
  { id: 'events' as const, label: 'Events', icon: ClipboardList }
];

export function App() {
  const [activePage, setActivePage] = useState<PageId>('live');
  const data = useDashboardData();
  const ActivePage = useMemo(() => {
    switch (activePage) {
      case 'equity':
        return <EquityCurve data={data} />;
      case 'trades':
        return <Trades data={data} />;
      case 'backtests':
        return <BacktestResults data={data} />;
      case 'risk':
        return <RiskControls data={data} />;
      case 'events':
        return <EventViewer data={data} />;
      default:
        return <LiveStatus data={data} />;
    }
  }, [activePage, data]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-mark">
          <Gauge size={24} />
          <div>
            <strong>LWK Futures</strong>
            <span>Execution Console</span>
          </div>
        </div>
        <nav aria-label="Dashboard sections">
          {pages.map((page) => {
            const Icon = page.icon;
            return (
              <button
                key={page.id}
                type="button"
                className={activePage === page.id ? 'nav-item active' : 'nav-item'}
                onClick={() => setActivePage(page.id)}
                title={page.label}
              >
                <Icon size={18} />
                <span>{page.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <h1>{pages.find((page) => page.id === activePage)?.label}</h1>
            <span className="muted">
              {data.latestSession ? `${data.latestSession.symbol} ${data.latestSession.timeframe}` : 'API-backed operator dashboard'}
            </span>
          </div>
          <div className="topbar-actions">
            {data.error ? <Badge value="warning" /> : <Badge value={data.loading ? 'loading' : 'connected'} />}
            <button className="icon-button" type="button" onClick={() => void data.refresh()} title="Refresh dashboard data">
              <RefreshCcw size={18} />
            </button>
          </div>
        </header>
        {data.error ? <div className="alert-strip">{data.error}</div> : null}
        {ActivePage}
      </main>
    </div>
  );
}
