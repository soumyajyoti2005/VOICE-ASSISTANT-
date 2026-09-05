import csv
import os
import time
from dataclasses import dataclass, asdict
from typing import Optional
from threading import Lock

from backend.agent.state import state_manager


@dataclass
class LatencyRecord:
    turn_id: int
    response_id: int
    t0: float
    t1: Optional[float]
    t2: Optional[float]
    t3: Optional[float]
    t4: Optional[float]
    t5: Optional[float]
    total_ms: Optional[float]
    cache_status: str
    speech_provider: str


class LatencyLogger:
    def __init__(self, filepath: str = "metrics/results.csv"):
        self.filepath = filepath
        self._lock = Lock()
        self._initialized = False
        self._warm_cache = False

    def _ensure_initialized(self):
        if not self._initialized:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            if not os.path.exists(self.filepath):
                with open(self.filepath, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        "turn_id", "response_id", "t0", "t1", "t2", "t3", "t4", "t5",
                        "total_ms", "cache_status", "speech_provider"
                    ])
            self._initialized = True

    def log_turn(
        self,
        turn_id: int,
        response_id: int,
        t0: float,
        t1: Optional[float],
        t2: Optional[float],
        t3: Optional[float],
        t4: Optional[float],
        t5: Optional[float],
        speech_provider: str = "Rime",
    ):
        self._ensure_initialized()

        total_ms = None
        if t0 is not None and t5 is not None:
            total_ms = (t5 - t0) * 1000

        cache_status = "warm" if self._warm_cache else "cold"
        self._warm_cache = True

        record = LatencyRecord(
            turn_id=turn_id,
            response_id=response_id,
            t0=t0,
            t1=t1,
            t2=t2,
            t3=t3,
            t4=t4,
            t5=t5,
            total_ms=total_ms,
            cache_status=cache_status,
            speech_provider=speech_provider,
        )

        with self._lock:
            with open(self.filepath, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    record.turn_id,
                    record.response_id,
                    record.t0,
                    record.t1,
                    record.t2,
                    record.t3,
                    record.t4,
                    record.t5,
                    record.total_ms,
                    record.cache_status,
                    record.speech_provider,
                ])

    def get_recent_records(self, limit: int = 100) -> list:
        self._ensure_initialized()
        records = []
        with open(self.filepath, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)
        return records[-limit:]


latency_logger = LatencyLogger()


def log_turn_metrics(state_dict: dict):
    state = state_manager.state if hasattr(state_manager, 'state') else None
    if state and state.current_turn_t0 is not None:
        latency_logger.log_turn(
            turn_id=state.turn_id,
            response_id=state.active_response_id,
            t0=state.current_turn_t0,
            t1=state.current_turn_t1,
            t2=state.current_turn_t2,
            t3=state.current_turn_t3,
            t4=state.current_turn_t4,
            t5=state.current_turn_t5,
            speech_provider=state.speech_provider,
        )