"""FH5 'Car Dash' extension layout (Horizon-specific, appends after Sled).

Layout offsets (relative to start of Horizon section after Sled's 232 bytes):
    Bytes 0..11   : HorizonPlaceholder (12 bytes, unused — skip)
    Bytes 12..90  : Dash extension (race + position + UI inputs, 79 bytes)

Combined with Sled (232 bytes), total parsed size is 323 bytes. Real FH5
packets are 324 bytes; the trailing byte is padding and is ignored.
"""

from __future__ import annotations

HORIZON_FH5_LAYOUT: list[tuple[str, str]] = [
    # HorizonPlaceholder (12 bytes, skip)
    ("_pad_horizon", "12x"),
    # Dash extension
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
