export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value);
}

export function formatNumber(value: number, digits = 2): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(value);
}

export function formatPercent(value: number): string {
  return `${formatNumber(value, 2)}%`;
}

export function formatDateTime(value: string | null): string {
  if (!value) {
    return '—';
  }
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(new Date(value));
}

export function statusTone(value: string): 'ok' | 'warn' | 'danger' | 'neutral' {
  const normalized = value.toLowerCase();
  if (['running', 'open', 'protected', 'info'].includes(normalized)) {
    return 'ok';
  }
  if (['warning', 'manual_review_required', 'stopped', 'paper'].includes(normalized)) {
    return 'warn';
  }
  if (['critical', 'emergency', 'failed_unprotected'].includes(normalized)) {
    return 'danger';
  }
  return 'neutral';
}
