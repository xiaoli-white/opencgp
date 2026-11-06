"""OpenCGP · backend application package.

Follows the Ports & Adapters architecture:

- ``ports/``      abstract interfaces (Python Protocol); business code depends on them only.
- ``adapters/``   concrete implementations (builtin single-node defaults plus external ones).
- ``container.py`` minimal dependency injection that picks adapters from the settings.

Rule: every infrastructure and capability stays pluggable; switching an adapter is a
configuration change, never a change to business code.
"""
