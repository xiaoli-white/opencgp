"""Adapter layer: concrete implementations of the ports.

Each subpackage corresponds to one kind of port and ships a ``builtin``
(single-node default) implementation; production can add an ``external``
implementation and plug it into the same port.
"""

# Subpackages are imported lazily on demand by the container; this file only organizes the namespace.
