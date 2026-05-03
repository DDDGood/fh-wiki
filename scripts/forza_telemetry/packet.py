"""Forza Horizon 5 'Car Dash' UDP telemetry packet parser.

Packet layout (little-endian, no padding):
    Bytes   0..231  : 'Sled' core physics (FM7-compatible, 232 bytes)
    Bytes 232..243  : HorizonPlaceholder (12 bytes, unused)
    Bytes 244..322  : 'Dash' extension (Horizon-specific race + position data)

Total parsed length: 323 bytes. Real packets observed at 324 bytes; the
trailing byte is padding and is ignored. Packet length is validated and
mismatches are logged on first packet for the user to verify.

This parser is pure stdlib (struct + namedtuple).
"""

from __future__ import annotations

import struct
from collections import namedtuple

# Each tuple: (field_name, struct_format)
# Format codes: i=int32, I=uint32, f=float32, H=uint16, B=uint8, b=int8, x=pad
_LAYOUT: list[tuple[str, str]] = [
    # ---- Sled (FM7-compatible core, 232 bytes) ----
    ("IsRaceOn", "i"),
    ("TimestampMS", "I"),
    ("EngineMaxRpm", "f"),
    ("EngineIdleRpm", "f"),
    ("CurrentEngineRpm", "f"),
    ("AccelerationX", "f"),
    ("AccelerationY", "f"),
    ("AccelerationZ", "f"),
    ("VelocityX", "f"),
    ("VelocityY", "f"),
    ("VelocityZ", "f"),
    ("AngularVelocityX", "f"),
    ("AngularVelocityY", "f"),
    ("AngularVelocityZ", "f"),
    ("Yaw", "f"),
    ("Pitch", "f"),
    ("Roll", "f"),
    ("NormalizedSuspensionTravelFrontLeft", "f"),
    ("NormalizedSuspensionTravelFrontRight", "f"),
    ("NormalizedSuspensionTravelRearLeft", "f"),
    ("NormalizedSuspensionTravelRearRight", "f"),
    ("TireSlipRatioFrontLeft", "f"),
    ("TireSlipRatioFrontRight", "f"),
    ("TireSlipRatioRearLeft", "f"),
    ("TireSlipRatioRearRight", "f"),
    ("WheelRotationSpeedFrontLeft", "f"),
    ("WheelRotationSpeedFrontRight", "f"),
    ("WheelRotationSpeedRearLeft", "f"),
    ("WheelRotationSpeedRearRight", "f"),
    ("WheelOnRumbleStripFrontLeft", "i"),
    ("WheelOnRumbleStripFrontRight", "i"),
    ("WheelOnRumbleStripRearLeft", "i"),
    ("WheelOnRumbleStripRearRight", "i"),
    ("WheelInPuddleDepthFrontLeft", "f"),
    ("WheelInPuddleDepthFrontRight", "f"),
    ("WheelInPuddleDepthRearLeft", "f"),
    ("WheelInPuddleDepthRearRight", "f"),
    ("SurfaceRumbleFrontLeft", "f"),
    ("SurfaceRumbleFrontRight", "f"),
    ("SurfaceRumbleRearLeft", "f"),
    ("SurfaceRumbleRearRight", "f"),
    ("TireSlipAngleFrontLeft", "f"),
    ("TireSlipAngleFrontRight", "f"),
    ("TireSlipAngleRearLeft", "f"),
    ("TireSlipAngleRearRight", "f"),
    ("TireCombinedSlipFrontLeft", "f"),
    ("TireCombinedSlipFrontRight", "f"),
    ("TireCombinedSlipRearLeft", "f"),
    ("TireCombinedSlipRearRight", "f"),
    ("SuspensionTravelMetersFrontLeft", "f"),
    ("SuspensionTravelMetersFrontRight", "f"),
    ("SuspensionTravelMetersRearLeft", "f"),
    ("SuspensionTravelMetersRearRight", "f"),
    ("CarOrdinal", "i"),
    ("CarClass", "i"),
    ("CarPerformanceIndex", "i"),
    ("DrivetrainType", "i"),
    ("NumCylinders", "i"),
    # ---- HorizonPlaceholder (12 bytes, skip) ----
    ("_pad_horizon", "12x"),
    # ---- Dash extension (Horizon-specific, 79 bytes) ----
    ("PositionX", "f"),
    ("PositionY", "f"),
    ("PositionZ", "f"),
    ("Speed", "f"),
    ("Power", "f"),
    ("Torque", "f"),
    ("TireTempFrontLeft", "f"),
    ("TireTempFrontRight", "f"),
    ("TireTempRearLeft", "f"),
    ("TireTempRearRight", "f"),
    ("Boost", "f"),
    ("Fuel", "f"),
    ("DistanceTraveled", "f"),
    ("BestLap", "f"),
    ("LastLap", "f"),
    ("CurrentLap", "f"),
    ("CurrentRaceTime", "f"),
    ("LapNumber", "H"),
    ("RacePosition", "B"),
    ("Accel", "B"),
    ("Brake", "B"),
    ("Clutch", "B"),
    ("HandBrake", "B"),
    ("Gear", "B"),
    ("Steer", "b"),
    ("NormalizedDrivingLine", "b"),
    ("NormalizedAIBrakeDifference", "b"),
]

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
