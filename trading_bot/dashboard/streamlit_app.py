"""Streamlit operator dashboard for research and paper/testnet monitoring."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from app.core.config import load_settings
from app.persistence.database import SessionFactory, create_session_factory
from app.persistence.models import (
    AccountSnapshotModel,
    BacktestResultModel,
    MarketDataModel,
    PerformanceHealthModel,
    PortfolioAllocationModel,
    RegimeModel,
    RiskEventModel,
    TradeModel,
)


def main() -> None:
    """Render the Streamlit dashboard."""
    settings = load_settings()
    session_factory = create_session_factory(settings.database_url)
    st.set_page_config(page_title="Trading Bot Quant Ops", layout="wide")
    st.title("Trading Bot Quant Ops")
    st.caption("Research, validation, paper/testnet execution, and risk monitoring.")

    snapshots = _latest_account_snapshots(session_factory)
    health = _latest_health(session_factory)
    risk_events = _latest_risk_events(session_factory)
    trades = _latest_trades(session_factory)
    regimes = _latest_regimes(session_factory)
    backtests = _latest_backtest_results(session_factory)
    allocations = _latest_allocations(session_factory)
    candles = _latest_market_data(session_factory)

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Mode", "TESTNET" if settings.use_testnet else "MAINNET")
    col_b.metric("Live Enabled", "YES" if settings.enable_live_trading else "NO")
    col_c.metric("Recent Trades", len(trades))
    col_d.metric("Risk Events", len(risk_events))

    st.subheader("Account Equity")
    if snapshots.empty:
        st.info("No account snapshots persisted yet.")
    else:
        st.line_chart(snapshots.set_index("event_time")["margin_balance"])
        st.dataframe(snapshots, use_container_width=True)

    st.subheader("Strategy Health")
    st.dataframe(health, use_container_width=True)

    st.subheader("Current Regimes")
    st.dataframe(regimes, use_container_width=True)

    st.subheader("Backtest Validation Results")
    st.dataframe(backtests, use_container_width=True)

    st.subheader("Trades")
    st.dataframe(trades, use_container_width=True)

    st.subheader("Portfolio Allocations")
    st.dataframe(allocations, use_container_width=True)

    st.subheader("Recent Market Data")
    st.dataframe(candles, use_container_width=True)

    st.subheader("Risk And System Events")
    st.dataframe(risk_events, use_container_width=True)


def _latest_account_snapshots(session_factory: SessionFactory, *, limit: int = 200) -> pd.DataFrame:
    with session_factory() as session:
        rows = session.scalars(
            select(AccountSnapshotModel).order_by(AccountSnapshotModel.event_time.desc()).limit(limit)
        ).all()
    return pd.DataFrame(
        [
            {
                "event_time": row.event_time,
                "asset": row.asset,
                "wallet_balance": row.wallet_balance,
                "margin_balance": row.margin_balance,
                "unrealized_pnl": row.unrealized_pnl,
                "available_balance": row.available_balance,
            }
            for row in reversed(rows)
        ]
    )


def _latest_health(session_factory: SessionFactory, *, limit: int = 50) -> pd.DataFrame:
    with session_factory() as session:
        rows = session.scalars(
            select(PerformanceHealthModel).order_by(PerformanceHealthModel.checked_at.desc()).limit(limit)
        ).all()
    return pd.DataFrame([_model_dict(row) for row in rows])


def _latest_risk_events(session_factory: SessionFactory, *, limit: int = 100) -> pd.DataFrame:
    with session_factory() as session:
        rows = session.scalars(select(RiskEventModel).order_by(RiskEventModel.created_at.desc()).limit(limit)).all()
    return pd.DataFrame([_model_dict(row) for row in rows])


def _latest_trades(session_factory: SessionFactory, *, limit: int = 100) -> pd.DataFrame:
    with session_factory() as session:
        rows = session.scalars(select(TradeModel).order_by(TradeModel.exit_time.desc()).limit(limit)).all()
    return pd.DataFrame([_model_dict(row) for row in rows])


def _latest_regimes(session_factory: SessionFactory, *, limit: int = 100) -> pd.DataFrame:
    with session_factory() as session:
        rows = session.scalars(select(RegimeModel).order_by(RegimeModel.event_time.desc()).limit(limit)).all()
    return pd.DataFrame([_model_dict(row) for row in rows])


def _latest_backtest_results(session_factory: SessionFactory, *, limit: int = 100) -> pd.DataFrame:
    with session_factory() as session:
        rows = session.scalars(select(BacktestResultModel).order_by(BacktestResultModel.created_at.desc()).limit(limit)).all()
    return pd.DataFrame([_model_dict(row) for row in rows])


def _latest_allocations(session_factory: SessionFactory, *, limit: int = 100) -> pd.DataFrame:
    with session_factory() as session:
        rows = session.scalars(
            select(PortfolioAllocationModel).order_by(PortfolioAllocationModel.created_at.desc()).limit(limit)
        ).all()
    return pd.DataFrame([_model_dict(row) for row in rows])


def _latest_market_data(session_factory: SessionFactory, *, limit: int = 200) -> pd.DataFrame:
    with session_factory() as session:
        rows = session.scalars(select(MarketDataModel).order_by(MarketDataModel.open_time.desc()).limit(limit)).all()
    return pd.DataFrame([_model_dict(row) for row in rows])


def _model_dict(model: object) -> dict[str, object]:
    return {
        column.name: getattr(model, column.name)
        for column in model.__table__.columns  # type: ignore[attr-defined]
        if column.name not in {"raw_payload", "raw_response", "payload"}
    }


if __name__ == "__main__":
    main()
