import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { LineChart } from '../components/LineChart';
import { MetricTile } from '../components/MetricTile';
import { Toggle } from '../components/Toggle';

describe('dashboard components', () => {
  it('renders metric tile label, value, and detail without exposing decorative icons', () => {
    render(<MetricTile label="Account Equity" value="$10,000.00" detail="USDT wallet $9,950.00" icon={<span>icon</span>} tone="ok" />);

    expect(screen.getByText('Account Equity')).toBeInTheDocument();
    expect(screen.getByText('$10,000.00')).toBeInTheDocument();
    expect(screen.getByText('USDT wallet $9,950.00')).toBeInTheDocument();
    expect(screen.getByText('icon').closest('[aria-hidden="true"]')).not.toBeNull();
  });

  it('calls toggle change handler with the next checked state', () => {
    const onChange = vi.fn();

    render(<Toggle label="Manual pause" checked={false} onChange={onChange} />);
    fireEvent.click(screen.getByLabelText('Manual pause'));

    expect(onChange).toHaveBeenCalledWith(true);
  });

  it('renders an accessible equity chart and empty state', () => {
    const { rerender } = render(<LineChart values={[100, 102, 101]} />);

    expect(screen.getByRole('img')).toHaveTextContent('Equity chart');

    rerender(<LineChart values={[]} />);

    expect(screen.getByText('No chart data')).toBeInTheDocument();
  });
});
