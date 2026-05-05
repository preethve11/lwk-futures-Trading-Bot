interface LineChartProps {
  values: number[];
  tone?: 'equity' | 'drawdown';
  height?: number;
}

export function LineChart({ values, tone = 'equity', height = 220 }: LineChartProps) {
  if (values.length === 0) {
    return <div className="empty-state">No chart data</div>;
  }

  const width = 720;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = values
    .map((value, index) => {
      const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
      const y = height - ((value - min) / range) * (height - 24) - 12;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');

  return (
    <svg className={`line-chart line-chart-${tone}`} viewBox={`0 0 ${width} ${height}`} role="img">
      <title>{tone === 'drawdown' ? 'Drawdown chart' : 'Equity chart'}</title>
      <line x1="0" y1={height - 12} x2={width} y2={height - 12} className="chart-axis" />
      <polyline points={points} className="chart-line" />
    </svg>
  );
}
