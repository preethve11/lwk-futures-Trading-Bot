"""Order lifecycle state machine for protected bracket orders."""

from __future__ import annotations

from dataclasses import dataclass

from app.persistence.models import OrderLifecycleState, OrderModel


@dataclass
class OrderStateMachine:
    """Validate and apply order protection lifecycle transitions."""

    state: OrderLifecycleState = OrderLifecycleState.PENDING
    entry_placed: bool = False
    tp_placed: bool = False
    sl_placed: bool = False

    @classmethod
    def from_order(cls, order: OrderModel) -> OrderStateMachine:
        """Create a state machine initialized from an order row."""
        state = OrderLifecycleState(order.state)
        return cls(
            state=state,
            entry_placed=state
            in {
                OrderLifecycleState.ENTRY_PLACED,
                OrderLifecycleState.TP_PLACED,
                OrderLifecycleState.SL_PLACED,
                OrderLifecycleState.PROTECTED,
            },
            tp_placed=state in {OrderLifecycleState.TP_PLACED, OrderLifecycleState.PROTECTED},
            sl_placed=state in {OrderLifecycleState.SL_PLACED, OrderLifecycleState.PROTECTED},
        )

    def mark_entry_placed(self) -> OrderLifecycleState:
        """Mark the entry order placed."""
        if self.state == OrderLifecycleState.FAILED_UNPROTECTED:
            raise ValueError("cannot place entry after FAILED_UNPROTECTED")
        self.entry_placed = True
        return self._refresh_state()

    def mark_tp_placed(self) -> OrderLifecycleState:
        """Mark the take-profit order placed."""
        self._require_entry()
        self.tp_placed = True
        return self._refresh_state()

    def mark_sl_placed(self) -> OrderLifecycleState:
        """Mark the stop-loss order placed."""
        self._require_entry()
        self.sl_placed = True
        return self._refresh_state()

    def mark_failed_unprotected(self) -> OrderLifecycleState:
        """Mark an entry with missing protection as failed."""
        if self.state == OrderLifecycleState.PROTECTED:
            raise ValueError("cannot fail a protected order")
        self.state = OrderLifecycleState.FAILED_UNPROTECTED
        return self.state

    def apply_to(self, order: OrderModel) -> OrderModel:
        """Apply the current state to an order row."""
        order.state = self.state
        return order

    def _require_entry(self) -> None:
        if not self.entry_placed:
            raise ValueError("entry must be placed before protection orders")
        if self.state == OrderLifecycleState.FAILED_UNPROTECTED:
            raise ValueError("cannot protect a failed order")

    def _refresh_state(self) -> OrderLifecycleState:
        if not self.entry_placed:
            self.state = OrderLifecycleState.PENDING
        elif self.tp_placed and self.sl_placed:
            self.state = OrderLifecycleState.PROTECTED
        elif self.tp_placed:
            self.state = OrderLifecycleState.TP_PLACED
        elif self.sl_placed:
            self.state = OrderLifecycleState.SL_PLACED
        else:
            self.state = OrderLifecycleState.ENTRY_PLACED
        return self.state
