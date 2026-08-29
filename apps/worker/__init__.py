"""OpenTrading worker service (Phase 7).

The worker runs the autonomous PAPER pipeline over Redis Streams consumer
groups (INV-15): research → fusion → proposal → risk → order intent → Nautilus
paper execution → position management → accounting → post-trade review, with
full trace_id propagation and restart recovery. See apps/worker/README.md and
docs/architecture/PHASE7_AUTONOMOUS_PAPER.md.
"""
