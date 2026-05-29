"""Policy engine + versioning (pure, no I/O).

Business policies are deterministic code, not prompts. Each policy
returns a verdict and whether it ``requires_human``. Policies are versioned with
``dev``/``staging``/``production`` aliases and only promoted through the gating
rules. Lands in Phase 2.
"""
