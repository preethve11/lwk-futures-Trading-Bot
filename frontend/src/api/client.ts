import type {
  BacktestRun,
  AccountSnapshot,
  AIReport,
  BotSession,
  ConfigSnapshot,
  DashboardSnapshot,
  LiveEvent,
  MultiBacktestRunRequest,
  MultiBacktestRunResult,
  Position,
  RiskEvent,
  RiskState,
  RiskStateUpdate,
  Signal,
  Trade
} from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';
const API_TOKEN = import.meta.env.VITE_API_TOKEN ?? '';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('Content-Type', 'application/json');
  if (API_TOKEN) {
    headers.set('X-API-Token', API_TOKEN);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export const apiClient = {
  getConfigs: () => request<ConfigSnapshot[]>('/configs'),
  getBacktests: () => request<BacktestRun[]>('/backtests'),
  getTrades: () => request<Trade[]>('/trades'),
  getSignals: () => request<Signal[]>('/signals'),
  getAIReports: () => request<AIReport[]>('/ai-reports'),
  getSessions: () => request<BotSession[]>('/sessions'),
  getPositions: () => request<Position[]>('/positions'),
  getRiskState: () => request<RiskState>('/risk/state'),
  getRiskEvents: () => request<RiskEvent[]>('/risk/events'),
  getAccountSnapshots: () => request<AccountSnapshot[]>('/account/snapshots?limit=250'),
  runMultiBacktest: (payload: MultiBacktestRunRequest) =>
    request<MultiBacktestRunResult>('/backtests/run-multi', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  setKillSwitch: (enabled: boolean, reason: string) =>
    request<RiskState>('/risk/kill-switch', {
      method: 'POST',
      body: JSON.stringify({ enabled, reason })
    }),
  updateRiskState: (update: RiskStateUpdate) =>
    request<RiskState>('/risk/state', {
      method: 'POST',
      body: JSON.stringify(update)
    })
};

export async function loadDashboardSnapshot(): Promise<DashboardSnapshot> {
  const [
    configs,
    backtests,
    trades,
    signals,
    aiReports,
    sessions,
    positions,
    riskState,
    riskEvents,
    accountSnapshots
  ] = await Promise.all([
    apiClient.getConfigs(),
    apiClient.getBacktests(),
    apiClient.getTrades(),
    apiClient.getSignals(),
    apiClient.getAIReports(),
    apiClient.getSessions(),
    apiClient.getPositions(),
    apiClient.getRiskState(),
    apiClient.getRiskEvents(),
    apiClient.getAccountSnapshots()
  ]);

  return { configs, backtests, trades, signals, aiReports, sessions, positions, riskState, riskEvents, accountSnapshots };
}

export function connectLiveEvents(onEvent: (event: LiveEvent) => void, onError: () => void): WebSocket | null {
  if (typeof WebSocket === 'undefined') {
    return null;
  }
  const wsBase = API_BASE_URL.replace(/^http/, 'ws');
  const socket = new WebSocket(`${wsBase}/ws/live`);
  socket.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data) as LiveEvent);
    } catch {
      onError();
    }
  };
  socket.onerror = onError;
  return socket;
}
