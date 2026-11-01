"""Composition root: the only module that knows about concrete adapters.

Builds infrastructure adapters from ``Settings`` and injects them into use cases.
Wiring is added phase by phase as adapters land.
"""
