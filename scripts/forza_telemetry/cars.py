"""Car database loader.

Reads per-car YAML files from a cars/ directory (default sibling of sessions/),
keyed by CarOrdinal. Looking up an ordinal returns the parsed dict or None when
no file exists for that car.

The car file is hand-maintained — see data/forza_telemetry/cars/_template.yml.
Tune evolution is tracked via git history of the file (intentionally NOT an
in-file array, which rots fast).

Units convention (project-wide, not stored in file):
  - tire pressure : psi
  - spring rate   : kgf/mm
  - ride height   : cm
  - camber/toe/caster : degrees
  - aero / brakes / diff : raw in-game numbers (no unit)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("forza_telemetry")


def load_car(ordinal: int, cars_dir: Path) -> dict[str, Any] | None:
    """Return parsed car data for `ordinal`, or None if no file / unreadable.

    Failures (missing pyyaml, malformed YAML, IO errors) are logged at WARNING
    and return None — the caller continues without enrichment.
    """
    path = cars_dir / f"{ordinal}.yml"
    if not path.is_file():
        return None

    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        log.warning(
            "pyyaml not installed; car lookup skipped for ordinal=%d. "
            "Run: pip install pyyaml",
            ordinal,
        )
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        log.warning("failed to load car file %s: %s", path, e)
        return None

    if not isinstance(data, dict):
        log.warning("car file %s did not parse to a mapping; ignoring", path)
        return None

    return data
