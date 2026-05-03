"""Session: one race recording = one folder under sessions/.

Folder name: {YYYY-MM-DD_HH-MM-SS}_car{CarOrdinal}_PI{PerformanceIndex}
Contents:
    raw.csv   - one row per packet; columns = arrival_ts, is_rewind, *FIELD_NAMES
    meta.json - written on finalize(); race summary + car id + rewind stats

Rewind detection
----------------
We track CurrentRaceTime, which in race mode resets to 0 at race start and
increments monotonically with the race. The in-game rewind makes CurrentRaceTime
jump backward; we flag all packets from the backward jump until the value climbs
back above the previous high-water mark.

(Empirical FH5 observation: TimestampMS is the game's wall clock and never goes
backward during rewind, so it cannot be used for this. CurrentRaceTime is the
only field that actually reflects the rewound time.)

The 'replayed' segment is flagged but not deleted — analysis stages can filter
on the is_rewind column while raw data stays intact for audit.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

from . import packet as pkt

REWIND_THRESHOLD_S = 0.1  # backward jump in CurrentRaceTime (seconds) that counts as rewind


@dataclass
class Session:
    output_root: Path
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).astimezone())
    folder: Path | None = None
    _csv_file: IO[str] | None = None
    _csv_writer: csv.writer | None = None
    _packet_count: int = 0
    _first_packet: pkt.Packet | None = None
    _last_packet: pkt.Packet | None = None
    _max_lap_number: int = 0
    _best_lap: float = 0.0
    _last_lap: float = 0.0

    # Rewind tracking (uses CurrentRaceTime, not TimestampMS)
    _prev_crt: float | None = None
    _max_crt: float = 0.0        # high-water mark of CurrentRaceTime seen so far
    _in_rewind: bool = False
    _rewind_count: int = 0
    _rewound_packet_count: int = 0
    _total_rewound_seconds: float = 0.0  # cumulative time rewound

    def _ensure_open(self, p: pkt.Packet) -> None:
        """Lazy-open the session folder using identification from the first packet."""
        if self.folder is not None:
            return
        ts = self.started_at.strftime("%Y-%m-%d_%H-%M-%S")
        base = f"{ts}_car{p.CarOrdinal}_PI{p.CarPerformanceIndex}"
        folder = self.output_root / base
        # Collision guard: two sessions started within the same second with the
        # same car (e.g., race A finalizes and race B starts immediately) would
        # otherwise overwrite each other's CSV.
        suffix = 2
        while folder.exists():
            folder = self.output_root / f"{base}_{suffix}"
            suffix += 1
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)

        csv_path = self.folder / "raw.csv"
        self._csv_file = csv_path.open("w", newline="", encoding="utf-8")
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow(["arrival_ts", "is_rewind", *pkt.FIELD_NAMES])
        self._first_packet = p

    def _classify_rewind(self, p: pkt.Packet) -> int:
        """Update rewind state machine and return is_rewind flag (0 or 1) for this packet.

        Empirical FH5 behavior during in-game rewind:
          - IsRaceOn drops to 0 for the duration of the rewind animation
          - CurrentRaceTime is zeroed during the animation
          - When animation ends, IsRaceOn returns to 1 and CurrentRaceTime
            jumps to the rewound-to point (lower than the previous peak)

        Race-end behavior is similar (IsRaceOn drops, CRT zeros), so we cannot
        rely on the IsRaceOn=0 + CRT=0 transition itself — it could be either.

        Therefore: only run the comparison on packets where IsRaceOn=1. The
        real rewind is detected on the *return* packet (CRT lower than prev
        peak), and race-end is automatically excluded because IsRaceOn never
        comes back to 1 after the race truly ends.
        """
        if int(p.IsRaceOn) != 1:
            return 0

        crt = float(p.CurrentRaceTime)

        if self._prev_crt is None:
            self._prev_crt = crt
            self._max_crt = crt
            return 0

        if not self._in_rewind:
            if crt < self._prev_crt - REWIND_THRESHOLD_S:
                # Backward jump → entering rewind. Note: jump amount uses
                # _prev_crt (last IsRaceOn=1 packet, i.e. just before rewind
                # animation), giving the actual rewound seconds.
                self._in_rewind = True
                self._rewind_count += 1
                self._total_rewound_seconds += (self._max_crt - crt)
                self._rewound_packet_count += 1
                self._prev_crt = crt
                return 1
            if crt > self._max_crt:
                self._max_crt = crt
            self._prev_crt = crt
            return 0

        # Currently in rewind: stay flagged until we climb back past the previous peak.
        if crt >= self._max_crt:
            self._in_rewind = False
            self._max_crt = crt
            self._prev_crt = crt
            return 0
        self._rewound_packet_count += 1
        self._prev_crt = crt
        return 1

    def write_packet(self, p: pkt.Packet, arrival_ts: float) -> None:
        self._ensure_open(p)
        assert self._csv_writer is not None
        is_rewind = self._classify_rewind(p)
        self._csv_writer.writerow([f"{arrival_ts:.6f}", is_rewind, *p])
        self._packet_count += 1
        self._last_packet = p
        # Only update lap counter for active-race packets (IsRaceOn=0 packets
        # during rewind animation / race end zero out LapNumber spuriously).
        if int(p.IsRaceOn) == 1 and p.LapNumber > self._max_lap_number:
            self._max_lap_number = p.LapNumber
        if p.BestLap > 0 and (self._best_lap == 0 or p.BestLap < self._best_lap):
            self._best_lap = p.BestLap
        if p.LastLap > 0:
            self._last_lap = p.LastLap

    def write_packets(self, packets: list[tuple[pkt.Packet, float]]) -> None:
        """Bulk write — used to flush the buffer when transitioning BUFFERING -> RECORDING."""
        for p, ts in packets:
            self.write_packet(p, ts)

    @property
    def is_open(self) -> bool:
        return self.folder is not None

    @property
    def packet_count(self) -> int:
        return self._packet_count

    def is_continuation(self, p: pkt.Packet) -> bool:
        """Decide whether `p` (the first IsRaceOn=1 packet after an IsRaceOn=0
        stretch) is the same race resuming, or a new race starting.

        Decision matrix:
          - Different car (CarOrdinal changed) → new
          - LapNumber regressed (< max seen so far) → new (race restart or
            different race)
          - CurrentRaceTime freshly zeroed (< 1.0) while we previously had
            meaningful race time (max_crt >= 1.0) → new (game zeroed the clock,
            which only happens at race start, not pause/rewind)
          - Otherwise → continuation (pause or rewind)

        Returns True for the very first packet of a session (no prior state).
        """
        if self._first_packet is None:
            return True
        if int(p.CarOrdinal) != int(self._first_packet.CarOrdinal):
            return False
        if int(p.LapNumber) < self._max_lap_number:
            return False
        if float(p.CurrentRaceTime) < 1.0 and self._max_crt >= 1.0:
            return False
        return True

    def finalize(self) -> Path | None:
        """Close CSV, write meta.json. Returns the session folder path, or None if empty."""
        if not self.is_open:
            return None
        assert self._csv_file is not None and self.folder is not None
        self._csv_file.close()

        ended_at = datetime.now(timezone.utc).astimezone()
        duration = (ended_at - self.started_at).total_seconds()
        first = self._first_packet
        meta = {
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "ended_at": ended_at.isoformat(timespec="seconds"),
            "duration_seconds": round(duration, 3),
            "packet_count": self._packet_count,
            "car": {
                "ordinal": int(first.CarOrdinal) if first else None,
                "class": int(first.CarClass) if first else None,
                "performance_index": int(first.CarPerformanceIndex) if first else None,
                "drivetrain_type": int(first.DrivetrainType) if first else None,
                "num_cylinders": int(first.NumCylinders) if first else None,
            },
            "race": {
                # FH5 LapNumber is 0-indexed (lap 0 = first lap).
                # max_lap_number observed + 1 = total laps reached.
                "total_laps": int(self._max_lap_number) + 1,
                "max_lap_number": int(self._max_lap_number),
                "best_lap_seconds": round(self._best_lap, 3) if self._best_lap > 0 else None,
                "last_lap_seconds": round(self._last_lap, 3) if self._last_lap > 0 else None,
            },
            "rewinds": {
                "count": self._rewind_count,
                "total_seconds_rewound": round(self._total_rewound_seconds, 3),
                "affected_packet_count": self._rewound_packet_count,
            },
        }
        meta_path = self.folder / "meta.json"
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.folder
