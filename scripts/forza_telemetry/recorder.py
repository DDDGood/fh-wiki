"""Recorder: UDP listener + state machine.

States and transitions:

    IDLE
      |--(IsRaceOn 0->1)--> BUFFERING

    BUFFERING (in-memory ring buffer, no disk I/O)
      |--(competitive flag detected)--> RECORDING (flush buffer to disk)
      |--(buffer_seconds elapsed, no competitive flag)--> IDLE (discard)
      |--(IsRaceOn 1->0)--> IDLE (discard)

    RECORDING (writing to Session)
      |--(IsRaceOn=1, normal)--> write packet
      |--(IsRaceOn 1->0)--> mark idle, write packet, keep recording
      |--(IsRaceOn 0->1, Session.is_continuation(p))--> resume same session
      |--(IsRaceOn 0->1, NOT is_continuation)--> finalize old, start new
      |--(IsRaceOn=0 sustained > idle_timeout_seconds)--> finalize -> IDLE

A 'competitive flag' = LapNumber > 0 OR RacePosition > 0.
This excludes free-roam driving (both stay 0) while still catching PGG races,
Rivals time trials, championship events, etc.

Session continuation (in RECORDING) decides between pause/rewind (same session)
and new race (new session) by comparing packet content rather than elapsed time.
See Session.is_continuation() for the decision rules. Idle timeout is only a
safety net for sessions that are truly abandoned (e.g., game closed without
returning).

(Note: CurrentRaceTime is NOT a reliable race indicator at the BUFFERING level —
empirical FH5 data shows it increments during free roam too.)
"""

from __future__ import annotations

import logging
import socket
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from . import packet as pkt
from .session import Session

log = logging.getLogger("forza_telemetry")


class State(Enum):
    IDLE = "idle"
    BUFFERING = "buffering"
    RECORDING = "recording"


def is_competitive_event(p: pkt.Packet) -> bool:
    """True when packet indicates a structured timed event (not free roam)."""
    return p.LapNumber > 0 or p.RacePosition > 0


@dataclass
class RecorderConfig:
    port: int = 5300
    bind_host: str = "0.0.0.0"
    output_dir: Path = Path("data/forza_telemetry/sessions")
    buffer_seconds: float = 30.0
    # Safety net only — finalizes a session if IsRaceOn stays 0 for this long
    # without any IsRaceOn=1 packet arriving. Pause/rewind detection uses packet
    # content (Session.is_continuation), not this timer.
    idle_timeout_seconds: float = 300.0
    socket_timeout: float = 1.0
    # Auto-generate summary.md after each session finalizes.
    auto_summarize: bool = True


@dataclass
class Recorder:
    config: RecorderConfig
    state: State = State.IDLE
    _buffer: deque[tuple[pkt.Packet, float]] = field(default_factory=deque)
    _buffer_started_at: float = 0.0
    # Set when IsRaceOn drops to 0 in RECORDING. Cleared on next IsRaceOn=1.
    # Used only for the safety-net idle timeout.
    _idle_started_at: float = 0.0
    _session: Session | None = None
    _stop: bool = False
    _first_packet_logged: bool = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        cfg = self.config
        cfg.output_dir.mkdir(parents=True, exist_ok=True)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((cfg.bind_host, cfg.port))
        sock.settimeout(cfg.socket_timeout)
        log.info("listening on %s:%d (state=%s)", cfg.bind_host, cfg.port, self.state.value)

        try:
            while not self._stop:
                try:
                    data, _ = sock.recvfrom(2048)
                except socket.timeout:
                    self._tick_no_packet()
                    continue
                except OSError as e:
                    log.error("socket error: %s", e)
                    break

                self._handle_datagram(data)
        finally:
            sock.close()
            self._finalize_if_open(reason="shutdown")

    # ---- packet path ----

    def _handle_datagram(self, data: bytes) -> None:
        try:
            p = pkt.parse(data)
        except pkt.PacketLengthError as e:
            if not self._first_packet_logged:
                log.error("first packet: %s", e)
                self._first_packet_logged = True
            return

        if not self._first_packet_logged:
            log.info(
                "first packet OK: len=%d, IsRaceOn=%d, CarOrdinal=%d, PI=%d",
                len(data), p.IsRaceOn, p.CarOrdinal, p.CarPerformanceIndex,
            )
            self._first_packet_logged = True

        now = time.monotonic()
        race_on = p.IsRaceOn == 1

        if self.state is State.IDLE:
            if race_on:
                self._enter_buffering(now)
                self._buffer.append((p, time.time()))
            return

        if self.state is State.BUFFERING:
            if not race_on:
                self._discard_buffer(reason="IsRaceOn dropped during buffering")
                return
            self._buffer.append((p, time.time()))
            if is_competitive_event(p):
                self._enter_recording()
            elif (now - self._buffer_started_at) >= self.config.buffer_seconds:
                self._discard_buffer(reason="buffer timeout (likely free roam)")
            return

        if self.state is State.RECORDING:
            assert self._session is not None
            self._handle_recording_packet(p, race_on, now)
            return

    def _handle_recording_packet(self, p: pkt.Packet, race_on: bool, now: float) -> None:
        assert self._session is not None

        if race_on:
            if self._idle_started_at > 0:
                # Resuming from an IsRaceOn=0 stretch (pause / rewind / race
                # boundary). Decide based on packet content whether this is
                # the same race or a fresh one.
                idle_duration = now - self._idle_started_at
                self._idle_started_at = 0.0

                if self._session.is_continuation(p):
                    log.info(
                        "RECORDING resumed (idle %.1fs, same session: car=%d lap=%d crt=%.2f)",
                        idle_duration, p.CarOrdinal, p.LapNumber, p.CurrentRaceTime,
                    )
                    self._session.write_packet(p, time.time())
                    return

                # New race detected — finalize current session and re-enter
                # the BUFFERING flow with this packet as the first observation.
                log.info(
                    "RECORDING ended (idle %.1fs, new race detected: car=%d lap=%d crt=%.2f)",
                    idle_duration, p.CarOrdinal, p.LapNumber, p.CurrentRaceTime,
                )
                self._finalize_if_open(reason="new race detected")
                self._enter_buffering(now)
                self._buffer.append((p, time.time()))
                if is_competitive_event(p):
                    self._enter_recording()
                return

            # Normal active recording.
            self._session.write_packet(p, time.time())
            return

        # IsRaceOn=0: pause / rewind animation / race-end transition.
        # Write packet for audit; mark idle for the safety-net timeout.
        self._session.write_packet(p, time.time())
        if self._idle_started_at == 0.0:
            self._idle_started_at = now
        elif (now - self._idle_started_at) >= self.config.idle_timeout_seconds:
            self._finalize_if_open(
                reason=f"idle timeout ({self.config.idle_timeout_seconds:.0f}s, abandoned)"
            )

    def _tick_no_packet(self) -> None:
        """Called when recv times out — advance time-based state transitions."""
        now = time.monotonic()
        if self.state is State.BUFFERING:
            if (now - self._buffer_started_at) >= self.config.buffer_seconds:
                self._discard_buffer(reason="buffer timeout (no packets)")
        elif self.state is State.RECORDING and self._idle_started_at > 0:
            if (now - self._idle_started_at) >= self.config.idle_timeout_seconds:
                self._finalize_if_open(
                    reason=f"idle timeout ({self.config.idle_timeout_seconds:.0f}s, no packets)"
                )

    # ---- state transitions ----

    def _enter_buffering(self, now: float) -> None:
        self.state = State.BUFFERING
        self._buffer_started_at = now
        self._buffer.clear()
        log.info("state -> BUFFERING (waiting for competitive flag)")

    def _discard_buffer(self, reason: str) -> None:
        log.info("state -> IDLE (%s, %d packets discarded)", reason, len(self._buffer))
        self._buffer.clear()
        self._buffer_started_at = 0.0
        self.state = State.IDLE

    def _enter_recording(self) -> None:
        self._session = Session(output_root=self.config.output_dir)
        buffered = list(self._buffer)
        self._session.write_packets(buffered)
        self._buffer.clear()
        self._buffer_started_at = 0.0
        self._idle_started_at = 0.0
        self.state = State.RECORDING
        log.info(
            "state -> RECORDING (flushed %d buffered packets, folder=%s)",
            len(buffered), self._session.folder,
        )

    def _finalize_if_open(self, reason: str) -> None:
        if self._session is None:
            self.state = State.IDLE
            return
        folder = self._session.finalize()
        log.info(
            "state -> IDLE (%s, %d packets written, folder=%s)",
            reason, self._session.packet_count, folder,
        )
        self._session = None
        self._idle_started_at = 0.0
        self.state = State.IDLE

        if self.config.auto_summarize and folder is not None:
            try:
                from .summarize import build_report
                summary, corners_detail = build_report(folder)
                (folder / "summary.md").write_text(summary, encoding="utf-8")
                log.info("auto-summarize: wrote %s", folder / "summary.md")
                if corners_detail:
                    (folder / "corners_detail.md").write_text(corners_detail, encoding="utf-8")
                    log.info("auto-summarize: wrote %s", folder / "corners_detail.md")
            except Exception as e:
                # Never let summary failure break the recorder loop.
                log.warning("auto-summarize failed: %s", e)
