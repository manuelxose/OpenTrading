"""Trading engines.

Each engine is implemented in its own Phase (see docs/architecture/IMPLEMENTATION_ORDER.md):

- ``signal_fusion`` — Phase 7 (INV-16, calibrated weights)
- ``risk``         — Phase 5 (INV-4, implemented: deterministic, property-tested)
- ``execution``    — Phase 7 (INV-6, implemented: broker reconciliation + Safe Mode)
- ``portfolio``    — Phase 7 (allocation, exposure)
- ``posttrade``    — Phase 7 (postmortem learning loop)
- ``promotion``    — Phase 10 (INV-8, no auto-promotion)

Phase 0 shipped the canonical contracts, clock and event envelope these engines
plug into (``core/``); Phase 5 added the deterministic Risk & Policy Engine
(``engines/risk``).
"""
