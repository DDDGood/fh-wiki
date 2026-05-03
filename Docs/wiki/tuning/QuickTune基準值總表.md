---
title: QuickTune 基準值總表（Part 2）
category: tuning
order: 120
tags: [QuickTune, 參考, 基準值, 胎壓, 定位, 防傾桿, 彈簧, 車高, 阻尼, 煞車, 差速器, 齒比, 空力]
related_cars: []
pi_class: []
game: FH5
version: 未標註
status: draft
sources:
  - Docs/_sources/地平線5_QuickTune完整調校指南_整理版.md
last_updated: 2026-04-21
revisions:
  - { date: 2026-04-21, note: 初版，源自 QuickTune Part 2：General Tuning }
---

# QuickTune 基準值總表

本表是 QuickTune 體系中 **10 個調校參數的基準值**，所有後續章節的修正都以此為起點。

先依 [車型分類框架](../cars/車型分類框架.md) 查出車型，再對照本表查基準值。

---

## 1. 輪胎（Tires）

### 各胎種基準胎壓（PSI）

| 胎種 | 胎壓 |
|---|---|
| Stock | 31.0 |
| Street | 31.0 |
| Sport | 31.5 |
| Semi Race | 32.0 |
| Race Slicks | 32.5 |
| Snow | 30.5 |
| Vintage Race | 29.0 |
| Off-road | 25.0 |
| Rally | 25.5 |
| Off-road Race | 26.0 |
| Vintage Rally | 22.5 |
| Drift | 35.0 |
| Drag | 20.5 |

### 高性能 / 賽車修正

下列車型在基準胎壓上 **+0.5 PSI**：
- High Performance Car
- Race Car
- Race Truck
- Prototype Race Car
- GP Race Car
- Off-road Race Truck

---

## 2. 定位（Alignment）

### Camber（外傾角，度，賽車懸吊）

| 車型 | 前 | 後 |
|---|---|---|
| Utility Car | -3.0 ~ 0.0 | -3.0 ~ 0.0 |
| Street Car | -3.0 ~ 0.0 | -3.0 ~ 0.0 |
| Sports Car | -3.0 ~ 0.0 | -3.0 ~ 0.0 |
| High Performance Car | -2.5 ~ -1.0 | -2.5 ~ -1.0 |
| Race Car | -2.5 ~ -1.5 | -2.5 ~ -1.5 |
| Race Truck | -2.0 ~ 0.0 | -2.0 ~ 0.0 |
| Prototype Race Car | -2.0 ~ -1.0 | -2.0 ~ -1.0 |
| GP Race Car | -3.5 ~ -1.5 | -3.5 ~ -1.5 |
| Rally Sports Car | -3.0 ~ 0.0 | -3.0 ~ 0.0 |
| Off-road Buggy | -2.5 ~ -1.0 | -2.5 ~ -1.0 |
| Off-road Car | -2.5 ~ -1.0 | -2.5 ~ -1.0 |
| Off-road Sports Car | -2.5 ~ -1.0 | -2.5 ~ -1.0 |
| Off-road Truck | -3.0 ~ -2.0 | -3.0 ~ -2.0 |
| Off-road Race Truck | -2.5 ~ -2.0 | -2.5 ~ -2.0 |

**懸吊類型修正**：
- **Rally / Off-road 懸吊**：相對於 Race 懸吊，**前 Camber +1.0、後 Camber +0.5**。
- **Open Wheel 車**：後 Camber **-1.0**。

### Toe（束角，度）— 後 Toe

| 車型 | 後 Toe |
|---|---|
| Utility Car | -0.3 ~ 0.0 |
| Street Car | -0.3 ~ 0.0 |
| Sports Car | -0.3 ~ 0.0 |
| High Performance Car | 0.0 |
| Race Car | 0.0 |
| Race Truck | 0.0 |
| Prototype Race Car | 0.0 |
| GP Race Car | 0.0 |
| Rally Sports Car | -0.1 ~ 0.0 |
| Off-road Buggy | -0.3 ~ 0.0 |
| Off-road Car | -0.3 ~ 0.0 |
| Off-road Sports Car | -0.3 ~ 0.0 |
| Off-road Truck | -0.3 ~ 0.0 |
| Off-road Race Truck | -0.3 ~ 0.0 |

### Caster（後傾角）— 賽車懸吊

| 車型 | Caster |
|---|---|
| Utility Car | 5.0 |
| Street Car | 5.0 |
| Sports Car | 5.0 / 6.5 |
| High Performance Car | 5.0 |
| Race Car | 5.0 / 6.0 |
| Race Truck | 6.0 |
| Prototype Race Car | 5.0 / 6.0 |
| GP Race Car | 5.0 / 6.0 |
| Rally Sports Car | 5.0 / 6.5 |
| Off-road Buggy | 6.5 |
| Off-road Car | 5.0 |
| Off-road Sports Car | 6.5 |
| Off-road Truck | 5.0 |
| Off-road Race Truck | 2.0 / 5.0 |

### Caster — Rally / Off-road 懸吊

| 車型 | Caster |
|---|---|
| Utility Car | 5.0 |
| Street Car | 5.0 |
| Sports Car | 6.5 |
| High Performance Car | 6.5 |
| Race Car | 6.0 |
| Race Truck | 6.0 |
| Prototype Race Car | 6.0 |
| GP Race Car | 6.0 |
| Rally Sports Car | 6.5 |
| Off-road Buggy | 2.0 |
| Off-road Car | 5.0 |
| Off-road Sports Car | 6.5 |
| Off-road Truck | 5.0 |
| Off-road Race Truck | 2.0 |

---

## 3. 防傾桿（Anti-Roll Bars / ARB）

### RWD 基準硬度與分布

| 車型 | 硬度（Stiffness） | 分布（Distribution） |
|---|---|---|
| Utility Car | 63–66% | 1.00–2.95 |
| Street Car | 63–66% | 0.98–1.50 |
| Sports Car | 61–65% | 0.66–1.00 |
| High Performance Car | 40–46% | 0.55–0.65 |
| Race Car | 35–62% | 0.35–0.80 |
| Race Truck | 15% | 0.35 |
| Prototype Race Car | 28–48% | 0.25–0.35 |
| GP Race Car | 18% | 0.35 |
| Rally Sports Car | 60–63% | 0.70–0.77 |
| Off-road Buggy | 61–65% | 1.45–2.95 |
| Off-road Car | 61–65% | 1.45–2.95 |
| Off-road Sports Car | 61–65% | 1.45–2.95 |
| Off-road Truck | 61–65% | 1.55–3.00 |
| Off-road Race Truck | 61–65% | 1.00–2.53 |

### ARB 基準計算公式

**Base ARB = (車重 / 2) ÷ (200 − 200 × ARB Stiffness)**

範例：街道車 2500 lb、硬度 63% → Base ARB = 16.89

### 傳動系統對 ARB 分布的影響

- **FWD**：每 1% 重量分布相對 RWD **−1**
- **AWD**：每 1% 重量分布相對 RWD **0.66**（RWD 為 1.0）

### 底盤強化對 ARB 硬度的影響

| 強化等級 | 硬度減量 |
|---|---|
| Sport Chassis | -3% |
| Race Chassis | -6% |

---

## 4. 彈簧（Springs）

### 彈簧硬度基準（占前/後分配重量的 %）— RWD、賽車懸吊

| 車型 | 前 | 後 |
|---|---|---|
| Utility Car | 93–100% | 57–80% |
| Street Car | 93–100% | 57–80% |
| Sports Car | 87–98% | 58–80% |
| High Performance Car | 85–93% | 63–84% |
| Race Car | 83–93% | 59–85% |
| Race Truck | 80% | 90% |
| Prototype Race Car | 79–83% | 70–89% |
| GP Race Car | 66% | 79% |
| Rally Sports Car | 87–94% | 60–80% |
| Off-road Buggy | 94–100% | 57–80% |
| Off-road Car | 94–100% | 57–80% |
| Off-road Sports Car | 94–100% | 57–80% |
| Off-road Truck | 94–100% | 57–80% |
| Off-road Race Truck | 94–100% | 57–80% |

### 懸吊類型修正
- **Rally 懸吊**：賽車懸吊彈簧值的 **一半**
- **Off-road 懸吊**：使用「可用彈簧範圍」的百分比（見下表）

### Off-road 懸吊彈簧（占可用範圍的 %）

| 車型 | 前 | 後 |
|---|---|---|
| Off-road Buggy | 39–40% | 6–7% |
| Off-road Car | 39–40% | 6–7% |
| Off-road Sports Car | 39–40% | 6–7% |
| Off-road Truck | 39–40% | 6–7% |
| Open Wheel Off-road | 39–40% | 6–7% |
| Off-road Race Truck | 38–39% | 6–7% |

### 懸吊互換倍率

| 變更 | 倍率 |
|---|---|
| Rally → Race | 加倍 |
| Race → Rally | 減半 |

### 底盤強化對前彈簧的影響

| 強化等級 | 前彈簧減量 |
|---|---|
| Sport Chassis | -2.75% |
| Race Chassis | -5.5% |

### 胎寬對彈簧的影響

每加寬 **10 mm**（前或後）：彈簧硬度 **+0.5%**。

### 下壓力對彈簧的影響

- 前下壓力每增加 **10 lb**：前彈簧 **+0.5**
- 後下壓力每增加 **25 lb**：後彈簧 **+0.5**
- 前後下壓力每偏離平衡 **2 lb**：彈簧 **±0.5**

### 原廠空力下壓力（不可調）

| 部件 | 下壓力 |
|---|---|
| Stock Front Bumper | 10 lb |
| Street Front Bumper | 10 lb |
| Sport Front Bumper | 40 lb |
| Stock Rear Wing | 25 lb |
| Street Rear Wing | 25 lb |
| Sport Rear Wing | 70 lb |
| Stock Rear Bumper | 25 lb |
| Street Rear Bumper | 25 lb |
| Sport Rear Bumper | 50 lb |

### AWD / FWD 彈簧分配

- **AWD**：與 RWD 相同
- **FWD**：前後彈簧值對調（相對 RWD 基準）

---

## 5. 車高（Ride Height）

### 各車型最低車高範圍

| 車型 | 最低車高 |
|---|---|
| Utility Car | 5.0–7.0 |
| Street Car | 5.0–7.0 |
| Sports Car | 5.0–7.0 |
| High Performance Car | 4.0–5.0 |
| Race Car | 4.0–6.0 |
| Race Truck | 4.5 |
| Prototype Race Car | 3.5–4.5 |
| GP Race Car | 5.5 |
| Rally Sports Car | 5.0 |
| Off-road Buggy | 5.0–7.0 |
| Off-road Car | 5.0–7.0 |
| Off-road Sports Car | 5.0–7.0 |
| Off-road Truck | 5.0–7.0 |
| Off-road Race Truck | 5.0–7.0 |

---

## 6. 阻尼（Dampers）

### 各車型最低前壓縮（Front Bump）值

| 車型 | 最低 Front Bump |
|---|---|
| Utility Car | 5.0–5.2 |
| Street Car | 4.4–4.8 |
| Sports Car | 4.4–4.7 |
| High Performance Car | 4.5–4.9 |
| Race Car | 4.7–4.9 |
| Race Truck | 5.0 |
| Prototype Race Car | 4.6–4.8 |
| GP Race Car | 4.5 |
| Rally Sports Car | 4.4–4.5 |
| Off-road Buggy | 5.0–5.1 |
| Off-road Car | 5.0–5.2 |
| Off-road Sports Car | 4.4–4.5 |
| Off-road Truck | 5.0–5.2 |
| Off-road Race Truck | 5.0–5.1 |

### 三步調整流程

1. 依上表設定前壓縮，每多 **200 lb 前部重量**就 **+0.1**。
2. 計算前回彈：**Damping Stiffness − Front Bump**。
3. 依前後彈簧差異套用下表，調整後輪阻尼。

### 前後彈簧差異對阻尼的影響

| 前後彈簧差距 | 回彈偏移 | 壓縮偏移 |
|---|---|---|
| 0 ~ 1.5% | +0.2 | +0.1 |
| 1.5 ~ 35% | +0.3 | +0.2 |
| 36 ~ 40% | +0.6 | +0.4 |
| > 40% | +1.2 | +0.8 |
| -1.5% ~ 0% | -0.2 | -0.1 |
| -1.5 ~ -35% | -0.3 | -0.2 |
| -36 ~ -40% | -0.6 | -0.4 |
| < -40% | -1.2 | -0.8 |

### Rally / Off-road 懸吊修正
- Rally 懸吊：回彈 **+1.0**
- Off-road 懸吊：回彈 **+1.0**

### 原型賽車與 GP 賽車額外偏移

| 車型 | 前阻尼偏移 | 後阻尼偏移 |
|---|---|---|
| Prototype Race Car | 0.0 | +3.5 |
| GP Race Car | +3.5 | 0.0 |

---

## 7. 煞車（Brakes）

### 賽車懸吊（前分布 % / 壓力 %）

| 車型 | 分布 | 壓力 |
|---|---|---|
| Utility Car | 50% | 120% |
| Street Car | 52% | 125% |
| Sports Car | 52% | 125% |
| High Performance Car | 54% | 135% |
| Race Car | 56% | 145% |
| Race Truck | 56% | 145% |
| Prototype Race Car | 56% | 145% |
| GP Race Car | 52% | 125% |
| Rally Sports Car | 48% | 125% |
| Off-road Buggy | 46% | 110% |
| Off-road Car | 48% | 115% |
| Off-road Sports Car | 48% | 115% |
| Off-road Truck | 52% | 135% |
| Off-road Race Truck | 52% | 135% |

### Rally / Off-road 懸吊（前分布 % / 壓力 %）

| 車型 | 分布 | 壓力 |
|---|---|---|
| Utility Car | 50% | 120% |
| Street Car | 48% | 125% |
| Sports Car | 48% | 125% |
| High Performance Car | 50% | 135% |
| Race Car | 52% | 145% |
| Race Truck | 52% | 145% |
| Prototype Race Car | 52% | 145% |
| GP Race Car | 48% | 125% |
| Rally Sports Car | 48% | 125% |
| Off-road Buggy | 46% | 110% |
| Off-road Car | 48% | 115% |
| Off-road Sports Car | 48% | 115% |
| Off-road Truck | 52% | 135% |
| Off-road Race Truck | 52% | 135% |

---

## 8. 差速器（Differential）

### RWD + 賽車懸吊 + 賽車差速器（加速 % / 減速 %）

| 車型 | 加速 | 減速 |
|---|---|---|
| Utility Car | 24–28% | 45–46% |
| Street Car | 24–28% | 45–46% |
| Sports Car | 24–28% | 45–46% |
| High Performance Car | 28% | 44% |
| Race Car | 28–30% | 43–44% |
| Race Truck | 30% | 44% |
| Prototype Race Car | 52–54% | 0% |
| GP Race Car | 2% | 0% |
| Rally Sports Car | 0% | 14–15% |
| Off-road Buggy | 0% | 0% |
| Off-road Car | 0% | 15–16% |
| Off-road Sports Car | 0% | 15–16% |
| Off-road Truck | 0% | 15–16% |
| Off-road Race Truck | 0% | 0% |

### RWD + Rally / Off-road 懸吊 + 賽車差速器

| 車型 | 加速 | 減速 |
|---|---|---|
| Utility Car | 14–18% | 35–36% |
| Street Car | 14–18% | 35–36% |
| Sports Car | 14–18% | 35–36% |
| High Performance Car | 18% | 34% |
| Race Car | 18–20% | 33–34% |
| Race Truck | 20% | 34% |
| Prototype Race Car | 42–44% | 0% |
| GP Race Car | 0% | 0% |
| Rally Sports Car | 0% | 4–5% |
| Off-road Buggy | 0% | 0% |
| Off-road Car | 0% | 5–6% |
| Off-road Sports Car | 0% | 5–6% |
| Off-road Truck | 0% | 5–6% |
| Off-road Race Truck | 0% | 0% |

### 差速器類型相對偏移（相對賽車差速器）

| 差速器類型 | 加速偏移 | 減速偏移 |
|---|---|---|
| Rally Differential | +24% | -20% |
| Off-road Differential | +48% | -40% |
| Drift Differential | -10% | -10% |
| Open Wheel Car | -24% | 設為 0% |

### FWD 車

- 前加速：**RWD 加速 − 20%**
- 前減速：**0%**

### AWD 車

- 前加速：**RWD 加速值**
- 前減速：**0%**
- 後加速：**100%**
- 後減速：**RWD 減速值**
- 差速器分布（Race）：**RWD 加速 + 50%**
- 差速器分布（Rally）：**RWD 加速 + 26%**
- 差速器分布（Off-road）：**RWD 加速 + 14%**

---

## 9. 齒比（Gearing）

### Final Drive 計算公式（Standard Forza Race Gearbox）

> 每比原廠馬力 **多 6 hp** → Final Drive **−0.01**
> 每比原廠馬力 **少 6 hp** → Final Drive **+0.01**

**公式**：`(原廠馬力 − 當前馬力) ÷ 6 × 0.01 + 參考 Final Drive`

### 各變速箱參考 Final Drive

| 變速箱類型 | 參考 FD |
|---|---|
| Standard Forza Race（6 速） | 4.25 |
| 5 速 Sport | 4.00 |
| 4 速 Sport | 4.75 |
| 3 速 Sport | 4.50 |
| 低齒比車（Low Gearing Cars） | 3.25 |
| 低齒比 6 速 Sport | 3.25 |
| 低齒比 5 速 Sport | 3.00 |
| 低齒比 4 速 Sport | 3.75 |
| 低齒比 3 速 Sport | 3.50 |

### 拉力 / 越野車的標準 Forza 變速箱偏移

| 車型 | Final Drive 偏移 |
|---|---|
| Rally Car | +0.50 |
| Off-road Car | +0.75 |

### 自訂變速箱（Custom Gearbox）

公式：`(原廠馬力 − 當前馬力) ÷ 6 × 0.01 + 原廠 Final Drive`

### 空力對 Final Drive 的影響（Standard Forza Race Gearbox）

| 前保險桿 | 後尾翼 | FD 偏移 |
|---|---|---|
| Race | Race | 0.00 |
| Sport | Race | -0.05 |
| Street | Race | -0.05 |
| Stock | Race | -0.05 |
| 移除 | Race | -0.05 |
| Race | Sport | -0.05 |
| Sport | Sport | -0.10 |
| Street | Sport | -0.15 |
| Stock | Sport | -0.15 |
| Street | Street | -0.20 |
| Stock | Street | -0.25 |
| Stock | Stock | -0.30 |
| 移除 | Stock | -0.35 |
| 移除 | 移除 | -0.40 |

### 傳動系統互換的 Final Drive 偏移（原廠變速箱）

**AWD Swap**

| 車型 | FD 偏移 | 齒比偏移 |
|---|---|---|
| Road Car | -1.0 | 0.0 |
| High Gearing Road | -0.5 | 0.0 |
| Low Gearing Road | -1.0 | 0.0 |
| Rally Car | -1.0 | +0.20 |
| Off-road Car | -1.5 | 0.0 |

**RWD Swap**

| 車型 | FD 偏移 | 齒比偏移 |
|---|---|---|
| Road Car | -0.5 | 0.0 |
| High Gearing Road | 0.0 | 0.0 |
| Low Gearing Road | +1.0 | 0.0 |
| Rally Car | 0.0 | -0.20 |
| Off-road Car | -0.5 | +0.20 |

### 底盤類型對 Final Drive 的偏移

| 底盤 | FD 偏移 |
|---|---|
| Drag | -0.2 |
| Off-road | -0.1 |
| Drift | +0.1 |

---

## 10. 空力（Aero）

### 依傳動方式設定下壓力

| 傳動 | 前 | 後 |
|---|---|---|
| RWD | 最小 | 最大 |
| FWD / AWD | 最大 | 最小 |

### 依馬力等級調整

**低馬力（< 400 hp）**
- RWD：前最小 / 後最大 × 0.85
- FWD / AWD：前最大 / 後最小

**高馬力（≥ 400 hp 且 ≥ 1.5 倍原廠馬力）**
- RWD：前最小 × 1.5 / 後最大
- FWD / AWD：前最大 / 後最小 × 1.5

**極端馬力（≥ 400 hp 且 ≥ 2 倍原廠馬力）**
- RWD：前最小 × 2 / 後最大
- FWD / AWD：前最大 / 後最小 × 2

### 平衡下壓力參考

- 空力理想前重量分布：**47%**
- 後下壓力每偏離 47% 1%：調整 **1.866667 lb**

---

## 延伸閱讀

- [車型分類框架](../cars/車型分類框架.md) — Part 1：查表前置
- [公路調校修正表](./公路調校修正表.md) — Part 3
- [越野調校修正表](./越野調校修正表.md) — Part 4
- [抓地與速度取向](./抓地與速度取向.md) — Part 5
- [環境條件修正表](./環境條件修正表.md) — Part 6
- [QuickTune 套用流程](./QuickTune套用流程.md) — 附錄

教學對照：
- [胎壓](./胎壓.md) · [四輪定位](./四輪定位.md) · [防傾桿](./防傾桿.md) · [彈簧與車高](./彈簧與車高.md) · [阻尼](./阻尼.md)
- [煞車調校](./煞車調校.md) · [差速器](./差速器.md) · [齒比](./齒比.md) · [下壓力](./下壓力.md)

## 來源

- [《QuickTune 完整調校指南》整理版](../../_sources/地平線5_QuickTune完整調校指南_整理版.md) — Part 2：General Tuning
- 原作者：Fifty Inch（Heinmarkus）· [forzaquicktune.com](https://forzaquicktune.com/tuning-guide/fh5/)
