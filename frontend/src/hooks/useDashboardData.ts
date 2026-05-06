import { useCallback, useEffect, useMemo, useState } from 'react';

import { apiClient, connectLiveEvents, loadDashboardSnapshot } from '../api/client';
import type { DashboardSnapshot, LiveEvent, RiskStateUpdate } from '../api/types';

const emptySnapshot: DashboardSnapshot = {
  configs: [],
  backtests: [],
  trades: [],
  signals: [],
  aiReports: [],
  sessions: [],
  positions: [],
  riskState: null,
  riskEvents: []
};

export function useDashboardData() {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot>(emptySnapshot);
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await loadDashboardSnapshot();
      setSnapshot(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load dashboard data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => {
      void refresh();
    }, 15000);
    return () => window.clearInterval(interval);
  }, [refresh]);

  useEffect(() => {
    const socket = connectLiveEvents(
      (event) => setLiveEvents((events) => [event, ...events].slice(0, 80)),
      () => setError((current) => current ?? 'Live event stream disconnected')
    );
    return () => socket?.close();
  }, []);

  const setKillSwitch = useCallback(
    async (enabled: boolean, reason: string) => {
      const riskState = await apiClient.setKillSwitch(enabled, reason);
      setSnapshot((current) => ({ ...current, riskState }));
    },
    []
  );

  const updateRiskState = useCallback(async (update: RiskStateUpdate) => {
    const riskState = await apiClient.updateRiskState(update);
    setSnapshot((current) => ({ ...current, riskState }));
  }, []);

  const derived = useMemo(() => {
    const realizedPnl = snapshot.trades.reduce((total, trade) => total + trade.pnl, 0);
    const latestSession = snapshot.sessions[0] ?? null;
    const currentPosition = snapshot.positions.find((position) => position.status === 'open') ?? null;
    const openRiskItems =
      Number(snapshot.riskState?.kill_switch_enabled ?? false) +
      Number(snapshot.riskState?.manual_pause_enabled ?? false) +
      Number(snapshot.riskState?.daily_loss_locked ?? false) +
      Number(snapshot.riskState?.drawdown_locked ?? false) +
      snapshot.riskEvents.filter((event) => ['CRITICAL', 'EMERGENCY'].includes(event.severity)).length;

    return { realizedPnl, latestSession, currentPosition, openRiskItems };
  }, [snapshot]);

  return {
    ...snapshot,
    ...derived,
    liveEvents,
    loading,
    error,
    refresh,
    setKillSwitch,
    updateRiskState
  };
}

export type DashboardData = ReturnType<typeof useDashboardData>;
