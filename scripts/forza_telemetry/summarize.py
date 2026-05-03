"""Generate summary.md for a recorded session.

Reads raw.csv + meta.json, produces summary.md with:
  - Race overview (lap times or segment times)
  - Tuning indicators (tire temps, slip, suspension, drivetrain)
  - Driving inputs (throttle/brake/steer patterns)
  - Detailed data tables
  - Anomaly events
  - Compact LLM context block (for the race-analyst skill)

Handles both lapped races (Road/Cross/Dirt) and single-run events
(Sprint/Street/Drag) — segments are by lap if available, else by equal
distance chunks of the run.

Usage:
    python -m scripts.forza_telemetry.summarize                  # most recent session
    python -m scripts.forza_telemetry.summarize <session_path>   # specific session
    python -m scripts.forza_telemetry.summarize --all            # regenerate every session
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

# TODO: TL;DR 罐頭建議的信心降階機制——當使用者已執行過 X 次相同方向的調整
# 但症狀仍在，TL;DR 應建議改方向。需要 tune snapshot（meta.json）才能可靠
# 判斷玩家當前 tune 值；目前因使用者拒絕手動輸入 tune card 而擱置。

# Number of equal-distance segments to split a single-run event into.
SINGLE_RUN_SEGMENTS = 5

# Threshold values used across analysis (documented for tuning later).
SUSPENSION_BOTTOM_THRESHOLD = 0.95   # NormalizedSuspensionTravel
TIRE_SLIP_RATIO_LOSS = 1.0           # |slip ratio| > 1.0 = grip lost
THROTTLE_FULL_THRESHOLD = 250        # 0-255
BRAKE_FULL_THRESHOLD = 250
GEARSHIFT_IDEAL_PCT = 0.95           # ideal shift point as % of redline
RPM_POWER_BAND_PCT = 0.80            # power band starts ~80% redline
DECEL_EVENT_G = 0.5                  # > 0.5 G decel counts as braking event
UNDERSTEER_RATIO = 1.5               # front slip angle > 1.5x rear = understeer
DRIVETRAIN_NAMES = {0: "FWD", 1: "RWD", 2: "AWD"}

# Corner detection — tuned empirically on G29 / AWD PI 700 sessions.
CORNER_ENTER_G = 0.4                 # |lateral G| above this → in corner (hysteresis enter)
CORNER_EXIT_G = 0.25                 # |lateral G| below this → out of corner (hysteresis exit)
CORNER_MIN_PACKETS = 18              # ~0.3s minimum corner duration (filter blips)
CORNER_LATERAL_G_CAP = 3.5           # FH5 physical max ~3G, anything beyond is crash/IMU noise
CORNER_ENTRY_LOOKBACK = 30           # 0.5s pre-corner sample for true entry speed
CORNER_BIAS_THRESHOLD = 0.7          # >70% in one direction → biased track
CORNER_MIN_APEX_KMH = 25             # apex < this is a stop/crash, not a real corner
CORNER_MAX_SPEED_DROP_KMH = 130      # speed drop > this means car was stopped, exclude
                                     # (raised from 90 → 130: long-straight-into-hairpin
                                     # corners legitimately drop 90-120 km/h; the previous
                                     # threshold filtered real corners, leaving the next
                                     # detected corner with mis-aligned phase boundaries.
                                     # Genuine "stopped car" events are already caught by
                                     # CRASH_SPEED_DROP_KMH=50 in detect_crashes.)
CORNER_MAX_RADIUS_M = 250            # apex radius > this is a high-speed sweeper, not a real corner

# Crash detection — collisions / wall impacts pollute G-force, decel, suspension stats.
# Conservative thresholds; legit hard braking peaks at ~3G longitudinal in FH5.
CRASH_LATERAL_G = 5.0                # sustained > 5G lateral (3 packets) = wall side-hit
CRASH_LONGITUDINAL_G = 6.0           # single packet > 6G longitudinal = wall front/rear-hit
CRASH_SPEED_DROP_KMH = 50            # > 50 km/h drop within 10 packets ≈ 9G avg → impact
CRASH_WINDOW_PACKETS = 30            # exclude ±0.5s (≈1s total) around each crash seed


# ----- packet helpers --------------------------------------------------------

def F(r, k):
    return float(r[k])


def I(r, k):
    return int(r[k])


def speed_kmh(v):
    return v * 3.6


def integrate_distance(speeds, hz=60):
    """Integrate speed (m/s) over packets at given Hz to get distance (m)."""
    return sum(speeds) / hz


# ----- segmentation ----------------------------------------------------------

@dataclass
class Segment:
    """One slice of the race for analysis (a lap, or a distance chunk)."""
    label: str               # "Lap 0" or "Seg 1/5"
    packets: list             # list of dict rows
    lap_number: int | None    # None for single-run segments
    completed_lap_time: float = 0.0  # LastLap from final packet of this lap, if lapped


def segment_by_lap(valid_rows: list) -> list[Segment]:
    """Group packets by LapNumber (for lapped events)."""
    laps = defaultdict(list)
    for r in valid_rows:
        laps[I(r, 'LapNumber')].append(r)
    out = []
    for lap_no, pkts in sorted(laps.items()):
        last_lap = F(pkts[-1], 'LastLap')
        out.append(Segment(label=f"Lap {lap_no}", packets=pkts,
                          lap_number=lap_no, completed_lap_time=last_lap))
    return out


def segment_by_distance(valid_rows: list, n_segments: int = SINGLE_RUN_SEGMENTS) -> list[Segment]:
    """Split a single run into N equal-distance segments."""
    speeds = [F(r, 'Speed') for r in valid_rows]
    cum_dist = [0.0]
    for s in speeds:
        cum_dist.append(cum_dist[-1] + s / 60)
    total = cum_dist[-1]
    if total <= 0:
        # Degenerate — fall back to equal-time
        chunk = max(1, len(valid_rows) // n_segments)
        return [Segment(label=f"Seg {k+1}/{n_segments}",
                       packets=valid_rows[k * chunk:(k + 1) * chunk],
                       lap_number=None) for k in range(n_segments)]
    boundaries = [total * k / n_segments for k in range(n_segments + 1)]
    out = []
    for k in range(n_segments):
        start_d, end_d = boundaries[k], boundaries[k + 1]
        pkts = [valid_rows[j] for j in range(len(valid_rows))
                if start_d <= cum_dist[j] < end_d]
        if not pkts:
            continue
        out.append(Segment(label=f"Seg {k+1}/{n_segments}",
                          packets=pkts, lap_number=None))
    return out


# ----- analysis primitives ---------------------------------------------------

def analyze_tires(segments: list[Segment]) -> dict:
    """Per-segment tire temperatures + overall pattern."""
    rows = []
    for seg in segments:
        fl = statistics.mean(F(r, 'TireTempFrontLeft') for r in seg.packets)
        fr = statistics.mean(F(r, 'TireTempFrontRight') for r in seg.packets)
        rl = statistics.mean(F(r, 'TireTempRearLeft') for r in seg.packets)
        rr = statistics.mean(F(r, 'TireTempRearRight') for r in seg.packets)
        rows.append({"label": seg.label, "fl": fl, "fr": fr, "rl": rl, "rr": rr,
                    "front_avg": (fl + fr) / 2, "rear_avg": (rl + rr) / 2,
                    "lr_front_delta": fl - fr, "lr_rear_delta": rl - rr,
                    "fr_delta": (fl + fr) / 2 - (rl + rr) / 2})
    # Overall (skip first segment if lapped — it's typically warm-up)
    skip_first = segments[0].lap_number == 0 and len(segments) > 1
    body = rows[1:] if skip_first else rows
    if body:
        ovr = {
            "fl": statistics.mean(r["fl"] for r in body),
            "fr": statistics.mean(r["fr"] for r in body),
            "rl": statistics.mean(r["rl"] for r in body),
            "rr": statistics.mean(r["rr"] for r in body),
        }
        ovr["front_avg"] = (ovr["fl"] + ovr["fr"]) / 2
        ovr["rear_avg"] = (ovr["rl"] + ovr["rr"]) / 2
        ovr["fr_delta"] = ovr["front_avg"] - ovr["rear_avg"]
        ovr["lr_front_delta"] = ovr["fl"] - ovr["fr"]
        ovr["lr_rear_delta"] = ovr["rl"] - ovr["rr"]
        hottest = max(["fl", "fr", "rl", "rr"], key=lambda k: ovr[k])
    else:
        ovr = None
        hottest = None
    return {"per_segment": rows, "overall": ovr, "hottest_corner": hottest,
            "skipped_first_segment": skip_first}


def analyze_slip(segments: list[Segment]) -> dict:
    """Slip ratio + slip angle patterns. Distinguishes understeer vs oversteer.

    過濾規則：slip ratio > SLIP_RATIO_ARTIFACT_CAP（=5.0）視為撞車/rewind 邊界 artifact，
    從 fr_max/rr_max 統計中剔除（FH5 物理上輪胎打滑率 5 已經是極端輪轉空轉，11 之類純為 IMU 尖峰）。
    若該 segment 任一輪有此尖峰，per-segment dict 多帶 ``ratio_artifact_filtered=True`` 旗標供格式化端標註。

    推頭/轉向過度 top 表使用 slip angle（非 ratio），但對 angle 同樣加 < 5 過濾，
    避免少數異常 packet 把整張表都洗掉。
    """
    SLIP_RATIO_ARTIFACT_CAP = 5.0
    SLIP_ANGLE_ARTIFACT_CAP = 5.0
    rows = []
    for seg in segments:
        fr_samples = [(abs(F(r, 'TireSlipRatioFrontLeft')) +
                       abs(F(r, 'TireSlipRatioFrontRight'))) / 2 for r in seg.packets]
        rr_samples = [(abs(F(r, 'TireSlipRatioRearLeft')) +
                       abs(F(r, 'TireSlipRatioRearRight'))) / 2 for r in seg.packets]
        artifact = (max(fr_samples, default=0) > SLIP_RATIO_ARTIFACT_CAP
                    or max(rr_samples, default=0) > SLIP_RATIO_ARTIFACT_CAP)
        fr_clean = [v for v in fr_samples if v <= SLIP_RATIO_ARTIFACT_CAP]
        rr_clean = [v for v in rr_samples if v <= SLIP_RATIO_ARTIFACT_CAP]
        fr_max = max(fr_clean) if fr_clean else 0.0
        rr_max = max(rr_clean) if rr_clean else 0.0
        fr_avg = statistics.mean(fr_clean) if fr_clean else 0.0
        rr_avg = statistics.mean(rr_clean) if rr_clean else 0.0
        rows.append({"label": seg.label, "fr_max": fr_max, "rr_max": rr_max,
                    "fr_avg": fr_avg, "rr_avg": rr_avg,
                    "ratio_artifact_filtered": artifact})
    # Understeer / oversteer moments (using slip angle, not ratio)
    understeer = []
    oversteer = []
    for seg in segments:
        for r in seg.packets:
            fs = (abs(F(r, 'TireSlipAngleFrontLeft')) +
                  abs(F(r, 'TireSlipAngleFrontRight'))) / 2
            rs = (abs(F(r, 'TireSlipAngleRearLeft')) +
                  abs(F(r, 'TireSlipAngleRearRight'))) / 2
            # 過濾 slip angle artifact（撞車/rewind 邊界尖峰）
            if fs >= SLIP_ANGLE_ARTIFACT_CAP or rs >= SLIP_ANGLE_ARTIFACT_CAP:
                continue
            if fs > 0.5 and fs > rs * UNDERSTEER_RATIO:
                understeer.append((F(r, 'CurrentRaceTime'), seg.label,
                                  fs, rs, F(r, 'Speed') * 3.6))
            elif rs > 0.5 and rs > fs * UNDERSTEER_RATIO:
                oversteer.append((F(r, 'CurrentRaceTime'), seg.label,
                                 fs, rs, F(r, 'Speed') * 3.6))
    understeer.sort(key=lambda x: -x[2])
    oversteer.sort(key=lambda x: -x[3])
    return {"per_segment": rows, "understeer_top": understeer[:5],
            "oversteer_top": oversteer[:5],
            "understeer_count": len(understeer),
            "oversteer_count": len(oversteer)}


def analyze_suspension(segments: list[Segment]) -> dict:
    rows = []
    total_bottom = 0
    for seg in segments:
        fl_max = max(F(r, 'NormalizedSuspensionTravelFrontLeft') for r in seg.packets)
        fr_max = max(F(r, 'NormalizedSuspensionTravelFrontRight') for r in seg.packets)
        rl_max = max(F(r, 'NormalizedSuspensionTravelRearLeft') for r in seg.packets)
        rr_max = max(F(r, 'NormalizedSuspensionTravelRearRight') for r in seg.packets)
        fl_avg = statistics.mean(F(r, 'NormalizedSuspensionTravelFrontLeft') for r in seg.packets)
        fr_avg = statistics.mean(F(r, 'NormalizedSuspensionTravelFrontRight') for r in seg.packets)
        rl_avg = statistics.mean(F(r, 'NormalizedSuspensionTravelRearLeft') for r in seg.packets)
        rr_avg = statistics.mean(F(r, 'NormalizedSuspensionTravelRearRight') for r in seg.packets)
        bottom = sum(1 for r in seg.packets if max(
            F(r, 'NormalizedSuspensionTravelFrontLeft'),
            F(r, 'NormalizedSuspensionTravelFrontRight'),
            F(r, 'NormalizedSuspensionTravelRearLeft'),
            F(r, 'NormalizedSuspensionTravelRearRight')) > SUSPENSION_BOTTOM_THRESHOLD)
        total_bottom += bottom
        rows.append({"label": seg.label,
                    "fl_max": fl_max, "fr_max": fr_max, "rl_max": rl_max, "rr_max": rr_max,
                    "fl_avg": fl_avg, "fr_avg": fr_avg, "rl_avg": rl_avg, "rr_avg": rr_avg,
                    "bottom_count": bottom})
    return {"per_segment": rows, "total_bottom_packets": total_bottom}


def analyze_rpm_observed(valid_rows: list) -> dict:
    """RPM 觀測統計：用實測值對照 EngineMaxRpm（硬限速），找出真正的紅線。"""
    rpms = [F(r, 'CurrentEngineRpm') for r in valid_rows]
    rpms_sorted = sorted(rpms)
    n = len(rpms_sorted)
    p99 = rpms_sorted[int(n * 0.99)] if n else 0
    p95 = rpms_sorted[int(n * 0.95)] if n else 0
    engine_max = F(valid_rows[0], 'EngineMaxRpm')
    max_rpm = max(rpms) if rpms else 0
    # 顯著低於 EngineMaxRpm（差 >500）= EngineMaxRpm 是硬限速、不是儀表紅線
    headroom = engine_max - max_rpm
    return {"max": max_rpm, "p99": p99, "p95": p95,
            "engine_max": engine_max, "headroom": headroom,
            "warn_hard_limiter": headroom > 500}


def analyze_dyno(valid_rows: list, bucket_rpm: int = 200) -> dict | None:
    """估算 dyno 曲線：依 RPM 分箱取 Power/Torque 中位數。

    需要 raw.csv 含 'Power' 與 'Torque' 欄位。FH5 UDP CarDashData 結構提供，
    但歷史 raw.csv 若無此欄位則回傳 None（呼叫端應 graceful fallback）。

    回傳:
      buckets        : list[dict(rpm_lo, rpm_hi, rpm_mid, power_med, torque_med, n)]
      peak_power_rpm : 峰值馬力對應的 RPM（取 bucket 中點）
      peak_power     : 峰值馬力數值（W，FH5 內部單位）
      peak_torque_rpm: 峰值扭矩對應的 RPM
      peak_torque    : 峰值扭矩數值（Nm）
    """
    # 必要欄位檢查
    if not valid_rows:
        return None
    sample = valid_rows[0]
    if 'Power' not in sample or 'Torque' not in sample:
        return None
    try:
        # 檢查樣本能否轉 float（缺欄會是空字串）
        float(sample['Power'])
        float(sample['Torque'])
    except (ValueError, TypeError):
        return None

    # 只取「玩家有踩油門 + 引擎在工作」的樣本，避免怠速/收油資料污染曲線
    samples = []
    for r in valid_rows:
        try:
            rpm = float(r['CurrentEngineRpm'])
            power = float(r['Power'])
            torque = float(r['Torque'])
            accel = int(r['Accel'])
        except (ValueError, KeyError, TypeError):
            continue
        # 油門 > 80% 且 RPM > 1500（過濾怠速/換檔瞬間）
        if accel > 200 and rpm > 1500 and power > 0:
            samples.append((rpm, power, torque))

    if len(samples) < 50:
        return None

    # 分箱
    buckets_raw: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for rpm, power, torque in samples:
        b = int(rpm // bucket_rpm) * bucket_rpm
        buckets_raw[b].append((power, torque))

    # 每桶 >= 3 個樣本才採信
    buckets = []
    for b in sorted(buckets_raw):
        bucket_samples = buckets_raw[b]
        if len(bucket_samples) < 3:
            continue
        powers = [p for p, _ in bucket_samples]
        torques = [t for _, t in bucket_samples]
        buckets.append({
            "rpm_lo": b,
            "rpm_hi": b + bucket_rpm,
            "rpm_mid": b + bucket_rpm // 2,
            "power_med": statistics.median(powers),
            "torque_med": statistics.median(torques),
            "n": len(bucket_samples),
        })

    if not buckets:
        return None

    peak_power_bucket = max(buckets, key=lambda x: x["power_med"])
    peak_torque_bucket = max(buckets, key=lambda x: x["torque_med"])
    return {
        "buckets": buckets,
        "peak_power_rpm": peak_power_bucket["rpm_mid"],
        "peak_power": peak_power_bucket["power_med"],
        "peak_torque_rpm": peak_torque_bucket["rpm_mid"],
        "peak_torque": peak_torque_bucket["torque_med"],
    }


def analyze_drivetrain(valid_rows: list, dyno: dict | None = None) -> dict:
    rpms = [F(r, 'CurrentEngineRpm') for r in valid_rows]
    gears = [I(r, 'Gear') for r in valid_rows]
    engine_max = F(valid_rows[0], 'EngineMaxRpm')

    # 換檔目標：若有 dyno 曲線，用峰值馬力 RPM；否則退回 engine_max × 95%
    if dyno is not None:
        ideal_shift = float(dyno["peak_power_rpm"])
        ideal_shift_basis = "peak_power_rpm"
    else:
        ideal_shift = engine_max * GEARSHIFT_IDEAL_PCT
        ideal_shift_basis = "engine_max_x_0.95"

    shift_pts = defaultdict(list)
    for j in range(1, len(valid_rows)):
        if gears[j] > gears[j - 1] and gears[j - 1] > 0:
            shift_pts[(gears[j - 1], gears[j])].append(rpms[j - 1])

    # 動力區：若有 dyno，用 power >= peak_power × 90%；否則退回 RPM 法
    if dyno is not None:
        peak_p = dyno["peak_power"]
        threshold = peak_p * 0.90
        # 用 dyno 桶反推：哪些 RPM 區段的 power_med >= 90% 峰值
        power_band_rpms = sorted(b["rpm_mid"] for b in dyno["buckets"]
                                if b["power_med"] >= threshold)
        if power_band_rpms:
            band_lo = power_band_rpms[0] - 100
            band_hi = power_band_rpms[-1] + 100
            in_power_band = sum(1 for r in rpms if band_lo <= r <= band_hi) / len(rpms) * 100
            power_band_start = band_lo
            power_band_end = band_hi
            power_band_basis = "power>=90%_peak"
        else:
            in_power_band = 0.0
            power_band_start = engine_max * RPM_POWER_BAND_PCT
            power_band_end = engine_max
            power_band_basis = "fallback_rpm_pct"
    else:
        power_band_start = engine_max * RPM_POWER_BAND_PCT
        power_band_end = engine_max
        in_power_band = sum(1 for r in rpms if r >= power_band_start) / len(rpms) * 100
        power_band_basis = "engine_max_x_0.80"

    in_redline = sum(1 for r in rpms if r >= ideal_shift) / len(rpms) * 100

    gear_time = defaultdict(int)
    for g in gears:
        gear_time[g] += 1
    gear_pct = {g: t / len(gears) * 100 for g, t in gear_time.items()}

    all_shifts = [r for pts in shift_pts.values() for r in pts]
    avg_shift = statistics.mean(all_shifts) if all_shifts else 0
    return {"engine_max": engine_max, "ideal_shift": ideal_shift,
            "ideal_shift_basis": ideal_shift_basis,
            "power_band_start": power_band_start,
            "power_band_end": power_band_end,
            "power_band_basis": power_band_basis,
            "shift_points": dict(shift_pts), "avg_shift_rpm": avg_shift,
            "shift_loss_rpm": ideal_shift - avg_shift,
            "in_power_band_pct": in_power_band,
            "in_redline_pct": in_redline,
            "gear_distribution": dict(sorted(gear_pct.items())),
            "max_rpm_seen": max(rpms)}


def analyze_inputs(valid_rows: list) -> dict:
    n = len(valid_rows)
    accel = [I(r, 'Accel') for r in valid_rows]
    brake = [I(r, 'Brake') for r in valid_rows]
    steer = [I(r, 'Steer') for r in valid_rows]
    abs_steer = [abs(s) for s in steer]
    steer_max = max(abs_steer) if abs_steer else 0

    # ---- Steer pin (方向打死) detection ----
    # |Steer| >= max_observed * 0.8 sustained for >= 0.5s (30 packets).
    # max_observed (not 127) because controller players rarely reach 127.
    pin_threshold = steer_max * 0.8 if steer_max > 0 else 1e9
    MIN_PIN_PKTS = 30  # 0.5s @ 60Hz
    pin_events: list[dict] = []  # {start, end, dur_pkts, dur_s, avg_kmh, avg_front_slip}
    j = 0
    while j < n:
        if abs_steer[j] >= pin_threshold:
            run_start = j
            while j < n and abs_steer[j] >= pin_threshold:
                j += 1
            run_end = j - 1
            if (run_end - run_start + 1) >= MIN_PIN_PKTS:
                pkts = valid_rows[run_start:run_end + 1]
                avg_kmh = statistics.mean(F(r, 'Speed') * 3.6 for r in pkts)
                avg_fs = statistics.mean(
                    (abs(F(r, 'TireSlipAngleFrontLeft')) +
                     abs(F(r, 'TireSlipAngleFrontRight'))) / 2 for r in pkts)
                pin_events.append({
                    "start": run_start, "end": run_end,
                    "t_start": F(valid_rows[run_start], 'CurrentRaceTime'),
                    "dur_pkts": run_end - run_start + 1,
                    "dur_s": (run_end - run_start + 1) / 60,
                    "avg_kmh": avg_kmh,
                    "avg_front_slip": avg_fs,
                })
        else:
            j += 1
    pin_total_s = sum(e["dur_s"] for e in pin_events)
    pin_max_s = max((e["dur_s"] for e in pin_events), default=0.0)
    pin_top = sorted(pin_events, key=lambda e: -e["dur_s"])[:3]

    # ---- 前輪硬推 (hard-push) detection ----
    # 比「方向打死」次嚴重的指標：|Steer| >= max × 0.6 + 前 slip > 1.0 持續 >= 0.3s。
    # 用來捕捉「方向打很大但沒打死 0.5s 仍超過前輪抓地極限」的場景，
    # 例如 entry 短促硬推、或半遊轉向角時就已 saturate slip——這些是真實推頭瞬間，
    # 但會被現有「方向打死」（0.8× max + 0.5s）漏掉。
    HARDPUSH_STEER_FRAC = 0.6
    HARDPUSH_FRONT_SLIP = 1.0
    MIN_HARDPUSH_PKTS = 18  # 0.3s @ 60Hz
    hardpush_threshold = steer_max * HARDPUSH_STEER_FRAC if steer_max > 0 else 1e9
    hardpush_events: list[dict] = []
    j = 0
    while j < n:
        # 提早算前輪 slip（避免在條件中重複計算）
        fs_j = (abs(F(valid_rows[j], 'TireSlipAngleFrontLeft')) +
                abs(F(valid_rows[j], 'TireSlipAngleFrontRight'))) / 2
        cond = (abs_steer[j] >= hardpush_threshold
                and fs_j > HARDPUSH_FRONT_SLIP
                and fs_j < 5.0)  # 排除 artifact
        if cond:
            run_start = j
            while j < n:
                fs_k = (abs(F(valid_rows[j], 'TireSlipAngleFrontLeft')) +
                        abs(F(valid_rows[j], 'TireSlipAngleFrontRight'))) / 2
                if (abs_steer[j] >= hardpush_threshold
                        and fs_k > HARDPUSH_FRONT_SLIP
                        and fs_k < 5.0):
                    j += 1
                else:
                    break
            run_end = j - 1
            if (run_end - run_start + 1) >= MIN_HARDPUSH_PKTS:
                pkts = valid_rows[run_start:run_end + 1]
                avg_kmh = statistics.mean(F(r, 'Speed') * 3.6 for r in pkts)
                avg_fs = statistics.mean(
                    (abs(F(r, 'TireSlipAngleFrontLeft')) +
                     abs(F(r, 'TireSlipAngleFrontRight'))) / 2 for r in pkts)
                hardpush_events.append({
                    "start": run_start, "end": run_end,
                    "t_start": F(valid_rows[run_start], 'CurrentRaceTime'),
                    "dur_pkts": run_end - run_start + 1,
                    "dur_s": (run_end - run_start + 1) / 60,
                    "avg_kmh": avg_kmh,
                    "avg_front_slip": avg_fs,
                })
        else:
            j += 1
    hardpush_total_s = sum(e["dur_s"] for e in hardpush_events)
    hardpush_max_s = max((e["dur_s"] for e in hardpush_events), default=0.0)
    hardpush_top = sorted(hardpush_events, key=lambda e: -e["dur_s"])[:3]

    # ---- Throttle surge (油門急升) detection ----
    # In a 12-packet (~200ms) window, throttle goes from <=50 to >=200.
    # Count non-overlapping events: once a surge is found at j, skip ahead
    # past the window so we don't double-count the same gas pedal stomp.
    SURGE_WINDOW = 12
    SURGE_LO = 50
    SURGE_HI = 200
    surge_events: list[dict] = []
    j = 0
    while j < n - SURGE_WINDOW:
        if accel[j] <= SURGE_LO:
            window_max = max(accel[j:j + SURGE_WINDOW + 1])
            if window_max >= SURGE_HI:
                # Locate end of surge (first packet hitting SURGE_HI)
                k = j
                while k < min(n, j + SURGE_WINDOW + 1) and accel[k] < SURGE_HI:
                    k += 1
                # Pre-200ms throttle avg = window before j
                pre_lo = max(0, j - SURGE_WINDOW)
                pre_avg = statistics.mean(accel[pre_lo:j + 1]) if j >= 0 else 0
                # Post-200ms = window after k
                post_hi = min(n, k + SURGE_WINDOW + 1)
                post_avg = statistics.mean(accel[k:post_hi]) if post_hi > k else accel[k]
                # |latG| at surge moment — distinguishes "straight-line stomp
                # after heavy braking" (legit) from "stomp mid-corner" (driver
                # error). Use the MEDIAN of the surge window rather than max,
                # so a single noisy IMU packet (kerb hop, residual crash spike)
                # cannot flip a real straight-line surge into "corner". A real
                # mid-corner stomp will have sustained latG, a wall-grazed
                # straight will not.
                lat_window_end = min(n, k + 1)
                # Cap each sample at the FH5 physical-grip max (CORNER_LATERAL_G_CAP);
                # anything above is curb/wall/IMU noise, not real cornering. Then
                # take median to suppress single-packet outliers. A genuine
                # mid-corner surge sustains latG; a straight-line surge that
                # happened to clip a kerb does not.
                lat_samples = [min(abs(F(valid_rows[m], 'AccelerationX') / 9.81),
                                   CORNER_LATERAL_G_CAP)
                               for m in range(j, lat_window_end)]
                surge_lat_g = statistics.median(lat_samples) if lat_samples else 0.0
                surge_context = "corner" if surge_lat_g >= 0.4 else "straight"
                surge_events.append({
                    "start": j, "peak": k,
                    "t_start": F(valid_rows[j], 'CurrentRaceTime'),
                    "pre_throttle": pre_avg,
                    "post_throttle": post_avg,
                    "kmh": F(valid_rows[j], 'Speed') * 3.6,
                    "lat_g": surge_lat_g,
                    "context": surge_context,
                })
                j = k + SURGE_WINDOW  # skip past the event
                continue
        j += 1
    surge_count = len(surge_events)
    surge_corner_count = sum(1 for e in surge_events if e["context"] == "corner")
    surge_straight_count = surge_count - surge_corner_count
    # Top 3 by climb magnitude (post - pre); ties broken by post throttle.
    surge_top = sorted(surge_events,
                       key=lambda e: (-(e["post_throttle"] - e["pre_throttle"]),
                                      -e["post_throttle"]))[:3]

    return {
        "throttle_full_pct": sum(1 for a in accel if a >= THROTTLE_FULL_THRESHOLD) / n * 100,
        "throttle_mid_pct": sum(1 for a in accel if 50 <= a < THROTTLE_FULL_THRESHOLD) / n * 100,
        "throttle_off_pct": sum(1 for a in accel if a < 50) / n * 100,
        "throttle_avg": statistics.mean(accel),
        "brake_max": max(brake),
        "brake_avg": statistics.mean(brake),
        "brake_full_pct": sum(1 for b in brake if b >= BRAKE_FULL_THRESHOLD) / n * 100,
        "trail_brake_pct": sum(1 for j in range(n) if accel[j] > 50 and brake[j] > 50) / n * 100,
        "coast_pct": sum(1 for j in range(n) if accel[j] < 5 and brake[j] < 5) / n * 100,
        "steer_max": steer_max,
        "steer_avg_abs": statistics.mean(abs_steer),
        "brake_appears_disabled": max(brake) == 0,  # Braking Assist hint
        # Steer pin
        "steer_pin_threshold": pin_threshold,
        "steer_pin_count": len(pin_events),
        "steer_pin_total_s": pin_total_s,
        "steer_pin_max_s": pin_max_s,
        "steer_pin_top": pin_top,
        # 前輪硬推（次嚴重於 steer pin）
        "hardpush_threshold": hardpush_threshold,
        "hardpush_count": len(hardpush_events),
        "hardpush_total_s": hardpush_total_s,
        "hardpush_max_s": hardpush_max_s,
        "hardpush_top": hardpush_top,
        # Throttle surge
        "throttle_surge_count": surge_count,
        "throttle_surge_corner_count": surge_corner_count,
        "throttle_surge_straight_count": surge_straight_count,
        "throttle_surge_top": surge_top,
    }


def analyze_g_forces(valid_rows: list, pre_crash_rows: list | None = None) -> dict:
    """G-force stats. `valid_rows` is the crash-excluded set (for clean stats);
    `pre_crash_rows` (optional) is the pre-exclusion set used to compute the
    "with-crash" values so summary.md can show both side-by-side. The clean
    values represent the car's real ability; with-crash values include the
    raw IMU spikes from impacts."""
    lat = [abs(F(r, 'AccelerationX')) / 9.81 for r in valid_rows]
    long_decel = [-F(r, 'AccelerationZ') / 9.81 for r in valid_rows]
    long_accel = [F(r, 'AccelerationZ') / 9.81 for r in valid_rows]
    out = {"max_lateral_g": max(lat),
           "max_decel_g": max(long_decel),
           "max_accel_g": max(long_accel),
           "avg_lateral_g": statistics.mean(lat)}
    # "Clean" aliases — same as max_*_g but explicit for the dual-display table.
    out["max_lateral_g_clean"] = out["max_lateral_g"]
    out["max_decel_g_clean"] = out["max_decel_g"]
    if pre_crash_rows:
        lat_pre = [abs(F(r, 'AccelerationX')) / 9.81 for r in pre_crash_rows]
        decel_pre = [-F(r, 'AccelerationZ') / 9.81 for r in pre_crash_rows]
        out["max_lateral_g_with_crash"] = max(lat_pre) if lat_pre else out["max_lateral_g"]
        out["max_decel_g_with_crash"] = max(decel_pre) if decel_pre else out["max_decel_g"]
    else:
        out["max_lateral_g_with_crash"] = out["max_lateral_g"]
        out["max_decel_g_with_crash"] = out["max_decel_g"]
    return out


def analyze_decel_events(valid_rows: list) -> list:
    """Estimate where heavy braking happens (compensates for missing brake input)."""
    out = []
    for j in range(5, len(valid_rows)):
        prev_speed = F(valid_rows[j - 5], 'Speed')
        curr_speed = F(valid_rows[j], 'Speed')
        if prev_speed > 30 and curr_speed < prev_speed:
            decel_g = (prev_speed - curr_speed) / 0.083 / 9.81
            if decel_g > DECEL_EVENT_G:
                out.append({"crt": F(valid_rows[j], 'CurrentRaceTime'),
                           "lap": I(valid_rows[j], 'LapNumber'),
                           "decel_g": decel_g,
                           "from_kmh": prev_speed * 3.6,
                           "to_kmh": curr_speed * 3.6})
    out.sort(key=lambda x: -x["decel_g"])
    return out


def analyze_speed(valid_rows: list) -> dict:
    speeds = [F(r, 'Speed') * 3.6 for r in valid_rows]  # km/h
    return {"max_kmh": max(speeds),
            "avg_kmh": statistics.mean(speeds),
            "min_kmh_in_motion": min(s for s in speeds if s > 5) if any(s > 5 for s in speeds) else 0,
            "stdev_kmh": statistics.stdev(speeds) if len(speeds) > 1 else 0}


def analyze_surface(valid_rows: list) -> dict:
    rumble_strip_events = sum(1 for r in valid_rows if max(
        I(r, 'WheelOnRumbleStripFrontLeft'), I(r, 'WheelOnRumbleStripFrontRight'),
        I(r, 'WheelOnRumbleStripRearLeft'), I(r, 'WheelOnRumbleStripRearRight')) > 0)
    max_puddle = max(max(F(r, 'WheelInPuddleDepthFrontLeft'),
                        F(r, 'WheelInPuddleDepthFrontRight'),
                        F(r, 'WheelInPuddleDepthRearLeft'),
                        F(r, 'WheelInPuddleDepthRearRight')) for r in valid_rows)
    return {"rumble_strip_packets": rumble_strip_events,
            "rumble_strip_seconds": rumble_strip_events / 60,
            "max_puddle_depth": max_puddle}


def analyze_wheelspin(valid_rows: list) -> dict:
    """Identify packets where rear wheels are slipping > 1.0 (clearly losing grip).

    Returns {"count": int, "indices": list[int]} so callers can subdivide the
    packet set by corner phase (straight / entry / apex / exit) — RWD power
    oversteer's exit-phase wheelspin is a different problem from straight-line
    traction loss."""
    indices = [j for j, r in enumerate(valid_rows) if max(
        abs(F(r, 'TireSlipRatioRearLeft')),
        abs(F(r, 'TireSlipRatioRearRight'))) > TIRE_SLIP_RATIO_LOSS]
    return {"count": len(indices), "indices": indices}


def classify_wheelspin_phases(indices: list[int], corners: list[dict]) -> dict:
    """Bucket each wheelspin packet into straight / entry / apex / exit.

    - straight: not inside any detected corner [start, end]
    - entry:    inside a corner, before that corner's apex
    - apex:     within ±5 packets of the corner's apex
    - exit:     inside a corner, after apex
    """
    if not indices:
        return {"straight": 0, "entry": 0, "apex": 0, "exit": 0, "total": 0}
    # Pre-compute (start, end, apex_global) ranges
    if not corners:
        return {"straight": len(indices), "entry": 0, "apex": 0, "exit": 0, "total": len(indices)}
    # Each corner dict has 'start' / 'end'; recompute apex_global from per-corner data
    # by matching min-speed packet — but we don't have speeds here, so use stored
    # heuristic: corner records carry start+end, apex packet is approximated
    # in analyze_corners as the slowest packet. We need it here, so the caller
    # must pass corners enriched with 'apex_global' (added below in analyze_corners).
    ranges = sorted(((c["start"], c["end"], c.get("apex_global", (c["start"] + c["end"]) // 2)) for c in corners),
                    key=lambda x: x[0])
    counts = {"straight": 0, "entry": 0, "apex": 0, "exit": 0}
    j = 0  # pointer into ranges
    for idx in indices:
        # advance pointer past corners that ended before idx
        while j < len(ranges) and ranges[j][1] < idx:
            j += 1
        if j < len(ranges) and ranges[j][0] <= idx <= ranges[j][1]:
            apex_g = ranges[j][2]
            if abs(idx - apex_g) <= 5:
                counts["apex"] += 1
            elif idx < apex_g:
                counts["entry"] += 1
            else:
                counts["exit"] += 1
        else:
            counts["straight"] += 1
    counts["total"] = sum(counts.values())
    return counts


def detect_crashes(valid_rows: list) -> tuple[set[int], int]:
    """Identify packets affected by crashes / collisions for exclusion.

    Three independent seeds (any one triggers):
      - 3 consecutive packets with |lateral G| > CRASH_LATERAL_G (sustained side-impact)
      - Single packet with |longitudinal G| > CRASH_LONGITUDINAL_G (wall hit)
      - Speed drop > CRASH_SPEED_DROP_KMH within 10 packets (~167ms, ≈9G avg decel)

    Each seed expands ±CRASH_WINDOW_PACKETS into an exclusion zone, since
    telemetry leading into and recovering from a crash is also unreliable.
    Adjacent / overlapping zones merge into a single "episode" for counting.

    Returns (excluded_indices, episode_count).
    """
    n = len(valid_rows)
    if n < 11:
        return set(), 0

    raw_lat = [F(r, 'AccelerationX') / 9.81 for r in valid_rows]
    raw_long = [F(r, 'AccelerationZ') / 9.81 for r in valid_rows]
    speeds = [F(r, 'Speed') for r in valid_rows]

    seeds: set[int] = set()
    # Sustained lateral spike
    for j in range(2, n):
        if all(abs(raw_lat[k]) > CRASH_LATERAL_G for k in range(j - 2, j + 1)):
            seeds.add(j)
    # Single longitudinal spike
    for j in range(n):
        if abs(raw_long[j]) > CRASH_LONGITUDINAL_G:
            seeds.add(j)
    # Speed-drop crash
    for j in range(10, n):
        if (speeds[j - 10] - speeds[j]) * 3.6 > CRASH_SPEED_DROP_KMH:
            seeds.add(j)

    if not seeds:
        return set(), 0

    # Expand seeds to exclusion windows
    excluded: set[int] = set()
    for s in seeds:
        for k in range(max(0, s - CRASH_WINDOW_PACKETS),
                      min(n, s + CRASH_WINDOW_PACKETS + 1)):
            excluded.add(k)

    # Count episodes (separate by gaps in excluded indices)
    sorted_idx = sorted(excluded)
    episodes = 1
    for i in range(1, len(sorted_idx)):
        if sorted_idx[i] - sorted_idx[i - 1] > 1:
            episodes += 1

    return excluded, episodes


def analyze_corners(valid_rows: list) -> dict:
    """Detect corners and compute aggregate cornering metrics.

    Detection:
      - Smooth lateral G with 3-packet rolling average to suppress jitter
      - Hysteresis: enter at CORNER_ENTER_G, exit at CORNER_EXIT_G
      - Cap absolute lateral G at CORNER_LATERAL_G_CAP (filters IMU spikes)
      - Discard corners shorter than CORNER_MIN_PACKETS

    Per-corner stats use a CORNER_ENTRY_LOOKBACK window before the corner
    starts to estimate true pre-corner ("approach") speed.

    Output is intentionally aggregate-focused: this analysis serves the user's
    goal of "improve overall tune + driving habits", not per-track-corner
    optimization. So we return summary stats and at most a handful of "notable"
    corners (the heaviest brake zones), not a 40-row table.
    """
    if len(valid_rows) < CORNER_MIN_PACKETS * 2:
        return {"corners": [], "count": 0, "track_bias": "unknown"}

    # Smooth lateral G
    raw_lat = [F(r, 'AccelerationX') / 9.81 for r in valid_rows]
    # Cap outliers (e.g., crash IMU spikes > 5G are physically impossible in FH5)
    capped = [max(-CORNER_LATERAL_G_CAP, min(CORNER_LATERAL_G_CAP, g)) for g in raw_lat]
    smooth: list[float] = []
    for j in range(len(capped)):
        lo, hi = max(0, j - 1), min(len(capped), j + 2)
        smooth.append(sum(capped[lo:hi]) / (hi - lo))

    # State machine with hysteresis
    corners_raw: list[tuple[int, int]] = []  # (start_idx, end_idx)
    in_corner = False
    cstart = 0
    for j, g in enumerate(smooth):
        ag = abs(g)
        if not in_corner and ag > CORNER_ENTER_G:
            in_corner = True
            cstart = j
        elif in_corner and ag < CORNER_EXIT_G:
            in_corner = False
            if j - cstart >= CORNER_MIN_PACKETS:
                corners_raw.append((cstart, j - 1))
    if in_corner and len(valid_rows) - 1 - cstart >= CORNER_MIN_PACKETS:
        corners_raw.append((cstart, len(valid_rows) - 1))

    # Build corner records
    corners = []
    filtered_sweeper_count = 0
    filtered_stop_count = 0
    # 全場彎內 packet 級的推頭/過度時間佔比累積（per-packet，不是 per-corner）
    total_in_corner_packets = 0
    understeer_packets_in_corners = 0
    oversteer_packets_in_corners = 0
    for start, end in corners_raw:
        approach_idx = max(0, start - CORNER_ENTRY_LOOKBACK)
        approach_speed = max(F(r, 'Speed') for r in valid_rows[approach_idx:start + 1])
        in_corner_pkts = valid_rows[start:end + 1]
        speeds = [F(r, 'Speed') for r in in_corner_pkts]
        lats = smooth[start:end + 1]
        peak_g = max(lats, key=abs)

        front_slip = [(abs(F(r, 'TireSlipAngleFrontLeft')) +
                      abs(F(r, 'TireSlipAngleFrontRight'))) / 2 for r in in_corner_pkts]
        rear_slip = [(abs(F(r, 'TireSlipAngleRearLeft')) +
                     abs(F(r, 'TireSlipAngleRearRight'))) / 2 for r in in_corner_pkts]
        rear_slip_ratio = [(abs(F(r, 'TireSlipRatioRearLeft')) +
                           abs(F(r, 'TireSlipRatioRearRight'))) / 2 for r in in_corner_pkts]
        throttle = [I(r, 'Accel') for r in in_corner_pkts]

        # Find the apex packet (slowest point in the corner)
        apex_local_idx = speeds.index(min(speeds))
        # Time from apex to "throttle reopen" (first packet after apex with Accel >= 200)
        # Only meaningful if the player actually lifted off (min throttle was low).
        throttle_min = min(throttle)
        throttle_avg = statistics.mean(throttle)
        if throttle_min < 100:
            throttle_reopen_pkt = None
            for k in range(apex_local_idx, len(throttle)):
                if throttle[k] >= 200:
                    throttle_reopen_pkt = k
                    break
            throttle_reopen_delay = ((throttle_reopen_pkt - apex_local_idx) / 60
                                    if throttle_reopen_pkt is not None else None)
        else:
            # Driver maintained throttle through corner — reopen metric is N/A.
            throttle_reopen_delay = None

        apex_kmh = min(speeds) * 3.6
        apex_speed_ms = min(speeds)
        speed_drop_kmh = (approach_speed - min(speeds)) * 3.6
        # Filter non-corner events: stops, crashes, near-zero apex
        if apex_kmh < CORNER_MIN_APEX_KMH or speed_drop_kmh > CORNER_MAX_SPEED_DROP_KMH:
            filtered_stop_count += 1
            continue
        # Filter high-speed sweepers: apex radius (= v² / (G·9.81)) too large
        # to count as a "real corner" (they pollute speed_drop and throttle stats).
        peak_g_abs = abs(peak_g) * 9.81
        apex_radius_m = (apex_speed_ms ** 2) / peak_g_abs if peak_g_abs > 0.01 else float('inf')
        if apex_radius_m > CORNER_MAX_RADIUS_M:
            filtered_sweeper_count += 1
            continue

        # Per-packet 推頭/轉向過度計數（彎內每 packet 比較 front/rear slip angle）
        # 對應 TL;DR「整體推頭傾向」與「過彎時間中推頭時間佔比」指標。
        # 5.0 上限同 analyze_slip 的 SLIP_ANGLE_ARTIFACT_CAP，過濾撞車尖峰。
        pkt_understeer = 0
        pkt_oversteer = 0
        for fs_v, rs_v in zip(front_slip, rear_slip):
            if fs_v >= 5.0 or rs_v >= 5.0:
                continue
            if fs_v > 0.5 and fs_v > rs_v * UNDERSTEER_RATIO:
                pkt_understeer += 1
            elif rs_v > 0.5 and rs_v > fs_v * UNDERSTEER_RATIO:
                pkt_oversteer += 1
        total_in_corner_packets += len(in_corner_pkts)
        understeer_packets_in_corners += pkt_understeer
        oversteer_packets_in_corners += pkt_oversteer

        corners.append({
            "start": start, "end": end,
            "apex_global": start + apex_local_idx,
            "lap": I(valid_rows[start], 'LapNumber'),
            "duration_s": (end - start + 1) / 60,
            "direction": "R" if peak_g > 0 else "L",
            "peak_g": peak_g,
            "approach_kmh": approach_speed * 3.6,
            "apex_kmh": apex_kmh,
            "exit_kmh": speeds[-1] * 3.6,
            "speed_drop_kmh": speed_drop_kmh,
            "front_slip_max": max(front_slip),
            "rear_slip_max": max(rear_slip),
            "rear_wheelspin_pkts": sum(1 for x in rear_slip_ratio if x > 1.0),
            "throttle_min": throttle_min,
            "throttle_avg": throttle_avg,
            "throttle_reopen_delay_s": throttle_reopen_delay,
            "front_rear_slip_ratio": (max(front_slip) / max(rear_slip)
                                     if max(rear_slip) > 0 else float('inf')),
            "understeer_packets": pkt_understeer,
            "oversteer_packets": pkt_oversteer,
        })

    if not corners:
        return {"corners": [], "count": 0, "track_bias": "unknown"}

    # Aggregates
    n_left = sum(1 for c in corners if c["direction"] == "L")
    n_right = len(corners) - n_left
    if max(n_left, n_right) / len(corners) >= CORNER_BIAS_THRESHOLD:
        track_bias = "left" if n_left > n_right else "right"
    else:
        track_bias = "balanced"

    total_corner_time = sum(c["duration_s"] for c in corners)
    valid_duration = len(valid_rows) / 60

    # Throttle behavior split
    delays = [c["throttle_reopen_delay_s"] for c in corners
             if c["throttle_reopen_delay_s"] is not None]
    corners_with_lift = sum(1 for c in corners if c["throttle_min"] < 100)

    return {
        "corners": corners,
        "count": len(corners),
        "raw_count": len(corners_raw),
        "filtered_sweeper_count": filtered_sweeper_count,
        "filtered_stop_count": filtered_stop_count,
        "left_count": n_left,
        "right_count": n_right,
        "track_bias": track_bias,
        "total_corner_time_s": total_corner_time,
        "corner_time_pct": total_corner_time / valid_duration * 100 if valid_duration > 0 else 0,
        "avg_peak_g": statistics.mean(abs(c["peak_g"]) for c in corners),
        "max_peak_g": max(abs(c["peak_g"]) for c in corners),
        "avg_speed_drop": statistics.mean(c["speed_drop_kmh"] for c in corners),
        "max_speed_drop": max(c["speed_drop_kmh"] for c in corners),
        "avg_apex_kmh": statistics.mean(c["apex_kmh"] for c in corners),
        "avg_throttle_min": statistics.mean(c["throttle_min"] for c in corners),
        "avg_throttle_avg": statistics.mean(c["throttle_avg"] for c in corners),
        "corners_with_lift": corners_with_lift,
        "avg_throttle_reopen_delay_s": statistics.mean(delays) if delays else None,
        "understeering_corners": sum(1 for c in corners if c["front_rear_slip_ratio"] > 1.5),
        "oversteering_corners": sum(1 for c in corners if c["front_rear_slip_ratio"] < 0.7),
        "wheelspin_exit_corners": sum(1 for c in corners if c["rear_wheelspin_pkts"] > 5),
        # 彎內 per-packet 累積（給「過彎時間中推頭/過度時間佔比」與 TL;DR 推頭主症狀使用）
        "total_in_corner_packets": total_in_corner_packets,
        "understeer_packets_in_corners": understeer_packets_in_corners,
        "oversteer_packets_in_corners": oversteer_packets_in_corners,
        "understeer_time_pct": (understeer_packets_in_corners / total_in_corner_packets * 100
                                if total_in_corner_packets > 0 else 0.0),
        "oversteer_time_pct": (oversteer_packets_in_corners / total_in_corner_packets * 100
                               if total_in_corner_packets > 0 else 0.0),
    }


def _score_problem_corner(c: dict, valid_rows: list, steer_max_obs: int) -> dict:
    """Compute (sustained_steer_pin_seconds, understeer_packets, score) for one corner.

    sustained_steer_pin_seconds = longest CONTINUOUS run of |Steer| >= steer_max_obs * 0.8
    understeer_packets = packets where front slip > rear slip * 1.5
    score = sustained_steer_pin_seconds + understeer_packets / 60
    """
    pin_thr = steer_max_obs * 0.8 if steer_max_obs > 0 else 1e9
    pkts = valid_rows[c["start"]:c["end"] + 1]
    abs_steer = [abs(I(r, 'Steer')) for r in pkts]

    # Longest continuous run with |steer| >= pin_thr
    longest = 0
    cur = 0
    for s in abs_steer:
        if s >= pin_thr:
            cur += 1
            longest = max(longest, cur)
        else:
            cur = 0
    sustained_pin_s = longest / 60

    # Understeer packets in corner
    us_pkts = 0
    for r in pkts:
        fs = (abs(F(r, 'TireSlipAngleFrontLeft')) +
              abs(F(r, 'TireSlipAngleFrontRight'))) / 2
        rs = (abs(F(r, 'TireSlipAngleRearLeft')) +
              abs(F(r, 'TireSlipAngleRearRight'))) / 2
        if fs > rs * 1.5 and fs > 0.5:
            us_pkts += 1

    score = sustained_pin_s + us_pkts / 60
    return {
        "sustained_pin_s": sustained_pin_s,
        "understeer_packets": us_pkts,
        "score": score,
    }


def _emit_corner_table(valid_rows: list, c: dict, n: int, label_prefix: str,
                       extras: list[str] | None = None) -> list[str]:
    """Emit one '彎 N' subsection (heading + per-frame table) for corners_detail.md.

    label_prefix is the heading lead-in, e.g. '彎 1' or '問題彎 1'.
    extras is a list of extra info lines to print before the per-frame table.
    """
    out: list[str] = []
    n_total = len(valid_rows)
    PRE = 30
    POST = 30
    STEP = 4
    APEX_WIN = 4

    start = c["start"]
    end = c["end"]
    in_pkts = valid_rows[start:end + 1]
    speeds_in = [F(r, 'Speed') for r in in_pkts]
    apex_local = speeds_in.index(min(speeds_in))
    apex_idx = start + apex_local
    apex_phase_end = min(apex_idx + APEX_WIN, end)

    sample_start = max(0, start - PRE)
    sample_end = min(n_total - 1, end + POST)

    t0 = F(valid_rows[start], 'CurrentRaceTime')
    approach_kmh = c["approach_kmh"]
    apex_kmh = c["apex_kmh"]
    drop = c["speed_drop_kmh"]
    peak_g = c["peak_g"]
    direction = c["direction"]

    out.append(f'## {label_prefix}：t={t0:.1f}s | 入彎 {approach_kmh:.0f}→彎心 {apex_kmh:.0f} km/h '
               f'(-{drop:.0f}) | Peak G {peak_g:+.2f} | {direction} 方向')
    out.append('')
    out.append(f'彎內持續 {c["duration_s"]:.2f}s')
    if extras:
        for line in extras:
            out.append(line)
    out.append('')
    out.append('| phase | t-rel (s) | 速度 (km/h) | RPM | latG | 油門 | 煞車 | 檔 | 方向 | 前slip | 後slip | 備註 |')
    out.append('|-------|-----------|-------------|-----|------|------|------|----|------|--------|--------|------|')

    prev_kmh: float | None = None
    prev_crt: float | None = None
    for j in range(sample_start, sample_end + 1, STEP):
        r = valid_rows[j]
        crt = F(r, 'CurrentRaceTime')
        kmh = F(r, 'Speed') * 3.6

        # rewind 邊界 / 不連續偵測：相鄰兩 row 速度跳 > 30 km/h 或 CRT 倒退
        # → 插入分隔行，提示讀者別把這兩行間視為駕駛動作。
        if prev_kmh is not None and prev_crt is not None:
            speed_jump = abs(kmh - prev_kmh) > 30
            time_back = crt < prev_crt - 0.01  # 容忍微小浮點誤差
            if speed_jump or time_back:
                reason = []
                if speed_jump:
                    reason.append(f'速度跳變 {prev_kmh:.0f}→{kmh:.0f} km/h')
                if time_back:
                    reason.append(f'CRT 倒退 {prev_crt:.2f}→{crt:.2f}s')
                out.append(f'| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | '
                           f'⚠️ rewind/discontinuity 邊界（{"; ".join(reason)}） |')

        if j < start:
            phase = 'approach'
        elif j > end:
            phase = 'after'
        elif apex_idx <= j <= apex_phase_end:
            phase = 'APEX'
        elif j < apex_idx:
            phase = 'entry'
        else:
            phase = 'exit'

        t_rel = crt - t0
        rpm = F(r, 'CurrentEngineRpm')
        latg = F(r, 'AccelerationX') / 9.81
        accel = I(r, 'Accel')
        brake = I(r, 'Brake')
        gear = I(r, 'Gear')
        steer = I(r, 'Steer')
        front_slip = (abs(F(r, 'TireSlipAngleFrontLeft')) +
                      abs(F(r, 'TireSlipAngleFrontRight'))) / 2
        rear_slip = (abs(F(r, 'TireSlipAngleRearLeft')) +
                     abs(F(r, 'TireSlipAngleRearRight'))) / 2

        # FH5 sticky-tire physical limit ≈ 2-3G; |latG| > 3.0 here is almost
        # always wall contact / curb hop / IMU spike rather than real grip.
        note = '⚠️ 異常 G' if abs(latg) > 3.0 else ''
        out.append(f'| {phase} | {t_rel:+.2f} | {kmh:.1f} | {rpm:.0f} | {latg:+.2f} '
                   f'| {accel} | {brake} | {gear} | {steer:+d} '
                   f'| {front_slip:.2f} | {rear_slip:.2f} | {note} |')
        prev_kmh = kmh
        prev_crt = crt
    out.append('')
    return out


def generate_corners_detail(valid_rows: list, corners_result: dict) -> str | None:
    """Generate corners_detail.md content: per-frame input tables for two top-3 boards.

    Board A — 最重煞車 top 3：依 speed_drop_kmh 排序的彎，看「煞車點 / 入彎重煞」。
    Board B — 問題彎 top 3：依 (sustained_steer_pin_seconds + understeer_packets/60)
              排序的彎，看「方向打死 / 推頭」這類駕駛操控問題；可能與 Board A 完全
              重疊，重疊時跳過避免重複。

    Sampling per corner（兩榜共用）:
      - approach: 30 packets (0.5s) before corner start
      - in-corner: corner start..end (subdivided into entry/APEX/exit by APEX idx)
      - after: 30 packets (0.5s) after corner end
      - emit one row every 4 packets (~67ms cadence)

    APEX = slowest packet within (start..end). APEX phase covers that packet
    plus the 4 following packets (~83ms window).

    Returns the markdown string, or None if there are fewer than 3 corners.
    """
    corners = corners_result.get("corners") or []
    if len(corners) < 3:
        return None

    # Observed max steer over ALL valid rows — controller players rarely hit 127.
    steer_max_obs = max(abs(I(r, 'Steer')) for r in valid_rows)

    heavy = sorted(corners, key=lambda c: -c["speed_drop_kmh"])[:3]

    # Score every corner for the problem-corner board; rank top 3.
    scored = []
    for c in corners:
        s = _score_problem_corner(c, valid_rows, steer_max_obs)
        scored.append({**c, **s})
    problem = sorted(scored, key=lambda c: -c["score"])[:3]

    out: list[str] = []
    out.append('# 過彎逐幀分析')
    out.append('')
    out.append('每行 ≈ 4 packets（67ms）。配合同層 [summary.md](summary.md) 「過彎分析」段使用。')
    out.append('')

    # ---- Board A: heaviest-braking ----
    out.append('## 最重煞車 top 3（依 speed_drop 排序）')
    out.append('')
    out.append('看「煞車點 / 入彎重煞」這類**減速**問題。')
    out.append('')

    heavy_keys = set()
    for n, c in enumerate(heavy, 1):
        heavy_keys.add((c["start"], c["end"]))
        out.extend(_emit_corner_table(valid_rows, c, n, f'彎 {n}'))

    # ---- Board B: problem corners ----
    out.append('---')
    out.append('')
    out.append(f'## 問題彎 top 3（依方向打死持續秒數 + 推頭 packet 數排序，Steer 觀測上限 = ±{steer_max_obs}/127）')
    out.append('')
    out.append('看「方向打死 / 推頭」這類**操控**問題；可能與「最重煞車 top 3」完全重疊，')
    out.append('重疊時跳過避免重複（重疊條目會以「同上 — 重煞車榜彎 N」標註）。')
    out.append('')
    out.append(f'評分公式：`score = sustained_steer_pin_seconds + understeer_packets / 60`')
    out.append('')

    n_emitted = 0
    for c in problem:
        key = (c["start"], c["end"])
        n_emitted += 1
        extras = [
            f'\n問題評分：**score = {c["score"]:.2f}**'
            f'（方向打死最長 {c["sustained_pin_s"]:.2f}s + 推頭 {c["understeer_packets"]} packet）',
        ]
        if key in heavy_keys:
            # Find which heavy slot it matches
            heavy_n = None
            for hi, hc in enumerate(heavy, 1):
                if (hc["start"], hc["end"]) == key:
                    heavy_n = hi
                    break
            out.append(f'## 問題彎 {n_emitted}：與「最重煞車榜彎 {heavy_n}」完全重疊，逐幀資料見上')
            out.append('')
            for line in extras:
                out.append(line.lstrip('\n'))
            out.append('')
            continue
        out.extend(_emit_corner_table(valid_rows, c, n_emitted,
                                      f'問題彎 {n_emitted}',
                                      extras=extras))

    out.append('---')
    out.append('')
    out.append('## 判讀指南')
    out.append('')
    out.append('- **純煞車段**：連續多筆 `煞車 ≥ 200` 且 `|方向| < 10` 的 row → 這段越長越好（理想 0.5s+，約 7-8 row）。煞車跟轉向**分離**才能把抓地全用在減速')
    out.append('- **邊煞邊轉**：`煞車 ≥ 100` 同時 `|方向| > 20` 的 row → 抓地超預算會推頭，越短越好；新手常見問題是煞車點太晚被迫邊煞邊轉')
    out.append('- **APEX 檔位是否對**：看 APEX phase 的 RPM 是否落在 summary.md「估算 dyno 曲線」的動力區範圍內。若 APEX RPM 太低（< peak power RPM 的 70%）→ 出彎拉不起來，應降一檔；若 APEX 已到紅線 → 該升檔')
    out.append('- **漸進給油**：APEX 之後的 `油門` 欄應該從低值平滑爬升到 255（vs 一下從 0 跳 255）；油門突然全開常伴隨後 slip 飆高，代表差速器/動力分配/腳法太猛')
    out.append('- **前 slip > 後 slip × 1.5**：那一瞬間在推頭。若集中在 entry/APEX → 入彎太用力或胎壓/外傾不對；若集中在 exit → 動力下太多前輪鎖死')
    out.append('- **異常 latG**：|latG| > 2.5 通常是撞牆/壓縁石（FH5 黏胎極限約 2-3 G），不是真實過彎抓地——這種 row 可忽略')
    out.append('- **方向打死（|方向| 接近觀測上限）**：FH5 控制器極少打到 ±127，所以「打死」的閾值是該場 max(|Steer|) × 0.8。在彎中持續 1s 以上方向打死、油門 0、煞車 0、前 slip > 2 → 經典 understeer 駕駛模式：超過抓地極限後再轉也轉不進去，正確處置是早 0.5s 鬆方向、減速進彎')
    out.append('- **問題彎 ≠ 最重煞車彎**：speed_drop 大的彎是「煞車重」、score 高的彎是「車不聽話」。兩榜都看才能分辨「煞太晚」vs「轉太多」')
    out.append('')

    return '\n'.join(out) + '\n'


# ----- formatting ------------------------------------------------------------

def fmt_segment_table_speed(segments: list[Segment]) -> list[str]:
    out = ['| 段 | 圈時 / 持續 (s) | 平均速度 (km/h) | 最高速 (km/h) | 距離 (m) | 封包數 |',
           '|----|----------------|----------------|--------------|----------|--------|']
    prev_lap_time = None
    for seg in segments:
        speeds = [F(r, 'Speed') for r in seg.packets]
        avg_kmh = statistics.mean(speeds) * 3.6
        max_kmh = max(speeds) * 3.6
        dist = integrate_distance(speeds)
        if seg.completed_lap_time > 0:
            delta = ''
            if prev_lap_time:
                d = seg.completed_lap_time - prev_lap_time
                delta = f' ({"+" if d > 0 else ""}{d:.3f})'
            time_str = f'{seg.completed_lap_time:.3f}{delta}'
            prev_lap_time = seg.completed_lap_time
        elif seg.lap_number is not None:
            time_str = '— (未過線)'
        else:
            duration = len(seg.packets) / 60
            time_str = f'{duration:.2f}'
        out.append(f'| {seg.label} | {time_str} | {avg_kmh:.1f} | {max_kmh:.1f} | {dist:.0f} | {len(seg.packets)} |')
    return out


def fmt_tire_table(tire_data: dict) -> list[str]:
    out = ['| 段 | FL | FR | RL | RR | L-R 前 | L-R 後 | 前-後 |',
           '|----|----|----|----|----|--------|--------|-------|']
    for r in tire_data["per_segment"]:
        out.append(f'| {r["label"]} | {r["fl"]:.0f} | {r["fr"]:.0f} | {r["rl"]:.0f} | {r["rr"]:.0f} | '
                  f'{r["lr_front_delta"]:+.1f} | {r["lr_rear_delta"]:+.1f} | {r["fr_delta"]:+.1f} |')
    return out


def fmt_slip_table(slip_data: dict) -> list[str]:
    out = ['| 段 | 前輪 max | 後輪 max | 前輪 avg | 後輪 avg | 前/後 比 | 備註 |',
           '|----|---------|---------|---------|---------|----------|------|']
    for r in slip_data["per_segment"]:
        ratio = r["fr_max"] / r["rr_max"] if r["rr_max"] > 0 else float('inf')
        note = '⚠️ 含異常 slip 尖峰已過濾' if r.get("ratio_artifact_filtered") else ''
        out.append(f'| {r["label"]} | {r["fr_max"]:.3f} | {r["rr_max"]:.3f} | '
                  f'{r["fr_avg"]:.3f} | {r["rr_avg"]:.3f} | {ratio:.2f}× | {note} |')
    return out


def fmt_suspension_table(susp_data: dict) -> list[str]:
    out = ['| 段 | FL max | FR max | RL max | RR max | FL avg | FR avg | RL avg | RR avg | 觸底 (>0.95) |',
           '|----|--------|--------|--------|--------|--------|--------|--------|--------|--------------|']
    for r in susp_data["per_segment"]:
        bold_fl = '**' if r["fl_max"] > SUSPENSION_BOTTOM_THRESHOLD else ''
        bold_fr = '**' if r["fr_max"] > SUSPENSION_BOTTOM_THRESHOLD else ''
        bold_rl = '**' if r["rl_max"] > SUSPENSION_BOTTOM_THRESHOLD else ''
        bold_rr = '**' if r["rr_max"] > SUSPENSION_BOTTOM_THRESHOLD else ''
        out.append(f'| {r["label"]} | {bold_fl}{r["fl_max"]:.2f}{bold_fl} | '
                  f'{bold_fr}{r["fr_max"]:.2f}{bold_fr} | {bold_rl}{r["rl_max"]:.2f}{bold_rl} | '
                  f'{bold_rr}{r["rr_max"]:.2f}{bold_rr} | {r["fl_avg"]:.2f} | {r["fr_avg"]:.2f} | '
                  f'{r["rl_avg"]:.2f} | {r["rr_avg"]:.2f} | {r["bottom_count"]} |')
    return out


# ----- drivetrain-aware TL;DR helpers ----------------------------------------

# Actions that only make sense for certain drivetrains. Keys are exact action
# strings as they may appear in any finding's "tuning" list; values are the
# set of drivetrain_type ints (0=FWD, 1=RWD, 2=AWD) for which the action is
# valid. An action NOT in this dict is allowed for all drivetrains.
#
# Two failure modes drove this table:
#   1. RWD oversteer sessions were getting 「動力分配往前移」 (no center diff
#      to redistribute) and 「提高後胎壓」 (the AWD wheelspin trick — wrong
#      sign for RWD oversteer; you want to *lower* rear pressure).
#   2. FWD getting "軟後防傾桿" advice when it would actually want the
#      opposite (stiffer rear ARB to rotate the car).
DRIVETRAIN_ACTION_GUARD: dict[str, set[int]] = {
    'AWD 若可調：動力分配往前移 5-10%': {2},
    'AWD 若可調：動力分配往後移 5-10%': {2},
    '動力分配往前移 5-10%': {2},
    '動力分配往後移': {2},
    '動力分配往後移 5-10%': {2},
    '提高後胎壓 1-2 psi（反直覺但能釋放動力）': {2},  # AWD-only trick
}


def _filter_actions_by_drivetrain(actions: list[str], drivetrain_type: int) -> list[str]:
    """Drop actions whose DRIVETRAIN_ACTION_GUARD set excludes this drivetrain."""
    out = []
    for a in actions:
        allowed = DRIVETRAIN_ACTION_GUARD.get(a)
        if allowed is None or drivetrain_type in allowed:
            out.append(a)
    return out


# 把處方字串 normalize 成 canonical key 用於去重（去括號補充說明、AWD 前綴、結尾百分比）。
# 例：「軟化加速差速器鎖定 5-10%（讓內輪能空轉緩衝）」與「軟化加速差速器鎖定 5-10%」
# canonical 後都是「軟化加速差速器鎖定」。
_CANON_PAREN = re.compile(r'[（(].*?[)）]')
_CANON_PREFIX = re.compile(r'^AWD 若可調：')
_CANON_TAIL_PCT = re.compile(r'\s*\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?\s*%?\s*$')


def _canonical_action_key(action: str) -> str:
    s = _CANON_PAREN.sub('', action).strip()
    s = _CANON_PREFIX.sub('', s).strip()
    s = _CANON_TAIL_PCT.sub('', s).strip()
    return s


# 互斥處方組——同 group 內最多保留一條（依 finding severity 排序，先進先保留）。
# 用 canonical key 為輸入。例：當推頭主症狀加了「動力分配往後移」，後續其他症狀
# 想加「動力分配往前移」時，因兩者同 group 直接跳過。
_CONFLICT_GROUPS: dict[str, str] = {
    '動力分配往前移': 'center_diff',
    '動力分配往後移': 'center_diff',
    '加前差加速鎖定': 'front_diff_accel',
    '前差加速鎖定降': 'front_diff_accel',
    '後差加速鎖定加': 'rear_diff_accel',
    '後差加速鎖定降': 'rear_diff_accel',
}


def _wheelspin_finding(wheelspin_pkts: int, drivetrain_type: int) -> dict:
    """Build the rear-wheelspin finding with prescriptions tailored to drivetrain.

    For RWD this is treated as power oversteer evidence — the prescriptions
    follow the RWD oversteer column of the project's drivetrain action table:
    soften (not stiffen) rear, lower (not raise) rear pressure, ease the rear
    diff on accel, firm it on decel.

    For AWD the historical prescriptions still apply (rear pressure trick,
    forward power split, looser accel diff).

    For FWD wheelspin > 60 packets is unusual (wrong wheels) but we keep a
    minimal prescription set in case it triggers on a FF car running wide
    rear tires off-camber.
    """
    sec = wheelspin_pkts / 60
    if drivetrain_type == 1:  # RWD
        return {
            "severity": "🔴",
            "title": f'後輪嚴重打滑 {sec:.1f}s（RWD power oversteer 訊號 / 出彎給油過猛 / 後軸過硬）',
            "tuning": [
                '降後胎壓 1-2 psi',
                '軟後防傾桿 1-2 級',
                '加後外傾 0.3-0.5°',
                '後差加速鎖定降 5-10%（讓內輪能空轉緩衝）',
                '後差減速鎖定加 20-30%（穩定入彎）',
            ],
            "driving": ['出彎漸進給油，前 0.5 秒不要全踩', '彎心後等車身擺正再加油'],
        }
    if drivetrain_type == 2:  # AWD
        return {
            "severity": "🟡",
            "title": f'後輪嚴重打滑 {sec:.1f}s（差速器 / 動力分配 / 出彎習慣）',
            "tuning": [
                # 明確指後差，避免與推頭處方的「前差加速」混淆
                '後差加速鎖定降 5-10%（讓內輪能空轉緩衝）',
                'AWD 若可調：動力分配往前移 5-10%',
                '提高後胎壓 1-2 psi（反直覺但能釋放動力）',
            ],
            "driving": ['出彎漸進給油，前 0.5 秒不要全踩'],
        }
    # FWD (rear wheelspin is rare — minimal prescription)
    return {
        "severity": "ℹ️",
        "title": f'後輪打滑 {sec:.1f}s（FWD 後輪打滑通常為負重轉移／壓縁石所致，較不影響動力）',
        "tuning": ['降後胎壓 1-2 psi', '加後外傾 0.3-0.5°'],
        "driving": [],
    }


def _understeer_tuning_for_drivetrain(drivetrain_type: int) -> list[str]:
    """Front-hot / understeer prescriptions vary by drivetrain.

    RWD/AWD: soften front, lower front pressure, more front camber.
    AWD additionally: push power forward (less rear-bias), soften accel diff.
    FWD: lower front pressure, soften front ARB, ease front diff on accel.
    """
    if drivetrain_type == 0:  # FWD
        return ['降前胎壓 1-2 psi', '軟前防傾桿 1-2 級', '加前外傾 0.3-0.5°（往 -3.0 方向）',
                '前差加速鎖定降 5-10%（FWD 出彎才不會推頭）']
    if drivetrain_type == 2:  # AWD
        # 推頭主症狀 → 動力分配往「後」移：讓前輪不必同時拉動力+轉向（中差% 拉高）。
        # 早期版本誤寫「往前移」，與後輪打滑處方衝突。對應 wiki/tuning/差速器.md
        # 「中央差速器」段。
        return ['降前胎壓 1-2 psi', '加前外傾 0.3-0.5°（往 -3.0 方向）', '軟前防傾桿 1-2 級',
                'AWD 若可調：動力分配往後移 5-10%', '加前差加速鎖定 5-10%（改善低速彎入彎推頭）']
    # RWD
    return ['降前胎壓 1-2 psi', '加前外傾 0.3-0.5°（往 -3.0 方向）', '軟前防傾桿 1-2 級',
            '加後防傾桿 1 級（反向幫前軸轉向）']


def _oversteer_tuning_for_drivetrain(drivetrain_type: int) -> list[str]:
    """Rear-hot / oversteer prescriptions vary by drivetrain.

    RWD: soften rear, lower rear pressure, more rear camber, easier accel diff,
         firmer decel diff. NEVER 'raise rear pressure' (that's the AWD trick).
    AWD: same softening + push power back.
    FWD: rear-hot is rare; soften rear, lower rear pressure.
    """
    if drivetrain_type == 0:  # FWD
        return ['降後胎壓 1-2 psi', '軟後防傾桿 1-2 級', '加後外傾 0.3-0.5°']
    if drivetrain_type == 2:  # AWD
        return ['降後胎壓 1-2 psi', '軟後防傾桿 1-2 級', '加後外傾 0.3-0.5°',
                '動力分配往後移']
    # RWD
    return ['降後胎壓 1-2 psi', '軟後防傾桿 1-2 級', '加後外傾 0.3-0.5°',
            '後差加速鎖定降 5-10%', '後差減速鎖定加 20-30%']


# ----- report builder --------------------------------------------------------

def build_report(session_dir: Path) -> tuple[str, str | None]:
    """Return (summary_md, corners_detail_md_or_None).

    corners_detail is None when fewer than 3 corners are detected.
    """
    raw_path = session_dir / 'raw.csv'
    meta_path = session_dir / 'meta.json'
    with raw_path.open(encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    meta = json.loads(meta_path.read_text(encoding='utf-8'))

    pre_crash_valid = [r for r in rows if r['IsRaceOn'] == '1' and r['is_rewind'] == '0']
    if not pre_crash_valid:
        return (f'# {session_dir.name}\n\n沒有可分析的有效資料（IsRaceOn=1 且非 rewind）。\n', None)

    # Filter crash-affected packets (G-force spikes, sudden velocity drops).
    # Crashes pollute G-force max, decel-event ranking, suspension bottom counts,
    # and wheelspin counts. Excluding them gives a true picture of "normal driving".
    crash_excluded, crash_count = detect_crashes(pre_crash_valid)
    valid = [r for j, r in enumerate(pre_crash_valid) if j not in crash_excluded]
    if not valid:
        return (f'# {session_dir.name}\n\n所有 packet 都被判定為撞車或無效，無法分析。\n', None)

    # Decide segmentation strategy
    max_lap = max(I(r, 'LapNumber') for r in valid)
    is_lapped = max_lap > 0
    if is_lapped:
        segments = segment_by_lap(valid)
        event_type = "lapped"
        seg_word = "圈"
    else:
        segments = segment_by_distance(valid)
        event_type = "single_run"
        seg_word = "段"

    # Run all analyses
    tires = analyze_tires(segments)
    slip = analyze_slip(segments)
    susp = analyze_suspension(segments)
    rpm_obs = analyze_rpm_observed(valid)
    dyno = analyze_dyno(valid)
    drvtrn = analyze_drivetrain(valid, dyno=dyno)
    inputs = analyze_inputs(valid)
    gforces = analyze_g_forces(valid, pre_crash_rows=pre_crash_valid)
    decels = analyze_decel_events(valid)
    speed = analyze_speed(valid)
    surf = analyze_surface(valid)
    wheelspin = analyze_wheelspin(valid)
    wheelspin_pkts = wheelspin["count"]
    corners = analyze_corners(valid)
    wheelspin_phases = classify_wheelspin_phases(wheelspin["indices"], corners.get("corners", []))
    drivetrain_type = meta["car"]["drivetrain_type"]
    drivetrain_name = DRIVETRAIN_NAMES.get(drivetrain_type, "?")

    # Identify "headline" issues with prescriptive fixes split into tuning vs driving.
    # Each finding may carry zero or more "tuning" / "driving" actions; the TL;DR
    # aggregates all actions from severity-ordered findings for one-glance reading.
    findings: list[dict] = []

    # === 整體推頭 / 轉向過度傾向（per-packet 在彎內的比例）===
    # 這是 TL;DR 必須最先看到的「車的天然取向」指標——以前只放 understeer_moments
    # 的絕對 packet 數在精煉 context，TL;DR 完全沒提，導致即使全場推頭 1300+ packet
    # 仍可能被「懸吊觸底」「後輪打滑」等次要症狀蓋過。
    total_corner_pkts = corners.get("total_in_corner_packets", 0) if corners["count"] > 0 else 0
    us_pkts_corner = corners.get("understeer_packets_in_corners", 0) if corners["count"] > 0 else 0
    os_pkts_corner = corners.get("oversteer_packets_in_corners", 0) if corners["count"] > 0 else 0
    if total_corner_pkts > 0:
        us_time_pct = us_pkts_corner / total_corner_pkts * 100
        os_time_pct = os_pkts_corner / total_corner_pkts * 100
        us_os_ratio = us_pkts_corner / max(os_pkts_corner, 1)
        os_us_ratio = os_pkts_corner / max(us_pkts_corner, 1)
        # 推頭主症狀：比例 >= 3:1 且 彎內時間佔比 >= 15%
        # （門檻原寫 20%，但實測中 18% + 3:1 的場景已經是駕駛體感明顯推頭，
        #  把門檻設 15% 才能捕捉這類場景；嚴重度（⛔ vs 🟡）依比例 5:1 / 時間 30% 區分。）
        if us_os_ratio >= 3 and us_time_pct >= 15:
            severity = "⛔" if (us_os_ratio >= 5 or us_time_pct >= 30) else "🟡"
            findings.append({
                "severity": severity,
                "title": (f'整體推頭傾向（彎內 {us_time_pct:.0f}% 時間推頭，'
                          f'推頭/過度比 {us_os_ratio:.1f}:1）'),
                "tuning": _understeer_tuning_for_drivetrain(drivetrain_type),
                "driving": ['入彎再慢 3-5 km/h、轉向更線性，避免打到 saturate 還繼續加角度'],
            })
        elif os_us_ratio >= 3 and os_time_pct >= 15:
            severity = "⛔" if (os_us_ratio >= 5 or os_time_pct >= 30) else "🟡"
            findings.append({
                "severity": severity,
                "title": (f'整體轉向過度傾向（彎內 {os_time_pct:.0f}% 時間轉向過度，'
                          f'過度/推頭比 {os_us_ratio:.1f}:1）'),
                "tuning": _oversteer_tuning_for_drivetrain(drivetrain_type),
                "driving": ['出彎油門更線性，前 0.5s 控制在 70%；入彎避免 trail brake 過深'],
            })

    if tires["overall"] and tires["overall"]["fr_delta"] > 10:
        d = tires["overall"]["fr_delta"]
        findings.append({
            "severity": "🔴",
            "title": f'前胎過熱（推頭傾向） +{d:.0f}°C',
            "tuning": _understeer_tuning_for_drivetrain(drivetrain_type),
            "driving": ['入彎再慢 3-5 km/h，出彎晚一點再給油'],
        })
    elif tires["overall"] and tires["overall"]["fr_delta"] < -10:
        d = abs(tires["overall"]["fr_delta"])
        findings.append({
            "severity": "🔴",
            "title": f'後胎過熱（轉向過度傾向） +{d:.0f}°C',
            "tuning": _oversteer_tuning_for_drivetrain(drivetrain_type),
            "driving": ['出彎別太早全油門，給油更線性'],
        })
    if slip["per_segment"]:
        ratios = [r["fr_max"] / r["rr_max"] for r in slip["per_segment"] if r["rr_max"] > 0]
        if ratios and statistics.mean(ratios) > 1.5:
            findings.append({
                "severity": "🔴",
                "title": f'前輪滑移 ≈ {statistics.mean(ratios):.1f}× 後輪（推頭證據）',
                "tuning": [],  # 與「前胎過熱」處方重複，避免 TL;DR 雜訊
                "driving": [],
            })
        elif ratios and statistics.mean(ratios) < 0.7:
            findings.append({
                "severity": "🔴",
                "title": f'後輪滑移 ≈ {1 / statistics.mean(ratios):.1f}× 前輪（轉向過度證據）',
                "tuning": [], "driving": [],
            })
    if susp["total_bottom_packets"] > 30:
        # Identify which corner bottoms most
        per_corner = {c: sum(r["bottom_count"] for r in susp["per_segment"])
                     for c in ['fl_max', 'fr_max', 'rl_max', 'rr_max']}
        findings.append({
            "severity": "🟡",
            "title": f'懸吊觸底 {susp["total_bottom_packets"]} 個 packet（彈簧過軟 / 車高過低）',
            "tuning": ['拉硬觸底那角彈簧 5-10%', '或拉高該角車高 0.5-1 cm', '或加大壓縮阻尼 1-2 級'],
            "driving": [],
        })
    if drvtrn["shift_loss_rpm"] > 500:
        basis_note = ('（基準=峰值馬力 RPM）' if drvtrn["ideal_shift_basis"] == "peak_power_rpm"
                      else '（基準=EngineMaxRpm × 95%，可能不準）')
        findings.append({
            "severity": "🟡",
            "title": f'換檔太早 {drvtrn["shift_loss_rpm"]:.0f} RPM（直線丟動力）{basis_note}',
            "tuning": ['拉長個別齒比（蓋過去峰值馬力 RPM）', '或拉長最終傳動 (Final Drive 往 Long 方向)'],
            "driving": [f'手排：晚一點換檔，等到聲音接近 {drvtrn["ideal_shift"]:.0f} RPM 再換'],
        })
    if wheelspin_pkts > 60:
        findings.append(_wheelspin_finding(wheelspin_pkts, drivetrain_type))

    # Corner-derived insights
    if corners["count"] > 3:
        # Track bias — context for asymmetric tire wear
        if corners["track_bias"] == "left" and tires["overall"] and tires["overall"]["lr_front_delta"] < -3:
            findings.append({
                "severity": "ℹ️",
                "title": f'本場 {corners["left_count"]}/{corners["count"]} 個彎為左彎 → 右前胎偏熱（{tires["overall"]["lr_front_delta"]:+.1f}°C）屬賽道特性，**非調校問題**',
                "tuning": [], "driving": [],
            })
        elif corners["track_bias"] == "right" and tires["overall"] and tires["overall"]["lr_front_delta"] > 3:
            findings.append({
                "severity": "ℹ️",
                "title": f'本場 {corners["right_count"]}/{corners["count"]} 個彎為右彎 → 左前胎偏熱（{tires["overall"]["lr_front_delta"]:+.1f}°C）屬賽道特性，**非調校問題**',
                "tuning": [], "driving": [],
            })

        # Slow throttle reopen → driver too cautious on exit (only flag when meaningful)
        delay = corners.get("avg_throttle_reopen_delay_s")
        if delay is not None and delay > 1.0 and corners["corners_with_lift"] >= 3:
            findings.append({
                "severity": "🟡",
                "title": f'有收油的 {corners["corners_with_lift"]} 個彎中，平均出彎油門重踩要 {delay:.2f}s → 出彎略保守',
                "tuning": [],
                "driving": [f'彎心後早 0.2-0.3s 把油門踩回去（目前 {delay:.2f}s → ~{max(0.3, delay - 0.3):.2f}s）'],
            })

        # Many corners showing wheelspin on exit
        if corners["wheelspin_exit_corners"] > corners["count"] * 0.3:
            pct = corners["wheelspin_exit_corners"] / corners["count"] * 100
            # RWD: power oversteer prescriptions; AWD: forward power split + diff;
            # FWD: rear wheelspin is rare and usually a symptom not root cause.
            if drivetrain_type == 1:
                tuning = ['後差加速鎖定降 5-10%', '軟後防傾桿 1 級', '降後胎壓 1 psi']
            elif drivetrain_type == 2:
                tuning = ['後差加速鎖定降 5-10%', '動力分配往前移 5-10%']
            else:
                tuning = ['降後胎壓 1 psi']
            findings.append({
                "severity": "🟡",
                "title": f'{corners["wheelspin_exit_corners"]}/{corners["count"]} 個彎（{pct:.0f}%）出彎時後輪打滑 → 出彎給油過猛 / 差速器過硬',
                "tuning": tuning,
                "driving": ['出彎油門更線性，前 0.5s 控制在 70% 不要全踩'],
            })

        # Per-corner understeer/oversteer prevalence
        if corners["understeering_corners"] > corners["count"] * 0.5:
            pct = corners["understeering_corners"] / corners["count"] * 100
            findings.append({
                "severity": "🟡",
                "title": f'{corners["understeering_corners"]}/{corners["count"]} 個彎（{pct:.0f}%）前輪滑移 > 後輪 1.5×（**彎中**推頭）',
                "tuning": [],  # 與整體推頭處方重複
                "driving": [],
            })

    # Crash episodes
    if crash_count > 0:
        excluded_s = len(crash_excluded) / 60
        if crash_count > 2:
            findings.append({
                "severity": "🟡",
                "title": f'撞車 {crash_count} 次（共 {len(crash_excluded)} packet ≈ {excluded_s:.1f}s 從統計排除）→ 撞太多了',
                "tuning": [],
                "driving": ['撞車多半是入彎太用力、路線太靠外側、或不熟賽道。先放慢 5-10 km/h 練線，熟了再加速'],
            })
        else:
            findings.append({
                "severity": "ℹ️",
                "title": f'撞車 {crash_count} 次（共 {len(crash_excluded)} packet ≈ {excluded_s:.1f}s 從統計排除，G-force / decel / 觸底已不含）',
                "tuning": [], "driving": [],
            })

    # Brake anomaly: pure diagnostic, no prescriptions.
    # Use speed-derived decel (decels list) as the "did player actually brake"
    # signal — it's more sensitive than the IMU AccelerationZ field which can
    # under-report on noisy single-packet samples.
    if inputs["brake_appears_disabled"]:
        inferred_decel_g = decels[0]["decel_g"] if decels else 0.0
        if inferred_decel_g > 1.0:
            findings.append({
                "severity": "⚠️",
                "title": f'Brake 欄位全 0，但實測最大減速 {inferred_decel_g:.2f}G（速度反推）→ FH5 Data Out 異常，煞車輸入分析不可信',
                "tuning": [], "driving": [],
            })
        else:
            findings.append({
                "severity": "ℹ️",
                "title": 'Brake 欄位全 0 且無明顯減速 → 可能本場真的沒煞車，或 Brake 輸入未傳送',
                "tuning": [], "driving": [],
            })

    # === Build markdown ===
    o = []
    o.append('# 賽事摘要')
    o.append('')
    crash_note = f'，{len(crash_excluded)} 撞車' if crash_count > 0 else ''
    o.append(f'> 自動產生於 raw.csv ({len(rows)} 筆 → {len(valid)} 有效；排除 {len(rows) - len(pre_crash_valid)} IsRaceOn=0/rewind{crash_note}）。資料源：[meta.json](meta.json) / [raw.csv](raw.csv)')
    o.append('')

    # --- Headline ---
    o.append('## TL;DR')
    o.append('')
    if findings:
        # --- Symptom list ---
        o.append('### 症狀')
        o.append('')
        for f_ in findings:
            o.append(f'- {f_["severity"]} {f_["title"]}')
        o.append('')

        # --- Aggregate prescriptions across all findings, deduplicated, severity-ordered ---
        sev_order = {"⛔": 0, "🔴": 1, "🟡": 2, "⚠️": 3, "ℹ️": 4}
        sorted_findings = sorted(findings, key=lambda f_: sev_order.get(f_["severity"], 9))

        seen_canon: set[str] = set()
        seen_groups: set[str] = set()
        tuning_actions: list[tuple[str, str]] = []  # (action, source title)
        for f_ in sorted_findings:
            # Defense in depth: even if a finding accidentally lists an
            # action that's incompatible with this drivetrain (e.g., RWD getting
            # 「動力分配往前移」), the guard drops it here.
            for action in _filter_actions_by_drivetrain(f_.get("tuning", []), drivetrain_type):
                canon = _canonical_action_key(action)
                # Dedup：相同語義（含括號補充差異）只保留首次。
                if canon in seen_canon:
                    continue
                # 衝突仲裁：同 _CONFLICT_GROUPS 組內最多一條，依 severity 先到先得。
                # 例：推頭主症狀（⛔）已加「動力分配往後移」，後輪打滑（🟡）的
                # 「動力分配往前移」會被跳過，避免 TL;DR 印出互斥處方。
                group = _CONFLICT_GROUPS.get(canon)
                if group and group in seen_groups:
                    continue
                tuning_actions.append((action, f_["title"]))
                seen_canon.add(canon)
                if group:
                    seen_groups.add(group)

        seen_d: set[str] = set()
        driving_actions: list[tuple[str, str]] = []
        for f_ in sorted_findings:
            for action in f_.get("driving", []):
                if action not in seen_d:
                    driving_actions.append((action, f_["title"]))
                    seen_d.add(action)

        if tuning_actions:
            o.append('### 🔧 調校建議（去 Garage 改，**一次只動一個**）')
            o.append('')
            for i, (action, source) in enumerate(tuning_actions, 1):
                o.append(f'{i}. {action}')
            o.append('')

        if driving_actions:
            o.append('### 🎮 駕駛建議（不需改車，下次直接試）')
            o.append('')
            for i, (action, source) in enumerate(driving_actions, 1):
                o.append(f'{i}. {action}')
            o.append('')

        if not tuning_actions and not driving_actions:
            o.append('（本場主要為資料異常或診斷項目，沒有對應的調校/駕駛處方）')
            o.append('')
    else:
        o.append('✅ 沒有偵測到明顯異常，這場開得相當乾淨。')
        o.append('')

    # --- Basic ---
    o.append('## 基本資訊')
    o.append('')
    o.append('| 項目 | 數值 |')
    o.append('|------|------|')
    o.append(f'| 賽事類型 | **{event_type}**（{"多圈" if is_lapped else "單趟（衝刺/街頭/直線）"}） |')
    o.append(f'| 開始時間 | {meta["started_at"]} |')
    o.append(f'| 持續時間 | {meta["duration_seconds"]:.1f} 秒 |')
    o.append(f'| 車輛 ordinal | {meta["car"]["ordinal"]} (PI {meta["car"]["performance_index"]}, class {meta["car"]["class"]}) |')
    o.append(f'| 傳動 | {drivetrain_name} |')
    o.append(f'| 引擎 | {meta["car"]["num_cylinders"]} 缸，紅線 {drvtrn["engine_max"]:.0f} RPM |')
    if is_lapped:
        o.append(f'| 完成圈數 | {meta["race"]["total_laps"]} |')
        o.append(f'| 最佳圈速 | **{meta["race"]["best_lap_seconds"]:.3f}s** |')
        o.append(f'| 最後圈速 | {meta["race"]["last_lap_seconds"]:.3f}s |')
    else:
        total_dist = integrate_distance([F(r, 'Speed') for r in valid])
        o.append(f'| 總距離 | {total_dist:.0f} m |')
        o.append(f'| 持續秒數 | {len(valid) / 60:.2f}s |')
    o.append(f'| Rewinds | {meta["rewinds"]["count"]} 次（共 {meta["rewinds"]["total_seconds_rewound"]:.1f}s） |')
    o.append(f'| 有效資料 | {len(valid)} / {len(rows)} 筆（排除 IsRaceOn=0 與 rewind 段） |')
    o.append('')

    # --- Per-segment overview ---
    o.append(f'## 進度分析（依{seg_word}）')
    o.append('')
    o.extend(fmt_segment_table_speed(segments))
    o.append('')

    # --- Headline findings detail ---
    o.append('## 主要調校線索')
    o.append('')

    # Tire detail
    if tires["overall"]:
        ovr = tires["overall"]
        o.append(f'### 1. 輪胎溫度分布')
        o.append('')
        skip_note = '（已排除 Lap 0 暖胎圈）' if tires["skipped_first_segment"] else ''
        o.append(f'排除暖胎後{skip_note}的平均：FL={ovr["fl"]:.0f}°C  FR={ovr["fr"]:.0f}°C  RL={ovr["rl"]:.0f}°C  RR={ovr["rr"]:.0f}°C')
        o.append('')
        o.append(f'- 前胎平均：**{ovr["front_avg"]:.0f}°C**')
        o.append(f'- 後胎平均：**{ovr["rear_avg"]:.0f}°C**')
        o.append(f'- 前後溫差：**{ovr["fr_delta"]:+.1f}°C**')
        o.append(f'- 左右前差：{ovr["lr_front_delta"]:+.1f}°C  /  左右後差：{ovr["lr_rear_delta"]:+.1f}°C')
        o.append(f'- 最熱角：**{tires["hottest_corner"].upper()}**（{ovr[tires["hottest_corner"]]:.0f}°C）')
        o.append('')
        o.append('**判讀指南**：')
        o.append('- 前後差 > +10°C → 推頭（understeer），考慮降前胎壓 / 軟前防傾 / 加前外傾')
        o.append('- 前後差 < -10°C → 轉向過度（oversteer），考慮降後胎壓 / 軟後防傾 / 加後外傾')
        o.append('- 左右差 > 5°C → 配重不平衡或單側過度負重，檢查彎道分布')
        o.append('- 單一角 > 200°C → 胎面熱衰退，需要更多冷卻（降胎壓 / 加 caster）')
        o.append('')
        o.append('每段詳細：')
        o.append('')
        o.extend(fmt_tire_table(tires))
        o.append('')

    # Slip detail
    o.append('### 2. 滑移分析（推頭 / 轉向過度）')
    o.append('')
    o.append('TireSlipRatio：縱向滑移（加速/煞車時輪轉速 vs 車速）。0 = 100% 抓地，>1.0 = 失抓。')
    o.append('TireSlipAngle：橫向滑移（過彎時輪指向 vs 實際前進方向）。')
    o.append('')
    o.extend(fmt_slip_table(slip))
    o.append('')
    o.append(f'**推頭瞬間**（前輪 slip angle > 1.5× 後輪）：共 {slip["understeer_count"]} 個 packet')
    if slip["understeer_top"]:
        o.append('')
        o.append('| 段 | 賽事時間 (s) | 前輪角 | 後輪角 | 速度 (km/h) |')
        o.append('|----|-------------|-------|-------|-------------|')
        for crt, label, fs, rs, kmh in slip["understeer_top"]:
            o.append(f'| {label} | {crt:.2f} | {fs:.2f} | {rs:.2f} | {kmh:.0f} |')
    o.append('')
    o.append(f'**轉向過度瞬間**（後輪 slip angle > 1.5× 前輪）：共 {slip["oversteer_count"]} 個 packet')
    if slip["oversteer_top"]:
        o.append('')
        o.append('| 段 | 賽事時間 (s) | 前輪角 | 後輪角 | 速度 (km/h) |')
        o.append('|----|-------------|-------|-------|-------------|')
        for crt, label, fs, rs, kmh in slip["oversteer_top"]:
            o.append(f'| {label} | {crt:.2f} | {fs:.2f} | {rs:.2f} | {kmh:.0f} |')
    o.append('')

    # Suspension detail
    o.append('### 3. 懸吊行程')
    o.append('')
    o.append('NormalizedSuspensionTravel：0 = 完全伸長，1.0 = 完全壓縮（觸底）。長期 0.7-0.85 是健康範圍。')
    o.append('')
    o.extend(fmt_suspension_table(susp))
    o.append('')
    if susp["total_bottom_packets"] > 0:
        o.append(f'**觸底總計**：{susp["total_bottom_packets"]} 個 packet ≈ {susp["total_bottom_packets"] / 60:.1f}s 觸底時間')
    o.append('')
    o.append('**判讀指南**：')
    o.append('- 任一輪持續 > 0.95 → 該角彈簧過軟或車高過低')
    o.append('- 平均 < 0.5 → 彈簧過硬，浪費抓地（行程沒用滿）')
    o.append('- 左右差距大 → 防傾桿 / 配重不平衡')
    o.append('- 前後差距大 → 配重偏前/後，考慮車高與彈簧比例')
    o.append('')

    # Drivetrain detail
    o.append('### 4. 引擎與換檔')
    o.append('')

    # --- RPM 觀測區塊 ---
    o.append('#### 4.1 觀測 RPM 統計')
    o.append('')
    o.append(f'- EngineMaxRpm（UDP 回傳）：**{rpm_obs["engine_max"]:.0f} RPM** — 這是**硬限速 (rev limiter)**，不一定等於儀表紅線')
    o.append(f'- 全場最高 RPM：**{rpm_obs["max"]:.0f}**')
    o.append(f'- p99 RPM：{rpm_obs["p99"]:.0f}')
    o.append(f'- p95 RPM：{rpm_obs["p95"]:.0f}')
    if rpm_obs["warn_hard_limiter"]:
        o.append('')
        o.append(f'> ⚠️ **觀測最高 RPM 比 EngineMaxRpm 低 {rpm_obs["headroom"]:.0f} RPM**：'
                 f'這代表 EngineMaxRpm 是引擎硬限速、不是儀表紅線。'
                 f'**實質紅線可能就在 max RPM 附近**（{rpm_obs["max"]:.0f} 上下），'
                 f'換檔目標應參考下面的「估算 dyno 曲線」之峰值馬力 RPM，而非 EngineMaxRpm × 95%。')
    o.append('')

    # --- Dyno 曲線區塊 ---
    o.append('#### 4.2 估算 dyno 曲線')
    o.append('')
    if dyno is None:
        # graceful fallback：缺欄位或樣本不足
        sample = valid[0] if valid else {}
        if 'Power' not in sample or 'Torque' not in sample:
            o.append('> ⚠️ 此 raw.csv 缺 `Power` / `Torque` 欄位（舊版錄製）。**需用更新後的 recorder.py 重新錄製此場才能算 dyno**。本場以 EngineMaxRpm × 95% 當換檔基準（可能不準）。')
        else:
            o.append('> ⚠️ Power/Torque 樣本不足以分箱（樣本可能太少或玩家全程低油門）。本場以 EngineMaxRpm × 95% 當換檔基準。')
        o.append('')
    else:
        o.append(f'從 (RPM, Power) 樣本依 200 RPM 分箱取中位數，估算本車真實馬力曲線：')
        o.append('')
        o.append(f'- **峰值馬力 RPM**：**{dyno["peak_power_rpm"]:.0f}**（峰值 power = {dyno["peak_power"]:.0f}）')
        o.append(f'- **峰值扭矩 RPM**：**{dyno["peak_torque_rpm"]:.0f}**（峰值 torque = {dyno["peak_torque"]:.0f} Nm）')
        o.append(f'- **理想換檔點 = 峰值馬力 RPM = {dyno["peak_power_rpm"]:.0f}**（純物理推導，不靠 95% 紅線經驗法則）')
        o.append('')
        # 每 1000 RPM 一行的精簡表（找最接近的 200-bucket）
        o.append('馬力曲線（每 1000 RPM 取最接近的 200-bucket 中位數）：')
        o.append('')
        o.append('| RPM | Power (中位數) | Torque (中位數, Nm) | 樣本數 |')
        o.append('|-----|----------------|---------------------|--------|')
        bucket_by_mid = {b["rpm_mid"]: b for b in dyno["buckets"]}
        # 找出 1000-step 的代表 RPM（取 1000、2000、… 最接近的桶）
        if dyno["buckets"]:
            min_b = dyno["buckets"][0]["rpm_mid"]
            max_b = dyno["buckets"][-1]["rpm_mid"]
            target_rpms = list(range(((min_b // 1000) + 1) * 1000,
                                     (max_b // 1000 + 1) * 1000 + 1, 1000))
            for tgt in target_rpms:
                # 找最近的 bucket
                closest = min(dyno["buckets"], key=lambda b: abs(b["rpm_mid"] - tgt))
                if abs(closest["rpm_mid"] - tgt) <= 200:
                    bold = '**' if closest["rpm_mid"] == dyno["peak_power_rpm"] else ''
                    o.append(f'| {tgt} | {bold}{closest["power_med"]:.0f}{bold} | '
                             f'{closest["torque_med"]:.0f} | {closest["n"]} |')
        o.append('')
        o.append('（粗體 = 峰值馬力所在桶。若峰值在兩 1000-step 之間，請看上方「峰值馬力 RPM」精確值。）')
        o.append('')

    # --- 換檔分析 ---
    o.append('#### 4.3 換檔分析')
    o.append('')
    basis_label = ('峰值馬力 RPM' if drvtrn["ideal_shift_basis"] == "peak_power_rpm"
                   else 'EngineMaxRpm × 95%')
    o.append(f'引擎硬限速 **{drvtrn["engine_max"]:.0f} RPM**，'
             f'理想換檔點 ≈ **{drvtrn["ideal_shift"]:.0f} RPM**（基準：{basis_label}）。')
    band_basis_label = ('Power ≥ 峰值馬力 90%' if drvtrn["power_band_basis"] == "power>=90%_peak"
                        else 'RPM ≥ 80% 紅線（fallback）')
    o.append(f'動力區範圍：{drvtrn["power_band_start"]:.0f}–{drvtrn["power_band_end"]:.0f} RPM（基準：{band_basis_label}）')
    o.append('')
    o.append(f'- 平均換檔點：**{drvtrn["avg_shift_rpm"]:.0f} RPM**（距理想 {drvtrn["shift_loss_rpm"]:+.0f}）')
    o.append(f'- 全程在動力區的時間：**{drvtrn["in_power_band_pct"]:.1f}%**')
    o.append(f'- 全程在 ≥ 理想換檔點的時間：{drvtrn["in_redline_pct"]:.1f}%')
    o.append(f'- 全程曾達到的最高 RPM：{drvtrn["max_rpm_seen"]:.0f}（{drvtrn["max_rpm_seen"] / drvtrn["engine_max"] * 100:.1f}% EngineMaxRpm）')
    o.append('')
    if drvtrn["shift_points"]:
        o.append('每檔換檔詳細：')
        o.append('')
        o.append('| 換檔 | 平均 RPM | 距理想 | 次數 |')
        o.append('|------|---------|-------|------|')
        for (g_from, g_to), pts in sorted(drvtrn["shift_points"].items()):
            avg = statistics.mean(pts)
            o.append(f'| {g_from}→{g_to} | {avg:.0f} | {drvtrn["ideal_shift"] - avg:+.0f} | {len(pts)} |')
        o.append('')
    o.append('每檔停留時間：')
    o.append('')
    o.append('| 檔位 | 時間佔比 |')
    o.append('|------|---------|')
    for g, pct in drvtrn["gear_distribution"].items():
        o.append(f'| {g} | {pct:.1f}% |')
    o.append('')
    o.append('**判讀指南**：')
    o.append('- 換檔點離理想 < 200 RPM：很好')
    o.append('- 換檔點低於理想 > 500 RPM：太早，丟動力（手排晚一點換、自排調整齒比）')
    o.append('- 換檔點**高於**理想 > 200 RPM：可能換檔太晚，過了功率帶反而失動力——縮短該檔齒比')
    o.append('- 在動力區時間 < 50%：齒比可能太密或太疏，沒讓引擎在甜蜜點工作')
    o.append('- 某檔位佔比異常低：可能可以略過該檔（常見於 6 檔車的 5 檔）')
    o.append('')

    # Inputs
    o.append('### 5. 駕駛輸入')
    o.append('')
    o.append('| 指標 | 數值 |')
    o.append('|------|------|')
    o.append(f'| 油門全開（≥250/255） | **{inputs["throttle_full_pct"]:.1f}%** |')
    o.append(f'| 油門中段（50-249） | {inputs["throttle_mid_pct"]:.1f}% |')
    o.append(f'| 油門收（<50） | {inputs["throttle_off_pct"]:.1f}% |')
    o.append(f'| 油門平均 | {inputs["throttle_avg"]:.0f}/255 |')
    o.append(f'| 煞車最大 | {inputs["brake_max"]}/255 |')
    o.append(f'| 煞車平均 | {inputs["brake_avg"]:.1f}/255 |')
    o.append(f'| 全煞車（≥250） | {inputs["brake_full_pct"]:.1f}% |')
    o.append(f'| Trail braking（油門 + 煞車同時 >50） | {inputs["trail_brake_pct"]:.1f}% |')
    o.append(f'| 滑行（油門/煞車都 <5） | {inputs["coast_pct"]:.1f}% |')
    o.append(f'| 轉向最大 | ±{inputs["steer_max"]}/127 |')
    o.append(f'| 轉向平均（絕對值） | {inputs["steer_avg_abs"]:.1f}/127 |')
    pin_thr = inputs["steer_pin_threshold"]
    o.append(f'| 方向打死次數（\\|Steer\\| ≥ max×0.8 = {pin_thr:.0f} 持續 ≥ 0.5s） | {inputs["steer_pin_count"]} |')
    o.append(f'| 方向打死總時間 | {inputs["steer_pin_total_s"]:.2f}s |')
    o.append(f'| 最長一次方向打死 | {inputs["steer_pin_max_s"]:.2f}s |')
    hp_thr = inputs["hardpush_threshold"]
    o.append(f'| 前輪硬推次數（\\|Steer\\| ≥ max×0.6 = {hp_thr:.0f} + 前 slip > 1.0 持續 ≥ 0.3s） | {inputs["hardpush_count"]} |')
    o.append(f'| 前輪硬推總時間 | {inputs["hardpush_total_s"]:.2f}s |')
    o.append(f'| 最長一次前輪硬推 | {inputs["hardpush_max_s"]:.2f}s |')
    surge_total = inputs["throttle_surge_count"]
    surge_corner = inputs["throttle_surge_corner_count"]
    surge_straight = inputs["throttle_surge_straight_count"]
    o.append(f'| 油門急升次數（200ms 內 <50 → >200） | {surge_total}（彎中 {surge_corner} / 直線 {surge_straight}） |')
    o.append('')

    if inputs["steer_pin_top"]:
        o.append('**最長方向打死 top 3**：')
        o.append('')
        o.append('| 賽事時間 (s) | 持續秒數 | 平均速度 (km/h) | 平均前 slip |')
        o.append('|-------------|----------|----------------|-------------|')
        for e in inputs["steer_pin_top"]:
            o.append(f'| {e["t_start"]:.2f} | {e["dur_s"]:.2f} | {e["avg_kmh"]:.0f} | {e["avg_front_slip"]:.2f} |')
        o.append('')

    if inputs["hardpush_top"]:
        o.append('**最長前輪硬推 top 3**（方向 ≥ 60% max + 前 slip > 1.0）：')
        o.append('')
        o.append('| 賽事時間 (s) | 持續秒數 | 平均速度 (km/h) | 平均前 slip |')
        o.append('|-------------|----------|----------------|-------------|')
        for e in inputs["hardpush_top"]:
            o.append(f'| {e["t_start"]:.2f} | {e["dur_s"]:.2f} | {e["avg_kmh"]:.0f} | {e["avg_front_slip"]:.2f} |')
        o.append('')

    if inputs["throttle_surge_top"]:
        o.append('**油門急升 top 3**：')
        o.append('')
        o.append('| 賽事時間 (s) | 前 200ms 油門 | 後 200ms 油門 | 當時速度 (km/h) | 情境 |')
        o.append('|-------------|---------------|---------------|-----------------|------|')
        for e in inputs["throttle_surge_top"]:
            ctx_label = (f'⚠️ corner（latG={e["lat_g"]:.1f}）'
                         if e["context"] == "corner"
                         else f'straight（latG={e["lat_g"]:.1f}）')
            o.append(f'| {e["t_start"]:.2f} | {e["pre_throttle"]:.0f}/255 | {e["post_throttle"]:.0f}/255 | {e["kmh"]:.0f} | {ctx_label} |')
        o.append('')
        o.append('> **彎中急升次數**（|latG| ≥ 0.4）才是真駕駛問題；直線急升通常是重煞後重啟、合理。')
        o.append('')


    if inputs["brake_appears_disabled"]:
        if gforces["max_decel_g"] > 1.5:
            o.append(f'⚠️ **Brake 欄位全為 0，但實測最大減速 {gforces["max_decel_g"]:.2f}G**（玩家明顯有煞車）。')
            o.append('這是 **FH5 Data Out 已知不穩定行為**——同一玩家、同設備、同設定不同場可能正常或異常。')
            o.append('本場煞車相關分析（trail brake %、煞車節奏）**不可信**，建議改看下面「最大減速瞬間」用速度變化反推。')
        else:
            o.append('ℹ️ Brake 欄位全為 0 且無顯著減速事件——可能玩家本場真的沒怎麼煞車，或 Brake 輸入未傳送。')
        o.append('')
    o.append('**判讀指南**：')
    o.append('- 油門全開 > 95%：典型衝刺賽 / 直線多賽道；< 50% 表示彎多需精細調節')
    o.append('- Trail braking > 5%：你會帶煞車入彎（進階技巧），對 FF 車有助於前輪轉向')
    o.append('- 滑行 > 20%：可能煞車點太早 / 過彎太保守')
    o.append('- 轉向平均接近 0：路線直；偏大表示車不太聽話需要常修方向')
    o.append('- **方向打死總時間 > 5s 或最長 > 1s** → 駕駛在硬轉硬推、典型 understeer 駕駛模式（前輪已超過抓地極限，再轉也轉不進去）')
    o.append('- **前輪硬推次數 > 3 次或最長 > 0.8s** → 多次入彎方向打很大但沒打死 0.5s，已超過前輪抓地極限——這是「方向打死」漏掉的次嚴重訊號，動作上同樣需要早 0.3-0.5s 鬆方向／降一點入彎速度')
    o.append('- **彎中油門急升** =「車還在轉就突然全踩」典型錯誤；AWD 容易引發動力推頭（前輪扭力把車拉出彎外），RWD 引發 power oversteer。出彎油門應該是平滑爬升，不是 0/255 開關')
    o.append('')

    # G-force + decel events
    o.append('### 6. G-force 與減速事件')
    o.append('')
    # Dual values: "with crash" = raw IMU max (includes wall-impact spikes);
    # "clean" = same set with crash windows excluded → represents the car's
    # real grip / brake capability, which is what調校 should be designed for.
    o.append(f'- 最大側向 G（含撞車）：**{gforces["max_lateral_g_with_crash"]:.2f}**')
    o.append(f'- 最大側向 G（排除撞車）：**{gforces["max_lateral_g_clean"]:.2f}**（FH5 黏胎極限約 2-3 G）')
    o.append(f'- 最大減速 G（含撞車）：**{gforces["max_decel_g_with_crash"]:.2f}**')
    o.append(f'- 最大減速 G（排除撞車）：**{gforces["max_decel_g_clean"]:.2f}**（反推自速度變化）')
    o.append(f'- 最大加速 G：{gforces["max_accel_g"]:.2f}')
    o.append(f'- 平均側向 G：{gforces["avg_lateral_g"]:.2f}')
    o.append('')
    if (gforces["max_decel_g_with_crash"] - gforces["max_decel_g_clean"] > 0.5
        or gforces["max_lateral_g_with_crash"] - gforces["max_lateral_g_clean"] > 0.5):
        o.append('> 「含撞車」是資料中的最高瞬間（含撞牆 IMU 尖峰）；「排除撞車」才是車的真實能力——調校與駕駛建議應以「排除撞車」值為準。')
        o.append('')
    o.append('**最大減速瞬間 top 8**（推測重煞車點，每筆抽 5 packet ≈ 83ms 視窗）：')
    o.append('')
    o.append('| 段 | 賽事時間 (s) | 減速 G | 速度變化 (km/h) |')
    o.append('|----|-------------|--------|-----------------|')
    for ev in decels[:8]:
        o.append(f'| Lap {ev["lap"]} | {ev["crt"]:.2f} | {ev["decel_g"]:.2f} | {ev["from_kmh"]:.0f}→{ev["to_kmh"]:.0f} |')
    o.append('')

    # Speed profile
    o.append('### 7. 速度與表面')
    o.append('')
    o.append(f'- 最高速：{speed["max_kmh"]:.1f} km/h')
    o.append(f'- 平均速度：{speed["avg_kmh"]:.1f} km/h')
    o.append(f'- 移動中最低速：{speed["min_kmh_in_motion"]:.1f} km/h（最慢彎的彎心速度估計）')
    o.append(f'- 速度標準差：{speed["stdev_kmh"]:.1f} km/h（變化幅度）')
    o.append(f'- Rumble strip 接觸：{surf["rumble_strip_seconds"]:.1f}s（壓 curb 時間）')
    o.append(f'- 最深水深：{surf["max_puddle_depth"]:.2f}（0=乾，1=最深）')
    o.append('')

    # === Section 8: Cornering ===
    o.append('### 8. 過彎分析')
    o.append('')
    if corners["count"] == 0:
        o.append('（沒偵測到明顯彎道——可能是直線/Drag 賽，或本場速度不足以觸發 0.4G 側向力門檻）')
        o.append('')
    else:
        filter_note = ''
        if corners.get("filtered_sweeper_count", 0) > 0 or corners.get("filtered_stop_count", 0) > 0:
            parts = []
            if corners["filtered_sweeper_count"] > 0:
                parts.append(f'{corners["filtered_sweeper_count"]} 個高速 sweeper（半徑 > {CORNER_MAX_RADIUS_M}m）')
            if corners["filtered_stop_count"] > 0:
                parts.append(f'{corners["filtered_stop_count"]} 個停車/撞車事件')
            filter_note = f'（原始候選 {corners["raw_count"]} 個，已過濾 {" + ".join(parts)}）'
        o.append(f'**偵測到 {corners["count"]} 個彎道**{filter_note}（側向 G > {CORNER_ENTER_G} 持續 ≥ {CORNER_MIN_PACKETS / 60:.2f}s），總過彎時間 **{corners["total_corner_time_s"]:.1f}s（{corners["corner_time_pct"]:.0f}%）**')
        o.append('')
        bias_label = {"left": "🔄 左偏（順時針賽道）", "right": "🔄 右偏（逆時針賽道）",
                     "balanced": "⚖️ 左右平衡", "unknown": "—"}[corners["track_bias"]]
        o.append(f'- 左/右彎：**{corners["left_count"]} L / {corners["right_count"]} R**  →  {bias_label}')
        o.append(f'- 彎中峰值側向 G：平均 {corners["avg_peak_g"]:.2f}，最大 {corners["max_peak_g"]:.2f}')
        o.append(f'- 入彎速度損失：平均 {corners["avg_speed_drop"]:.1f} km/h，最大 {corners["max_speed_drop"]:.1f} km/h')
        o.append(f'- 平均彎心速度：{corners["avg_apex_kmh"]:.1f} km/h')
        # Throttle behavior — show min throttle (always meaningful) and reopen delay (only if user lifts)
        o.append(f'- 彎中油門：平均最低 **{corners["avg_throttle_min"]:.0f}/255**，平均整段 {corners["avg_throttle_avg"]:.0f}/255')
        delay = corners.get("avg_throttle_reopen_delay_s")
        if delay is not None and corners["corners_with_lift"] >= 3:
            o.append(f'- 出彎油門重踩時機：彎心後平均 **{delay:.2f}s**（{corners["corners_with_lift"]}/{corners["count"]} 個彎有明顯收油時才計算）')
        elif corners["corners_with_lift"] < 3:
            o.append(f'- 出彎油門重踩時機：N/A（**{corners["count"] - corners["corners_with_lift"]}/{corners["count"]} 個彎全程沒收油到 100 以下**——典型衝刺/全油門風格）')
        o.append('')
        o.append('**彎中操控分布**（衡量「車聽不聽你話」）：')
        o.append('')
        o.append(f'- 整段推頭主導彎（per-corner 平均：前輪滑移 > 後輪 1.5×）：**{corners["understeering_corners"]}/{corners["count"]}**（{corners["understeering_corners"]/corners["count"]*100:.0f}%）')
        o.append(f'- 整段過度主導彎（per-corner 平均：後輪滑移 > 前輪 1.5×）：**{corners["oversteering_corners"]}/{corners["count"]}**（{corners["oversteering_corners"]/corners["count"]*100:.0f}%）')
        o.append(f'- 出彎打滑彎（後輪 wheelspin > 5 packet）：**{corners["wheelspin_exit_corners"]}/{corners["count"]}**（{corners["wheelspin_exit_corners"]/corners["count"]*100:.0f}%）')
        o.append('')
        # 新指標：per-packet 時間佔比（更接近體感，避免「entry 推頭+apex 中性+exit 推頭」被平均成中性）
        if corners.get("total_in_corner_packets", 0) > 0:
            us_pct = corners.get("understeer_time_pct", 0.0)
            os_pct = corners.get("oversteer_time_pct", 0.0)
            o.append('**過彎時間中的 per-packet 推頭/過度時間佔比**（更接近體感；分母=所有彎內 packet 數 = '
                     f'{corners["total_in_corner_packets"]}）：')
            o.append('')
            o.append(f'- 推頭時間佔比：**{us_pct:.1f}%**（{corners["understeer_packets_in_corners"]} packet）')
            o.append(f'- 轉向過度時間佔比：**{os_pct:.1f}%**（{corners["oversteer_packets_in_corners"]} packet）')
            o.append('')
        o.append('**判讀指南**：')
        o.append('')
        o.append('- **賽道 L/R 偏向**會直接影響輪胎溫度對稱性。左偏賽道 → 右前胎多承受外彎負荷 → 偏熱屬正常；想分辨「賽道特性」vs「真實調校問題」必須先看 L/R 比例')
        o.append('- **平均速度損失** 5-15 km/h 為合理範圍；若 > 25 km/h 可能入彎太用力 / 煞車點太晚 / 彎角太銳')
        o.append('- **出彎油門全開時機** < 0.5s 屬積極駕駛、 > 1s 屬保守；> 1.5s 通常是出彎抓地不足或心理保守')
        o.append('- **過彎時間中推頭時間佔比 > 25% → 整體推頭傾向**（這是真實體感的指標）；同時看「整段推頭主導彎」數量是否集中在某幾彎或散布全程：散布全程→車的天然取向，集中→特定彎的線路/煞車點問題')
        o.append('- **「整段推頭主導彎」少（如 5/26）但「推頭時間佔比」高（如 30%）** → 推頭發生在每個彎的特定 phase（通常是 entry/exit），而非整段——這仍是調校問題，但同時要看駕駛輸入')
        o.append('- **出彎打滑彎比例** > 30% → 差速器過硬 / 動力分配偏後 / 出彎習慣過猛（任三選一）')
        o.append('')
        # Top 3 heaviest brake corners (notable but not exhaustive listing)
        if corners["count"] >= 3:
            heavy = sorted(corners["corners"], key=lambda c: -c["speed_drop_kmh"])[:3]
            o.append('**最重煞車的 3 個彎**（速度損失排序）：')
            o.append('')
            o.append('| 圈 | 方向 | 入彎 km/h | 彎心 km/h | 速度損失 | Peak G |')
            o.append('|----|------|----------|----------|----------|--------|')
            for c in heavy:
                o.append(f'| {c["lap"]} | {c["direction"]} | {c["approach_kmh"]:.0f} | {c["apex_kmh"]:.0f} | {c["speed_drop_kmh"]:.0f} | {c["peak_g"]:+.2f} |')
            o.append('')
            o.append('> 這 3 個彎的逐幀輸入分析（煞車/油門/方向/檔位/slip）見同層 [corners_detail.md](corners_detail.md)。')
            o.append('')

    # Anomalies
    o.append('## 異常事件')
    o.append('')
    if meta["rewinds"]["count"] > 0:
        o.append(f'- ✅ Rewind {meta["rewinds"]["count"]} 次，共 {meta["rewinds"]["total_seconds_rewound"]:.2f}s（已從統計中排除）')
    if crash_count > 0:
        o.append(f'- ⚠️ 撞車 {crash_count} 次，共 {len(crash_excluded)} packet ≈ {len(crash_excluded) / 60:.1f}s（已從 G-force / decel / 觸底 / 滑移統計中排除）')
    if susp["total_bottom_packets"] > 0:
        o.append(f'- ⚠️ 懸吊觸底 {susp["total_bottom_packets"]} 個 packet（>0.95 normalized travel；已排除撞車）')
    if wheelspin_pkts > 50:
        o.append(f'- ⚠️ 後輪嚴重打滑 {wheelspin_pkts} 個 packet ≈ {wheelspin_pkts / 60:.1f}s（slip ratio > 1.0；已排除撞車）')
        # Phase break-down: distinguishes straight-line traction loss (often
        # normal — TC turned off, monster torque) from corner phases that
        # signal genuine handling problems. RWD's exit-phase wheelspin is the
        # signature of power oversteer.
        ws = wheelspin_phases
        if ws["total"] > 0:
            def _line(label: str, pkts: int, hint: str) -> str:
                pad = ' ' * (8 - len(label))
                return f'  - {label}:{pad}{pkts} packets ≈ {pkts / 60:.1f}s{hint}'
            o.append(_line('straight', ws["straight"], '（直線加速打滑——通常 normal）'))
            o.append(_line('entry',    ws["entry"],    '（lift-off oversteer 嫌疑）'))
            o.append(_line('apex',     ws["apex"],     ''))
            exit_hint = '（power oversteer 嫌疑——RWD 主問題）' if drivetrain_type == 1 else '（出彎給油過猛嫌疑）'
            o.append(_line('exit',     ws["exit"],     exit_hint))
            # Inline guidance for the reader
            total = ws["total"]
            if total > 0:
                exit_pct = ws["exit"] / total * 100
                entry_pct = ws["entry"] / total * 100
                hints = []
                if exit_pct > 30:
                    hints.append(f'**exit > 30%**（實際 {exit_pct:.0f}%）：'
                                 + ('RWD 出彎 power oversteer 是主問題' if drivetrain_type == 1
                                    else '出彎給油過猛或差速器過硬'))
                if entry_pct > 20:
                    hints.append(f'**entry > 20%**（實際 {entry_pct:.0f}%）：lift-off oversteer 嫌疑')
                for h in hints:
                    o.append(f'  - 判讀：{h}')
    if not (meta["rewinds"]["count"] or crash_count or susp["total_bottom_packets"] or wheelspin_pkts > 50):
        o.append('- ✅ 沒有偵測到顯著異常事件')
    o.append('')

    # LLM context block
    o.append('---')
    o.append('')
    o.append('## 給分析師（forza-race-analyst skill）的精煉 context')
    o.append('')
    o.append('```')
    o.append(f'event_type    : {event_type}')
    o.append(f'car           : ordinal={meta["car"]["ordinal"]} PI={meta["car"]["performance_index"]} class={meta["car"]["class"]} drivetrain={drivetrain_name} cyl={meta["car"]["num_cylinders"]}')
    if is_lapped:
        o.append(f'race          : {meta["race"]["total_laps"]} laps, best={meta["race"]["best_lap_seconds"]:.3f}s, last={meta["race"]["last_lap_seconds"]:.3f}s')
        lap_times = [F(p[-1], "LastLap") for lap, p in segments[0:0]]  # placeholder
        lap_times = [seg.completed_lap_time for seg in segments if seg.completed_lap_time > 0]
        o.append(f'lap_times     : {[f"{t:.3f}" for t in lap_times]}')
    else:
        o.append(f'duration      : {meta["duration_seconds"]:.1f}s, total_distance ≈ {integrate_distance([F(r, "Speed") for r in valid]):.0f}m')
    o.append('')
    o.append('symptoms:')
    if tires["overall"]:
        o.append(f'  tire_temps  : FL={tires["overall"]["fl"]:.0f} FR={tires["overall"]["fr"]:.0f} RL={tires["overall"]["rl"]:.0f} RR={tires["overall"]["rr"]:.0f} (front-rear delta {tires["overall"]["fr_delta"]:+.1f}°C)')
    if slip["per_segment"]:
        ratios = [r["fr_max"] / r["rr_max"] for r in slip["per_segment"] if r["rr_max"] > 0]
        if ratios:
            o.append(f'  slip_ratio  : front_max ≈ {statistics.mean([r["fr_max"] for r in slip["per_segment"]]):.3f}, rear_max ≈ {statistics.mean([r["rr_max"] for r in slip["per_segment"]]):.3f} (front/rear ≈ {statistics.mean(ratios):.2f}x)')
    o.append(f'  understeer_moments: {slip["understeer_count"]}, oversteer_moments: {slip["oversteer_count"]}')
    o.append(f'  suspension  : bottom_count={susp["total_bottom_packets"]}, max_per_corner=FL/{max(r["fl_max"] for r in susp["per_segment"]):.2f} FR/{max(r["fr_max"] for r in susp["per_segment"]):.2f} RL/{max(r["rl_max"] for r in susp["per_segment"]):.2f} RR/{max(r["rr_max"] for r in susp["per_segment"]):.2f}')
    if dyno is not None:
        o.append(f'  dyno        : peak_power_rpm={dyno["peak_power_rpm"]:.0f} (peak_power={dyno["peak_power"]:.0f}), peak_torque_rpm={dyno["peak_torque_rpm"]:.0f}')
    else:
        o.append('  dyno        : not_available (raw.csv lacks Power/Torque or insufficient samples)')
    o.append(f'  rpm_observed: max={rpm_obs["max"]:.0f}, p99={rpm_obs["p99"]:.0f}, p95={rpm_obs["p95"]:.0f}, engine_max={rpm_obs["engine_max"]:.0f}'
             + (' [hard_limiter≠redline]' if rpm_obs["warn_hard_limiter"] else ''))
    o.append(f'  drivetrain  : avg_shift={drvtrn["avg_shift_rpm"]:.0f} RPM (ideal {drvtrn["ideal_shift"]:.0f} basis={drvtrn["ideal_shift_basis"]}, loss {drvtrn["shift_loss_rpm"]:+.0f}), in_power_band={drvtrn["in_power_band_pct"]:.0f}% basis={drvtrn["power_band_basis"]}')
    o.append(f'  inputs      : throttle_full={inputs["throttle_full_pct"]:.0f}%, brake_max={inputs["brake_max"]}/255 {"(BRAKING_ASSIST?)" if inputs["brake_appears_disabled"] else ""}, trail_brake={inputs["trail_brake_pct"]:.1f}%, coast={inputs["coast_pct"]:.1f}%')
    o.append(f'  g_force     : lat_max={gforces["max_lateral_g_clean"]:.2f} (with_crash={gforces["max_lateral_g_with_crash"]:.2f}), '
             f'decel_max={gforces["max_decel_g_clean"]:.2f} (with_crash={gforces["max_decel_g_with_crash"]:.2f}), '
             f'accel_max={gforces["max_accel_g"]:.2f}')
    o.append(f'  surface     : rumble_strip={surf["rumble_strip_seconds"]:.1f}s, max_puddle={surf["max_puddle_depth"]:.2f}')
    o.append(f'  wheelspin   : {wheelspin_pkts} packets >1.0 slip (post-crash-filter); '
             f'phase straight/entry/apex/exit = '
             f'{wheelspin_phases["straight"]}/{wheelspin_phases["entry"]}/'
             f'{wheelspin_phases["apex"]}/{wheelspin_phases["exit"]}')
    o.append(f'  surge_split : total={inputs["throttle_surge_count"]} '
             f'(corner={inputs["throttle_surge_corner_count"]}, '
             f'straight={inputs["throttle_surge_straight_count"]})')
    o.append(f'  crashes     : count={crash_count}, excluded_packets={len(crash_excluded)}')
    if corners["count"] > 0:
        delay_str = f'{corners["avg_throttle_reopen_delay_s"]:.2f}s' if corners.get("avg_throttle_reopen_delay_s") is not None else "n/a (no lift)"
        o.append(f'  cornering   : count={corners["count"]} ({corners["left_count"]}L/{corners["right_count"]}R bias={corners["track_bias"]}), '
                f'time_pct={corners["corner_time_pct"]:.0f}%, avg_peak_g={corners["avg_peak_g"]:.2f}, '
                f'avg_speed_drop={corners["avg_speed_drop"]:.0f}km/h')
        o.append(f'                throttle_min_avg={corners["avg_throttle_min"]:.0f}/255, '
                f'corners_with_lift={corners["corners_with_lift"]}/{corners["count"]}, '
                f'avg_reopen_delay={delay_str}')
        o.append(f'                understeering_corners={corners["understeering_corners"]}/{corners["count"]}, '
                f'oversteering_corners={corners["oversteering_corners"]}/{corners["count"]}, '
                f'wheelspin_exit_corners={corners["wheelspin_exit_corners"]}/{corners["count"]}')
    o.append('```')
    o.append('')

    summary_md = '\n'.join(o) + '\n'
    corners_detail_md = generate_corners_detail(valid, corners)
    return summary_md, corners_detail_md


# ----- CLI -------------------------------------------------------------------

def find_session(arg: str | None, root: Path) -> Path:
    """Resolve session path. None → most recent."""
    if arg:
        p = Path(arg)
        if p.is_dir():
            return p
        # Try as a name under root
        cand = root / arg
        if cand.is_dir():
            return cand
        raise SystemExit(f'session not found: {arg}')
    sessions = sorted([p for p in root.iterdir() if p.is_dir()
                      if (p / 'raw.csv').exists()],
                     key=lambda p: p.stat().st_mtime, reverse=True)
    if not sessions:
        raise SystemExit(f'no sessions in {root}')
    return sessions[0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog='python -m scripts.forza_telemetry.summarize',
        description='Generate summary.md for one or all telemetry sessions.')
    parser.add_argument('session', nargs='?', default=None,
                       help='session folder path or name (default: most recent)')
    parser.add_argument('--root', type=Path,
                       default=Path('data/forza_telemetry/sessions'),
                       help='sessions root directory')
    parser.add_argument('--all', action='store_true',
                       help='regenerate summary for every session')
    parser.add_argument('--output', default='summary.md',
                       help='output filename within the session folder')
    args = parser.parse_args(argv)

    if args.all:
        targets = [p for p in args.root.iterdir() if p.is_dir()
                  if (p / 'raw.csv').exists()]
    else:
        targets = [find_session(args.session, args.root)]

    for sess in targets:
        try:
            summary, corners_detail = build_report(sess)
            summary_path = sess / args.output
            summary_path.write_text(summary, encoding='utf-8')
            print(f'wrote {summary_path} ({len(summary.splitlines())} lines)')
            if corners_detail is not None:
                detail_path = sess / 'corners_detail.md'
                detail_path.write_text(corners_detail, encoding='utf-8')
                print(f'wrote {detail_path} ({len(corners_detail.splitlines())} lines)')
        except Exception as e:
            print(f'FAILED {sess}: {e}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
