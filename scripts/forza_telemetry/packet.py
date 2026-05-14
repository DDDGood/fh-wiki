"""Forza Horizon UDP telemetry packet parser (currently FH5).

Composition:
    sled.SLED_LAYOUT          # FM7-compatible 232 bytes, shared across Forza
    horizon_fh5.HORIZON_FH5_LAYOUT  # FH5 'Car Dash' extension (91 bytes incl. pad)
    -------------------------
    total parsed length:      323 bytes (real packets: 324, trailing pad ignored)

Public API (preserved from earlier monolithic packet.py):
    Packet, PACKET_SIZE, FIELD_NAMES, PacketLengthError, parse(data)

FH6 future plan:
    Add horizon_fh6.py with HORIZON_FH6_LAYOUT and route by packet size in
    recorder (see FH6_遷移計畫.md Phase 2).

This parser is pure stdlib (struct + namedtuple).
"""

from __future__ import annotations

import struct
from collections import namedtuple

from .sled import SLED_LAYOUT
from .horizon_fh5 import HORIZON_FH5_LAYOUT

_LAYOUT: list[tuple[str, str]] = SLED_LAYOUT + HORIZON_FH5_LAYOUT

FIELD_NAMES: list[str] = [name for name, _ in _LAYOUT if not name.startswith("_pad")]
_STRUCT_FMT: str = "<" + "".join(fmt for _, fmt in _LAYOUT)
PACKET_SIZE: int = struct.calcsize(_STRUCT_FMT)  # 323

_struct = struct.Struct(_STRUCT_FMT)
Packet = namedtuple("Packet", FIELD_NAMES)


class PacketLengthError(ValueError):
    """Raised when an incoming packet is too short to parse."""


def parse(data: bytes) -> Packet:
    """Parse a Forza Car Dash UDP datagram into a Packet namedtuple.

    Accepts any datagram >= PACKET_SIZE bytes; trailing bytes are ignored
    (Forza pads to 324 bytes; we parse 323).
    """
    if len(data) < PACKET_SIZE:
        raise PacketLengthError(
            f"packet too short: got {len(data)} bytes, need >= {PACKET_SIZE}. "
            "Confirm Data Out format is set to 'Car Dash' (not 'Sled')."
        )
    return Packet._make(_struct.unpack_from(data, 0))
