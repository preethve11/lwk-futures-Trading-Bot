import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { App } from '../App';

const emptyArrayEndpoints = ['/configs', '/backtests', '/trades', '/signals', '/sessions', '/positions', '/risk/events'];

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public readonly url: string) {
    MockWebSocket.instances.push(this);
  }

  close() {
    return undefined;
  }
}

describe('App', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith('/risk/state')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                id: 1,
                kill_switch_enabled: false,
                manual_pause_enabled: false,
                daily_loss_locked: false,
                drawdown_locked: false,
                reason: '',
                updated_at: '2026-01-01T00:00:00Z'
              }),
              { status: 200, headers: { 'Content-Type': 'application/json' } }
            )
          );
        }
        if (emptyArrayEndpoints.some((path) => url.endsWith(path))) {
          return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
        }
        return Promise.resolve(new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }));
      })
    );
    vi.stubGlobal('WebSocket', MockWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    MockWebSocket.instances = [];
  });

  it('renders the operator dashboard shell with API-backed empty state', async () => {
    render(<App />);

    expect(screen.getByText('LWK Futures')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Risk Controls/i })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('No persisted open position')).toBeInTheDocument());
    expect(fetch).toHaveBeenCalled();
    expect(MockWebSocket.instances[0]?.url).toContain('/ws/live');
  });
});
