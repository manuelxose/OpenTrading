"""Clock abstractions — the only sanctioned sources of time."""

from core.clock.clocks import Clock, SystemClock, VirtualClock

__all__ = ["Clock", "SystemClock", "VirtualClock"]
