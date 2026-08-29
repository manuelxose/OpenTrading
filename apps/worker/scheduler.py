"""Unattended PAPER runner: scheduler + worker supervision (Phase 7).

Two modes:

- ``run_once`` — drive exactly one research cycle per watchlist instrument
  synchronously through the stage graph (tests, manual runs);
- ``serve`` — long-running: a scheduler thread starts cycles on the configured
  cadence and one thread per stage consumer group consumes the Redis stream.

Recovery is built into every layer (bus reconnect, store retries, stage
idempotency, PEL reclaim); a crashed thread logs and resumes on the next pass —
the platform keeps operating unattended while Redis/PostgreSQL return.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from decimal import Decimal
from typing import Any

from core.clock.clocks import Clock, SystemClock
from core.schemas.events import DomainEvent
from core.schemas.pipeline import PaperAccountRecord

from apps.worker.bus import InMemoryStreamBus
from apps.worker.pipeline import PaperPipeline, StageWorker
from apps.worker.stages.base import StageRuntime
from apps.worker.stages.ingest import IngestOrchestrator

__all__ = ["UnattendedPaperRunner"]

logger = logging.getLogger(__name__)


class UnattendedPaperRunner:
    """Runs the autonomous PAPER pipeline, optionally forever."""

    def __init__(
        self,
        *,
        rt: StageRuntime,
        pipeline: PaperPipeline,
        bus: object,
        config: Any,
        clock: Clock | None = None,
    ) -> None:
        self._rt = rt
        self._pipeline = pipeline
        self._bus = bus
        self._config = config
        self._clock = clock or SystemClock()
        self._ingest = IngestOrchestrator(rt)
        self._stop = threading.Event()
        self._steps: dict[str, int] = dict.fromkeys(config.watchlist, 0)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def seed_account(self) -> PaperAccountRecord:
        """Create the paper account if absent (idempotent)."""
        existing = self._rt.store.get_account(self._config.account_id)
        if existing is not None:
            return existing
        now = self._clock.now()
        record = PaperAccountRecord(
            account_id=self._config.account_id,
            currency=self._config.account_currency,
            balance=self._config.starting_balance,
            equity=self._config.starting_balance,
            realized_pnl=Decimal("0"),
            daily_pnl=Decimal("0"),
            peak_equity=self._config.starting_balance,
            consecutive_losses=0,
            last_loss_at=None,
            open_positions=0,
            version=1,
            updated_at=now,
        )
        return self._rt.store.upsert_account(record, expected_version=None)

    def rebuild_ledger(self) -> None:
        """Reattach persisted open positions (worker restart recovery)."""
        positions = self._rt.execution_store.list_positions(open_only=True)
        self._rt.ledger.load(positions)

    def run_once(self) -> list[DomainEvent]:
        """One full synchronous cycle across the watchlist.

        Drives the stage graph in-process (no bus round trip); returns every
        event produced, in order.
        """
        self.seed_account()
        self.rebuild_ledger()
        produced: list[DomainEvent] = []
        queue: deque[DomainEvent] = deque()
        for instrument_id in self._config.watchlist:
            self._steps[instrument_id] += 1
            step = self._steps[instrument_id]
            for event in self._ingest.start_cycle(instrument_id, step=step, now=self._clock.now()):
                queue.append(event)
        while queue:
            event = queue.popleft()
            produced.append(event)
            mirror_only = getattr(self._bus, "mirror_only", None)
            if mirror_only is not None:
                mirror_only(event)
            outputs = self._pipeline.dispatch(self._rt, event)
            queue.extend(outputs)
        return produced

    def serve(self) -> None:
        """Long-running unattended mode: scheduler + worker threads."""
        self.seed_account()
        self.rebuild_ledger()

        workers: list[StageWorker] = []
        for suffix, stages in self._pipeline.worker_specs():
            group = f"{self._config.bus.group_prefix}:{suffix.removeprefix('paper:')}"
            workers.append(
                StageWorker(
                    group=group,
                    consumer=self._config.bus.consumer_name,
                    stages=stages,
                    rt=self._rt,
                    bus=self._bus,
                    clock=self._clock,
                )
            )

        threads: list[threading.Thread] = []
        for worker in workers:
            thread = threading.Thread(
                target=self._worker_loop,
                args=(worker,),
                name=worker.group,
                daemon=True,
            )
            threads.append(thread)
        scheduler = threading.Thread(
            target=self._scheduler_loop, name="paper-scheduler", daemon=True
        )
        threads.append(scheduler)

        logger.info(
            "starting unattended paper pipeline: watchlist=%s cycle=%ds",
            list(self._config.watchlist),
            self._config.cycle_interval_seconds,
        )
        for thread in threads:
            thread.start()
        try:
            while not self._stop.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            logger.info("shutting down paper pipeline")
        self._stop.set()

    def stop(self) -> None:
        self._stop.set()

    # ── internals ─────────────────────────────────────────────────────────────

    def _worker_loop(self, worker: StageWorker) -> None:
        worker.start()
        while not self._stop.is_set():
            try:
                reclaimed, processed = worker.run_iteration()
                if (
                    reclaimed == 0
                    and processed == 0
                    and isinstance(getattr(self._bus, "raw_bus", self._bus), InMemoryStreamBus)
                ):
                    time.sleep(0.05)  # in-memory bus does not block
            except Exception as exc:  # unattended: never die silently
                logger.error("worker %s error: %s; resuming", worker.group, exc)
                time.sleep(min(5.0, self._config.bus.retry_max_seconds))

    def _scheduler_loop(self) -> None:
        while not self._stop.is_set():
            try:
                for instrument_id in self._config.watchlist:
                    self._steps[instrument_id] += 1
                    step = self._steps[instrument_id]
                    for event in self._ingest.start_cycle(
                        instrument_id, step=step, now=self._clock.now()
                    ):
                        self._bus.publish(event)  # type: ignore[attr-defined]
            except Exception as exc:
                logger.error("scheduler error: %s; resuming", exc)
            self._stop.wait(self._config.cycle_interval_seconds)
