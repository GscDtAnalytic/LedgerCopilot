"""Evaluation + gating harness.

Runs prompt/policy versions against the dataset slices, computes metrics, and
gates promotion (``dev`` → ``staging`` → ``production``). ``eval.gate`` must exit
non-zero when any promotion rule is violated.
"""
