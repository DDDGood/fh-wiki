"""Forza Horizon UDP telemetry packet parser (currently FH5).

Composition:
    sled.SLED_LAYOUT          # FM7-compatible 232 bytes, shared across Forza
    horizon_fh5.HORIZON_FH5_LAYOUT  # FH5 'Car Dash' extension (91 bytes incl. pad)
    -------------------------
    total parsed length:      323 bytes (real packets: 324, trailing pad ignored)

Public API (preserved from earlier monolithic packet.py):
    Packet, PACKET_SIZE, FIELD_NAMES, PacketLengthError, parse(data)
    resolve_game(requested: str, packet_size: int | None) -> str

FH6 future plan:
    Add horizon_fh6.py with HORIZON_FH6_LAYOUT, then extend resolve_game() to
    route 'auto'/'fh6' to that layout (see FH6_遷移計畫.md Phase 2).

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


class UnsupportedGameError(NotImplementedError):
    """Raised when a game version is requested but its parser is not yet implemented."""


# Known packet sizes per game (raw datagram length from the wire, including any
# trailing pad). Used by resolve_game('auto') for first-packet routing.
# FH5 Car Dash format: 324 bytes on wire (we parse 323, last byte is pad).
KNOWN_PACKET_SIZES: dict[int, str] = {
    324: "fh5",
    # 325+: "fh6"  # populate once observed
}


def resolve_game(requested: str, packet_size: int | None = None) -> str:
    """Resolve a requested game label ('fh5' | 'fh6' | 'auto') to a concrete one.

    - 'fh5': returned as-is (only currently implemented parser).
    - 'fh6': raises UnsupportedGameError until horizon_fh6.py exists.
    - 'auto': if packet_size is provided, look it up; otherwise fall back to 'fh5'.

    Returns the resolved game label.
    """
    if requested == "fh5":
        return "fh5"
    if requested == "fh6":
        raise UnsupportedGameError(
            "FH6 packet parser not yet implemented. "
            "Add scripts/forza_telemetry/horizon_fh6.py and update resolve_game(). "
            "For now, use --game fh5 (or --game auto, which falls back to fh5)."
        )
    if requested == "auto":
        if packet_size is None:
            return "fh5"
        detected = KNOWN_PACKET_SIZES.get(packet_size)
        if detected is None:
            # Unknown size — could be a future FH6 packet. Surface clearly.
            raise UnsupportedGameError(
                f"unknown packet size {packet_size} bytes; cannot auto-route. "
                f"Known sizes: {KNOWN_PACKET_SIZES}. If this is FH6, add the parser "
                "in scripts/forza_telemetry/horizon_fh6.py."
            )
        if detected == "fh5":
            return "fh5"
        raise UnsupportedGameError(
            f"packet size {packet_size} routes to '{detected}', parser not yet implemented."
        )
    raise ValueError(f"unknown game label: {requested!r}; expected fh5 / fh6 / auto")


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
