"""Reconciliation engine (pure, no I/O).

Reconciles extracted fields against purchase orders, payments, ledger entries and
history, returning a match flag plus the deltas that explain a mismatch. Pure and
deterministic; the retrieved context it reasons over is fetched at the I/O
boundary and passed in. Lands in Phase 2.
"""
