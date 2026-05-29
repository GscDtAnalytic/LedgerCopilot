"""Pydantic v2 schemas for API request/response shapes.

Kept separate from packages/domain/ (pure business entities) and apps/api/models/
(ORM). These are the wire-format contracts the API exposes to clients. Types are
derived from the domain vocabulary, not duplicated independently.
"""
