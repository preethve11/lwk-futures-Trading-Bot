from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.ai.journal import (
    AIJournalQueue,
    AIJournalRequest,
    AIJournalResult,
    AIJournalService,
    build_ai_journal_prompt,
)
from app.persistence.database import create_session_factory, init_db, session_scope
from app.persistence.models import AIReportModel
from app.persistence.repositories import AIReportRepository


class FakeAIJournalClient:
    def generate(self, request: AIJournalRequest) -> AIJournalResult:
        return AIJournalResult(
            model="fake-model",
            prompt=build_ai_journal_prompt(request),
            report_text="Advisory journal only.",
            raw_response={"output_text": "Advisory journal only."},
        )


def _request() -> AIJournalRequest:
    return AIJournalRequest(
        symbol="ZECUSDT",
        strategy_name="ema_rsi_vwap",
        event_type="signal_taken",
        input_snapshot={
            "side": "BUY",
            "entry_price": 100.0,
            "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        },
        risk_state={"allowed": True, "quantity": 0.5},
        market_regime={"ema_trend": "bullish", "vwap_position": "above"},
        outcome={"protected": True},
        bot_session_id=None,
        signal_id=None,
    )


def test_ai_journal_service_persists_advisory_report() -> None:
    factory = create_session_factory("sqlite:///:memory:")
    init_db(factory)
    service = AIJournalService(factory, FakeAIJournalClient())

    report_id = service.generate_and_persist(_request())

    with session_scope(factory) as session:
        report = session.get(AIReportModel, report_id)
        assert report is not None
        assert report.symbol == "ZECUSDT"
        assert report.model == "fake-model"
        assert report.report_text == "Advisory journal only."
        assert report.outcome["protected"] is True


def test_ai_journal_prompt_enforces_advisory_boundary() -> None:
    prompt = build_ai_journal_prompt(_request())

    assert "advisory" in prompt
    assert "Do not issue trade instructions" in prompt
    assert "no orders or state mutation" in prompt


def test_ai_journal_queue_is_nonblocking_when_full() -> None:
    factory = create_session_factory("sqlite:///:memory:")
    init_db(factory)
    queue = AIJournalQueue(
        AIJournalService(factory, FakeAIJournalClient()),
        enabled=True,
        maxsize=1,
        autostart=False,
    )

    assert queue.enqueue(_request()) is True
    assert queue.enqueue(_request()) is False


def test_ai_report_repository_filters_recent_reports() -> None:
    factory = create_session_factory("sqlite:///:memory:")
    init_db(factory)
    with session_scope(factory) as session:
        repository = AIReportRepository(session)
        repository.create(
            symbol="ZECUSDT",
            strategy_name="ema_rsi_vwap",
            event_type="signal_rejected",
            model="fake",
            prompt="prompt",
            report_text="report",
            input_snapshot={},
            risk_state={},
            market_regime={},
            outcome={},
        )
        repository.create(
            symbol="BTCUSDT",
            strategy_name="ema_rsi_vwap",
            event_type="signal_taken",
            model="fake",
            prompt="prompt",
            report_text="report",
            input_snapshot={},
            risk_state={},
            market_regime={},
            outcome={},
        )

    with session_scope(factory) as session:
        reports = AIReportRepository(session).list_recent(symbol="ZECUSDT")
        all_reports = session.scalars(select(AIReportModel)).all()

    assert len(all_reports) == 2
    assert len(reports) == 1
    assert reports[0].event_type == "signal_rejected"
