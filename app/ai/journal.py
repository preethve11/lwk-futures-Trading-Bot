"""Advisory-only AI trade journal generation."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from queue import Full, Queue
from threading import Lock, Thread
from typing import Protocol, cast

import httpx

from app.persistence.database import SessionFactory, session_scope
from app.persistence.repositories import AIReportRepository

logger = logging.getLogger("trading_bot.ai.journal")


@dataclass(frozen=True)
class AIJournalRequest:
    """Context needed to create one advisory AI journal report."""

    symbol: str
    strategy_name: str
    event_type: str
    input_snapshot: dict[str, object]
    risk_state: dict[str, object] = field(default_factory=dict)
    market_regime: dict[str, object] = field(default_factory=dict)
    outcome: dict[str, object] = field(default_factory=dict)
    bot_session_id: int | None = None
    signal_id: int | None = None
    trade_id: int | None = None


@dataclass(frozen=True)
class AIJournalResult:
    """Generated journal text and audit payload."""

    model: str
    prompt: str
    report_text: str
    raw_response: dict[str, object]


class AIJournalClient(Protocol):
    def generate(self, request: AIJournalRequest) -> AIJournalResult:
        """Generate an advisory journal report."""


class OpenAIResponsesJournalClient:
    """OpenAI Responses API client for advisory trade journal text."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 15.0,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def generate(self, request: AIJournalRequest) -> AIJournalResult:
        prompt = build_ai_journal_prompt(request)
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "You are an advisory trading journal analyst. "
                        "Explain the decision context, risks, and lessons. "
                        "Never recommend placing, modifying, or cancelling orders. "
                        "Never claim authority to mutate trading state."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "max_output_tokens": 500,
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                f"{self.base_url}/responses",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            raw = response.json()
        if not isinstance(raw, dict):
            raise ValueError("OpenAI response must be an object")
        return AIJournalResult(
            model=self.model,
            prompt=prompt,
            report_text=_extract_response_text(raw),
            raw_response=_json_object(raw),
        )


class AIJournalService:
    """Generate and persist advisory AI journal reports."""

    def __init__(self, session_factory: SessionFactory, client: AIJournalClient) -> None:
        self.session_factory = session_factory
        self.client = client

    def generate_and_persist(self, request: AIJournalRequest) -> int:
        result = self.client.generate(request)
        with session_scope(self.session_factory) as session:
            report = AIReportRepository(session).create(
                bot_session_id=request.bot_session_id,
                signal_id=request.signal_id,
                trade_id=request.trade_id,
                symbol=request.symbol,
                strategy_name=request.strategy_name,
                event_type=request.event_type,
                model=result.model,
                prompt=result.prompt,
                report_text=result.report_text,
                input_snapshot=request.input_snapshot,
                risk_state=request.risk_state,
                market_regime=request.market_regime,
                outcome=request.outcome,
                raw_response=result.raw_response,
            )
            return report.id


class AIJournalQueue:
    """Non-blocking queue that keeps AI network I/O off the trading path."""

    def __init__(
        self,
        service: AIJournalService | None,
        *,
        enabled: bool,
        maxsize: int = 1000,
        autostart: bool = True,
    ) -> None:
        self.service = service
        self.enabled = enabled and service is not None
        self._queue: Queue[AIJournalRequest | None] = Queue(maxsize=maxsize)
        self._lock = Lock()
        self._thread: Thread | None = None
        if self.enabled and autostart:
            self.start()

    def start(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = Thread(target=self._run, name="trading-bot-ai-journal", daemon=True)
            self._thread.start()

    def enqueue(self, request: AIJournalRequest) -> bool:
        if not self.enabled:
            return False
        try:
            self._queue.put_nowait(request)
            return True
        except Full:
            logger.warning("AI journal queue full, dropping request", extra={"symbol": request.symbol})
            return False

    def stop(self, *, drain: bool = False, timeout: float = 2.0) -> None:
        if not self.enabled:
            return
        if drain:
            self._queue.join()
        try:
            self._queue.put_nowait(None)
        except Full:
            logger.warning("AI journal queue full during stop; background thread is daemonized")
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)

    def _run(self) -> None:
        service = self.service
        if service is None:
            return
        while True:
            request = self._queue.get()
            try:
                if request is None:
                    return
                service.generate_and_persist(request)
            except Exception as exc:
                logger.exception("AI journal generation failed", extra={"error": str(exc)})
            finally:
                self._queue.task_done()


def build_ai_journal_prompt(request: AIJournalRequest) -> str:
    """Build a compact JSON prompt for an advisory AI journal report."""
    payload = {
        "task": "Create an advisory trade journal entry. Do not issue trade instructions.",
        "symbol": request.symbol,
        "strategy_name": request.strategy_name,
        "event_type": request.event_type,
        "input_snapshot": request.input_snapshot,
        "risk_state": request.risk_state,
        "market_regime": request.market_regime,
        "outcome": request.outcome,
        "required_output": {
            "summary": "one concise paragraph",
            "risk_notes": "bullet-style risks observed",
            "review_focus": "what the operator should inspect manually",
            "boundary": "advisory only; no orders or state mutation",
        },
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _extract_response_text(payload: dict[str, object]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    output = payload.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for content_item in content:
                if isinstance(content_item, dict):
                    text = content_item.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
        if chunks:
            return "\n".join(chunks).strip()
    return "AI journal response did not include text."


def _json_object(value: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], json.loads(json.dumps(value, default=str)))
