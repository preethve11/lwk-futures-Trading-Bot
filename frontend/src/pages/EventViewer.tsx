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

      <section className="panel">
        <div className="section-heading">
          <h2>AI Trade Journal</h2>
          <span>{data.aiReports.length} reports</span>
        </div>
        <div className="table-wrap">
          <table className="journal-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Symbol</th>
                <th>Model</th>
                <th>Report</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {data.aiReports.map((report) => (
                <tr key={report.id}>
                  <td><Badge value={report.event_type} /></td>
                  <td>{report.symbol}</td>
                  <td>{report.model}</td>
                  <td>{report.report_text}</td>
                  <td>{formatDateTime(report.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.aiReports.length === 0 ? <div className="empty-state">No AI journal reports</div> : null}
        </div>
      </section>
    </div>
  );
}
