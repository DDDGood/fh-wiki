"""CLI entry point: python -m scripts.forza_telemetry"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path

from . import packet as pkt
from .recorder import Recorder, RecorderConfig

BANNER_TEMPLATE = """\
============================================================
  Forza Horizon 5 Telemetry Recorder
------------------------------------------------------------
  監聽埠     : UDP {port}
  輸出位置   : {output_dir}\\
  暫停/倒轉  : 內容判斷（同 session 接續，不切檔）
  Idle 兜底  : {idle_timeout:.0f}s（IsRaceOn=0 持續這麼久才強制結束）
  自動摘要   : 賽事結束時自動產生 summary.md

  FH5 設定 → HUD → Data Out:
    Data Out               : ON
    Data Out IP            : 127.0.0.1
    Data Out Port          : {port}
    Data Out Packet Format : Car Dash

  按 Ctrl+C 安全停止 / 直接關閉視窗也可以
============================================================
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.forza_telemetry",
        description=(
            "Record Forza Horizon 5 'Car Dash' UDP telemetry. "
            "Auto-detects race events; ignores free roam by default."
        ),
    )
    parser.add_argument("--port", type=int, default=5300,
                        help="UDP port to listen on (must match FH5 Data Out Port). Default: 5300")
    parser.add_argument("--bind", default="0.0.0.0",
                        help="Bind address. Default: 0.0.0.0 (all interfaces)")
    parser.add_argument("--output-dir", type=Path,
                        default=Path("data/forza_telemetry/sessions"),
                        help="Where session folders are written. Default: data/forza_telemetry/sessions")
    parser.add_argument("--buffer-seconds", type=float, default=30.0,
                        help="How long to buffer before deciding race vs free-roam. Default: 30")
    parser.add_argument("--idle-timeout-seconds", type=float, default=300.0,
                        help="Safety-net timeout: end the session if IsRaceOn stays 0 "
                             "for this long (no pause/rewind brings the game back). "
                             "Pause/rewind detection is content-based, not time-based, "
                             "so this only fires for truly abandoned sessions. Default: 300")
    parser.add_argument("--no-auto-summarize", action="store_false", dest="auto_summarize",
                        help="Disable auto-generation of summary.md when each session finalizes.")
    parser.add_argument("--game", choices=["fh5", "fh6", "auto"], default="fh5",
                        help="Game version label written to meta.json (so race-analyst picks "
                             "version-appropriate wiki refs). 'auto' routes by first-packet size. "
                             "FH6 support pending until horizon_fh6.py lands. Default: fh5")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose logging (state transitions, first packet info)")
    args = parser.parse_args(argv)

    # Resolve --game early so a bad request (e.g. fh6 before parser lands)
    # fails fast with a clear message instead of running and writing wrong meta.
    try:
        resolved_game = pkt.resolve_game(args.game, packet_size=None)
    except pkt.UnsupportedGameError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # Force UTF-8 for stdout/stderr so the Chinese banner renders correctly
    # on Windows consoles that default to Big5 / cp950.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    print(BANNER_TEMPLATE.format(
        port=args.port,
        output_dir=args.output_dir,
        idle_timeout=args.idle_timeout_seconds,
    ), flush=True)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = RecorderConfig(
        port=args.port,
        bind_host=args.bind,
        output_dir=args.output_dir,
        buffer_seconds=args.buffer_seconds,
        idle_timeout_seconds=args.idle_timeout_seconds,
        auto_summarize=args.auto_summarize,
        game=resolved_game,
    )
    recorder = Recorder(config=cfg)

    def _handle_sigint(_signum, _frame):
        logging.getLogger("forza_telemetry").info("interrupt received, shutting down...")
        recorder.stop()

    signal.signal(signal.SIGINT, _handle_sigint)
    try:
        signal.signal(signal.SIGTERM, _handle_sigint)
    except (AttributeError, ValueError):
        pass  # SIGTERM not available on Windows in some contexts

    recorder.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
