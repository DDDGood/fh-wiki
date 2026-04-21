# 【地平線 5】QuickTune 完整調校指南（整理版）

> 來源：[Forza Horizon 5 Tuning Guide — forzaquicktune.com](https://forzaquicktune.com/tuning-guide/fh5/)
> 作者：Fifty Inch（Heinmarkus），© 2023
> 整理日期：2026-04-21
> 對應版本：原作對應 2023 年 FH5 調校機制；後續 Series 更新可能微調，套用前請對照當前遊戲內預設值校驗。
> 說明：本文以繁體中文整理 QuickTune 全系列七篇教學的**結構化調校資料**（數值、百分比、偏移量、計算公式）。所有遊戲數值（PSI、外傾度、阻尼、差速器百分比、車高、齒比、空力磅數）皆完整保留並交叉核對。原文的散文敘述以繁中重新組織說明，未做逐字翻譯。專業術語首次出現時保留英文原文以利查證。
> 章節對應：本文一～七章對應原站 Part 1～Part 7；Part 7（Balance and Stiffness Tuning）原作者尚未發布，本文於第七章標示「待補」。

---

## 目錄

- [一、基礎分類框架（Part 1：Horizon Tuning Basics）](#一基礎分類框架)
- [二、通用調校基準（Part 2：General Tuning）](#二通用調校基準)
- [三、公路調校修正（Part 3：Road Tuning）](#三公路調校修正)
- [四、越野調校（Part 4：Off-road Tuning）](#四越野調校)
- [五、抓地與速度導向調校（Part 5：Grip and Speed Tuning）](#五抓地與速度導向調校)
- [六、季節、時段與天氣修正（Part 6：Season and Weather Tuning）](#六季節時段與天氣修正)
- [七、平衡與剛性調校（Part 7：Balance and Stiffness Tuning）](#七平衡與剛性調校)
- [附錄：套用流程建議](#附錄套用流程建議)

---

## 一、基礎分類框架

QuickTune 的調校體系建立在三層分類上：**車型（Car Type）／車身年代（Body Type）／底盤類型（Chassis Type）**，所有後續章節的偏移值都依此查表套用。

### 1.1 車型（Car Type）分類

#### 公路車（Road Cars）
- 多用途車（Utility）：廂型車、SUV
- 街道車（Street）：房車、旅行車、肌肉車、小型車
- 跑車（Sports）：跑車、拉力車、GT 跑車
- 高性能車（High Performance）：超跑、Hyper Car

#### 賽車（Race Cars）
- 賽車（Race）：GT 賽車
- 賽車卡車（Race Truck）
- 原型賽車（Prototype Race）：LMP 系列
- GP 賽車（GP Race）：經典方程式賽車

#### 拉力車（Rally Cars）
- 拉力跑車（Rally Sports Car）

#### 越野車（Off-road Cars）
- 越野沙灘車（Off-road Buggy）
- 越野車（Off-road Car）：Jeep 類
- 越野跑車（Off-road Sports Car）
- 越野卡車（Off-road Truck）：皮卡
- 越野賽車卡車（Off-road Race Truck）：Trophy Truck

### 1.2 車身年代（Body Type）

依製造年代分為五代：**Modern（現代）／Early Modern（早期現代）／Vintage（古典）／Early Vintage（早期古典）／Pre-War（戰前）**。

**核心原則**：年代越早的車，**底盤與懸吊越要硬**；現代車與賽車則**越軟越好**。

各年代對六大子系統的調整方向（↑＝偏高、↓＝偏低、→ 表示往後年代漸進變化）：

| 年代 | Camber/Caster | ARB | Springs | Dampers | Brakes | Diff |
|---|---|---|---|---|---|---|
| Modern | ↑/↓ | ↓/↓ | ↓/↑ | ↑/↓ | ↑/↓ | ↑/↓ |
| Early Modern | ↑→低 | ↓→低 | ↓→低 | ↑→低 | ↑→低 | ↑→低 |
| Vintage | ↑→低 | ↓→低 | ↓→低 | ↑→低 | ↑→低 | ↑→低 |
| Early Vintage | ↑→↓ | ↓→↑ | ↓→↑ | ↑→↓ | ↑→↓ | ↑→↓ |
| Pre-War | ↓/↑ | ↑/↑ | ↑/↓ | ↓/↑ | ↓/↑ | ↓/↑ |

### 1.3 底盤類型（Chassis Type）

FH5 引入的關鍵新機制——**升級胎種會改變底盤類型**，整體底盤反應隨之改變。共五種底盤：

| 底盤類型 | 對應胎種 |
|---|---|
| Road（公路） | Stock、Street、Sport、Semi-Race Slicks、Race Slicks、Snow、Vintage Race |
| Off-Road（越野） | Off-road、Rally、Off-road Race、Vintage Rally |
| Rally（拉力） | AWD Swap + Rally Tires |
| Drift（漂移） | Drift Tires |
| Drag（拖曳） | Drag Tires |

各底盤類型的整體傾向（相對於 Road 基準）：

| 參數 | Drag | Off-Road | Road | Drift |
|---|---|---|---|---|
| 胎壓（前/後） | 低/高 | 低→高 | 高→低 | 高/低 |
| Camber/Caster | 低 | 低 | 高 | 高 |
| 防傾桿（ARB） | 高/低 | 低 | 高/低 | 低/高 |
| 車高（Ride Height） | 最大 | 最大 | 標準 | 標準 |
| 煞車壓力 | 高/低 | 高 | 標準 | 低/高 |
| 下壓力（前/後） | 低/高 | 低 | 標準 | 低/高 |

### 1.4 量產車六大子系統的車型對應傾向

| 車型 | Camber/Caster | ARB（分布/硬度） | Springs（前/後） | Dampers（回彈/壓縮） | Brakes（前分布/壓力） | Diff（加速/減速） |
|---|---|---|---|---|---|---|
| Utility | 低/高 | 高/高 | 高/低 | 低/高 | 高/低 | 低/高 |
| Street | 低→高 | 高→低 | 高→低 | 低→高 | 高→低 | 低→高 |
| Sports | 低→高 | 高→低 | 高→低 | 低→高 | 高→低 | 低→高 |
| High Performance | 低→高 | 高→低 | 高→低 | 低→高 | 高→低 | 低→高 |
| Race | 低→高 | 高→低 | 高→低 | 低→高 | 高→低 | 低→高 |
| Race Truck | 低→高 | 高→低 | 高→低 | 低→高 | 高→低 | 低→高 |

### 1.5 特殊賽車

| 車型 | Camber/Caster | ARB | Springs | Dampers | Brakes | Diff |
|---|---|---|---|---|---|---|
| Prototype | 低→高 | 高 | 高 | 高（僅後） | 高→低 | 高/低 |
| GP Race | 低/高 | 高 | 高 | 高 | 高 | 低/高 |
| Off-Road | 低→高 | 高→低 | 高→低 | 低→高 | 高→低 | 低→低 |
| Off-Road Sports | 高→低 | 低→高 | 低→高 | 低→高 | 高→低 | 低→低 |
| Off-Road Truck | 高/低 | 低/低 | 低/高 | 高/低 | 低/高 | 低 |

### 1.6 開輪 vs 閉輪（Open Wheel vs Closed Wheel）

開輪賽車因車身結構與懸吊幾何關係，**先天有推頭傾向**，需以下調整對抗：

| 設計 | 後 Camber | 差速器（加速/減速） |
|---|---|---|
| Closed Wheel（閉輪） | 標準 | 標準 |
| Open Wheel（開輪） | 較低 | 較低（更開放） |

---

## 二、通用調校基準

本章是所有後續修正的**基準值**——先依車型查出基準，再依公路／越野／抓地速度／季節天氣等情境疊加偏移量。

### 2.1 輪胎（Tires）

#### 各胎種基準胎壓（PSI）

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

#### 高性能 / 賽車修正

下列車型在基準胎壓上 **+0.5 PSI**：

- High Performance Car
- Race Car
- Race Truck
- Prototype Race Car
- GP Race Car
- Off-road Race Truck

### 2.2 定位（Alignment）

#### Camber（外傾角，度，賽車懸吊）

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

#### Toe（束角，度）— 後 Toe

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

#### Caster（後傾角）— 賽車懸吊

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

#### Caster — Rally / Off-road 懸吊

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

### 2.3 防傾桿（Anti-Roll Bars / ARB）

#### RWD 基準硬度與分布

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

#### ARB 基準計算公式

**Base ARB = (車重 / 2) ÷ (200 − 200 × ARB Stiffness)**

範例：街道車 2500 lb、硬度 63% → Base ARB = 16.89

#### 傳動系統對 ARB 分布的影響

- **FWD**：每 1% 重量分布相對 RWD **−1**
- **AWD**：每 1% 重量分布相對 RWD **0.66**（RWD 為 1.0）

#### 底盤強化對 ARB 硬度的影響

| 強化等級 | 硬度減量 |
|---|---|
| Sport Chassis | -3% |
| Race Chassis | -6% |

### 2.4 彈簧（Springs）

#### 彈簧硬度基準（占前/後分配重量的 %）— RWD、賽車懸吊

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

#### 懸吊類型修正
- **Rally 懸吊**：賽車懸吊彈簧值的 **一半**
- **Off-road 懸吊**：使用「可用彈簧範圍」的百分比（見下表）

#### Off-road 懸吊彈簧（占可用範圍的 %）

| 車型 | 前 | 後 |
|---|---|---|
| Off-road Buggy | 39–40% | 6–7% |
| Off-road Car | 39–40% | 6–7% |
| Off-road Sports Car | 39–40% | 6–7% |
| Off-road Truck | 39–40% | 6–7% |
| Open Wheel Off-road | 39–40% | 6–7% |
| Off-road Race Truck | 38–39% | 6–7% |

#### 懸吊互換倍率

| 變更 | 倍率 |
|---|---|
| Rally → Race | 加倍 |
| Race → Rally | 減半 |

#### 底盤強化對前彈簧的影響

| 強化等級 | 前彈簧減量 |
|---|---|
| Sport Chassis | -2.75% |
| Race Chassis | -5.5% |

#### 胎寬對彈簧的影響

每加寬 **10 mm**（前或後）：彈簧硬度 **+0.5%**。

#### 下壓力對彈簧的影響

- 前下壓力每增加 **10 lb**：前彈簧 **+0.5**
- 後下壓力每增加 **25 lb**：後彈簧 **+0.5**
- 前後下壓力每偏離平衡 **2 lb**：彈簧 **±0.5**

#### 原廠空力下壓力（不可調）

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

#### AWD / FWD 彈簧分配

- **AWD**：與 RWD 相同
- **FWD**：前後彈簧值對調（相對 RWD 基準）

### 2.5 車高（Ride Height）

#### 各車型最低車高範圍

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

### 2.6 阻尼（Dampers）

#### 各車型最低前壓縮（Front Bump）值

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

#### 三步調整流程

1. 依上表設定前壓縮，每多 **200 lb 前部重量**就 **+0.1**。
2. 計算前回彈：**Damping Stiffness − Front Bump**。
3. 依前後彈簧差異套用下表，調整後輪阻尼。

#### 前後彈簧差異對阻尼的影響

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

#### Rally / Off-road 懸吊修正

- Rally 懸吊：回彈 **+1.0**
- Off-road 懸吊：回彈 **+1.0**

#### 原型賽車與 GP 賽車額外偏移

| 車型 | 前阻尼偏移 | 後阻尼偏移 |
|---|---|---|
| Prototype Race Car | 0.0 | +3.5 |
| GP Race Car | +3.5 | 0.0 |

### 2.7 煞車（Brakes）

#### 賽車懸吊（前分布 % / 壓力 %）

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

#### Rally / Off-road 懸吊（前分布 % / 壓力 %）

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

### 2.8 差速器（Differential）

#### RWD + 賽車懸吊 + 賽車差速器（加速 % / 減速 %）

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

#### RWD + Rally / Off-road 懸吊 + 賽車差速器

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

#### 差速器類型相對偏移（相對賽車差速器）

| 差速器類型 | 加速偏移 | 減速偏移 |
|---|---|---|
| Rally Differential | +24% | -20% |
| Off-road Differential | +48% | -40% |
| Drift Differential | -10% | -10% |
| Open Wheel Car | -24% | 設為 0% |

#### FWD 車

- 前加速：**RWD 加速 − 20%**
- 前減速：**0%**

#### AWD 車

- 前加速：**RWD 加速值**
- 前減速：**0%**
- 後加速：**100%**
- 後減速：**RWD 減速值**
- 差速器分布（Race）：**RWD 加速 + 50%**
- 差速器分布（Rally）：**RWD 加速 + 26%**
- 差速器分布（Off-road）：**RWD 加速 + 14%**

### 2.9 齒比（Gearing）

#### Final Drive 計算公式（Standard Forza Race Gearbox）

> 每比原廠馬力 **多 6 hp** → Final Drive **−0.01**
> 每比原廠馬力 **少 6 hp** → Final Drive **+0.01**

**公式**：(原廠馬力 − 當前馬力) ÷ 6 × 0.01 + 參考 Final Drive

#### 各變速箱參考 Final Drive

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

#### 拉力 / 越野車的標準 Forza 變速箱偏移

| 車型 | Final Drive 偏移 |
|---|---|
| Rally Car | +0.50 |
| Off-road Car | +0.75 |

#### 自訂變速箱（Custom Gearbox）

公式：**(原廠馬力 − 當前馬力) ÷ 6 × 0.01 + 原廠 Final Drive**

#### 空力對 Final Drive 的影響（Standard Forza Race Gearbox）

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

#### 傳動系統互換的 Final Drive 偏移（原廠變速箱）

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

#### 底盤類型對 Final Drive 的偏移

| 底盤 | FD 偏移 |
|---|---|
| Drag | -0.2 |
| Off-road | -0.1 |
| Drift | +0.1 |

### 2.10 空力（Aero）

#### 依傳動方式設定下壓力

| 傳動 | 前 | 後 |
|---|---|---|
| RWD | 最小 | 最大 |
| FWD / AWD | 最大 | 最小 |

#### 依馬力等級調整

**低馬力（< 400 hp）**
- RWD：前最小 / 後最大 × 0.85
- FWD / AWD：前最大 / 後最小

**高馬力（≥ 400 hp 且 ≥ 1.5 倍原廠馬力）**
- RWD：前最小 × 1.5 / 後最大
- FWD / AWD：前最大 / 後最小 × 1.5

**極端馬力（≥ 400 hp 且 ≥ 2 倍原廠馬力）**
- RWD：前最小 × 2 / 後最大
- FWD / AWD：前最大 / 後最小 × 2

#### 平衡下壓力參考

- 空力理想前重量分布：**47%**
- 後下壓力每偏離 47% 1%：調整 **1.866667 lb**

---

## 三、公路調校修正

**核心觸發條件**：
- **馬力 < 400 hp 且使用原廠胎或無可調懸吊** → 直接用第二章通用值。
- **馬力 ≥ 400 hp 且使用可調懸吊 + 升級胎種** → 套用本章偏移。

### 3.1 輪胎胎壓偏移（PSI）

#### Stock → 升級底盤（公路車）

| Stock | 升級後 | 偏移 |
|---|---|---|
| Street | Sport | +0.5 |
| Street | Semi Race | +1.0 |
| Street | Race | +1.5 |
| Street | Snow | -0.5 |
| Street | Vintage Race | -1.0 |
| Sport | Semi Race | +0.5 |
| Sport | Race | +1.0 |
| Semi Race | Race | +0.5 |
| Semi Race | Snow | -1.5 |
| Race | Semi Race | +0.5 |
| Race | Snow | -2.0 |
| Vintage Race | Street | +1.0 |
| Vintage Race | Sport | +1.5 |
| Vintage Race | Semi Race | +2.0 |
| Vintage Race | Race | +2.5 |
| Vintage Race | Snow | +0.5 |

#### Drag / Rally / Off-road / Drift 胎

| 底盤 | 前偏移 | 後偏移 |
|---|---|---|
| Drag | -1.0 | 0.0 |
| Off-road | -0.5 | 0.0 |
| Rally | -0.5 | 0.0 |
| Drift | 0.0 | +0.5 |

#### 拉力 / 越野車跑公路（依胎種）

| 胎種 | 前偏移 | 後偏移 |
|---|---|---|
| Drag | -1.0 | 0.0 |
| Off-road | -0.5 | 0.0 |
| Rally | -0.5 | 0.0 |
| Road | 0.0 | +0.5 |
| Drift | 0.0 | +1.0 |

#### 底盤強化的胎壓偏移

| 強化等級 | 前 | 後 |
|---|---|---|
| Stock | -0.5 | +0.5 |
| Street | 0.0 | 0.0 |
| Sport | +0.5 | -0.5 |
| Race | +1.0 | -1.0 |

#### 重車修正（4000 lb 以上）

| 重量範圍 | 胎壓偏移 |
|---|---|
| 4000–4999 lb | +5.0 |
| 5000–5999 lb | +10.0 |
| 6000–6999 lb | +15.0 |
| 7000–7999 lb | +20.0 |
| 8000–9999 lb | +5.0 |
| 10000–11999 lb | +10.0 |
| 12000–13999 lb | +15.0 |
| 14000–15999 lb | +20.0 |

#### 輕車修正（2000 lb 以下）

| 重量範圍 | 胎壓偏移 |
|---|---|
| 1500–1999 lb | -5.0 |
| 1000–1499 lb | -10.0 |
| 500–999 lb | -15.0 |
| 0–499 lb | -20.0 |

### 3.2 定位偏移

#### Stock → 升級底盤的 Camber & Caster

| Stock | 升級後 | Camber | Caster |
|---|---|---|---|
| Street | Sport | -0.5 | +0.5 |
| Street | Semi Race | -1.0 | +1.0 |
| Street | Race | -1.5 | +1.5 |
| Street | Snow | +0.5 | -0.5 |
| Street | Vintage Race | +1.0 | -1.0 |
| Sport | Semi Race | -0.5 | +0.5 |
| Sport | Race | -1.0 | +1.0 |
| Sport | Snow | +1.0 | -1.0 |
| Semi Race | Race | -0.5 | +0.5 |
| Semi Race | Snow | +1.5 | -1.5 |
| Race | Semi Race | -0.5 | +0.5 |
| Race | Snow | +2.0 | -2.0 |
| Vintage Race | Street | -1.0 | +1.0 |
| Vintage Race | Sport | -1.5 | +1.5 |
| Vintage Race | Semi Race | -2.0 | -2.0 |
| Vintage Race | Race | -2.5 | -2.5 |
| Vintage Race | Snow | -0.5 | +0.5 |

#### Drag / Rally / Off-road / Drift 底盤定位

| 底盤 | 前 Camber | 後 Camber | Caster |
|---|---|---|---|
| Drag | +1.0 | 0.0 | -1.0 |
| Off-road | +0.5 | 0.0 | -0.5 |
| Rally | +0.5 | 0.0 | -0.5 |
| Drift | 0.0 | -0.5 | +0.5 |

#### 拉力 / 越野車跑公路（依胎種）

| 胎種 | 前 Camber | 後 Camber | Caster |
|---|---|---|---|
| Drag | +1.0 | 0.0 | -1.0 |
| Off-road | +0.5 | 0.0 | -0.5 |
| Rally | +0.5 | 0.0 | -0.5 |
| Road | 0.0 | -0.5 | +0.5 |
| Drift | 0.0 | -1.0 | +1.0 |

#### 拉力 / 越野懸吊跑公路

| 項目 | 偏移 |
|---|---|
| 前 Camber | +1.0 |
| 後 Camber | +0.5 |
| Caster | -1.0 |

#### 底盤強化定位偏移

| 強化等級 | Camber | 前 Toe | 後 Toe | Caster |
|---|---|---|---|---|
| Stock | +0.1 | -0.1 | +0.1 | +0.1 |
| Street | 0.0 | 0.0 | 0.0 | 0.0 |
| Sport | -0.1 | +0.1 | -0.1 | -0.1 |
| Race | -0.2 | +0.2 | -0.2 | -0.2 |

### 3.3 防傾桿偏移

#### Stock → 升級底盤（公路車）

| Stock | 升級後 | 前 ARB | 後 ARB |
|---|---|---|---|
| Street | Sport | 0 | +12% |
| Street | Semi Race | 0 | +24% |
| Street | Race | 0 | +36% |
| Street | Snow | +12% | 0 |
| Street | Vintage Race | +24% | 0 |
| Sport | Semi Race | 0 | +12% |
| Sport | Race | 0 | +24% |
| Sport | Snow | +24% | 0 |
| Semi Race | Race | 0 | +12% |
| Semi Race | Snow | +36% | 0 |
| Race | Semi Race | 0 | +12% |
| Race | Snow | +48% | 0 |
| Vintage Race | Street | 0 | +24% |
| Vintage Race | Sport | 0 | +36% |
| Vintage Race | Semi Race | 0 | +48% |
| Vintage Race | Race | 0 | +60% |
| Vintage Race | Snow | 0 | +12% |

#### Drag / Rally / Off-road / Drift 底盤 ARB

| 底盤 | 前 ARB | 後 ARB |
|---|---|---|
| Drag | +24% | -24% |
| Off-road | +12% | -12% |
| Rally | -12% | +12% |
| Drift | -12% | +12% |

#### 拉力 / 越野車跑公路（依胎種）

| 胎種 | 前 ARB | 後 ARB |
|---|---|---|
| Drag | +24% | -24% |
| Off-road | +12% | -12% |
| Road | -12% | +12% |
| Rally | -12% | +12% |
| Drift | -24% | +24% |

#### 底盤強化 ARB 偏移

| 強化等級 | 前 ARB | 後 ARB |
|---|---|---|
| Stock | +0.1 | -0.1 |
| Street | 0.0 | 0.0 |
| Sport | -0.1 | +0.1 |
| Race | -0.2 | +0.2 |

### 3.4 彈簧偏移

#### Stock → 升級底盤（公路車）

| Stock | 升級後 | 前彈簧 | 後彈簧 |
|---|---|---|---|
| Street | Sport | 0 | -12% |
| Street | Semi Race | 0 | -24% |
| Street | Race | 0 | -36% |
| Street | Snow | -12% | 0 |
| Street | Vintage Race | -24% | 0 |
| Sport | Semi Race | 0 | -12% |
| Sport | Race | 0 | -24% |
| Sport | Snow | -24% | 0 |
| Semi Race | Race | 0 | -12% |
| Semi Race | Snow | -36% | 0 |
| Race | Semi Race | 0 | -12% |
| Race | Snow | -48% | 0 |
| Vintage Race | Street | 0 | -24% |
| Vintage Race | Sport | 0 | -36% |
| Vintage Race | Semi Race | 0 | -48% |
| Vintage Race | Race | 0 | -60% |
| Vintage Race | Snow | 0 | -12% |

#### Drag / Rally / Off-road / Drift 底盤彈簧

| 底盤 | 前彈簧 | 後彈簧 |
|---|---|---|
| Drag | -24% | -24% |
| Off-road | -12% | -12% |
| Rally | -12% | -12% |
| Drift | -12% | -12% |

#### 拉力 / 越野車跑公路（依胎種）

| 胎種 | 前彈簧 | 後彈簧 |
|---|---|---|
| Drag | -24% | -24% |
| Off-road | -12% | -12% |
| Road | -12% | -12% |
| Rally | -12% | -12% |
| Drift | -24% | -24% |

#### 拉力 / 越野懸吊跑公路
彈簧值需 **加倍**（抵消拉力懸吊原本的減半規則）。

#### 底盤強化彈簧偏移

| 強化等級 | 前彈簧 | 後彈簧 |
|---|---|---|
| Stock | +0.5 | -0.5 |
| Street | 0.0 | 0.0 |
| Sport | -0.5 | +0.5 |
| Race | -1.0 | +1.0 |

### 3.5 車高偏移

#### Stock → 升級底盤

| Stock | 升級後 | 車高偏移 |
|---|---|---|
| Street | Sport | -0.1 |
| Street | Semi Race | -0.2 |
| Street | Race | -0.3 |
| Street | Snow | +0.1 |
| Street | Vintage Race | +0.2 |
| Sport | Semi Race | -0.1 |
| Sport | Race | -0.2 |
| Sport | Snow | +0.2 |
| Semi Race | Race | -0.1 |
| Semi Race | Snow | +0.3 |
| Race | Semi Race | -0.1 |
| Race | Snow | +0.4 |
| Vintage Race | Street | -0.2 |
| Vintage Race | Sport | -0.3 |
| Vintage Race | Semi Race | -0.4 |
| Vintage Race | Race | -0.5 |
| Vintage Race | Snow | -0.1 |

#### Drag / Rally / Off-road / Drift 底盤車高

| 底盤 | 前車高 | 後車高 |
|---|---|---|
| Drag | 設為最大 | 0 |
| Off-road | 設為最大 | 0 |
| Rally | 0 | 0 |
| Drift | 0 | 設為最大 |

#### 底盤強化車高偏移

| 強化等級 | 前車高 | 後車高 |
|---|---|---|
| Stock | +0.1 | -0.1 |
| Street | 0.0 | 0.0 |
| Sport | -0.1 | +0.1 |
| Race | -0.2 | +0.2 |

### 3.6 阻尼偏移（回彈與壓縮合併）

#### Stock → 升級底盤

| Stock | 升級後 | 前阻尼 | 後阻尼 |
|---|---|---|---|
| Street | Sport | 0.0 | +0.5 |
| Street | Semi Race | 0.0 | +1.5 |
| Street | Race | 0.0 | +2.5 |
| Street | Snow | +0.5 | 0.0 |
| Street | Vintage Race | +1.5 | 0.0 |
| Sport | Semi Race | 0.0 | +0.5 |
| Sport | Race | 0.0 | +1.5 |
| Sport | Snow | +1.5 | 0.0 |
| Semi Race | Race | 0.0 | +0.5 |
| Semi Race | Snow | +2.5 | 0.0 |
| Race | Semi Race | 0.0 | +0.5 |
| Race | Snow | +3.5 | 0.0 |
| Vintage Race | Street | 0.0 | +1.5 |
| Vintage Race | Sport | 0.0 | +2.5 |
| Vintage Race | Semi Race | 0.0 | +3.5 |
| Vintage Race | Race | 0.0 | +4.5 |
| Vintage Race | Snow | 0.0 | +0.5 |

#### Drag / Rally / Off-road / Drift 底盤阻尼

| 底盤 | 前回彈 | 後回彈 | 前壓縮 | 後壓縮 |
|---|---|---|---|---|
| Drag | +3.5 | 0.0 | 0.0 | +3.5 |
| Off-road | +2.5 | 0.0 | 0.0 | +2.5 |
| Rally | 0.0 | +2.5 | +2.5 | 0.0 |
| Drift | 0.0 | +3.5 | +3.5 | 0.0 |

#### 拉力 / 越野車跑公路（依胎種）

| 胎種 | 前回彈 | 後回彈 | 前壓縮 | 後壓縮 |
|---|---|---|---|---|
| Drag | +3.5 | 0.0 | 0.0 | +3.5 |
| Off-road | +2.5 | 0.0 | 0.0 | +2.5 |
| Road | 0.0 | +2.5 | +2.5 | 0.0 |
| Rally | 0.0 | +2.5 | +2.5 | 0.0 |
| Drift | 0.0 | +3.5 | +3.5 | 0.0 |

#### 拉力 / 越野懸吊跑公路

| 項目 | 偏移 |
|---|---|
| 前回彈 | +3.5 |
| 後回彈 | +3.5 |
| 前壓縮 | +3.5 |
| 後壓縮 | +3.5 |

#### 底盤強化阻尼偏移

| 強化等級 | 前回彈 | 後回彈 | 前壓縮 | 後壓縮 |
|---|---|---|---|---|
| Stock | +0.1 | -0.1 | -0.1 | +0.1 |
| Street | 0.0 | 0.0 | 0.0 | 0.0 |
| Sport | -0.1 | +0.1 | +0.1 | -0.1 |
| Race | -0.2 | +0.2 | +0.2 | -0.2 |

### 3.7 煞車偏移

#### Stock → 升級底盤的煞車壓力

| Stock | 升級後 | 煞車壓力 |
|---|---|---|
| Street | Sport | 0 |
| Street | Semi Race | 0 |
| Street | Race | 0 |
| Street | Drift | +20% |
| Street | Off-road | -15% |
| Street | Rally | 0 |
| Street | Snow | -10% |
| Street | Vintage Race | -20% |
| Street | Drag | -20% |
| Sport | Semi Race | 0 |
| Sport | Race | 0 |
| Sport | Drift | +15% |
| Sport | Off-road | -20% |
| Sport | Rally | 0 |
| Sport | Snow | -20% |
| Sport | Drag | -25% |
| Semi Race | Race | 0 |
| Semi Race | Drift | +10% |
| Semi Race | Off-road | -25% |
| Semi Race | Rally | 0 |
| Semi Race | Snow | -30% |
| Semi Race | Drag | -30% |
| Race | Semi Race | 0 |
| Race | Drift | +5% |
| Race | Off-road | -30% |
| Race | Rally | 0 |
| Race | Snow | -40% |
| Race | Drag | -35% |
| Vintage Race | Sport | 0 |
| Vintage Race | Semi Race | 0 |
| Vintage Race | Race | 0 |
| Vintage Race | Drift | +30% |
| Vintage Race | Off-road | -15% |
| Vintage Race | Rally | 0 |
| Vintage Race | Snow | 0 |
| Vintage Race | Drag | -10% |

#### 拉力 / 越野懸吊跑公路：煞車分布

| 項目 | 偏移 |
|---|---|
| 煞車分布 | +4% |

#### 底盤強化煞車偏移

| 強化等級 | 煞車分布 | 煞車壓力 |
|---|---|---|
| Stock | -1% | -1% |
| Street | 0 | 0 |
| Sport | +1% | +1% |
| Race | +2% | +2% |

### 3.8 差速器偏移

#### 賽車懸吊
無特殊調整，使用第二章通用值。

#### 拉力 / 越野懸吊跑公路

| 項目 | 偏移 |
|---|---|
| 加速 | +10% |
| 減速 | +10% |

#### 底盤強化差速器偏移

| 強化等級 | 加速偏移 | 減速偏移 |
|---|---|---|
| Stock | -2% | +1% |
| Street | 0 | 0 |
| Sport | +2% | -1% |
| Race | +4% | -2% |

### 3.9 齒比

公路賽道無特殊偏移，直接套用第二章通用值。

### 3.10 空力下壓力偏移

#### Stock → 升級底盤

| Stock | 升級後 | 前下壓力 | 後下壓力 |
|---|---|---|---|
| Street | Sport | 0 | 0 |
| Street | Semi Race | 0 | 0 |
| Street | Race | 0 | 0 |
| Street | Drift | -60% | 0 |
| Street | Off-road | 0 | +45% |
| Street | Rally | 0 | 0 |
| Street | Snow | +15% | +15% |
| Street | Vintage Race | +30% | +30% |
| Street | Drag | 0 | +60% |
| Sport | Semi Race | 0 | 0 |
| Sport | Race | 0 | 0 |
| Sport | Drift | -45% | 0 |
| Sport | Off-road | 0 | +60% |
| Sport | Rally | 0 | 0 |
| Sport | Snow | +30% | +30% |
| Sport | Drag | 0 | +75% |
| Semi Race | Race | 0 | 0 |
| Semi Race | Drift | -30% | 0 |
| Semi Race | Off-road | 0 | +75% |
| Semi Race | Rally | 0 | 0 |
| Semi Race | Snow | +45% | +45% |
| Semi Race | Drag | 0 | +90% |
| Race | Semi Race | 0 | 0 |
| Race | Drift | -15% | 0 |
| Race | Off-road | 0 | +90% |
| Race | Rally | 0 | 0 |
| Race | Snow | +60% | +60% |
| Race | Drag | 0 | +105% |
| Vintage Race | Sport | 0 | 0 |
| Vintage Race | Semi Race | 0 | 0 |
| Vintage Race | Race | 0 | 0 |
| Vintage Race | Drift | -90% | 0 |
| Vintage Race | Off-road | 0 | +15% |
| Vintage Race | Rally | 0 | 0 |
| Vintage Race | Snow | 0 | 0 |
| Vintage Race | Drag | 0 | +30% |

---

## 四、越野調校

越野賽道分為 **Dirt（泥地賽道）** 與 **Cross Country（越野鄉野）** 兩類，許多參數方向相反，需分別套用。

### 4.1 輪胎

#### 基準胎壓偏移（在第二章基準上）

| 場景 | 前 (PSI) | 後 (PSI) |
|---|---|---|
| Dirt 基準 | -3.5 | -3.5 |
| Dirt 推頭修正 | -3.5 - 0.5 = -4.0 | -3.5 + 0.5 = -3.0 |
| Cross Country 基準 | -5.5 | -5.5 |
| Cross Country 甩尾修正 | -5.5 + 0.5 = -5.0 | -5.5 - 0.5 = -6.0 |

#### 公路 / 拉力 / 越野車使用非原廠底盤（Dirt）

| 底盤 | 前偏移 | 後偏移 |
|---|---|---|
| Drag | -0.5 | 0.0 |
| Off-road | 0.0 | +0.5 |
| Rally | 0.0 | +0.5 |
| Road | 0.0 | +1.0 |
| Drift | 0.0 | +1.0 |

#### 公路 / 拉力 / 越野車使用非原廠底盤（Cross Country）

| 底盤 | 前偏移 | 後偏移 |
|---|---|---|
| Drag | 0.0 | +0.5 |
| Off-road | -0.5 | 0.0 |
| Rally | -0.5 | 0.0 |
| Road | -1.0 | 0.0 |
| Drift | -1.0 | 0.0 |

#### 底盤強化偏移（Dirt 與 Cross Country 共用）

| 強化等級 | 前 | 後 |
|---|---|---|
| Stock | 0.0 | 0.0 |
| Street | +0.5 | -0.5 |
| Sport | +1.0 | -1.0 |
| Race | +1.5 | -1.5 |

#### 重車修正

| 重量範圍 | Dirt 偏移 | Cross Country 偏移 |
|---|---|---|
| 5000–5999 lb | +5.0 | 0.0 |
| 6000–6999 lb | +5.0 | +5.0 |
| 7000–7999 lb | +10.0 | +5.0 |
| 8000–9999 lb | 0.0 | 0.0 |
| 10000–11999 lb | +5.0 | 0.0 |
| 12000–13999 lb | +5.0 | +5.0 |
| 14000–15999 lb | +10.0 | +5.0 |

#### 輕車修正（Dirt 3000 lb 以下 / Cross Country 4000 lb 以下）

| 重量範圍 | Dirt 偏移 | Cross Country 偏移 |
|---|---|---|
| 3000–3999 lb | 0.0 | -5.0 |
| 2000–2999 lb | -5.0 | -5.0 |
| 1000–1999 lb | -10.0 | -10.0 |
| 0–999 lb | -15.0 | -10.0 |

### 4.2 定位

#### 基準偏移

| 項目 | Dirt | Cross Country |
|---|---|---|
| 前 Camber | +0.1 | -0.1 |
| 後 Camber | +0.1 | -0.1 |
| 前 Toe | -0.1 | +0.1 |
| 後 Toe | +0.1 | -0.1 |
| Caster | +0.1 | -0.1 |

#### 公路 / 拉力 / 越野車（Dirt）

| 底盤 | 前 Camber | 後 Camber | Caster |
|---|---|---|---|
| Drag | +0.5 | 0.0 | -0.5 |
| Off-road | 0.0 | -0.5 | +0.5 |
| Rally | 0.0 | -0.5 | +0.5 |
| Road | 0.0 | -1.0 | +1.0 |
| Drift | 0.0 | -1.0 | +1.0 |

#### 公路 / 拉力 / 越野車（Cross Country）

| 底盤 | 前 Camber | 後 Camber | Caster |
|---|---|---|---|
| Drag | 0.0 | -0.5 | +0.5 |
| Off-road | +0.5 | 0.0 | -0.5 |
| Rally | +0.5 | 0.0 | -0.5 |
| Road | +1.0 | 0.0 | -1.0 |
| Drift | +1.0 | 0.0 | -1.0 |

#### 賽車懸吊修正

| 項目 | 偏移 |
|---|---|
| 前 Camber | -1.0 |
| 後 Camber | -0.5 |
| Caster | +1.0 |

#### 高馬力（400+ hp）

| 場景 | Camber | Caster |
|---|---|---|
| Dirt | +1.0 | -1.0 |
| Cross Country | -1.0 | +1.0 |

#### 底盤強化偏移

| 強化等級 | Camber | 前 Toe | 後 Toe | Caster |
|---|---|---|---|---|
| Stock | 0.0 | 0.0 | 0.0 | 0.0 |
| Street | -0.1 | +0.1 | -0.1 | -0.1 |
| Sport | -0.2 | +0.2 | -0.2 | -0.2 |
| Race | -0.3 | +0.3 | -0.3 | -0.3 |

### 4.3 防傾桿

#### 基準偏移

| 場景 | 前 ARB | 後 ARB |
|---|---|---|
| Dirt 基準 | +0.1 + 0.1 = +0.2 | +0.1 - 0.1 = 0.0 |
| Cross Country 基準 | -0.1 - 0.1 = -0.2 | -0.1 + 0.1 = 0.0 |

#### 公路 / 拉力 / 越野車（Dirt）

| 底盤 | 前硬度 | 後硬度 |
|---|---|---|
| Drag | +12% | -12% |
| Off-road | -12% | +12% |
| Rally | -12% | +12% |
| Road | -24% | +24% |
| Drift | -24% | +24% |

#### 公路 / 拉力 / 越野車（Cross Country）

| 底盤 | 前硬度 | 後硬度 |
|---|---|---|
| Drag | -12% | +12% |
| Off-road | +12% | -12% |
| Rally | +12% | -12% |
| Road | +24% | -24% |
| Drift | +24% | -24% |

#### 高馬力（400+ hp）

| 場景 | ARB 硬度 |
|---|---|
| Dirt | -24% |
| Cross Country | -12% |

#### 底盤強化偏移

| 強化等級 | 前 ARB | 後 ARB |
|---|---|---|
| Stock | 0.0 | 0.0 |
| Street | -0.1 | +0.1 |
| Sport | -0.2 | +0.2 |
| Race | -0.3 | +0.3 |

### 4.4 彈簧

#### 基準偏移

| 場景 | 前彈簧 | 後彈簧 |
|---|---|---|
| Dirt 基準 | -0.5 + 0.5 = 0.0 | -0.5 - 0.5 = -1.0 |
| Cross Country 基準 | +0.5 - 0.5 = 0.0 | +0.5 + 0.5 = +1.0 |

#### 公路 / 拉力 / 越野車

| 底盤 | 前硬度 | 後硬度 |
|---|---|---|
| Drag | -12% | -12% |
| Off-road | -12% | -12% |
| Rally | -12% | -12% |
| Road | -24% | -24% |
| Drift | -24% | -24% |

#### 賽車懸吊修正
Dirt 與 Cross Country 皆 **彈簧值減半**。

#### 高馬力（400+ hp）

| 場景 | 彈簧值 |
|---|---|
| Dirt | -24% |
| Cross Country | -12% |

#### 底盤強化偏移

| 強化等級 | 前彈簧 | 後彈簧 |
|---|---|---|
| Stock | 0.0 | 0.0 |
| Street | -0.5 | +0.5 |
| Sport | -1.0 | +1.0 |
| Race | -1.5 | +1.5 |

### 4.5 車高

#### 基準

| 場景 | 前 | 後 |
|---|---|---|
| Dirt | 設為最大 | 設為最大 - 0.1 |
| Cross Country | 設為最大 - 0.1 | 設為最大 |

#### 公路 / 拉力 / 越野車（Dirt）

| 底盤 | 前 | 後 |
|---|---|---|
| Drag | 設為最大 | 0.0 |
| Off-road | 0.0 | 設為最大 |
| Rally | 0.0 | 設為最大 |
| Road | 0.0 | 設為最大 |
| Drift | 0.0 | 設為最大 |

#### 公路 / 拉力 / 越野車（Cross Country）

| 底盤 | 前 | 後 |
|---|---|---|
| Drag | 0.0 | 設為最大 |
| Off-road | 設為最大 | 0.0 |
| Rally | 設為最大 | 0.0 |
| Road | 設為最大 | 0.0 |
| Drift | 設為最大 | 0.0 |

#### 底盤強化偏移

| 強化等級 | 前偏移 | 後偏移 |
|---|---|---|
| Stock | 0.0 | 0.0 |
| Street | -0.1 | +0.1 |
| Sport | -0.2 | +0.3 |
| Race | -0.3 | +0.3 |

### 4.6 阻尼、煞車、差速器、齒比、空力

Part 4 對於阻尼、煞車、差速器、齒比、空力**未提供越野特定偏移**，請直接套用第二章通用值。

---

## 五、抓地與速度導向調校

抓地（Grip）導向適用於慢彎多的賽道；速度（Speed）導向適用於直線多、彎少的賽道。

**判定關鍵**：
- **差速器設定**：低差速器 = 抓地；高差速器 = 速度
- **馬力等級**：400+ hp 需額外底盤補償

### 5.1 胎壓偏移

| 設定 | 前偏移 | 後偏移 |
|---|---|---|
| Grip（抓地） | -1.0 + 0.5 | -1.0 - 0.5 |
| Medium Grip | -0.5 + 0.5 | -0.5 - 0.5 |
| Medium Speed | +0.5 - 0.5 | +0.5 + 0.5 |
| Speed（速度） | +1.0 - 0.5 | +1.0 + 0.5 |

範例：起始 28.5/28.5 → Grip 變 28.0/27.0；Speed 變 29.0/30.0。

### 5.2 定位（Camber / Caster）

- **一般車**：僅微調
- **高馬力（400+ hp）**：變動較大，且依是否裝可調空力而異

| 設定 | 前 Camber | 後 Camber | Caster |
|---|---|---|---|
| Grip + 有空力 | +1.0 | +1.0 -3.0 | -1.0 |
| Speed + 無空力 | -1.0 +3.0 | -1.0 | +1.0 |

### 5.3 防傾桿

- 標準偏移：前後 ±0.1 ~ ±0.2
- 高馬力車：
  - Grip：硬度 **-24%**
  - Speed：硬度 **+24%**

範例：原前 ARB 20.5 → Grip 變 12.8；Speed 變 57.9。

### 5.4 彈簧

- 標準偏移：-1.0/-1.0（Grip）~ +1.0/+1.0（Speed）
- 高馬力車：硬度 **±24%**

範例：原前彈簧 738.71 → Grip 變 556.63；Speed 變 897.15。

### 5.5 車高

- 高馬力車：依是否有空力與 Grip/Speed 取向，**設為最大**
- 標準偏移：前後 ±0.1 ~ ±0.2

範例：5.0/6.0 → Grip 維持 5.0/6.4；Speed 變 5.0/5.6。

### 5.6 阻尼

- 標準偏移：±0.1 ~ ±0.2
- 高馬力車：
  - Grip：前 **+2.5**
  - Speed：後 **+2.5**

範例：原回彈 12.4 → Grip 變 14.9；Speed 變 12.8。

### 5.7 煞車

- 標準分布：±2%；標準壓力：±5%
- 高馬力車：壓力額外 ±20%

範例：52% / 125% → Grip 變 54% / 110%；Speed 變 50% / 140%。

### 5.8 差速器（核心對偶切換表）

| 設定 | 加速偏移 | 減速偏移 |
|---|---|---|
| Grip | -24% | +40% |
| Speed | +24% | -40% |

範例：28% / 45% → Grip 變 4% / 85%；Speed 變 52% / 5%。

#### FWD 修正
僅前加速調整，前減速保持 0%。

#### AWD 修正
- 前加速 + 後減速調整
- Race / Rally / Off-road 差速器另含分布修正

### 5.9 齒比

| 設定 | Final Drive 偏移 |
|---|---|
| Grip | +0.5 |
| Speed | -0.5 |

範例：4.38 → Grip 變 4.88；Speed 變 3.88。

### 5.10 空力

- Grip：下壓力設為最大
- Speed：下壓力設為最小
- 高馬力 Speed 取向：前下壓力需提高以維持穩定

範例：原 127 min / 395 max → Medium Grip 變 146 前 / 513 後；Medium Speed 變 108 前 / 277 後。

---

## 六、季節、時段與天氣修正

**核心原則**：高溫 = 高抓地 = 偏硬；低溫／濕／雪 = 低抓地 = 偏軟。

**疊加方式**：季節、時段、天氣三類修正可**直接相加**——例如夜間 + 雨天就同時套用兩組偏移。

### 6.1 季節（Spring / Summer / Autumn / Winter）

墨西哥地圖的氣溫特徵：
- **Spring（春）**：氣溫高、地溫高 → 偏硬
- **Summer（夏）**：氣溫低、地溫高 → 平衡
- **Autumn（秋）**：氣溫低、地溫低 → 偏軟
- **Winter（冬）**：氣溫高、地溫低 → 補償

| 設定 | Spring | Summer | Autumn | Winter |
|---|---|---|---|---|
| 胎壓（前/後） | +0.5/+0.5 | -0.5/-0.5 | -0.5/-0.5 | +0.5/+0.5 |
| ARB（前/後） | -0.1/-0.1 | +0.1/+0.1 | +0.1/+0.1 | -0.1/-0.1 |
| 彈簧（前/後） | -0.1/-0.1 | +0.1/+0.1 | +0.1/+0.1 | -0.1/-0.1 |
| 車高（前/後） | -0.1/-0.1 | +0.1/+0.1 | +0.1/+0.1 | -0.1/-0.1 |
| 阻尼回彈（前/後） | +0.1/+0.1 | +0.1/+0.1 | -0.1/-0.1 | -0.1/-0.1 |
| 阻尼壓縮（前/後） | +0.1/+0.1 | +0.1/+0.1 | -0.1/-0.1 | -0.1/-0.1 |
| 齒比（Sport/Race） | +0.1/+0.1 | +0.1/+0.1 | -0.1/-0.1 | -0.1/-0.1 |

### 6.2 時段（Morning / Noon / Afternoon / Evening，僅乾燥條件）

- **Morning（晨）**：氣溫高、地溫低
- **Noon（午）**：氣溫高、地溫高
- **Afternoon（下午）**：氣溫低、地溫高
- **Evening（晚）**：氣溫低、地溫低

| 設定 | Morning | Noon | Afternoon | Evening |
|---|---|---|---|---|
| 胎壓（前/後） | +0.5/+0.5 | +0.5/+0.5 | -0.5/-0.5 | -0.5/-0.5 |
| ARB（前/後） | -0.1/-0.1 | -0.1/-0.1 | +0.1/+0.1 | +0.1/+0.1 |
| 彈簧（前/後） | -0.1/-0.1 | -0.1/-0.1 | +0.1/+0.1 | +0.1/+0.1 |
| 車高（前/後） | -0.1/-0.1 | -0.1/-0.1 | +0.1/+0.1 | +0.1/+0.1 |
| 阻尼回彈（前/後） | -0.1/-0.1 | +0.1/+0.1 | +0.1/+0.1 | -0.1/-0.1 |
| 阻尼壓縮（前/後） | -0.1/-0.1 | +0.1/+0.1 | +0.1/+0.1 | -0.1/-0.1 |

### 6.3 天氣（依賽道類型）

#### Road（公路）

| 設定 | Fog | Night | Rain/Snow |
|---|---|---|---|
| 胎壓（前/後） | -0.5/+0.5 | -0.5 ~ +0.5 / -0.5 ~ +0.5 | -1.0 ~ +1.0 / -1.0 ~ +1.0 |
| Camber | +0.1 | +0.1 | +0.2 |
| 前 Toe | -0.1 | -0.1 | -0.2 |
| 後 Toe | +0.1 | +0.1 | +0.2 |
| Caster | +0.1 | +0.1 | +0.2 |
| ARB（前/後） | +0.1/-0.1 | +0.1 ~ +0.1 / +0.1 ~ -0.1 | +0.2 ~ +0.2 / +0.2 ~ -0.2 |
| 彈簧（前/後） | +0.1/-0.1 | +0.1 ~ +0.1 / +0.1 ~ -0.1 | +0.2 ~ +0.2 / +0.2 ~ -0.2 |
| 車高（前/後） | +0.1/-0.1 | +0.2/0.0 | +0.4/0.0 |
| 阻尼回彈（前/後） | +0.1/-0.1 | 0.0/-0.2 | 0.0/-0.4 |
| 阻尼壓縮（前/後） | +0.1/-0.1 | 0.0/-0.2 | 0.0/-0.4 |
| 煞車分布 | -1% | -1% | -2% |
| 煞車壓力 | -1% | -1% | -2% |
| 差速器加速 | -2% | -2% | -4% |
| 差速器減速 | +1% | +1% | +2% |
| 齒比（Sport/Race） | 0.0/0.0 | -0.1/-0.1 | -0.2/-0.2 |

#### Cross-Country（越野鄉野）

| 設定 | Fog | Night | Rain/Snow |
|---|---|---|---|
| 胎壓（前/後） | -1.0/+1.0 | -1.0 ~ +1.0 / -1.0 ~ +1.0 | -1.5 ~ +1.5 / -1.5 ~ +1.5 |
| Camber | +0.2 | +0.2 | +0.3 |
| 前 Toe | -0.2 | -0.2 | -0.3 |
| 後 Toe | +0.2 | +0.2 | +0.3 |
| Caster | +0.2 | +0.2 | +0.3 |
| ARB（前/後） | +0.2/-0.2 | +0.2 ~ +0.2 / +0.2 ~ -0.2 | +0.3 ~ +0.3 / +0.3 ~ -0.3 |
| 彈簧（前/後） | +0.2/-0.2 | +0.2 ~ +0.2 / +0.2 ~ -0.2 | +0.3 ~ +0.3 / +0.3 ~ -0.3 |
| 車高（前/後） | +0.2/-0.2 | +0.4/0.0 | +0.6/0.0 |
| 阻尼回彈（前/後） | +0.2/-0.2 | 0.0/-0.4 | 0.0/-0.6 |
| 阻尼壓縮（前/後） | +0.2/-0.2 | 0.0/-0.4 | 0.0/-0.6 |
| 煞車分布 | -2% | -2% | -3% |
| 煞車壓力 | -2% | -2% | -3% |
| 差速器加速 | -4% | -4% | -6% |
| 差速器減速 | +2% | +2% | +3% |
| 齒比（Sport/Race） | -0.1/-0.1 | -0.2/-0.2 | -0.3/-0.3 |

#### Dirt（泥地）

| 設定 | Fog | Night | Rain/Snow |
|---|---|---|---|
| 胎壓（前/後） | -2.0/+2.0 | -1.5 ~ +1.5 / -1.5 ~ +1.5 | -2.0 ~ +2.0 / -2.0 ~ +2.0 |
| Camber | +0.3 | +0.3 | +0.4 |
| 前 Toe | -0.3 | -0.3 | -0.4 |
| 後 Toe | +0.3 | +0.3 | +0.4 |
| Caster | +0.3 | +0.3 | +0.4 |
| ARB（前/後） | -0.3/-0.3 | +0.3 ~ +0.3 / +0.3 ~ -0.3 | +0.4 ~ +0.4 / +0.4 ~ -0.4 |
| 彈簧（前/後） | -0.3/-0.3 | +0.3 ~ +0.3 / +0.3 ~ -0.3 | +0.4 ~ +0.4 / +0.4 ~ -0.4 |
| 車高（前/後） | +0.3/-0.3 | +0.6/0.0 | +0.8/0.0 |
| 阻尼回彈（前/後） | +0.3/-0.3 | 0.0/-0.6 | 0.0/-0.8 |
| 阻尼壓縮（前/後） | +0.3/-0.3 | 0.0/-0.6 | 0.0/-0.8 |
| 煞車分布 | -3% | -3% | -4% |
| 煞車壓力 | -3% | -3% | -4% |
| 差速器加速 | -6% | -6% | -8% |
| 差速器減速 | +3% | +3% | +4% |
| 齒比（Sport/Race） | -0.2/-0.2 | -0.3/-0.3 | -0.4/-0.4 |

---

## 七、平衡與剛性調校

> ⚠️ **原作者尚未發布**：截至本整理日期（2026-04-21），forzaquicktune.com Part 7 仍標示為 "Coming soon..."。此章待原作者更新後補入本文件。

---

## 附錄：套用流程建議

依 QuickTune 的設計，建議的套用順序為：

1. **第一章查表**：確認車型（Car Type）、車身年代（Body Type）、底盤類型（Chassis Type）、是否開輪。
2. **第二章設基準**：依車型查每一子系統的基準值（胎壓、定位、ARB、彈簧、車高、阻尼、煞車、差速器、齒比、空力）。
3. **第三或四章疊加情境偏移**：依賽事類型（公路 / Dirt / Cross Country）查表加上偏移。
4. **第五章 Grip/Speed 微調**：依賽道彎道密度做最後的抓地 vs 速度傾向調整。
5. **第六章季節 / 時段 / 天氣修正**：依比賽當下的環境條件加上偏移（可加總疊加）。
6. **第七章（待補）**：用於整體平衡與剛性的最終校準。

> **數值校驗提醒**：QuickTune 的所有偏移皆為相對值，套用時請務必先記錄遊戲內預設值，再以加減方式套入。遊戲版本若有更新（Series Update），原廠基準值可能微調，請先在實車上確認。
