"""Policy engine + versioning (pure, no I/O).

Business policies are deterministic code, not prompts.
Phase 2 ships a set of essential rules under alias 'dev'. Each policy returns a
verdict and whether it requires_human. Policies are versioned with
``dev``/``staging``/``production`` aliases and only promoted through gating
. See engine.py for the rule implementations.
"""

from packages.policy.engine import PolicyDecision, run_policy

__all__ = ["PolicyDecision", "run_policy"]
