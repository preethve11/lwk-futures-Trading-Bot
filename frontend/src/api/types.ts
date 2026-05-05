export interface ConfigSnapshot {
  id: number;
  name: string;
  payload: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface BacktestRun {
  id: number;
  run_id: string;
  strategy_name: string;
  symbol: string;
  timeframe: string;
  start_date: string | null;
  end_date: string | null;
  initial_capital: number;
  final_capital: number;
  total_trades: number;
  total_return_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  win_rate: number;
  profit_factor: number;
  expectancy: number;
  config_snapshot: Record<string, unknown>;
  created_at: string;
}

export interface CandleInput {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MultiBacktestRunRequest {
  symbols: string[];
  timeframe?: string;
  start_date?: string;
  end_date?: string;
  candles_by_symbol: Record<string, CandleInput[]>;
}

export interface BacktestReport {
  symbol: string;
  timeframe: string;
  initial_capital: number;
  final_capital: number;
  total_pnl: number;
  total_trades: number;
  run_id: string | null;
  metrics: Record<string, number | null>;
  equity_curve: number[];
}

export interface MultiBacktestRunResult {
  aggregate: BacktestReport;
  symbols: BacktestReport[];
}

export interface Trade {
  id: number;
  bot_session_id: number | null;
  signal_id: number | null;
  order_id: number | null;
  symbol: string;
  side: string;
  quantity: number;
  entry_price: number;
  exit_price: number;
  pnl: number;
  pnl_pct: number;
  entry_time: string;
  exit_time: string;
  exit_reason: string;
  fees: number;
  slippage_usd: number;
  source: string;
  created_at: string;
}

export interface Signal {
  id: number;
  bot_session_id: number | null;
  symbol: string;
  strategy_name: string;
  side: string;
  entry_price: number;
  stop_price: number;
  take_profit_price: number;
  quantity: number;
  timestamp: string;
  status: string;
  reason: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface BotSession {
  id: number;
  session_id: string;
  mode: string;
  strategy_name: string;
  symbol: string;
  timeframe: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  config_snapshot: Record<string, unknown>;
}

export interface RiskState {
  id: number;
  kill_switch_enabled: boolean;
  manual_pause_enabled: boolean;
  daily_loss_locked: boolean;
  drawdown_locked: boolean;
  reason: string;
  updated_at: string;
}

export interface Position {
  id: number;
  bot_session_id: number | null;
  symbol: string;
  side: string;
  quantity: number;
  entry_price: number;
  unrealized_pnl: number;
  leverage: number;
  status: string;
  opened_at: string;
  closed_at: string | null;
}

export interface RiskEvent {
  id: number;
  bot_session_id: number | null;
  symbol: string;
  event_type: string;
  severity: string;
  reason: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface LiveEvent {
  event_type: string;
  payload: Record<string, unknown>;
}

export interface DashboardSnapshot {
  configs: ConfigSnapshot[];
  backtests: BacktestRun[];
  trades: Trade[];
  signals: Signal[];
  sessions: BotSession[];
  positions: Position[];
  riskState: RiskState | null;
  riskEvents: RiskEvent[];
}

export interface RiskStateUpdate {
  kill_switch_enabled?: boolean;
  manual_pause_enabled?: boolean;
  daily_loss_locked?: boolean;
  drawdown_locked?: boolean;
  reason?: string;
}
