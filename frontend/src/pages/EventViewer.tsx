import { Badge } from '../components/Badge';
import type { DashboardData } from '../hooks/useDashboardData';
import { formatDateTime } from '../utils/format';

export function EventViewer({ data }: { data: DashboardData }) {
  return (
    <div className="page-stack">
      <section className="panel">
        <div className="section-heading">
          <h2>Live Events</h2>
          <span>{data.liveEvents.length} received</span>
        </div>
        <div className="event-list">
          {data.liveEvents.length === 0 ? (
            <div className="empty-state">No WebSocket events received</div>
          ) : (
            data.liveEvents.map((event, index) => (
              <div className="event-row" key={`${event.event_type}-${index}`}>
                <Badge value={event.event_type} />
                <code>{JSON.stringify(event.payload)}</code>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <h2>Risk Events</h2>
          <span>{data.riskEvents.length} records</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Severity</th>
                <th>Type</th>
                <th>Symbol</th>
                <th>Reason</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {data.riskEvents.map((event) => (
                <tr key={event.id}>
                  <td><Badge value={event.severity} /></td>
                  <td>{event.event_type}</td>
                  <td>{event.symbol}</td>
                  <td>{event.reason}</td>
                  <td>{formatDateTime(event.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
