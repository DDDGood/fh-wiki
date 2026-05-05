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
UNDERSTEER_RATIO = 1.5               # legacy slip-angle 法閾值；目前不使用，留作 fallback
DRIVETRAIN_NAMES = {0: "FWD", 1: "RWD", 2: "AWD"}

# === US/OS 偵測：yaw-rate 法（取代舊的 slip-angle ratio 法）===
# 業界標準（NHTSA、ESC 系統都用）：實際 yaw rate vs 物理預期 yaw rate
#   expected_yaw = lateral_acceleration / speed   （rad/s，純運動學公式）
# 與 PI 級／速度／車型無關，比舊的固定門檻更精準。
#
# **重要**：AngularVelocityY 才是 FH5 的 yaw rate（不是 Z）。實測 sustained turn
# 中 AngVel_Y 與 AccelerationX 同號率 99.7%、ratio 中位數 1.012；AngVel_Z 同號率
# 47% 是雜訊。Z 軸是 roll（繞前後軸的側翻）、X 軸是 pitch（繞左右軸的俯仰）。
YAW_DETECTION_LAT_G_MIN = 0.4        # 進彎門檻（同 CORNER_ENTER_G）
YAW_DETECTION_SPEED_MIN = 5.0        # m/s，避免低速分母過小
YAW_DETECTION_BRAKE_MAX = 200        # < 200 才判定（過濾「煞車中 US 是正常」）
# 嚴重度門檻（ratio = actual_yaw / expected_yaw）
# 實測 ratio 分布：median 1.035，p5-p95 = 0.50-1.67，所以這個範圍算「正常 transient」。
# severe 門檻設在 0.4 / 1.7（約 p3 / p97），確保只有真正脫節才觸發。
YAW_US_SEVERE = 0.4                  # ratio < 0.4 → ⛔ 嚴重 US（車完全轉不過）
YAW_US_MODERATE_ENTRY = 0.65         # entry phase 較寬鬆（turn-in transient）
YAW_US_MODERATE_MIDEXIT = 0.70       # mid/exit 較嚴
YAW_US_MILD = 0.82                   # ratio 0.82-1.20 視為平衡，外為 mild
YAW_OS_SEVERE = 1.7
YAW_OS_MODERATE_ENTRY = 1.40
YAW_OS_MODERATE_MIDEXIT = 1.35
YAW_OS_MILD = 1.20
# Slip-angle 確認信號（FH5 normalized slip：>1 = grip lost）
YAW_SLIP_CONFIRM_THRESHOLD = 0.7     # front/rear slip ≥ 0.7 表示胎接近 grip 極限

# 缺陷 11：依 PI 級的橫向 G 力達標基準（對照 [wiki/upgrades/輪胎配件.md]
# Mustuff124 提出的 build 健康度指標：選用適合的輪胎 + 減重等級，達到該 PI 級
# 應有的橫向 G 力。低於下限 → 升輪胎或減重，先不要急著升馬力）
PI_GRIP_TARGETS = [
    # (PI 上限, 級距標籤, G 下限, G 上限)
    (500,  "D",  None, None),  # D 級無 G 力基準（多數為慢車）
    (600,  "C",  None, None),
    (700,  "B",  1.3, 1.4),
    (800,  "A",  1.7, 1.9),
    (900,  "S1", 2.1, 2.3),
    (998,  "S2", 2.5, None),
    (999,  "X",  2.5, None),
]

# 缺陷 9：Launch 階段偵測（對應 [wiki/driving/RWD駕駛技巧.md] § Launch 找頂速法）
# 起步 = 從 IsRaceOn=1 後首個 speed > 5 km/h 的封包開始，到 distance 達 LAUNCH_DISTANCE_M 為止
LAUNCH_DISTANCE_M = 200              # 起步分析距離（前 200 m，多數車覆蓋 1-3 檔）
LAUNCH_SLIP_LOSS_THRESHOLD = 1.0     # 後輪 slip ratio > 1.0 = 抓地丟失
LAUNCH_GEAR3_SLIP_PCT = 0.30         # 三檔仍有 ≥ 30% packet 打滑 → 後胎抓地不夠

# 缺陷 10：Exit phase「彎太多 + 加油太早」（對應 [wiki/driving/賽車線與彎道基礎.md]
# 過 apex 後同時放鬆方向盤 + 加油 + 瞄外。常見錯：仍在大角度轉向就已踩半油以上）
EXIT_HARD_STEER_RATIO = 0.5          # |Steer| / steer_max 仍 > 50% → 仍在大角度轉向
EXIT_EARLY_THROTTLE = 128            # Accel >= 128 (半油以上) → 已進入加油
EXIT_OVERTURN_MIN_PACKETS = 8        # 同一彎此症狀 ≥ 8 packet ≈ 0.13s 才算問題彎
EXIT_OVERTURN_CORNER_PCT = 0.25      # session 內 ≥ 25% 彎為問題彎才觸發 finding

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


def _rolling_avg(vals: list[float], i: int, window: int = 3) -> float:
    """Centered rolling average，邊界用 clamp。用於平滑 yaw rate 等 transient 雜訊。"""
    half = window // 2
    lo, hi = max(0, i - half), min(len(vals), i + half + 1)
    return sum(vals[lo:hi]) / (hi - lo)


def _classify_yaw_balance(actual_yaw: float, lat_acc: float, speed: float,
                          brake: int, phase: str
                          ) -> tuple[str | None, str | None, float | None]:
    """缺陷 (新)：yaw-rate-based US/OS 判定。

    比較實際 yaw rate（AngularVelocityY，已平滑）與物理預期 yaw rate
    （= lateral_acc / speed，純運動學）。

    Args:
        actual_yaw: AngularVelocityY 平滑後的值（rad/s，signed）
        lat_acc: AccelerationX (m/s²，signed)
        speed: m/s（必須正）
        brake: Brake (0-255)
        phase: 'entry' | 'apex' | 'exit'

    Returns:
        (kind, severity, ratio) where:
            kind ∈ {'us', 'os', None}
            severity ∈ {'mild', 'moderate', 'severe', None}
            ratio = actual_yaw / expected_yaw（>0 才有意義）
        若 packet 不符判定條件（速度過低/G 過低/煞車中/異號）回 (None, None, None)。
    """
    # 過濾條件
    if speed < YAW_DETECTION_SPEED_MIN:
        return (None, None, None)
    if abs(lat_acc) < YAW_DETECTION_LAT_G_MIN * 9.81:
        return (None, None, None)
    if brake >= YAW_DETECTION_BRAKE_MAX:
        # 煞車中 US 是正常的（wiki/tuning/三段彎道診斷.md）
        return (None, None, None)
    # Sign 必須同號（正常過彎，不是反打/drift）
    if (lat_acc > 0) != (actual_yaw > 0):
        return (None, None, None)

    expected_yaw = lat_acc / speed
    if abs(expected_yaw) < 0.01:  # 太小的 expected 容易產生不穩定 ratio
        return (None, None, None)

    ratio = actual_yaw / expected_yaw  # 同號 → ratio > 0

    # phase-dependent moderate threshold
    us_moderate = YAW_US_MODERATE_ENTRY if phase == 'entry' else YAW_US_MODERATE_MIDEXIT
    os_moderate = YAW_OS_MODERATE_ENTRY if phase == 'entry' else YAW_OS_MODERATE_MIDEXIT

    if ratio < YAW_US_SEVERE:
        return ('us', 'severe', ratio)
    if ratio < us_moderate:
        return ('us', 'moderate', ratio)
    if ratio < YAW_US_MILD:
        return ('us', 'mild', ratio)
    if ratio > YAW_OS_SEVERE:
        return ('os', 'severe', ratio)
    if ratio > os_moderate:
        return ('os', 'moderate', ratio)
    if ratio > YAW_OS_MILD:
        return ('os', 'mild', ratio)
    return (None, None, ratio)  # balanced


def dedupe_attempts(rows: list) -> tuple[list, int]:
    """Rewind-aware filter：對每個 CRT 時刻只保留**錄製時間最晚**的 packet。

    過去的 `is_rewind=='0'` 過濾正好搞反——它**保留**了 rewind 前的失敗嘗試、
    **丟棄**了 redo 段（玩家最終選擇的線）。本函式用 CRT-bucket 取最晚 arrival
    一勞永逸：

    - 對每個 1/60 秒 CRT 桶（packet 級解析度），多個嘗試中只保留 arrival 最大者
    - 不論玩家在同一段 rewind 幾次（例：彎 X 倒轉 4 次直到第 5 次成功），最終
      只保留第 5 次成功的資料
    - 跨彎 rewind（例：玩家倒轉到彎 X 之後重做彎 Y）也自然處理——每個 CRT 桶
      獨立判定，沒被重做的段落維持原樣
    - 輸出依 CRT 排序，確保下游分析的「1 packet = 1/60s」假設仍成立

    僅處理 IsRaceOn=1 的 packet（rewind 動畫期 IsRaceOn=0 自動排除）。
    回傳 (filtered_rows, n_superseded)。
    """
    bucket_to_idx: dict[int, int] = {}
    for i, r in enumerate(rows):
        if r['IsRaceOn'] != '1':
            continue
        try:
            crt = float(r.get('CurrentRaceTime', 0))
        except (TypeError, ValueError):
            continue
        if crt < 0:
            continue
        # 1/60 秒桶；後寫入會覆蓋前寫入（latest arrival wins）
        bucket = int(crt * 60)
        bucket_to_idx[bucket] = i

    # 依 CRT 桶排序輸出（= 賽事時間順序），保持「相鄰 packet 差 1/60 秒」假設
    sorted_buckets = sorted(bucket_to_idx.keys())
    filtered = [rows[bucket_to_idx[b]] for b in sorted_buckets]

    total_race_on = sum(1 for r in rows if r['IsRaceOn'] == '1')
    n_superseded = total_race_on - len(filtered)
    return filtered, n_superseded


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

def _f_to_c(f: float) -> float:
    """FH5 UDP TireTemp* 欄位是華氏度（cold ≈ 130°F、operating ≈ 200°F、hot ≈ 230°F）。
    全分析以攝氏為準，故在資料邊界一次轉換。"""
    return (f - 32.0) * 5.0 / 9.0


def analyze_tires(segments: list[Segment]) -> dict:
    """Per-segment tire temperatures + overall pattern.

    回傳值的所有溫度欄位皆為 **攝氏**（UDP 原始值是華氏，已在此函式邊界轉換）。

    **RR data quality 檢測**：FH5 已知 bug——TireTempRearRight 欄位常常逐 packet
    複製 TireTempRearLeft（max|RL-RR| < 0.01°F 全程都成立）。若偵測到此情況，
    `rr_unreliable=True`，下游應隱藏 RR 欄位與 lr_rear_delta，避免假陰性。
    """
    # RR mirrors RL? 全場任一 packet 出現差異就判可信。
    rr_unreliable = True
    for seg in segments:
        for r in seg.packets:
            if abs(F(r, 'TireTempRearLeft') - F(r, 'TireTempRearRight')) > 0.01:
                rr_unreliable = False
                break
        if not rr_unreliable:
            break

    rows = []
    for seg in segments:
        fl = _f_to_c(statistics.mean(F(r, 'TireTempFrontLeft') for r in seg.packets))
        fr = _f_to_c(statistics.mean(F(r, 'TireTempFrontRight') for r in seg.packets))
        rl = _f_to_c(statistics.mean(F(r, 'TireTempRearLeft') for r in seg.packets))
        rr = _f_to_c(statistics.mean(F(r, 'TireTempRearRight') for r in seg.packets))
        # RR 不可信時：rear_avg 改用 RL 單值，lr_rear_delta 標 None
        rear_avg = rl if rr_unreliable else (rl + rr) / 2
        lr_rear_delta = None if rr_unreliable else rl - rr
        rows.append({"label": seg.label, "fl": fl, "fr": fr, "rl": rl, "rr": rr,
                    "front_avg": (fl + fr) / 2, "rear_avg": rear_avg,
                    "lr_front_delta": fl - fr, "lr_rear_delta": lr_rear_delta,
                    "fr_delta": (fl + fr) / 2 - rear_avg})
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
        ovr["rear_avg"] = ovr["rl"] if rr_unreliable else (ovr["rl"] + ovr["rr"]) / 2
        ovr["fr_delta"] = ovr["front_avg"] - ovr["rear_avg"]
        ovr["lr_front_delta"] = ovr["fl"] - ovr["fr"]
        ovr["lr_rear_delta"] = None if rr_unreliable else ovr["rl"] - ovr["rr"]
        # RR 不可信時不把 RR 列入 hottest 候選
        candidates = ["fl", "fr", "rl"] if rr_unreliable else ["fl", "fr", "rl", "rr"]
        hottest = max(candidates, key=lambda k: ovr[k])
    else:
        ovr = None
        hottest = None
    return {"per_segment": rows, "overall": ovr, "hottest_corner": hottest,
            "skipped_first_segment": skip_first,
            "rr_unreliable": rr_unreliable}


def analyze_slip(segments: list[Segment]) -> dict:
    """Slip ratio 統計（per-segment 最大／平均）。

    過濾規則：slip ratio > SLIP_RATIO_ARTIFACT_CAP（=5.0）視為撞車/rewind 邊界 artifact，
    從 fr_max/rr_max 統計中剔除（FH5 物理上輪胎打滑率 5 已經是極端輪轉空轉，11 之類純為 IMU 尖峰）。

    **歷史**：本函式原本也輸出基於 slip angle 的 understeer / oversteer top moments
    （`understeer_top` / `oversteer_top` / `understeer_count` / `oversteer_count`），
    但該邏輯（front > 1.5× rear AND > 0.5）會把正常過彎的 turn-in 誤判為推頭
    （實測 78% false positive）。已改用 `analyze_corners` 內的 yaw-rate-based 法
    （見 `_classify_yaw_balance`），US/OS top moments 從 corners 的 `top_imbalance`
    彙總取得。
    """
    SLIP_RATIO_ARTIFACT_CAP = 5.0
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
    return {"per_segment": rows}


def analyze_suspension(segments: list[Segment]) -> dict:
    """Per-corner suspension stats.

    - max/avg/bottom_count: existing bottoming check.
    - std: NormalizedSuspensionTravel oscillation amplitude. High std on a
      relatively flat track ≈ visual 「波動幅度大」 in the in-game telemetry
      bar → spring on that corner is too soft. Low std + low avg → spring
      too stiff (travel unused).
    - in_15_85_pct / in_20_80_pct: % of packets where the corner stays inside
      the wiki's healthy ranges (硬核指南: 15-85%, HokiHoshi: 20-80%).
    """
    rows = []
    total_bottom = 0
    for seg in segments:
        fl_vals = [F(r, 'NormalizedSuspensionTravelFrontLeft') for r in seg.packets]
        fr_vals = [F(r, 'NormalizedSuspensionTravelFrontRight') for r in seg.packets]
        rl_vals = [F(r, 'NormalizedSuspensionTravelRearLeft') for r in seg.packets]
        rr_vals = [F(r, 'NormalizedSuspensionTravelRearRight') for r in seg.packets]
        n = len(seg.packets)
        if n == 0:
            continue

        def pct_in_range(vals, lo, hi):
            return sum(1 for v in vals if lo <= v <= hi) / len(vals) * 100

        std = lambda vs: statistics.pstdev(vs) if len(vs) > 1 else 0.0

        bottom = sum(1 for r in seg.packets if max(
            F(r, 'NormalizedSuspensionTravelFrontLeft'),
            F(r, 'NormalizedSuspensionTravelFrontRight'),
            F(r, 'NormalizedSuspensionTravelRearLeft'),
            F(r, 'NormalizedSuspensionTravelRearRight')) > SUSPENSION_BOTTOM_THRESHOLD)
        total_bottom += bottom
        rows.append({"label": seg.label,
                    "fl_max": max(fl_vals), "fr_max": max(fr_vals),
                    "rl_max": max(rl_vals), "rr_max": max(rr_vals),
                    "fl_avg": statistics.mean(fl_vals), "fr_avg": statistics.mean(fr_vals),
                    "rl_avg": statistics.mean(rl_vals), "rr_avg": statistics.mean(rr_vals),
                    "fl_std": std(fl_vals), "fr_std": std(fr_vals),
                    "rl_std": std(rl_vals), "rr_std": std(rr_vals),
                    "fl_in_15_85": pct_in_range(fl_vals, 0.15, 0.85),
                    "fr_in_15_85": pct_in_range(fr_vals, 0.15, 0.85),
                    "rl_in_15_85": pct_in_range(rl_vals, 0.15, 0.85),
                    "rr_in_15_85": pct_in_range(rr_vals, 0.15, 0.85),
                    "fl_in_20_80": pct_in_range(fl_vals, 0.20, 0.80),
                    "fr_in_20_80": pct_in_range(fr_vals, 0.20, 0.80),
                    "rl_in_20_80": pct_in_range(rl_vals, 0.20, 0.80),
                    "rr_in_20_80": pct_in_range(rr_vals, 0.20, 0.80),
                    "bottom_count": bottom})
    return {"per_segment": rows, "total_bottom_packets": total_bottom}


def analyze_brake_balance(valid_rows: list) -> dict:
    """缺陷 4：煞車期間前後軸鎖死分布 → 煞車平衡診斷。

    煞車調校.md：偏前 → 增轉向過度（前輪鎖死多）；偏後 → 減轉向（後輪鎖死多）。
    在 Brake > 200 的 packet 中，若前輪 slip ratio > 1.0 → 前鎖死；後輪同理。
    比例顯著偏一邊 → 滑桿應反方向調整。
    """
    BRAKING_THR = 200       # Brake (0-255) > 200 視為實質減速
    LOCKUP_THR = 1.0        # |TireSlipRatio| > 1.0 = 失抓 / 鎖死
    braking = 0
    front_lock = 0
    rear_lock = 0
    both_lock = 0
    for r in valid_rows:
        if I(r, 'Brake') < BRAKING_THR:
            continue
        braking += 1
        fl = abs(F(r, 'TireSlipRatioFrontLeft'))
        fr = abs(F(r, 'TireSlipRatioFrontRight'))
        rl = abs(F(r, 'TireSlipRatioRearLeft'))
        rr = abs(F(r, 'TireSlipRatioRearRight'))
        f_locked = fl > LOCKUP_THR or fr > LOCKUP_THR
        r_locked = rl > LOCKUP_THR or rr > LOCKUP_THR
        if f_locked and r_locked:
            both_lock += 1
        elif f_locked:
            front_lock += 1
        elif r_locked:
            rear_lock += 1
    f_total = front_lock + both_lock
    r_total = rear_lock + both_lock
    return {
        "braking_packets": braking,
        "front_lockup_packets": f_total,
        "rear_lockup_packets": r_total,
        "front_only_packets": front_lock,
        "rear_only_packets": rear_lock,
        "both_packets": both_lock,
        # ratio: > 1 偏前鎖死多, < 1 偏後鎖死多
        "front_rear_ratio": (f_total / r_total) if r_total > 0 else (float('inf') if f_total > 0 else 0.0),
    }


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
    # 缺陷 8：upshift 後落點分析（齒比.md：理想是換完檔仍在 power band 內）
    # 落點取換檔後 12 packet (≈0.2s) 的 RPM——讓引擎轉速穩定後再看。
    POST_SHIFT_LOOKAHEAD = 12
    post_shift_landings = []  # 每個 upshift 落在哪個 RPM
    for j in range(1, len(valid_rows)):
        if gears[j] > gears[j - 1] and gears[j - 1] > 0:
            shift_pts[(gears[j - 1], gears[j])].append(rpms[j - 1])
            land_idx = min(j + POST_SHIFT_LOOKAHEAD, len(valid_rows) - 1)
            post_shift_landings.append(rpms[land_idx])

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

    # 缺陷 8：post-shift dead zone — 換完檔後 RPM 是否掉出 power band
    if post_shift_landings:
        below_band = sum(1 for r in post_shift_landings if r < power_band_start)
        post_shift_dead_pct = below_band / len(post_shift_landings) * 100
        post_shift_avg = statistics.mean(post_shift_landings)
    else:
        post_shift_dead_pct = 0.0
        post_shift_avg = 0.0

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
            "max_rpm_seen": max(rpms),
            "post_shift_count": len(post_shift_landings),
            "post_shift_dead_pct": post_shift_dead_pct,
            "post_shift_avg_rpm": post_shift_avg}


def analyze_inputs(valid_rows: list) -> dict:
    n = len(valid_rows)
    accel = [I(r, 'Accel') for r in valid_rows]
    brake = [I(r, 'Brake') for r in valid_rows]
    steer = [I(r, 'Steer') for r in valid_rows]
    abs_steer = [abs(s) for s in steer]
    steer_max = max(abs_steer) if abs_steer else 0
    # Trail-brake / brake-throttle-overlap 用：橫向 G 用 AccelerationX（車身座標）
    # 0.4 G 是「明顯彎中」門檻，低於此視為直線煞車。
    abs_lat_g = [abs(F(r, 'AccelerationX')) / 9.81 for r in valid_rows]

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
        # trail braking = 帶煞入彎（煞車期間有明顯橫向 G）；不是「油門煞車同踩」
        "trail_brake_pct": (sum(1 for j in range(n) if brake[j] > 50 and abs_lat_g[j] > 0.4) / n * 100),
        # brake/throttle overlap = 同時踩油門與煞車（左腳煞車或誤踩）；獨立指標
        "brake_throttle_overlap_pct": sum(1 for j in range(n) if accel[j] > 50 and brake[j] > 50) / n * 100,
        # trail brake 占「有煞車 packet」比例——避免看似 trail brake 高但其實只是煞車總量低
        "trail_brake_share_of_braking": (
            sum(1 for j in range(n) if brake[j] > 50 and abs_lat_g[j] > 0.4)
            / max(sum(1 for j in range(n) if brake[j] > 50), 1) * 100
        ),
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


def analyze_pi_grip_target(gforces: dict, meta: dict, corners: dict) -> dict | None:
    """缺陷 11：依 PI 級的橫向 G 力達標檢查。

    對照 [wiki/upgrades/輪胎配件.md] Mustuff124 表：
        B 1.3-1.4 / A 1.7-1.9 / S1 2.1-2.3 / S2 2.5+

    **量測值**：用 corners.max_peak_g（彎內最大側向 G，已被 CORNER_LATERAL_G_CAP=3.5
    過濾且來自偵測到的彎，避免微撞擊／IMU 尖峰污染）。若沒有偵測到的彎則 fallback
    到 gforces.max_lateral_g_clean，但會在輸出標註資料來源不可靠。

    回傳 dict 含級距、目標範圍、實測值、資料源、達標狀態與 gap；若 PI 級無基準（D/C）
    亦回完整 dict（status="no_target"）讓輸出端統一判斷。
    """
    pi = meta.get("car", {}).get("performance_index")
    if pi is None:
        return None
    label, lo, hi = None, None, None
    for cap, lbl, l, h in PI_GRIP_TARGETS:
        if pi <= cap:
            label, lo, hi = lbl, l, h
            break

    # 量測穩健化：用「top-3 corner peaks 平均」而非單一 max（單一彎可能因
    # 微撞擊或 IMU 抖動觸 CORNER_LATERAL_G_CAP=3.5 上限）。代表「車能穩定發揮的
    # 側向 G 上限」，比 max_peak_g 更貼近 build 能力。彎數 < 3 時 fallback 到 max。
    # 同時保留 avg_peak_g 作為次要參考（所有彎平均，反映「常態 grip 使用率」）。
    corner_list = corners.get("corners", []) if corners.get("count", 0) > 0 else []
    avg_peak = corners.get("avg_peak_g")
    if len(corner_list) >= 3:
        peaks = sorted((abs(c["peak_g"]) for c in corner_list), reverse=True)
        observed = sum(peaks[:3]) / 3
        source = "corners_top3"
    elif corner_list:
        observed = max(abs(c["peak_g"]) for c in corner_list)
        source = "corners_max"
    else:
        observed = gforces["max_lateral_g_clean"]
        source = "raw"

    if lo is None:  # D / C 級無基準
        return {"pi": pi, "class_label": label, "expected_lo": None,
                "expected_hi": None, "observed": observed, "source": source,
                "avg_peak": avg_peak, "status": "no_target", "gap": 0.0}

    # status 判定：
    #   under = 低於下限（建議升輪胎/減重）
    #   target = 落在範圍內（達標）
    #   over = 高於上限（build 操控過剩，可考慮減重→換更激進取向）
    #   over 在 hi=None（S2/X 無上限）時不會觸發
    if observed < lo:
        status = "under"
        gap = lo - observed
    elif hi is not None and observed > hi:
        status = "over"
        gap = observed - hi
    else:
        status = "target"
        gap = 0.0
    return {"pi": pi, "class_label": label, "expected_lo": lo,
            "expected_hi": hi, "observed": observed, "source": source,
            "avg_peak": avg_peak, "status": status, "gap": gap}


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


def analyze_launch(valid_rows: list, drivetrain_type: int) -> dict | None:
    """缺陷 9：起步 launch 階段後輪 slip ratio 分析。

    對應 [wiki/driving/RWD駕駛技巧.md] § Launch 找頂速法：
    - 起步全油門是最快的，但要在頂速前一刻升檔
    - **三檔仍打滑** → 後胎抓地不夠（不是駕駛問題）

    流程：
      1. 從第一個 packet 開始找「靜止 → 加速」的真實起步點
      2. 從起步點往前累積到 LAUNCH_DISTANCE_M（200 m）
      3. 依 gear (1/2/3) 統計後輪平均 slip ratio 與打滑 packet 比例
      4. 若 gear 3 仍 ≥ 30% packet 打滑 → 標記為 build 問題

    僅 RWD/AWD（drivetrain_type ∈ {1, 2}）有意義；FWD 回 None。
    若找不到合格的 launch 段（玩家可能從中段插入錄製）也回 None。
    """
    if drivetrain_type not in (1, 2):
        return None
    if len(valid_rows) < 60:
        return None

    # 找起步點：第一個 speed < 2 m/s 後緊接著 speed 持續上升的點
    # （避免抓到「停下來再加速」的中段事件——只取從錄製開始的首個起步）
    start_idx = None
    for j in range(min(len(valid_rows) - 30, 600)):  # 只在前 10 秒內找
        if F(valid_rows[j], 'Speed') < 2.0:
            # 看後續 30 packet 是否持續加速到 > 5 m/s
            ahead_max = max(F(valid_rows[k], 'Speed')
                            for k in range(j, min(j + 30, len(valid_rows))))
            if ahead_max > 5.0:
                start_idx = j
                break
    if start_idx is None:
        return None

    # 從 start_idx 往前累積到達 LAUNCH_DISTANCE_M 為止
    accum_m = 0.0
    end_idx = start_idx
    for j in range(start_idx, len(valid_rows) - 1):
        accum_m += F(valid_rows[j], 'Speed') / 60  # m/s × 1/60 s = m
        end_idx = j
        if accum_m >= LAUNCH_DISTANCE_M:
            break

    launch_rows = valid_rows[start_idx:end_idx + 1]
    if len(launch_rows) < 30:  # 不足 0.5s 的 launch 不分析
        return None

    # 依 gear 分組
    by_gear: dict[int, dict] = {}
    for r in launch_rows:
        g = I(r, 'Gear')
        if g <= 0 or g > 8:
            continue
        rear_slip = (abs(F(r, 'TireSlipRatioRearLeft'))
                     + abs(F(r, 'TireSlipRatioRearRight'))) / 2
        accel = I(r, 'Accel')
        d = by_gear.setdefault(g, {"packets": 0, "slip_total": 0.0,
                                    "loss_packets": 0, "wot_packets": 0,
                                    "max_slip": 0.0})
        d["packets"] += 1
        d["slip_total"] += rear_slip
        if rear_slip > LAUNCH_SLIP_LOSS_THRESHOLD:
            d["loss_packets"] += 1
        if accel >= THROTTLE_FULL_THRESHOLD:
            d["wot_packets"] += 1
        if rear_slip > d["max_slip"]:
            d["max_slip"] = rear_slip

    per_gear = []
    gear3_problem = False
    for g in sorted(by_gear.keys()):
        d = by_gear[g]
        loss_pct = d["loss_packets"] / d["packets"] if d["packets"] > 0 else 0.0
        wot_pct = d["wot_packets"] / d["packets"] if d["packets"] > 0 else 0.0
        per_gear.append({
            "gear": g,
            "packets": d["packets"],
            "avg_slip": d["slip_total"] / d["packets"] if d["packets"] > 0 else 0.0,
            "max_slip": d["max_slip"],
            "loss_pct": loss_pct * 100,
            "wot_pct": wot_pct * 100,
        })
        # gear 3 才檢查（gear 1-2 打滑是正常的）
        if g >= 3 and d["packets"] >= 30 and loss_pct >= LAUNCH_GEAR3_SLIP_PCT:
            gear3_problem = True

    return {
        "start_packet": start_idx,
        "distance_m": accum_m,
        "duration_s": len(launch_rows) / 60,
        "per_gear": per_gear,
        "gear3_problem": gear3_problem,
        "drivetrain": drivetrain_type,
    }


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
    # 缺陷 B2：路面類型分類 — 用 SurfaceRumble 平均強度 + 水深 + 觸縐石比例推測
    # 公路 / 拉力（混合）/ 越野，套用對應的 wiki 修正表（公路調校修正表.md / 越野調校修正表.md）
    rumble_avgs = [(F(r, 'SurfaceRumbleFrontLeft') +
                    F(r, 'SurfaceRumbleFrontRight') +
                    F(r, 'SurfaceRumbleRearLeft') +
                    F(r, 'SurfaceRumbleRearRight')) / 4 for r in valid_rows]
    avg_surface_rumble = statistics.mean(rumble_avgs) if rumble_avgs else 0.0
    avg_puddle = statistics.mean([
        max(F(r, 'WheelInPuddleDepthFrontLeft'),
            F(r, 'WheelInPuddleDepthFrontRight'),
            F(r, 'WheelInPuddleDepthRearLeft'),
            F(r, 'WheelInPuddleDepthRearRight')) for r in valid_rows
    ]) if valid_rows else 0.0
    rumble_strip_pct = rumble_strip_events / len(valid_rows) * 100 if valid_rows else 0.0
    # Heuristic 門檻（粗估，待實測校準）：
    # 公路（純柏油）：avg_surface_rumble < 0.10 且 avg_puddle < 0.02
    # 越野（土路 / 沙）：avg_surface_rumble >= 0.30 或 avg_puddle >= 0.10
    # 拉力（混合）：介於兩者
    if avg_surface_rumble >= 0.30 or avg_puddle >= 0.10:
        surface_type = "offroad"
    elif avg_surface_rumble >= 0.10 or avg_puddle >= 0.02:
        surface_type = "rally"
    else:
        surface_type = "road"
    return {"rumble_strip_packets": rumble_strip_events,
            "rumble_strip_seconds": rumble_strip_events / 60,
            "max_puddle_depth": max_puddle,
            "avg_surface_rumble": avg_surface_rumble,
            "avg_puddle_depth": avg_puddle,
            "rumble_strip_pct": rumble_strip_pct,
            "surface_type": surface_type}


def analyze_aero(valid_rows: list) -> dict:
    """缺陷 B1：下壓力（aero）診斷 — 比較不同速度區間的側向 G 上限。

    若高速段（> 200 km/h）累積 > 5s 且側向 G 上限明顯低於中速段（100-200 km/h）
    上限的 60%，提示「下壓力可能不足」（也可能是高速彎駕駛偏保守，需與駕駛建議
    並列、不下死論）。

    對應 wiki/tuning/下壓力.md。
    """
    low, mid, high = [], [], []
    for r in valid_rows:
        kmh = F(r, 'Speed') * 3.6
        # Cap 同 CORNER_LATERAL_G_CAP（FH5 物理極限 ~3G，> 5G 為 IMU 撞牆殘留尖峰）
        lat_g = min(abs(F(r, 'AccelerationX') / 9.81), CORNER_LATERAL_G_CAP)
        if kmh < 100:
            low.append(lat_g)
        elif kmh < 200:
            mid.append(lat_g)
        else:
            high.append(lat_g)

    def p95(vals):
        if not vals:
            return None
        s = sorted(vals)
        return s[min(len(s) - 1, int(len(s) * 0.95))]

    low_p95 = p95(low)
    mid_p95 = p95(mid)
    high_p95 = p95(high)
    return {
        "low_packets": len(low),
        "mid_packets": len(mid),
        "high_packets": len(high),
        "low_p95_lat_g": low_p95,
        "mid_p95_lat_g": mid_p95,
        "high_p95_lat_g": high_p95,
    }


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
        # Per-tire slip ratios kept separately for left-right delta (diff lock validation).
        rl_slip_ratio = [F(r, 'TireSlipRatioRearLeft') for r in in_corner_pkts]
        rr_slip_ratio = [F(r, 'TireSlipRatioRearRight') for r in in_corner_pkts]
        fl_slip_ratio = [F(r, 'TireSlipRatioFrontLeft') for r in in_corner_pkts]
        fr_slip_ratio = [F(r, 'TireSlipRatioFrontRight') for r in in_corner_pkts]
        # 懸吊行程（缺陷 2：d/dt 分析）+ rumble strip flag（缺陷 3：過 curb）
        front_susp_avg = [(F(r, 'NormalizedSuspensionTravelFrontLeft') +
                           F(r, 'NormalizedSuspensionTravelFrontRight')) / 2 for r in in_corner_pkts]
        rear_susp_avg = [(F(r, 'NormalizedSuspensionTravelRearLeft') +
                          F(r, 'NormalizedSuspensionTravelRearRight')) / 2 for r in in_corner_pkts]
        rumble_any = [(I(r, 'WheelOnRumbleStripFrontLeft') |
                       I(r, 'WheelOnRumbleStripFrontRight') |
                       I(r, 'WheelOnRumbleStripRearLeft') |
                       I(r, 'WheelOnRumbleStripRearRight')) > 0 for r in in_corner_pkts]
        ang_vel_z = [F(r, 'AngularVelocityZ') for r in in_corner_pkts]
        # AngularVelocityY 才是 yaw rate（實證 99.7% sign match w/ AccelerationX；
        # AngVel_Z 47% 是 roll、AngVel_X 是 pitch）。Z/X 仍保留供既有檢測使用。
        ang_vel_y = [F(r, 'AngularVelocityY') for r in in_corner_pkts]
        # signed lateral acc (m/s²)，用於 yaw-rate 法的 expected yaw 計算
        lat_acc_signed = [F(r, 'AccelerationX') for r in in_corner_pkts]
        brake = [I(r, 'Brake') for r in in_corner_pkts]
        throttle = [I(r, 'Accel') for r in in_corner_pkts]
        steer = [I(r, 'Steer') for r in in_corner_pkts]

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
        #
        # 三段切片（缺陷 0）：對照 wiki/tuning/三段彎道診斷.md，入彎/中段/出彎
        # 各有不同處方。phase boundary 與 _emit_corner_table 一致：
        #   entry  = [0, apex_local_idx)
        #   apex   = [apex_local_idx, apex_phase_end_local]
        #   exit   = (apex_phase_end_local, len-1]
        APEX_WIN_LOCAL = 4
        apex_phase_end_local = min(apex_local_idx + APEX_WIN_LOCAL, len(in_corner_pkts) - 1)

        def _phase_of(local_i: int) -> str:
            if local_i < apex_local_idx:
                return 'entry'
            if local_i <= apex_phase_end_local:
                return 'apex'
            return 'exit'

        # === Yaw-rate-based US/OS 偵測（取代舊的 slip-angle ratio 法）===
        # 業界 ESC 標準：實際 yaw 與物理預期 yaw（lat_acc/speed）的偏差。
        # Slip angle 作為次級確認信號（>= 0.7 視為胎接近 grip 極限）。
        phase_us = {'entry': 0, 'apex': 0, 'exit': 0}
        phase_os = {'entry': 0, 'apex': 0, 'exit': 0}
        phase_pkts = {'entry': 0, 'apex': 0, 'exit': 0}
        pkt_understeer = 0
        pkt_oversteer = 0
        pkt_us_severe = 0
        pkt_os_severe = 0
        pkt_us_moderate = 0
        pkt_os_moderate = 0
        pkt_us_confirmed = 0  # yaw 法 + slip angle ≥ 0.7
        pkt_os_confirmed = 0
        # Top-N imbalance packets（給報表「最異常瞬間」表用）
        local_imbalance: list[tuple[float, int, str, str, float, float]] = []
        for li in range(len(in_corner_pkts)):
            ph = _phase_of(li)
            phase_pkts[ph] += 1
            yaw_smooth = _rolling_avg(ang_vel_y, li, 3)
            kind, sev, ratio = _classify_yaw_balance(
                yaw_smooth, lat_acc_signed[li], speeds[li], brake[li], ph)
            if kind is None:
                continue
            fs_v = front_slip[li]
            rs_v = rear_slip[li]
            if kind == 'us':
                pkt_understeer += 1
                phase_us[ph] += 1
                if sev == 'severe':
                    pkt_us_severe += 1
                if sev in ('moderate', 'severe'):
                    pkt_us_moderate += 1
                if fs_v >= YAW_SLIP_CONFIRM_THRESHOLD:
                    pkt_us_confirmed += 1
            else:  # 'os'
                pkt_oversteer += 1
                phase_os[ph] += 1
                if sev == 'severe':
                    pkt_os_severe += 1
                if sev in ('moderate', 'severe'):
                    pkt_os_moderate += 1
                if rs_v >= YAW_SLIP_CONFIRM_THRESHOLD:
                    pkt_os_confirmed += 1
            # 追蹤該彎內最異常的 5 個 packet（依與 1.0 的距離）
            local_imbalance.append((abs(1.0 - ratio), li, kind, sev, ratio, fs_v if kind == 'us' else rs_v))
        local_imbalance.sort(reverse=True)
        top_imbalance = local_imbalance[:5]
        total_in_corner_packets += len(in_corner_pkts)
        understeer_packets_in_corners += pkt_understeer
        oversteer_packets_in_corners += pkt_oversteer

        # 缺陷 1：左右輪 slip ratio Δ — 差速器鎖定驗證（差速器.md:147-174）
        # 入彎（煞車中）取後輪左右 Δ → 後 diff decel 鬆緊
        # 出彎（油門打開）取後輪 / 前輪左右 Δ → 後/前 diff accel 鬆緊
        def _abs_lr_delta(left_vals, right_vals, l_start, l_end):
            """|left - right| per packet, max over phase. AWD/RWD 出彎時常常一輪
            spin、另一輪有抓地力 → 差距大；diff lock 越鬆差距越大。"""
            if l_start >= l_end:
                return 0.0
            best = 0.0
            for k in range(l_start, l_end):
                d = abs(abs(left_vals[k]) - abs(right_vals[k]))
                if d > best:
                    best = d
            return best

        entry_lr_rear_delta = _abs_lr_delta(rl_slip_ratio, rr_slip_ratio, 0, apex_local_idx)
        exit_lr_rear_delta = _abs_lr_delta(rl_slip_ratio, rr_slip_ratio,
                                            apex_phase_end_local + 1, len(in_corner_pkts))
        exit_lr_front_delta = _abs_lr_delta(fl_slip_ratio, fr_slip_ratio,
                                             apex_phase_end_local + 1, len(in_corner_pkts))

        # === 缺陷 2：懸吊行程 d/dt（壓縮/回彈速度，1 packet = 1/60 s）===
        # 入彎前懸吊壓縮速度過快 → 前 bump 阻尼不足 / 軟前彈簧（重心轉移過大，三段彎道診斷.md:138）
        # 出彎後（過 apex 後）懸吊回彈速度過快 → rebound 阻尼不足
        # 0.10 / packet ≈ 6.0/s 的歸一化行程變化，是經驗門檻——多數平路打彎在 0.03-0.06。
        def _max_pos_delta(vals, lo, hi):  # 壓縮速度（行程往 1 衝）
            best = 0.0
            for k in range(max(1, lo), min(len(vals), hi)):
                d = vals[k] - vals[k - 1]
                if d > best:
                    best = d
            return best

        def _max_neg_delta(vals, lo, hi):  # 回彈速度（行程往 0 衝），回傳絕對值
            best = 0.0
            for k in range(max(1, lo), min(len(vals), hi)):
                d = vals[k - 1] - vals[k]
                if d > best:
                    best = d
            return best

        entry_front_compress_rate = _max_pos_delta(front_susp_avg, 0, apex_local_idx)
        entry_rear_compress_rate = _max_pos_delta(rear_susp_avg, 0, apex_local_idx)
        exit_front_rebound_rate = _max_neg_delta(front_susp_avg,
                                                   apex_phase_end_local + 1, len(front_susp_avg))
        exit_rear_rebound_rate = _max_neg_delta(rear_susp_avg,
                                                  apex_phase_end_local + 1, len(rear_susp_avg))

        # === 缺陷 3：過 curb 甩飛偵測 ===
        # 觸發條件（同一彎內任一 packet 同時滿足）：
        #   (1) 任一輪在 rumble strip 上
        #   (2) 該 packet 或前後 3 packet 內懸吊 Δ > 0.20（受到衝擊）
        #   (3) AngularVelocityZ 偏離該彎平均 > 1.5 rad/s（車尾被踢開）
        # 寬鬆估計，僅作標記而非精確計數。
        curb_launch = False
        if any(rumble_any):
            avg_yaw = statistics.mean(ang_vel_z) if ang_vel_z else 0.0
            for li in range(len(in_corner_pkts)):
                if not rumble_any[li]:
                    continue
                # 看 ±3 packet 內的最大懸吊壓縮 Δ
                lo, hi = max(1, li - 3), min(len(front_susp_avg), li + 4)
                spike = max(
                    _max_pos_delta(front_susp_avg, lo, hi),
                    _max_pos_delta(rear_susp_avg, lo, hi),
                    _max_neg_delta(front_susp_avg, lo, hi),
                    _max_neg_delta(rear_susp_avg, lo, hi),
                )
                yaw_dev = abs(ang_vel_z[li] - avg_yaw)
                if spike > 0.20 and yaw_dev > 1.5:
                    curb_launch = True
                    break

        # === 缺陷 7：出彎 yaw 過衝（差速器 accel 過鬆驗證）===
        # entry phase 的 max |yaw rate| vs exit phase 的 max |yaw rate|
        # 出彎 yaw > 入彎 yaw × 1.5 → 後 diff accel 太鬆，車尾在出彎被 diff 釋放反而轉太多
        # **修正**：原本用 AngularVelocityZ（其實是 roll），改用正確的 AngularVelocityY (yaw)
        entry_yaw_peak = max((abs(ang_vel_y[k]) for k in range(0, apex_local_idx)),
                             default=0.0)
        exit_yaw_peak = max((abs(ang_vel_y[k]) for k in range(apex_phase_end_local + 1,
                                                                len(ang_vel_y))),
                            default=0.0)
        # 至少 yaw 有意義（> 0.5 rad/s ≈ 28°/s）才作判斷
        yaw_overshoot = (exit_yaw_peak > 0.5 and
                         entry_yaw_peak > 0.3 and
                         exit_yaw_peak > entry_yaw_peak * 1.5)

        # === 缺陷 10：Exit phase「彎太多 + 加油太早」===
        # HokiHoshi 2021 RWD 指南：過 apex 後應同時放鬆方向盤 + 加油 + 瞄外。
        # 常見錯：仍在大角度轉向就已踩半油以上 → 阻礙出彎加速、RWD 易甩。
        # 用「**該彎自己的 max 轉向 × ratio**」當門檻，跨彎類型可比較
        # （髮夾彎 max 大、sweeper max 小，但 50% 都意味「仍在大角度」）。
        corner_steer_max = max((abs(s) for s in steer), default=0)
        # 至少 corner_steer_max 要 ≥ 20（避免幾乎不轉的彎觸發誤判）
        exit_overturn_packets = 0
        if corner_steer_max >= 20:
            steer_threshold = corner_steer_max * EXIT_HARD_STEER_RATIO
            for k in range(apex_phase_end_local + 1, len(in_corner_pkts)):
                if abs(steer[k]) > steer_threshold and throttle[k] >= EXIT_EARLY_THROTTLE:
                    exit_overturn_packets += 1
        # 是否為「過彎太多」問題彎
        is_overturn_corner = exit_overturn_packets >= EXIT_OVERTURN_MIN_PACKETS

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
            # 缺陷 0：三段切片（entry/apex/exit）us/os 計數與該段封包數
            "entry_us": phase_us['entry'], "entry_os": phase_os['entry'],
            "entry_pkts": phase_pkts['entry'],
            "mid_us": phase_us['apex'], "mid_os": phase_os['apex'],
            "mid_pkts": phase_pkts['apex'],
            "exit_us": phase_us['exit'], "exit_os": phase_os['exit'],
            "exit_pkts": phase_pkts['exit'],
            # 缺陷 1：左右輪 slip ratio Δ（差速器鎖定診斷）
            "entry_lr_rear_delta": entry_lr_rear_delta,
            "exit_lr_rear_delta": exit_lr_rear_delta,
            "exit_lr_front_delta": exit_lr_front_delta,
            # 缺陷 2：懸吊行程速度（壓縮/回彈，per 1/60 s）
            "entry_front_compress_rate": entry_front_compress_rate,
            "entry_rear_compress_rate": entry_rear_compress_rate,
            "exit_front_rebound_rate": exit_front_rebound_rate,
            "exit_rear_rebound_rate": exit_rear_rebound_rate,
            # 缺陷 3：過 curb 甩飛
            "curb_launch": curb_launch,
            # 缺陷 7：出彎 yaw 過衝
            "entry_yaw_peak": entry_yaw_peak,
            "exit_yaw_peak": exit_yaw_peak,
            "yaw_overshoot": yaw_overshoot,
            # 缺陷 10：出彎「彎太多 + 加油太早」
            "corner_steer_max": corner_steer_max,
            "exit_overturn_packets": exit_overturn_packets,
            "is_overturn_corner": is_overturn_corner,
            # Yaw-rate-based US/OS（嚴重度與 slip 確認分層）
            "us_severe_packets": pkt_us_severe,
            "os_severe_packets": pkt_os_severe,
            "us_moderate_packets": pkt_us_moderate,  # 含 severe
            "os_moderate_packets": pkt_os_moderate,
            "us_confirmed_packets": pkt_us_confirmed,  # yaw + slip 雙確認
            "os_confirmed_packets": pkt_os_confirmed,
            "top_imbalance": top_imbalance,
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
        # === Yaw-rate-based US/OS：嚴重度與 slip 確認彙總 ===
        "us_severe_packets_in_corners": sum(c.get("us_severe_packets", 0) for c in corners),
        "os_severe_packets_in_corners": sum(c.get("os_severe_packets", 0) for c in corners),
        "us_moderate_packets_in_corners": sum(c.get("us_moderate_packets", 0) for c in corners),
        "os_moderate_packets_in_corners": sum(c.get("os_moderate_packets", 0) for c in corners),
        "us_confirmed_packets_in_corners": sum(c.get("us_confirmed_packets", 0) for c in corners),
        "os_confirmed_packets_in_corners": sum(c.get("os_confirmed_packets", 0) for c in corners),
        # === 缺陷 0：三段切片彙總（dominant = 該段 us/os 占該段 packet 數 >= 30% 且 us > os*2）===
        # 對應 wiki/tuning/三段彎道診斷.md 的入彎/中段/出彎不同處方表
        "entry_us_corners": _phase_dominant_count(corners, 'entry', 'us'),
        "mid_us_corners":   _phase_dominant_count(corners, 'mid',   'us'),
        "exit_us_corners":  _phase_dominant_count(corners, 'exit',  'us'),
        "entry_os_corners": _phase_dominant_count(corners, 'entry', 'os'),
        "mid_os_corners":   _phase_dominant_count(corners, 'mid',   'os'),
        "exit_os_corners":  _phase_dominant_count(corners, 'exit',  'os'),
        # 各段累計 us/os 時間佔比（packet 級）
        "entry_us_time_pct": _phase_pct(corners, 'entry', 'us'),
        "mid_us_time_pct":   _phase_pct(corners, 'mid',   'us'),
        "exit_us_time_pct":  _phase_pct(corners, 'exit',  'us'),
        "entry_os_time_pct": _phase_pct(corners, 'entry', 'os'),
        "mid_os_time_pct":   _phase_pct(corners, 'mid',   'os'),
        "exit_os_time_pct":  _phase_pct(corners, 'exit',  'os'),
        # === 缺陷 1：左右輪 slip ratio Δ 異常彎統計 ===
        # 出彎後輪 Δ > 0.20 → 後 diff accel 太鬆（一輪 spin 一輪有抓地）
        # 出彎前輪 Δ > 0.20 → 前 diff accel 太鬆（FWD/AWD）
        # 入彎後輪 Δ > 0.15 → 後 diff decel 太鬆
        "exit_diff_rear_loose_corners": sum(1 for c in corners if c["exit_lr_rear_delta"] > 0.20),
        "exit_diff_front_loose_corners": sum(1 for c in corners if c["exit_lr_front_delta"] > 0.20),
        "entry_diff_rear_loose_corners": sum(1 for c in corners if c["entry_lr_rear_delta"] > 0.15),
        "max_exit_lr_rear_delta": max((c["exit_lr_rear_delta"] for c in corners), default=0.0),
        "max_exit_lr_front_delta": max((c["exit_lr_front_delta"] for c in corners), default=0.0),
        # === 缺陷 2：懸吊壓縮/回彈速度（門檻 0.10 / packet ≈ 6/s）===
        "entry_front_overcompress_corners": sum(1 for c in corners
                                                  if c["entry_front_compress_rate"] > 0.10),
        "entry_rear_overcompress_corners":  sum(1 for c in corners
                                                  if c["entry_rear_compress_rate"] > 0.10),
        "exit_front_rebound_high_corners":  sum(1 for c in corners
                                                  if c["exit_front_rebound_rate"] > 0.10),
        "exit_rear_rebound_high_corners":   sum(1 for c in corners
                                                  if c["exit_rear_rebound_rate"] > 0.10),
        "max_entry_front_compress_rate": max((c["entry_front_compress_rate"]
                                              for c in corners), default=0.0),
        "max_exit_rear_rebound_rate":    max((c["exit_rear_rebound_rate"]
                                              for c in corners), default=0.0),
        # === 缺陷 3：過 curb 甩飛事件數 ===
        "curb_launch_corners": sum(1 for c in corners if c["curb_launch"]),
        # === 缺陷 10：出彎「彎太多 + 加油太早」彎數 ===
        "exit_overturn_corners": sum(1 for c in corners if c.get("is_overturn_corner")),
        "exit_overturn_total_packets": sum(c.get("exit_overturn_packets", 0) for c in corners),
        # === 缺陷 7：出彎 yaw 過衝彎數 ===
        "yaw_overshoot_corners": sum(1 for c in corners if c["yaw_overshoot"]),
        # === 缺陷 6：S 彎過渡（快速 L↔R）統計 ===
        # 對應三段彎道診斷.md:133「快速 left→right 過渡 under/oversteer → 阻尼與 ARB」
        # 過渡彎定義：相鄰兩彎方向相反，且 end_i → start_{i+1} 間距 < 1.0s（60 packet）
        # 過渡彎有問題：兩彎中至少一彎 us 或 os 顯著高於該段所有彎平均
        **_analyze_s_transitions(corners),
    }


def _analyze_s_transitions(corners: list) -> dict:
    """缺陷 6：偵測 S 彎過渡與其問題彎數。"""
    if len(corners) < 2:
        return {"s_transition_count": 0, "s_transition_trouble_count": 0}
    GAP_PKT = 60  # 1.0s @ 60 Hz
    avg_us_pkts = (statistics.mean(c["understeer_packets"] for c in corners)
                   if corners else 0)
    avg_os_pkts = (statistics.mean(c["oversteer_packets"] for c in corners)
                   if corners else 0)
    transitions = 0
    trouble = 0
    for i in range(len(corners) - 1):
        a, b = corners[i], corners[i + 1]
        if a["direction"] == b["direction"]:
            continue
        gap = b["start"] - a["end"]
        if gap > GAP_PKT or gap < 0:
            continue
        transitions += 1
        # 該過渡 pair 中任一彎 us 或 os > 該場均值 1.5×
        a_bad = (a["understeer_packets"] > avg_us_pkts * 1.5 or
                 a["oversteer_packets"] > avg_os_pkts * 1.5)
        b_bad = (b["understeer_packets"] > avg_us_pkts * 1.5 or
                 b["oversteer_packets"] > avg_os_pkts * 1.5)
        if a_bad or b_bad:
            trouble += 1
    return {"s_transition_count": transitions, "s_transition_trouble_count": trouble}


def _phase_dominant_count(corners: list, phase: str, kind: str) -> int:
    """Count corners where `phase` (entry/mid/exit) is dominated by us/os.

    Dominant = phase has >= 30% of its packets flagged us/os AND that count
    is >= 2× the opposite. Skips corners with too few packets in that phase
    (< 6 ≈ 0.1s) to avoid noise."""
    cnt = 0
    pkts_key = f'{phase}_pkts'
    me_key = f'{phase}_{kind}'
    op_key = f'{phase}_{"os" if kind == "us" else "us"}'
    for c in corners:
        n = c[pkts_key]
        if n < 6:
            continue
        me = c[me_key]
        op = c[op_key]
        if me / n >= 0.30 and me >= max(op * 2, 2):
            cnt += 1
    return cnt


def _phase_pct(corners: list, phase: str, kind: str) -> float:
    """Total us/os packets in `phase` ÷ total packets in `phase`, all corners."""
    pkts_key = f'{phase}_pkts'
    val_key = f'{phase}_{kind}'
    total = sum(c[pkts_key] for c in corners)
    me = sum(c[val_key] for c in corners)
    return (me / total * 100) if total > 0 else 0.0


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
    rr_bad = tire_data.get("rr_unreliable", False)
    rr_header = 'RR ⚠️' if rr_bad else 'RR'
    lr_rear_header = 'L-R 後 ⚠️' if rr_bad else 'L-R 後'
    out = [f'| 段 | FL | FR | RL | {rr_header} | L-R 前 | {lr_rear_header} | 前-後 |',
           '|----|----|----|----|----|--------|--------|-------|']
    for r in tire_data["per_segment"]:
        rr_cell = 'n/a' if rr_bad else f'{r["rr"]:.0f}'
        lr_rear_cell = 'n/a' if r["lr_rear_delta"] is None else f'{r["lr_rear_delta"]:+.1f}'
        out.append(f'| {r["label"]} | {r["fl"]:.0f} | {r["fr"]:.0f} | {r["rl"]:.0f} | {rr_cell} | '
                  f'{r["lr_front_delta"]:+.1f} | {lr_rear_cell} | {r["fr_delta"]:+.1f} |')
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


def fmt_suspension_range_table(susp_data: dict) -> list[str]:
    """Per-corner 在 15-85% 健康範圍佔比 + std 振幅。"""
    out = ['| 段 | FL 範圍% | FR 範圍% | RL 範圍% | RR 範圍% | FL std | FR std | RL std | RR std |',
           '|----|----------|----------|----------|----------|--------|--------|--------|--------|']
    for r in susp_data["per_segment"]:
        def cell(pct):
            return f'**{pct:.0f}**' if pct < 60 else f'{pct:.0f}'
        out.append(f'| {r["label"]} | {cell(r["fl_in_15_85"])} | {cell(r["fr_in_15_85"])} | '
                  f'{cell(r["rl_in_15_85"])} | {cell(r["rr_in_15_85"])} | '
                  f'{r["fl_std"]:.3f} | {r["fr_std"]:.3f} | '
                  f'{r["rl_std"]:.3f} | {r["rr_std"]:.3f} |')
    return out


# ----- finding helpers -------------------------------------------------------
#
# Findings 形狀：{severity, title, wiki, hint, driving}
#   wiki    — 對應的 wiki 章節指引（race-analyst 會 Read 該頁）
#   hint    — 一句話「通常方向」，僅作粗略指引；具體處方由 race-analyst
#             結合車況、當前 tune、駕駛軌跡、wiki 處方表綜合後才下
#   driving — 列點式駕駛建議（universal、可立即試的低風險動作）
#
# Summarize 不下調校處方、不做互斥仲裁、不依驅動方式分支處方文字。處方權與
# 仲裁是 race-analyst skill 的工作。本檔的 helpers 因此只剩 _wheelspin_finding
# 一個（drivetrain-aware 的標題與 hint，內聯到 call site 不方便所以抽出）。


def _wheelspin_finding(wheelspin_pkts: int, drivetrain_type: int) -> dict:
    """Drivetrain-aware title + wiki pointer for sustained rear wheelspin."""
    sec = wheelspin_pkts / 60
    if drivetrain_type == 1:  # RWD
        return {
            "severity": "🔴",
            "title": f'後輪嚴重打滑 {sec:.1f}s（RWD power oversteer 訊號 / 出彎給油過猛 / 後軸過硬）',
            "wiki": "[tuning/差速器.md] + [tuning/三段彎道診斷.md] 出彎 OS / RWD 出彎",
            "hint": "RWD 出彎 OS：節流量管理優先；真要調 → 後 diff accel 鬆 / 後 ARB 軟 / 後胎壓降 / 加後外傾",
            "driving": ['出彎漸進給油，前 0.5 秒不要全踩', '彎心後等車身擺正再加油'],
        }
    if drivetrain_type == 2:  # AWD
        return {
            "severity": "🟡",
            "title": f'後輪嚴重打滑 {sec:.1f}s（差速器 / 動力分配 / 出彎習慣）',
            "wiki": "[tuning/差速器.md] 後差 + 中差章節",
            "hint": "AWD 通常 → 後 diff accel 鎖定降 / 動力分配往前移 / 提高後胎壓（反直覺但有效）",
            "driving": ['出彎漸進給油，前 0.5 秒不要全踩'],
        }
    return {
        "severity": "ℹ️",
        "title": f'後輪打滑 {sec:.1f}s（FWD 後輪打滑通常為負重轉移／壓縐石所致，較不影響動力）',
        "wiki": "—",
        "hint": "FWD 後輪打滑罕見，通常無需處方",
        "driving": [],
    }


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

    # Rewind-aware filter：對每個 CRT 時刻只保留錄製時間最晚的 packet
    # （= 玩家最終定案的線；rewind 前的失敗嘗試自動排除）。
    # 不再依 is_rewind 欄位——舊邏輯把標籤搞反了，會丟棄玩家的 redo 而保留失敗。
    pre_crash_valid, n_superseded = dedupe_attempts(rows)
    if not pre_crash_valid:
        return (f'# {session_dir.name}\n\n沒有可分析的有效資料（所有 IsRaceOn=1 packet 都被後續 redo 取代）。\n', None)

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
    brake_balance = analyze_brake_balance(valid)
    rpm_obs = analyze_rpm_observed(valid)
    dyno = analyze_dyno(valid)
    drvtrn = analyze_drivetrain(valid, dyno=dyno)
    inputs = analyze_inputs(valid)
    gforces = analyze_g_forces(valid, pre_crash_rows=pre_crash_valid)
    decels = analyze_decel_events(valid)
    speed = analyze_speed(valid)
    drivetrain_type_pre = meta["car"]["drivetrain_type"]
    launch = analyze_launch(valid, drivetrain_type_pre)
    surf = analyze_surface(valid)
    aero = analyze_aero(valid)
    wheelspin = analyze_wheelspin(valid)
    wheelspin_pkts = wheelspin["count"]
    corners = analyze_corners(valid)
    pi_grip = analyze_pi_grip_target(gforces, meta, corners)
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
    us_severe = corners.get("us_severe_packets_in_corners", 0)
    os_severe = corners.get("os_severe_packets_in_corners", 0)
    us_moderate = corners.get("us_moderate_packets_in_corners", 0)
    os_moderate = corners.get("os_moderate_packets_in_corners", 0)
    us_confirmed = corners.get("us_confirmed_packets_in_corners", 0)
    os_confirmed = corners.get("os_confirmed_packets_in_corners", 0)
    if total_corner_pkts > 0:
        us_time_pct = us_pkts_corner / total_corner_pkts * 100
        os_time_pct = os_pkts_corner / total_corner_pkts * 100
        us_severe_pct = us_severe / total_corner_pkts * 100
        os_severe_pct = os_severe / total_corner_pkts * 100
        us_moderate_pct = us_moderate / total_corner_pkts * 100
        os_moderate_pct = os_moderate / total_corner_pkts * 100
        us_confirmed_pct = (us_confirmed / us_pkts_corner * 100) if us_pkts_corner > 0 else 0
        os_confirmed_pct = (os_confirmed / os_pkts_corner * 100) if os_pkts_corner > 0 else 0

        # Yaw-rate-based 法判定（取代舊 slip-angle ratio 法的雙門檻）
        # - severe % >= 5% → ⛔（明確失控等級）
        # - moderate %（含 severe）>= 15% → 🔴（明顯偏向）
        # - moderate % >= 8% → 🟡（輕度偏向）
        # 信心註記：confirmed (yaw + slip) 比 ≥ 50% → "高信心 (slip 確認)"，否則
        # 標 "kinematic only — 可能含 banked corner/感測雜訊"
        def _confidence_note(confirmed_pct: float) -> str:
            if confirmed_pct >= 50:
                return f'，slip-angle 雙確認（{confirmed_pct:.0f}%）'
            if confirmed_pct >= 25:
                return f'，部分 slip 確認（{confirmed_pct:.0f}%）'
            return '，kinematic only（未 slip 確認）'

        # 推頭判定（用 moderate-or-worse）
        if us_moderate_pct >= 8 and us_moderate >= os_moderate * 1.5:
            # ⛔ 必須 severe ≥ 5% **AND** confirmed ≥ 30%（避免 healthy oversteer
            # 等 transient 誤觸發；slip-angle 雙確認才升級為 ⛔）
            if us_severe_pct >= 5 and us_confirmed_pct >= 30:
                sev = "⛔"
                sev_label = f'⛔ severe {us_severe_pct:.0f}% + slip 雙確認'
            elif us_moderate_pct >= 15:
                sev = "🔴"
                sev_label = f'🔴 moderate+ {us_moderate_pct:.0f}%'
            else:
                sev = "🟡"
                sev_label = f'🟡 mild-moderate {us_moderate_pct:.0f}%'
            conf_note = _confidence_note(us_confirmed_pct)
            findings.append({
                "severity": sev,
                "title": (f'整體推頭傾向（{sev_label}{conf_note}；'
                          f'yaw-rate 偏差法）'),
                "wiki": "[tuning/三段彎道診斷.md] 整體 US 對策清單 + [tuning/胎壓.md] / [tuning/防傾桿.md]",
                "hint": "通常涉及前胎壓 / 軟前 ARB / 加前 camber；AWD 中差偏後、FWD 降前 diff accel",
                "driving": ['入彎再慢 3-5 km/h、轉向更線性，避免打到 saturate 還繼續加角度'],
            })
        elif os_moderate_pct >= 8 and os_moderate >= us_moderate * 1.5:
            if os_severe_pct >= 5 and os_confirmed_pct >= 30:
                sev = "⛔"
                sev_label = f'⛔ severe {os_severe_pct:.0f}% + slip 雙確認'
            elif os_moderate_pct >= 15:
                sev = "🔴"
                sev_label = f'🔴 moderate+ {os_moderate_pct:.0f}%'
            else:
                sev = "🟡"
                sev_label = f'🟡 mild-moderate {os_moderate_pct:.0f}%'
            conf_note = _confidence_note(os_confirmed_pct)
            findings.append({
                "severity": sev,
                "title": (f'整體轉向過度傾向（{sev_label}{conf_note}；'
                          f'yaw-rate 偏差法）'),
                "wiki": "[tuning/三段彎道診斷.md] OS 對策（US 對策反向） + [tuning/差速器.md]",
                "hint": "通常涉及後胎壓 / 軟後 ARB / 加後 camber；RWD 注意是 power OS 還是 lift-off",
                "driving": ['出彎油門更線性，前 0.5s 控制在 70%；入彎避免 trail brake 過深'],
            })

    # === 缺陷 0：三段切片 dominant 段定位（對應三段彎道診斷.md 不同處方表）===
    # 即使整體 us/os 沒過門檻，個別段的問題若 dominant 多彎也值得提示。
    # 「dominant 彎數 >= 3 且 >= 總彎數 25%」才觸發，避免單一彎拉警報。
    if corners["count"] >= 4:
        n = corners["count"]
        phase_label = {'entry': '入彎', 'mid': '中段', 'exit': '出彎'}
        for ph in ('entry', 'mid', 'exit'):
            us_n = corners[f'{ph}_us_corners']
            os_n = corners[f'{ph}_os_corners']
            us_pct = corners[f'{ph}_us_time_pct']
            os_pct = corners[f'{ph}_os_time_pct']
            phase_us_hints = {
                'entry': '通常：軟前 ARB / 前 toe out / 降前 diff decel / 加前 bump 阻尼 / 煞車平衡偏前',
                'mid':   '通常：硬後 ARB + 硬後彈簧（讓尾巴幫前軸轉）+ 加後 rebound + 後 bump',
                'exit':  '通常：差速器（AWD 中差偏後 + 加後 diff accel；FWD 加前 diff accel；RWD 加後 diff accel）',
            }
            phase_os_hints = {
                'entry': '通常：硬前 ARB / 前 toe in / 加前 diff decel / 減前 bump / 煞車平衡偏後',
                'mid':   '通常：軟後 ARB + 軟後彈簧 + 減後 rebound + 加後 camber',
                'exit':  'RWD：節流量管理優先；真要調 → 後 diff accel 鬆 / 後 ARB 軟 / 後胎壓降',
            }
            if us_n >= 3 and us_n / n >= 0.25:
                findings.append({
                    "severity": "🟡",
                    "title": (f'{phase_label[ph]} understeer 主導 {us_n}/{n} 個彎'
                              f'（該段時間推頭佔 {us_pct:.0f}%）'),
                    "wiki": f"[tuning/三段彎道診斷.md] {phase_label[ph]} understeer 對策清單",
                    "hint": phase_us_hints[ph],
                    "driving": [],
                })
            if os_n >= 3 and os_n / n >= 0.25:
                exit_driving = ['出彎油門更線性'] if ph == 'exit' else []
                findings.append({
                    "severity": "🟡",
                    "title": (f'{phase_label[ph]} oversteer 主導 {os_n}/{n} 個彎'
                              f'（該段時間轉向過度佔 {os_pct:.0f}%）'),
                    "wiki": f"[tuning/三段彎道診斷.md] {phase_label[ph]} oversteer 對策清單",
                    "hint": phase_os_hints[ph],
                    "driving": exit_driving,
                })

    # === 缺陷 1：左右輪 slip ratio Δ（差速器鎖定診斷）===
    # 差速器.md:155-188 直接告訴你 diff lock 鬆/緊的對應症狀。
    # 後輪出彎左右差距大 → diff accel 太鬆，一邊空轉一邊有抓地。
    if corners["count"] >= 4:
        n = corners["count"]
        rear_loose = corners["exit_diff_rear_loose_corners"]
        front_loose = corners["exit_diff_front_loose_corners"]
        decel_loose = corners["entry_diff_rear_loose_corners"]
        if rear_loose >= 3 and rear_loose / n >= 0.25 and drivetrain_type in (1, 2):
            findings.append({
                "severity": "🟡",
                "title": (f'出彎後輪左右 slip Δ 過大 {rear_loose}/{n} 個彎'
                          f'（max Δ {corners["max_exit_lr_rear_delta"]:.2f}）'),
                "wiki": "[tuning/差速器.md:155-188] 後差加速鎖定",
                "hint": "通常 → 加後 diff accel 鎖定 5-10%（讓兩後輪轉速更同步）",
                "driving": ['出彎前 0.5s 收一點油門，避免內輪先空轉'],
            })
        if front_loose >= 3 and front_loose / n >= 0.25 and drivetrain_type in (0, 2):
            findings.append({
                "severity": "🟡",
                "title": (f'出彎前輪左右 slip Δ 過大 {front_loose}/{n} 個彎'
                          f'（max Δ {corners["max_exit_lr_front_delta"]:.2f}）'),
                "wiki": "[tuning/差速器.md] 前差加速鎖定（FWD/AWD）",
                "hint": "通常 → 加前 diff accel 鎖定 5-10%（改善低速彎出彎拉力）",
                "driving": [],
            })
        if decel_loose >= 3 and decel_loose / n >= 0.25:
            findings.append({
                "severity": "🟡",
                "title": (f'入彎後輪左右 slip Δ 過大 {decel_loose}/{n} 個彎'
                          f'（鬆油時兩輪轉速不同步、入彎不穩）'),
                "wiki": "[tuning/差速器.md] 後差減速鎖定",
                "hint": "通常 → 加後 diff decel 鎖定 10-20%（拉力 / 越野更明顯）",
                "driving": [],
            })

    # === 缺陷 2：懸吊壓縮/回彈速度過快（阻尼診斷）===
    # 三段彎道診斷.md:138「車太彈、重心轉移過大」→ 加 bump 阻尼 + 加彈簧硬度
    # 阻尼.md：bump 控制壓縮、rebound 控制回彈
    if corners["count"] >= 4:
        n = corners["count"]
        ef = corners["entry_front_overcompress_corners"]
        er = corners["entry_rear_overcompress_corners"]
        rf = corners["exit_front_rebound_high_corners"]
        rr = corners["exit_rear_rebound_high_corners"]
        if ef >= 3 and ef / n >= 0.25:
            findings.append({
                "severity": "🟡",
                "title": (f'入彎前懸吊壓縮過快 {ef}/{n} 個彎'
                          f'（max Δ {corners["max_entry_front_compress_rate"]:.3f}/packet）'),
                "wiki": "[tuning/阻尼.md] bump + [tuning/三段彎道診斷.md:138]「車太彈、重心轉移過大」",
                "hint": "通常 → 加前 bump 阻尼 1-2 級，或硬前彈簧 5%",
                "driving": ['入彎更線性減速、避免 brake stab'],
            })
        if er >= 3 and er / n >= 0.25:
            findings.append({
                "severity": "🟡",
                "title": f'入彎後懸吊壓縮過快 {er}/{n} 個彎',
                "wiki": "[tuning/阻尼.md] bump",
                "hint": "通常 → 加後 bump 阻尼 1-2 級",
                "driving": [],
            })
        if rf >= 3 and rf / n >= 0.25:
            findings.append({
                "severity": "🟡",
                "title": f'出彎前懸吊回彈過快 {rf}/{n} 個彎',
                "wiki": "[tuning/阻尼.md] rebound",
                "hint": "通常 → 加前 rebound 阻尼 1-2 級",
                "driving": [],
            })
        if rr >= 3 and rr / n >= 0.25:
            findings.append({
                "severity": "🟡",
                "title": (f'出彎後懸吊回彈過快 {rr}/{n} 個彎'
                          f'（max Δ {corners["max_exit_rear_rebound_rate"]:.3f}/packet，出彎後車身彈跳）'),
                "wiki": "[tuning/阻尼.md] rebound",
                "hint": "通常 → 加後 rebound 阻尼 1-2 級",
                "driving": [],
            })

    # === 缺陷 3：過 curb 甩飛 ===
    # 三段彎道診斷.md:134「過 curb 容易把車甩飛 → 降低 bump 阻尼」
    # B2 gating：越野賽道路面本來就持續顛簸 + rumble strip 訊號失真 → 不報，避免誤判
    if (corners.get("curb_launch_corners", 0) >= 2
        and surf.get("surface_type") != "offroad"):
        cl = corners["curb_launch_corners"]
        findings.append({
            "severity": "🟡",
            "title": f'過 curb 甩飛事件 {cl} 次（壓縐石後車身被踢開）',
            "wiki": "[tuning/三段彎道診斷.md:134]",
            "hint": "通常 → 降 bump 阻尼 1-2 級（縐石衝擊吸收更柔）",
            "driving": ['壓縐石的角度小一點、車身正一點再壓'],
        })

    # === 缺陷 5：胎不夠熱 + over/understeer 組合（三段彎道診斷.md:135-137）===
    # 全車整體偏冷 + 推頭/過度 → 一次解兩個問題：toe out/in
    # 門檻：依 surface_type 區分（B2 gating）—
    #   公路（race/sport 胎）：< 65°C 偏冷
    #   拉力（rally 胎）：< 55°C 偏冷
    #   越野（offroad 胎）：< 50°C 偏冷（offroad 胎本來就跑得比較涼）
    cold_threshold = {"road": 65, "rally": 55, "offroad": 50}.get(
        surf.get("surface_type", "road"), 65)
    if tires["overall"] and total_corner_pkts > 0:
        ovr = tires["overall"]
        avg_all = (ovr["fl"] + ovr["fr"] + ovr["rl"] + ovr["rr"]) / 4
        if avg_all < cold_threshold:
            us_pct_chk = us_pkts_corner / total_corner_pkts * 100
            os_pct_chk = os_pkts_corner / total_corner_pkts * 100
            if us_pct_chk >= 15 and us_pct_chk > os_pct_chk * 1.5:
                findings.append({
                    "severity": "🟡",
                    "title": f'胎溫偏冷（四輪均 {avg_all:.0f}°C）+ 推頭傾向',
                    "wiki": "[tuning/三段彎道診斷.md:135] 胎冷 + US",
                    "hint": "通常 → 全車 toe out +0.1°（前後各 +0.1，總和 ≤ 0.3°）一次解兩個問題",
                    "driving": ['前 1-2 圈先暖胎再開始衝圈速'],
                })
            elif os_pct_chk >= 15 and os_pct_chk > us_pct_chk * 1.5:
                findings.append({
                    "severity": "🟡",
                    "title": f'胎溫偏冷（四輪均 {avg_all:.0f}°C）+ 轉向過度',
                    "wiki": "[tuning/三段彎道診斷.md:136] 胎冷 + OS",
                    "hint": "通常 → 全車 toe in +0.1°（前後各 +0.1）一次解兩個問題",
                    "driving": ['前 1-2 圈先暖胎再開始衝圈速'],
                })
            else:
                findings.append({
                    "severity": "ℹ️",
                    "title": f'胎溫整體偏冷（四輪均 {avg_all:.0f}°C），抓地未達峰值',
                    "wiki": "[tuning/三段彎道診斷.md:137] 胎冷無方向偏好 + [tuning/下壓力.md]",
                    "hint": "通常 → 加下壓力（前後各加 1-2 級）",
                    "driving": ['先跑 1-2 圈暖胎、用 S 形蛇行加溫'],
                })

    # === 缺陷 7：出彎 yaw 過衝（差速器 accel 過鬆）===
    # 與「出彎後輪左右 slip Δ 過大」（缺陷 1）方向一致但獨立——
    # 即使左右 slip Δ 沒到門檻，整體 yaw 過衝也是 diff 太鬆的訊號。
    if corners["count"] >= 4 and corners.get("yaw_overshoot_corners", 0) >= 3:
        yo = corners["yaw_overshoot_corners"]
        if yo / corners["count"] >= 0.25:
            findings.append({
                "severity": "🟡",
                "title": (f'出彎 yaw 過衝 {yo}/{corners["count"]} 個彎'
                          f'（出彎角速度 > 入彎 1.5×）'),
                "wiki": "[tuning/差速器.md] 後差加速鎖定",
                "hint": "通常 → 加後 diff accel 鎖定 5-10%（讓出彎兩後輪更同步、抑制 yaw 過衝）",
                "driving": ['出彎油門更線性、避免一次踩到底激發 yaw'],
            })

    # === 缺陷 10：出彎「彎太多 + 加油太早」（[wiki/driving/賽車線與彎道基礎.md] 常見錯）===
    # 過 apex 後仍在大角度（≥ 50% 該彎 max steer）已踩半油以上 → 阻礙加速、RWD 易甩。
    # 純駕駛習慣問題（與 build 無關），改變動作就能修。
    if (corners["count"] >= 4
        and corners.get("exit_overturn_corners", 0) >= 3
        and corners["exit_overturn_corners"] / corners["count"] >= EXIT_OVERTURN_CORNER_PCT):
        oc = corners["exit_overturn_corners"]
        is_rwd_or_awd = drivetrain_type in (1, 2)
        # RWD 因甩尾風險嚴重度高一級
        sev = "🟡" if is_rwd_or_awd else "ℹ️"
        rwd_note = "（RWD：尤其甩尾風險）" if drivetrain_type == 1 else ""
        findings.append({
            "severity": sev,
            "title": (f'出彎彎太多 + 加油太早 {oc}/{corners["count"]} 個彎'
                      f'（仍在 ≥ 50% max 轉向就已踩半油）{rwd_note}'),
            "wiki": "[driving/賽車線與彎道基礎.md] 過 apex 後不要彎太多 + "
                    "[driving/RWD駕駛技巧.md] 過彎油門管理",
            "hint": "純駕駛習慣：過 apex 後**同時放鬆方向盤 + 加油**，視覺瞄向**彎外**而非內側",
            "driving": [
                '過 apex 後「先放方向盤再加油」——不要邊轉邊加',
                '視線瞄向出彎外側（不是內側）——眼睛帶手',
            ],
        })

    # === 缺陷 6：S 彎過渡（快速 L↔R）有問題（三段彎道診斷.md:133）===
    if (corners.get("s_transition_count", 0) >= 2 and
        corners.get("s_transition_trouble_count", 0) >= 2):
        st = corners["s_transition_count"]
        tr = corners["s_transition_trouble_count"]
        findings.append({
            "severity": "🟡",
            "title": f'S 彎過渡 {tr}/{st} 對有 under/oversteer',
            "wiki": "[tuning/三段彎道診斷.md:133] 阻尼與 ARB",
            # 方向取決於主症狀（US 或 OS），不直接給；分析師結合該場主症狀判斷
            "hint": "依主症狀方向（看其他 finding）同步調 ARB 與 bump/rebound 阻尼平衡",
            "driving": ['過渡彎間方向盤切換更線性、避免反向打死'],
        })

    # === 缺陷 4：煞車鎖死前後軸比 → 煞車平衡（煞車調校.md）===
    # 煞車期間若前鎖死遠多於後鎖死 → 偏前太多 → 滑桿往後
    # 反之 → 偏後太多 → 滑桿往前
    # 至少要有意義的煞車量才作判斷（>= 60 packet ≈ 1s）
    if brake_balance["braking_packets"] >= 60:
        f_lock = brake_balance["front_lockup_packets"]
        r_lock = brake_balance["rear_lockup_packets"]
        ratio = brake_balance["front_rear_ratio"]
        # 至少有 20 packet 鎖死才值得提（避免微量鎖死打擾）
        if (f_lock + r_lock) >= 20:
            if ratio >= 3 and f_lock >= 20:
                findings.append({
                    "severity": "🟡",
                    "title": (f'煞車前軸鎖死 {f_lock} packet，後軸 {r_lock}（比 {ratio:.1f}:1，'
                              f'煞車偏前 / 前胎飽和）'),
                    "wiki": "[tuning/煞車調校.md] 煞車平衡 + [tuning/四輪定位.md] caster",
                    "hint": "通常 → 煞車平衡往後 2-3% / 加 caster 0.3-0.5° / 硬前懸吊（已飽和才適用）",
                    "driving": ['煞車力道前期更線性、避免一次到底'],
                })
            elif ratio > 0 and ratio <= 0.4 and r_lock >= 20:
                findings.append({
                    "severity": "🟡",
                    "title": (f'煞車後軸鎖死 {r_lock} packet，前軸 {f_lock}（比 1:{1/max(ratio,0.001):.1f}，'
                              f'煞車偏後 / 入彎甩尾風險）'),
                    "wiki": "[tuning/煞車調校.md] 煞車平衡 + [tuning/差速器.md] 後差減速",
                    "hint": "通常 → 煞車平衡往前 2-3% / 加後 diff decel 鎖定 10-20%",
                    "driving": ['trail brake 收得更快、減少入彎時殘留煞車'],
                })

    # === 缺陷 11：依 PI 級的橫向 G 力達標檢查（[wiki/upgrades/輪胎配件.md]）===
    # 把 build 的「操控健康度」與駕駛技術分離 — G 力達標主要取決於 build（胎質 / 胎寬 / 減重 /
    # 下壓力），玩家技術只在彎中能不能逼到極限這層才介入。低於下限 → 多半是 build 問題。
    if pi_grip is not None and pi_grip["status"] == "under":
        gap = pi_grip["gap"]
        # 嚴重度：差距 > 0.3 G 視為大缺口（明顯升一級胎），否則 🟡
        sev = "🔴" if gap > 0.3 else "🟡"
        hi_str = f'{pi_grip["expected_hi"]:.1f}' if pi_grip["expected_hi"] is not None else '—'
        findings.append({
            "severity": sev,
            "title": (f'{pi_grip["class_label"]} 級橫向 G 力未達標：'
                      f'實測 {pi_grip["observed"]:.2f} G / 目標 {pi_grip["expected_lo"]:.1f}-{hi_str} G'
                      f'（差 {gap:.2f} G）'),
            "wiki": "[upgrades/輪胎配件.md] 依 PI 級的橫向 G 力指標 + Mustuff124 G 力指標表",
            "hint": "通常 → 升輪胎（拉力胎→半熱熔→熱熔）或減重；先別急著升馬力。"
                    "若已用最強胎仍未達標，再看 [tuning/下壓力.md] 是否能加更多。",
            "driving": ['彎中敢踩到極限——若實測接近目標下限，可能是駕駛保守而非 build 不足'],
        })
    # （status == "over" 不視為問題：表示 build 操控過剩，玩家可考慮減重換更激進取向；
    # 但不會被歸類為「缺陷」。這個資訊在 Section 6 的詳細表中會看到。）

    # === 缺陷 9：Launch 階段三檔仍打滑（[wiki/driving/RWD駕駛技巧.md]）===
    # gear 1-2 打滑是 RWD/AWD 起步常態，不視為問題；
    # **gear 3 仍 ≥ 30% packet 打滑** → 後胎抓地不夠（HokiHoshi 直接指向 build 問題）。
    if launch is not None and launch["gear3_problem"]:
        # 找 gear 3 的具體數據
        g3 = next((g for g in launch["per_gear"] if g["gear"] == 3), None)
        if g3 is not None:
            findings.append({
                "severity": "🟡",
                "title": (f'起步三檔仍打滑（{g3["loss_pct"]:.0f}% packet slip > 1.0，'
                          f'max slip {g3["max_slip"]:.2f}）→ 後胎抓地不夠'),
                "wiki": "[upgrades/輪胎配件.md] 胎質 / 後胎寬 + [driving/RWD駕駛技巧.md] § Launch",
                "hint": "通常 → 升一級胎質（Sport→Rally→Semi-slick→Slick）或加大後胎寬；"
                        "若胎已最強，再考慮 [upgrades/改造選擇.md] 動力曲線（單渦輪在低檔易爆衝）",
                "driving": [],
            })

    # === 缺陷 B1：下壓力 / aero 不足偵測（下壓力.md）===
    # 高速段（>200 km/h）累積 ≥ 5s 且側向 G p95 顯著低於中速段 p95（< 60%）
    # → 提示「可能下壓力不足」（也可能是高速彎駕駛偏保守，不下死論）
    # 中速段 p95 必須 ≥ 1.5G 才有可比性（否則低速能力本身就不行，不能用此指標）
    if (aero["high_packets"] >= 300  # 5s @ 60 Hz
        and aero["mid_p95_lat_g"] is not None
        and aero["mid_p95_lat_g"] >= 1.5
        and aero["high_p95_lat_g"] is not None
        and aero["high_p95_lat_g"] < aero["mid_p95_lat_g"] * 0.6):
        findings.append({
            "severity": "🟡",
            "title": (f'高速段（>200 km/h, {aero["high_packets"]/60:.1f}s）'
                      f'側向 G p95 = {aero["high_p95_lat_g"]:.2f}'
                      f'（中速段 {aero["mid_p95_lat_g"]:.2f}，可能下壓力不足或高速彎駕駛保守）'),
            "wiki": "[tuning/下壓力.md]",
            "hint": "通常 → 加前後下壓力（先各加 10-20%）；若已最大或追求尾速 → 改 build 取向",
            "driving": ['高速彎敢踩到極限，目前可能還沒摸到車的物理上限'],
        })

    if tires["overall"] and tires["overall"]["fr_delta"] > 10:
        d = tires["overall"]["fr_delta"]
        findings.append({
            "severity": "🔴",
            "title": f'前胎過熱（推頭傾向） +{d:.0f}°C',
            "wiki": "[tuning/胎壓.md] + [tuning/三段彎道診斷.md] 整體 US",
            "hint": "通常與整體推頭同方向：前胎壓 / 前 ARB / 前 camber",
            "driving": ['入彎再慢 3-5 km/h，出彎晚一點再給油'],
        })
    elif tires["overall"] and tires["overall"]["fr_delta"] < -10:
        d = abs(tires["overall"]["fr_delta"])
        findings.append({
            "severity": "🔴",
            "title": f'後胎過熱（轉向過度傾向） +{d:.0f}°C',
            "wiki": "[tuning/胎壓.md] + [tuning/三段彎道診斷.md] 整體 OS",
            "hint": "通常與整體 OS 同方向：後胎壓 / 後 ARB / 後 camber；RWD 注意是 power OS",
            "driving": ['出彎別太早全油門，給油更線性'],
        })
    if slip["per_segment"]:
        ratios = [r["fr_max"] / r["rr_max"] for r in slip["per_segment"] if r["rr_max"] > 0]
        if ratios and statistics.mean(ratios) > 1.5:
            findings.append({
                "severity": "🔴",
                "title": f'前輪滑移 ≈ {statistics.mean(ratios):.1f}× 後輪（推頭證據）',
                "wiki": "—（與「前胎過熱」/「整體推頭」同方向）",
                "hint": "",
                "driving": [],
            })
        elif ratios and statistics.mean(ratios) < 0.7:
            findings.append({
                "severity": "🔴",
                "title": f'後輪滑移 ≈ {1 / statistics.mean(ratios):.1f}× 前輪（轉向過度證據）',
                "wiki": "—（與「後胎過熱」/「整體 OS」同方向）",
                "hint": "",
                "driving": [],
            })
    if susp["total_bottom_packets"] > 30:
        findings.append({
            "severity": "🟡",
            "title": f'懸吊觸底 {susp["total_bottom_packets"]} 個 packet（彈簧過軟 / 車高過低）',
            "wiki": "[tuning/彈簧與車高.md] + [tuning/阻尼.md] bump",
            "hint": "通常 → 拉硬觸底那角彈簧 5-10% / 拉高該角車高 0.5-1 cm / 加 bump 阻尼 1-2 級",
            "driving": [],
        })
    if drvtrn["shift_loss_rpm"] > 500:
        basis_note = ('（基準=峰值馬力 RPM）' if drvtrn["ideal_shift_basis"] == "peak_power_rpm"
                      else '（基準=EngineMaxRpm × 95%，可能不準）')
        findings.append({
            "severity": "🟡",
            "title": f'換檔太早 {drvtrn["shift_loss_rpm"]:.0f} RPM（直線丟動力）{basis_note}',
            "wiki": "[tuning/齒比.md]",
            "hint": "通常 → 拉長個別齒比（蓋過峰值馬力 RPM）或拉長 Final Drive（往 Long）",
            "driving": [f'手排：晚一點換檔，等到聲音接近 {drvtrn["ideal_shift"]:.0f} RPM 再換'],
        })

    # === 缺陷 8：換檔後落點掉出 power band（齒比間距太寬）===
    # 換 N→N+1 後 RPM 穩定到 < power_band_start，代表這個檔位的銜接掉到動力死區
    # 與「換檔太早」獨立——即使換檔點正確、若 ratio 間距太寬也會落到死區
    if drvtrn.get("post_shift_count", 0) >= 5 and drvtrn.get("post_shift_dead_pct", 0) >= 30:
        dp = drvtrn["post_shift_dead_pct"]
        n_shift = drvtrn["post_shift_count"]
        avg_landing = drvtrn["post_shift_avg_rpm"]
        findings.append({
            "severity": "🟡",
            "title": (f'換檔後 {dp:.0f}% 落到 power band 外'
                      f'（{n_shift} 次換檔 / 平均落點 {avg_landing:.0f} RPM '
                      f'/ band 起點 {drvtrn["power_band_start"]:.0f} RPM，齒比間距太寬）'),
            "wiki": "[tuning/齒比.md]",
            "hint": "通常 → 縮短個別齒比間距（把 N→N+1 之間距拉近）或縮短 Final Drive（往 Short）",
            "driving": [],
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
                "wiki": "—（純診斷，無處方）",
                "hint": "",
                "driving": [],
            })
        elif corners["track_bias"] == "right" and tires["overall"] and tires["overall"]["lr_front_delta"] > 3:
            findings.append({
                "severity": "ℹ️",
                "title": f'本場 {corners["right_count"]}/{corners["count"]} 個彎為右彎 → 左前胎偏熱（{tires["overall"]["lr_front_delta"]:+.1f}°C）屬賽道特性，**非調校問題**',
                "wiki": "—（純診斷，無處方）",
                "hint": "",
                "driving": [],
            })

        # Slow throttle reopen → driver too cautious on exit (only flag when meaningful)
        delay = corners.get("avg_throttle_reopen_delay_s")
        if delay is not None and delay > 1.0 and corners["corners_with_lift"] >= 3:
            findings.append({
                "severity": "🟡",
                "title": f'有收油的 {corners["corners_with_lift"]} 個彎中，平均出彎油門重踩要 {delay:.2f}s（出彎略保守）',
                "wiki": "[driving/賽車線與彎道基礎.md]",
                "hint": "駕駛問題優先；若拉不回時間考慮提升出彎抓地（後 ARB 軟、後胎壓降）",
                "driving": [f'彎心後早 0.2-0.3s 把油門踩回去（目前 {delay:.2f}s → ~{max(0.3, delay - 0.3):.2f}s）'],
            })

        # Many corners showing wheelspin on exit
        if corners["wheelspin_exit_corners"] > corners["count"] * 0.3:
            pct = corners["wheelspin_exit_corners"] / corners["count"] * 100
            findings.append({
                "severity": "🟡",
                "title": f'{corners["wheelspin_exit_corners"]}/{corners["count"]} 個彎（{pct:.0f}%）出彎時後輪打滑（出彎給油過猛 / 差速器過硬）',
                "wiki": "[tuning/差速器.md] + [driving/賽車線與彎道基礎.md]",
                "hint": "RWD：節流量管理優先；AWD：後 diff accel 鬆 / 動力分配往前；FWD：通常非根因",
                "driving": ['出彎油門更線性，前 0.5s 控制在 70% 不要全踩'],
            })

        # Per-corner understeer/oversteer prevalence
        if corners["understeering_corners"] > corners["count"] * 0.5:
            pct = corners["understeering_corners"] / corners["count"] * 100
            findings.append({
                "severity": "🟡",
                "title": f'{corners["understeering_corners"]}/{corners["count"]} 個彎（{pct:.0f}%）前輪滑移 > 後輪 1.5×（**彎中**推頭）',
                "wiki": "—（與「整體推頭」/「中段 US 主導」同方向）",
                "hint": "",
                "driving": [],
            })

    # Crash episodes
    if crash_count > 0:
        excluded_s = len(crash_excluded) / 60
        if crash_count > 2:
            findings.append({
                "severity": "🟡",
                "title": f'撞車 {crash_count} 次（共 {len(crash_excluded)} packet ≈ {excluded_s:.1f}s 從統計排除，撞太多了）',
                "wiki": "[driving/賽車線與彎道基礎.md]",
                "hint": "撞車是駕駛問題不是調校問題——先把路線/煞車點/入彎速度做穩",
                "driving": ['撞車多半是入彎太用力、路線太靠外側、或不熟賽道。先放慢 5-10 km/h 練線，熟了再加速'],
            })
        else:
            findings.append({
                "severity": "ℹ️",
                "title": f'撞車 {crash_count} 次（共 {len(crash_excluded)} packet ≈ {excluded_s:.1f}s 從統計排除，G-force / decel / 觸底已不含）',
                "wiki": "—（已從統計排除，無處方）",
                "hint": "",
                "driving": [],
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
                "wiki": "[settings/駕駛輔助與輸入設定.md]（檢查 Braking Assist 是否開啟）",
                "hint": "資料異常，無調校處方；下次重跑前確認 Braking Assist 關閉",
                "driving": [],
            })
        else:
            findings.append({
                "severity": "ℹ️",
                "title": 'Brake 欄位全 0 且無明顯減速 → 可能本場真的沒煞車，或 Brake 輸入未傳送',
                "wiki": "—（純診斷）",
                "hint": "",
                "driving": [],
            })

    # === Build markdown ===
    o = []
    o.append('# 賽事摘要')
    o.append('')
    crash_note = f'，{len(crash_excluded)} 撞車' if crash_count > 0 else ''
    n_race_off = sum(1 for r in rows if r['IsRaceOn'] != '1')
    super_note = f'、{n_superseded} 已被後續 redo 取代' if n_superseded > 0 else ''
    o.append(f'> 自動產生於 raw.csv ({len(rows)} 筆 → {len(valid)} 有效；排除 {n_race_off} IsRaceOn=0{super_note}{crash_note}）。資料源：[meta.json](meta.json) / [raw.csv](raw.csv)')
    if n_superseded > 0:
        o.append('>')
        o.append(f'> ⚠️ **本場含 {meta["rewinds"]["count"]} 次 rewind**——已自動排除 **{n_superseded} packet ≈ {n_superseded/60:.1f}s** 你 rewind 前的失敗嘗試。分析以你最終定案的線為準（每個 CRT 時刻只保留錄製時間最晚的 packet）。')
    o.append('>')
    o.append('> ℹ️ **US/OS 偵測方法**：用 yaw-rate 法（比較實際 yaw 與物理預期 `lat_acc / speed`），對所有 PI 級／速度通用，比舊 slip-angle 比值法精準。slip angle 作為「胎是否接近 grip 極限」的次級確認信號。')
    o.append('')

    # --- Headline ---
    o.append('## TL;DR')
    o.append('')
    if findings:
        # 排序：嚴重度從高到低
        sev_order = {"⛔": 0, "🔴": 1, "🟡": 2, "⚠️": 3, "ℹ️": 4}
        sorted_findings = sorted(findings, key=lambda f_: sev_order.get(f_["severity"], 9))

        # === 症狀清單（觀測 + wiki 指引；不下死論的調校處方）===
        # 設計原則：summarize 是「觀測層」——列出客觀症狀並指向 wiki 章節，附一
        # 句話「通常方向」作為粗略指引。實際處方由 race-analyst 結合車況、當前
        # tune、駕駛軌跡綜合判斷後才下。
        o.append('### 症狀（依嚴重度排序）')
        o.append('')
        o.append('> summarize 的職責是**觀測 + 指向 wiki**，不直接給最終調校處方。'
                 '具體該改什麼要結合車輛資料、當前 tune、駕駛技術綜合判斷——'
                 '請用 `/race-analyst` 取得完整建議。')
        o.append('')
        # title 在第一行；hint 換行至第二行（兩個尾隨空格 = Markdown 強制換行）。
        # wiki 對照不放 TL;DR——race-analyst 會依症狀關鍵字自行查 Phase 2 的對應
        # 表，TL;DR 留乾淨；wiki 路徑仍存在 finding dict 內供日後其他段落引用。
        for f_ in sorted_findings:
            title_line = f'- {f_["severity"]} **{f_["title"]}**'
            hint_str = f_.get("hint", "")
            if hint_str:
                o.append(title_line + '  ')
                o.append(f'  💡 {hint_str}')
            else:
                o.append(title_line)
        o.append('')

        # === 駕駛建議（保留：universal、低風險、玩家可立刻試）===
        seen_d: set[str] = set()
        driving_actions: list[str] = []
        for f_ in sorted_findings:
            for action in f_.get("driving", []):
                if action and action not in seen_d:
                    driving_actions.append(action)
                    seen_d.add(action)

        if driving_actions:
            o.append('### 🎮 駕駛建議（不需改車，下次直接試）')
            o.append('')
            for i, action in enumerate(driving_actions, 1):
                o.append(f'{i}. {action}')
            o.append('')

        # === 接下來：明確指向 race-analyst ===
        o.append('### 📍 接下來')
        o.append('')
        o.append('上述「💡 通常方向」**僅為粗略指引**，不要直接照抄。實際調校建議請用 '
                 '`/race-analyst`（會綜合車輛用途、當前 tune、駕駛軌跡、wiki 處方表後'
                 '給出**排優先順序、互不衝突**的具體動作）。')
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
    car_db = meta["car"].get("db") or {}
    car_label = car_db.get("name") or f'ordinal {meta["car"]["ordinal"]}'
    name_str = car_db.get("name") or ""
    car_extras = []
    if car_db.get("manufacturer") and car_db["manufacturer"] not in name_str:
        car_extras.append(car_db["manufacturer"])
    if car_db.get("model_year") and str(car_db["model_year"]) not in name_str:
        car_extras.append(str(car_db["model_year"]))
    if car_db.get("purpose"):
        car_extras.append(f'用途：{car_db["purpose"]}')
    extras_str = f'（{"，".join(car_extras)}）' if car_extras else ''
    o.append(f'| 車輛 | **{car_label}**{extras_str} — ordinal {meta["car"]["ordinal"]}, PI {meta["car"]["performance_index"]}, class {meta["car"]["class"]} |')
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
        rr_bad = tires.get("rr_unreliable", False)
        o.append(f'### 1. 輪胎溫度分布')
        o.append('')
        skip_note = '（已排除 Lap 0 暖胎圈）' if tires["skipped_first_segment"] else ''
        if rr_bad:
            o.append(f'> ⚠️ **TireTempRearRight 全程與 RL 完全相同（FH5 已知 bug）**——本場 RR 視為不可信，後胎統計改以 RL 單值代表，左右後差不輸出。')
            o.append('')
            o.append(f'排除暖胎後{skip_note}的平均：FL={ovr["fl"]:.0f}°C  FR={ovr["fr"]:.0f}°C  RL={ovr["rl"]:.0f}°C  RR=n/a (mirrors RL)')
        else:
            o.append(f'排除暖胎後{skip_note}的平均：FL={ovr["fl"]:.0f}°C  FR={ovr["fr"]:.0f}°C  RL={ovr["rl"]:.0f}°C  RR={ovr["rr"]:.0f}°C')
        o.append('')
        o.append(f'- 前胎平均：**{ovr["front_avg"]:.0f}°C**')
        rear_label = '後胎（RL，RR 不可信）' if rr_bad else '後胎平均'
        o.append(f'- {rear_label}：**{ovr["rear_avg"]:.0f}°C**')
        o.append(f'- 前後溫差：**{ovr["fr_delta"]:+.1f}°C**')
        if rr_bad:
            o.append(f'- 左右前差：{ovr["lr_front_delta"]:+.1f}°C  /  左右後差：n/a')
        else:
            o.append(f'- 左右前差：{ovr["lr_front_delta"]:+.1f}°C  /  左右後差：{ovr["lr_rear_delta"]:+.1f}°C')
        o.append(f'- 最熱角：**{tires["hottest_corner"].upper()}**（{ovr[tires["hottest_corner"]]:.0f}°C）')
        o.append('')
        o.append('**判讀指南**：')
        o.append('- 前後差 > +10°C → 推頭（understeer），考慮降前胎壓 / 軟前防傾 / 加前外傾')
        o.append('- 前後差 < -10°C → 轉向過度（oversteer），考慮降後胎壓 / 軟後防傾 / 加後外傾')
        if not rr_bad:
            o.append('- 左右差 > 5°C → 配重不平衡或單側過度負重，檢查彎道分布')
        o.append('- 單一角 > 100°C → 胎面熱衰退，需要更多冷卻（降胎壓 / 加 caster）')
        o.append('')
        o.append('每段詳細：')
        o.append('')
        o.extend(fmt_tire_table(tires))
        o.append('')

    # Slip detail
    o.append('### 2. 滑移分析（grip 使用率）')
    o.append('')
    o.append('TireSlipRatio：縱向滑移（加速/煞車時輪轉速 vs 車速）。0 = 100% 抓地，>1.0 = 失抓。')
    o.append('TireSlipAngle：橫向滑移，FH5 為 normalized 值——**>1.0 表示已失去 grip**（grip 使用率超過極限）。')
    o.append('')
    o.extend(fmt_slip_table(slip))
    o.append('')
    o.append('> 推頭 / 轉向過度判定**已改用 yaw-rate 法**（見 § 8 過彎分析），更準確：')
    o.append('> 比較實際 yaw rate vs 物理預期 yaw rate（= lat_acc / speed），不再用 slip angle 比值')
    o.append('> （舊邏輯把正常 turn-in 幾何誤判為推頭）。')
    o.append('')

    # Suspension detail
    o.append('### 3. 懸吊行程')
    o.append('')
    o.append('NormalizedSuspensionTravel：0 = 完全伸長，1.0 = 完全壓縮（觸底）。')
    o.append('wiki 健康區：硬核指南 **15-85%**、HokiHoshi **20-80%**（兩派方向一致——全程不該到頂或到底）。')
    o.append('')
    o.extend(fmt_suspension_table(susp))
    o.append('')
    o.append('**在 15-85% 健康範圍佔比 + std 振幅**（對照 wiki/tuning/遙測使用指南.md）：')
    o.append('')
    o.extend(fmt_suspension_range_table(susp))
    o.append('')
    if susp["total_bottom_packets"] > 0:
        o.append(f'**觸底總計**：{susp["total_bottom_packets"]} 個 packet ≈ {susp["total_bottom_packets"] / 60:.1f}s 觸底時間')
    o.append('')
    o.append('**判讀指南**：')
    o.append('- 任一輪持續 > 0.95 → 該角彈簧過軟或車高過低（→ 拉硬彈簧 5-10% / 拉高車高 0.5-1 cm / 加大壓縮阻尼 1-2 級）')
    o.append('- 平均 < 0.5 → 彈簧過硬，浪費抓地（行程沒用滿）')
    o.append('- **健康範圍佔比 < 60%**（表中粗體）→ 該角行程偏離 [0.15, 0.85]；若 max 高 → 偏軟，若 avg 低 → 偏硬')
    o.append('- **std > 0.10** → 平路波動明顯（紫粉色條視覺上「跳很大」）→ 該角彈簧偏軟，考慮調硬')
    o.append('- **std < 0.03** → 波動極小，彈簧可能偏硬（也可能賽道平整，需主觀對照）')
    o.append('- 左右差距大 → 防傾桿 / 配重不平衡')
    o.append('- 前後差距大 → 配重偏前/後，考慮車高與彈簧比例')
    o.append('- 車仍好開但 std 偏小 → HokiHoshi 提醒：依路況與駕駛風格略有差異，不必硬調')
    o.append('')
    o.append('> ⚠️ 「車身觸底」≠「懸掛觸底」：本表只能偵測**懸掛觸底**（NormalizedSuspensionTravel > 0.95）。'
             '若駕駛感覺被路面「敲」、聽到車底碰撞聲但表中沒觸底，那是車身觸底——需抬高車身高度。')
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
    _loss = drvtrn["shift_loss_rpm"]  # = ideal - avg；正數 = 低於理想（早換），負數 = 高於理想（晚換）
    if abs(_loss) < 1:
        _shift_label = '與理想一致'
    elif _loss > 0:
        _shift_label = f'低於理想 {_loss:.0f} RPM，換得早'
    else:
        _shift_label = f'高於理想 {-_loss:.0f} RPM，換得晚'
    o.append(f'- 平均換檔點：**{drvtrn["avg_shift_rpm"]:.0f} RPM**（{_shift_label}）')
    o.append(f'- 全程在動力區的時間：**{drvtrn["in_power_band_pct"]:.1f}%**')
    o.append(f'- 全程在 ≥ 理想換檔點的時間：{drvtrn["in_redline_pct"]:.1f}%')
    o.append(f'- 全程曾達到的最高 RPM：{drvtrn["max_rpm_seen"]:.0f}（{drvtrn["max_rpm_seen"] / drvtrn["engine_max"] * 100:.1f}% EngineMaxRpm）')
    o.append('')
    if drvtrn["shift_points"]:
        o.append('每檔換檔詳細：')
        o.append('')
        o.append('| 換檔 | 平均 RPM | 偏離理想 | 次數 |')
        o.append('|------|---------|---------|------|')
        for (g_from, g_to), pts in sorted(drvtrn["shift_points"].items()):
            avg = statistics.mean(pts)
            diff = drvtrn["ideal_shift"] - avg  # 正 = 低於理想
            if abs(diff) < 1:
                diff_cell = '一致'
            elif diff > 0:
                diff_cell = f'低 {diff:.0f}'
            else:
                diff_cell = f'高 {-diff:.0f}'
            o.append(f'| {g_from}→{g_to} | {avg:.0f} | {diff_cell} | {len(pts)} |')
        o.append('')
    o.append('每檔停留時間：')
    o.append('')
    o.append('| 檔位 | 時間佔比 |')
    o.append('|------|---------|')
    for g, pct in drvtrn["gear_distribution"].items():
        o.append(f'| {g} | {pct:.1f}% |')
    o.append('')
    # === 缺陷 8：post-shift 落點 ===
    if drvtrn.get("post_shift_count", 0) >= 1:
        o.append('**換檔後落點**（缺陷 8：齒比間距驗證）：')
        o.append('')
        o.append(f'- upshift 次數：{drvtrn["post_shift_count"]}')
        o.append(f'- 換檔後 0.2s RPM 平均：**{drvtrn["post_shift_avg_rpm"]:.0f}**')
        o.append(f'- power band 起點：{drvtrn["power_band_start"]:.0f} RPM（基準: {drvtrn["power_band_basis"]}）')
        o.append(f'- 落到 power band **外**比例：**{drvtrn["post_shift_dead_pct"]:.0f}%**')
        if drvtrn["post_shift_dead_pct"] >= 30:
            o.append('  → 齒比間距太寬，建議縮短個別齒比或縮短 Final Drive')
        o.append('')

    o.append('**判讀指南**：')
    o.append('- 換檔點離理想 < 200 RPM：很好')
    o.append('- 換檔點低於理想 > 500 RPM：太早，丟動力（手排晚一點換、自排調整齒比）')
    o.append('- 換檔點**高於**理想 > 200 RPM：可能換檔太晚，過了功率帶反而失動力——縮短該檔齒比')
    o.append('- 在動力區時間 < 50%：齒比可能太密或太疏，沒讓引擎在甜蜜點工作')
    o.append('- 某檔位佔比異常低：可能可以略過該檔（常見於 6 檔車的 5 檔）')
    o.append('- **換檔後落到 power band 外 > 30%** → 齒比間距太寬，銜接掉到動力死區')
    o.append('')

    # === 4.4 Launch 階段（缺陷 9） ===
    if launch is not None:
        dt_label = DRIVETRAIN_NAMES.get(launch["drivetrain"], "?")
        o.append(f'#### 4.4 Launch 起步分析（缺陷 9，{dt_label} 專屬）')
        o.append('')
        o.append(f'起步點：packet #{launch["start_packet"]}（前 {launch["distance_m"]:.0f} m / '
                 f'{launch["duration_s"]:.1f} s 視窗）')
        o.append('')
        if launch["per_gear"]:
            o.append('| 檔 | packet | WOT% | 平均後輪 slip | 最大 slip | slip > 1.0 比例 |')
            o.append('|----|--------|------|---------------|-----------|----------------|')
            for g in launch["per_gear"]:
                bold = '**' if g["gear"] >= 3 and g["loss_pct"] >= LAUNCH_GEAR3_SLIP_PCT * 100 else ''
                o.append(f'| {g["gear"]} | {g["packets"]} | {g["wot_pct"]:.0f}% | '
                         f'{g["avg_slip"]:.2f} | {g["max_slip"]:.2f} | '
                         f'{bold}{g["loss_pct"]:.0f}%{bold} |')
            o.append('')
        o.append('**判讀**（對照 [wiki/driving/RWD駕駛技巧.md] § Launch）：')
        o.append('- gear 1-2 打滑是 RWD/AWD 起步**正常現象**，無需處理')
        o.append('- **gear 3 仍 ≥ 30% packet slip > 1.0** → **後胎抓地不夠**（HokiHoshi 直接指向 build 問題）')
        o.append('- WOT% < 80% 時表示玩家未持續全油，數據參考價值低（試試「就直接油門踩到底，看頂速升檔」）')
        if launch["gear3_problem"]:
            o.append('')
            o.append('> ⚠️ 本場三檔仍打滑 — 升一級胎質或加大後胎寬，此症狀不是駕駛技術可解決的。')
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
    o.append(f'| Trail braking（煞車 >50 + \\|latG\\| > 0.4，帶煞入彎） | {inputs["trail_brake_pct"]:.1f}%（占有煞車 packet {inputs["trail_brake_share_of_braking"]:.0f}%） |')
    o.append(f'| 油煞同踩（油門 + 煞車同時 >50，左腳煞車或誤踩） | {inputs["brake_throttle_overlap_pct"]:.1f}% |')
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

    # === 缺陷 11：依 PI 級的橫向 G 力達標檢查 ===
    if pi_grip is not None:
        o.append('**PI 級橫向 G 力達標檢查**（缺陷 11，對照 [wiki/upgrades/輪胎配件.md]）：')
        o.append('')
        source_str = {
            "corners_top3": '彎內 top-3 peak 平均（穩健，已過濾撞擊／sweeper）',
            "corners_max":  '彎內 max peak（彎數 < 3，無法用 top-3 平均）',
            "raw":          '⚠️ raw IMU 最大值（無偵測到的彎，可能含微撞擊殘留）',
        }.get(pi_grip["source"], '—')
        if pi_grip["expected_lo"] is None:
            # D / C 級無基準
            o.append(f'- PI {pi_grip["pi"]} ({pi_grip["class_label"]} 級)：此級距無 G 力基準資料。')
            o.append(f'- 實測：**{pi_grip["observed"]:.2f} G**（資料源：{source_str}）')
        else:
            hi_str = f'{pi_grip["expected_hi"]:.1f}' if pi_grip["expected_hi"] is not None else '—（無上限）'
            status_str = {
                "under":  f'❌ **未達標**（差 {pi_grip["gap"]:.2f} G）',
                "target": '✅ 達標',
                "over":   f'⬆️ 超標（高 {pi_grip["gap"]:.2f} G，操控過剩可考慮減重換更激進取向）',
            }.get(pi_grip["status"], '—')
            o.append(f'- PI {pi_grip["pi"]} ({pi_grip["class_label"]} 級) 目標：'
                     f'**{pi_grip["expected_lo"]:.1f} ~ {hi_str} G**')
            o.append(f'- 實測：**{pi_grip["observed"]:.2f} G**（資料源：{source_str}） → {status_str}')
            if pi_grip.get("avg_peak") is not None:
                o.append(f'- 參考：所有彎 peak G 平均 **{pi_grip["avg_peak"]:.2f} G**（反映常態 grip 使用率，非上限）')
            if pi_grip["status"] == "under":
                o.append('  → 通常 → 升輪胎或減重；若彎中駕駛已逼到極限再考慮其他方向')
            elif pi_grip["status"] == "over" and pi_grip["gap"] > 1.0:
                o.append('  → ⚠️ 差距 > 1 G 超出常理，可能含未過濾的微撞擊；建議交叉看「常態 G 使用率」是否也異常')
        o.append('')
    o.append('**最大減速瞬間 top 8**（推測重煞車點，每筆抽 5 packet ≈ 83ms 視窗）：')
    o.append('')
    o.append('| 段 | 賽事時間 (s) | 減速 G | 速度變化 (km/h) |')
    o.append('|----|-------------|--------|-----------------|')
    for ev in decels[:8]:
        o.append(f'| Lap {ev["lap"]} | {ev["crt"]:.2f} | {ev["decel_g"]:.2f} | {ev["from_kmh"]:.0f}→{ev["to_kmh"]:.0f} |')
    o.append('')

    # === 缺陷 4：煞車鎖死前後軸比 ===
    if brake_balance["braking_packets"] >= 60:
        bb = brake_balance
        o.append('**煞車鎖死前後軸分布**（缺陷 4：煞車平衡診斷，對照 [wiki/tuning/煞車調校.md]）：')
        o.append('')
        o.append(f'- 煞車中 packet（Brake > 200）：**{bb["braking_packets"]}**')
        o.append(f'- 前軸鎖死（FL 或 FR slip ratio > 1.0）：**{bb["front_lockup_packets"]} packet**')
        o.append(f'- 後軸鎖死（RL 或 RR slip ratio > 1.0）：**{bb["rear_lockup_packets"]} packet**')
        o.append(f'- 同時前後鎖死：{bb["both_packets"]} packet')
        ratio = bb["front_rear_ratio"]
        if ratio == float('inf'):
            ratio_str = '前 only（後完全沒鎖）'
        elif ratio == 0:
            ratio_str = '後 only（前完全沒鎖）'
        else:
            ratio_str = f'**{ratio:.2f}:1**（前/後）'
        o.append(f'- 前/後鎖死比：{ratio_str}')
        o.append('')
        o.append('> 比 ≥ 3:1 → 偏前太多（滑桿往後）；比 ≤ 0.4:1 → 偏後太多（滑桿往前）。')
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
    # === B2：路面類型分類 ===
    surface_label = {"road": "🛣️ 公路",
                     "rally": "🪨 拉力（混合）",
                     "offroad": "🏜️ 越野"}.get(surf.get("surface_type", "road"), "—")
    o.append(f'- **路面類型**：{surface_label}'
             f'（avg surface rumble {surf.get("avg_surface_rumble", 0):.3f}, '
             f'avg puddle {surf.get("avg_puddle_depth", 0):.3f}, '
             f'rumble strip {surf.get("rumble_strip_pct", 0):.1f}%）')
    o.append('  → 用途：套用對應的 wiki 修正表（[公路調校修正表] / [越野調校修正表]），'
             '同時調整胎冷／curb-launch 等門檻')
    o.append('')

    # === B1：下壓力 / aero 速度區段對比 ===
    if aero["high_packets"] >= 60 or aero["mid_packets"] >= 600:
        o.append('**速度區段側向 G**（缺陷 B1：aero / 下壓力診斷，對照 [wiki/tuning/下壓力.md]）：')
        o.append('')
        o.append('| 速度區間 | packet 數 | 時間 | p95 側向 G |')
        o.append('|----------|-----------|------|------------|')
        for label, pkts, p95 in [
            ("低速 < 100 km/h", aero["low_packets"], aero["low_p95_lat_g"]),
            ("中速 100-200 km/h", aero["mid_packets"], aero["mid_p95_lat_g"]),
            ("高速 > 200 km/h", aero["high_packets"], aero["high_p95_lat_g"]),
        ]:
            p95_str = f'{p95:.2f}' if p95 is not None else '—'
            o.append(f'| {label} | {pkts} | {pkts/60:.1f}s | {p95_str} |')
        o.append('')
        o.append('> 高速 p95 < 中速 p95 × 60% → 可能下壓力不足（也可能高速彎駕駛偏保守）')
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

        # === 缺陷 0：彎內三段（入彎/中段/出彎）症狀切片 ===
        # 對應 wiki/tuning/三段彎道診斷.md 的不同處方表
        o.append('**彎內三段（入彎/中段/出彎）症狀切片**（對照 [wiki/tuning/三段彎道診斷.md] 不同處方）：')
        o.append('')
        o.append('| 段 | US 主導彎 | OS 主導彎 | 該段 US 時間% | 該段 OS 時間% |')
        o.append('|----|-----------|-----------|----------------|----------------|')
        for ph_key, ph_label in [('entry', '入彎'), ('mid', '中段'), ('exit', '出彎')]:
            o.append(f'| **{ph_label}** | '
                    f'{corners[ph_key + "_us_corners"]}/{corners["count"]} | '
                    f'{corners[ph_key + "_os_corners"]}/{corners["count"]} | '
                    f'{corners[ph_key + "_us_time_pct"]:.1f}% | '
                    f'{corners[ph_key + "_os_time_pct"]:.1f}% |')
        o.append('')
        o.append('> 「主導彎」= 該段該症狀佔該段 packet 數 ≥ 30% 且 ≥ 對手 2×。'
                 '入彎與中段 US 主導 → 不同處方（看 [三段彎道診斷.md] 各段對策清單）。')
        o.append('')

        # === 缺陷 1：左右輪 slip ratio Δ（差速器鎖定診斷）===
        o.append('**左右輪 slip ratio Δ**（缺陷 1：差速器鎖定診斷，對照 [wiki/tuning/差速器.md]）：')
        o.append('')
        o.append(f'- 出彎後輪 max Δ：**{corners["max_exit_lr_rear_delta"]:.2f}**（> 0.20 視為過大；異常彎 {corners["exit_diff_rear_loose_corners"]}/{corners["count"]}） → 後 diff accel')
        o.append(f'- 出彎前輪 max Δ：**{corners["max_exit_lr_front_delta"]:.2f}**（> 0.20 視為過大；異常彎 {corners["exit_diff_front_loose_corners"]}/{corners["count"]}） → 前 diff accel (FWD/AWD)')
        o.append(f'- 入彎後輪 Δ 過大彎：**{corners["entry_diff_rear_loose_corners"]}/{corners["count"]}** → 後 diff decel')
        o.append('')

        # === 缺陷 2：懸吊 d/dt（壓縮/回彈速度，阻尼診斷）===
        o.append('**懸吊壓縮/回彈速度**（缺陷 2：阻尼診斷，門檻 0.10/packet ≈ 6/s）：')
        o.append('')
        o.append('| 項目 | 異常彎數 | max Δ |')
        o.append('|------|----------|-------|')
        o.append(f'| 入彎前懸吊壓縮 | {corners["entry_front_overcompress_corners"]}/{corners["count"]} | {corners["max_entry_front_compress_rate"]:.3f} |')
        o.append(f'| 入彎後懸吊壓縮 | {corners["entry_rear_overcompress_corners"]}/{corners["count"]} | — |')
        o.append(f'| 出彎前懸吊回彈 | {corners["exit_front_rebound_high_corners"]}/{corners["count"]} | — |')
        o.append(f'| 出彎後懸吊回彈 | {corners["exit_rear_rebound_high_corners"]}/{corners["count"]} | {corners["max_exit_rear_rebound_rate"]:.3f} |')
        o.append('')
        o.append('> 入彎壓縮過快 → bump 阻尼不足 / 彈簧太軟。出彎回彈過快 → rebound 阻尼不足。')
        o.append('')

        # === 缺陷 3 / 6 / 7 / 10：過 curb / S 彎過渡 / yaw 過衝 / 出彎彎太多 ===
        cl = corners.get("curb_launch_corners", 0)
        st = corners.get("s_transition_count", 0)
        st_t = corners.get("s_transition_trouble_count", 0)
        yo = corners.get("yaw_overshoot_corners", 0)
        ot = corners.get("exit_overturn_corners", 0)
        if cl + st + yo + ot > 0:
            o.append('**其他事件偵測**：')
            o.append('')
            if cl > 0:
                o.append(f'- 過 curb 甩飛事件：**{cl} 次**（rumble strip + 懸吊 spike + yaw deviation） → 降 bump 阻尼')
            if st > 0:
                o.append(f'- S 彎過渡（< 1.0s 內 L↔R 切換）：**{st} 對**（其中 {st_t} 對有 us/os 異常）')
            if yo > 0:
                o.append(f'- 出彎 yaw 過衝（出彎 yaw > 入彎 1.5×）：**{yo}/{corners["count"]} 個彎** → 後 diff accel 鎖定不足')
            if ot > 0:
                tot = corners.get("exit_overturn_total_packets", 0)
                o.append(f'- **出彎彎太多 + 加油太早**：**{ot}/{corners["count"]} 個彎**（共 {tot} packet ≈ {tot/60:.1f}s 過 apex 後仍 ≥ 50% max 轉向 + Accel ≥ 128） → 駕駛習慣，過 apex 後**先放方向盤再加油**')
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
    car_name_str = f' name="{car_db["name"]}"' if car_db.get("name") else ''
    car_purpose_str = f' purpose={car_db["purpose"]}' if car_db.get("purpose") else ''
    o.append(f'car           :{car_name_str} ordinal={meta["car"]["ordinal"]} PI={meta["car"]["performance_index"]} class={meta["car"]["class"]} drivetrain={drivetrain_name} cyl={meta["car"]["num_cylinders"]}{car_purpose_str}')
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
        rr_str = 'unreliable[mirrors_RL]' if tires.get("rr_unreliable") else f'{tires["overall"]["rr"]:.0f}'
        o.append(f'  tire_temps  : FL={tires["overall"]["fl"]:.0f} FR={tires["overall"]["fr"]:.0f} RL={tires["overall"]["rl"]:.0f} RR={rr_str} (front-rear delta {tires["overall"]["fr_delta"]:+.1f}°C, units=°C)')
    if slip["per_segment"]:
        ratios = [r["fr_max"] / r["rr_max"] for r in slip["per_segment"] if r["rr_max"] > 0]
        if ratios:
            o.append(f'  slip_ratio  : front_max ≈ {statistics.mean([r["fr_max"] for r in slip["per_segment"]]):.3f}, rear_max ≈ {statistics.mean([r["rr_max"] for r in slip["per_segment"]]):.3f} (front/rear ≈ {statistics.mean(ratios):.2f}x)')
    if total_corner_pkts > 0:
        o.append(f'  understeer  : moderate+ {us_moderate} pkt ({us_moderate_pct:.1f}%), severe {us_severe} ({us_severe_pct:.1f}%), confirmed {us_confirmed_pct:.0f}%')
        o.append(f'  oversteer   : moderate+ {os_moderate} pkt ({os_moderate_pct:.1f}%), severe {os_severe} ({os_severe_pct:.1f}%), confirmed {os_confirmed_pct:.0f}%')
    o.append(f'  suspension  : bottom_count={susp["total_bottom_packets"]}, max_per_corner=FL/{max(r["fl_max"] for r in susp["per_segment"]):.2f} FR/{max(r["fr_max"] for r in susp["per_segment"]):.2f} RL/{max(r["rl_max"] for r in susp["per_segment"]):.2f} RR/{max(r["rr_max"] for r in susp["per_segment"]):.2f}')
    if dyno is not None:
        o.append(f'  dyno        : peak_power_rpm={dyno["peak_power_rpm"]:.0f} (peak_power={dyno["peak_power"]:.0f}), peak_torque_rpm={dyno["peak_torque_rpm"]:.0f}')
    else:
        o.append('  dyno        : not_available (raw.csv lacks Power/Torque or insufficient samples)')
    o.append(f'  rpm_observed: max={rpm_obs["max"]:.0f}, p99={rpm_obs["p99"]:.0f}, p95={rpm_obs["p95"]:.0f}, engine_max={rpm_obs["engine_max"]:.0f}'
             + (' [hard_limiter≠redline]' if rpm_obs["warn_hard_limiter"] else ''))
    o.append(f'  drivetrain  : avg_shift={drvtrn["avg_shift_rpm"]:.0f} RPM (ideal {drvtrn["ideal_shift"]:.0f} basis={drvtrn["ideal_shift_basis"]}, loss {drvtrn["shift_loss_rpm"]:+.0f}), in_power_band={drvtrn["in_power_band_pct"]:.0f}% basis={drvtrn["power_band_basis"]}')
    o.append(f'  inputs      : throttle_full={inputs["throttle_full_pct"]:.0f}%, brake_max={inputs["brake_max"]}/255 {"(BRAKING_ASSIST?)" if inputs["brake_appears_disabled"] else ""}, trail_brake={inputs["trail_brake_pct"]:.1f}% (share_of_braking={inputs["trail_brake_share_of_braking"]:.0f}%), brake_throttle_overlap={inputs["brake_throttle_overlap_pct"]:.1f}%, coast={inputs["coast_pct"]:.1f}%')
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
        o.append(f'                slip_us_corners={corners["understeering_corners"]}/{corners["count"]}, '
                f'slip_os_corners={corners["oversteering_corners"]}/{corners["count"]} '
                f'(legacy slip-ratio 法，僅供參考；正確 US/OS 看上方 yaw 法)')
        o.append(f'                wheelspin_exit_corners={corners["wheelspin_exit_corners"]}/{corners["count"]}')
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
