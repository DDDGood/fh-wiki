---
title: QuickTune 套用流程（附錄）
category: tuning
tags: [QuickTune, 流程, 套用步驟, 速查]
related_cars: []
pi_class: []
game: FH5
version: 未標註
status: draft
sources:
  - Docs/_sources/地平線5_QuickTune完整調校指南_整理版.md
last_updated: 2026-04-21
revisions:
  - { date: 2026-04-21, note: 初版，源自 QuickTune 附錄：套用流程建議 }
---

# QuickTune 套用流程

依 QuickTune 的設計，建議的**套用順序**如下。

---

## 步驟

1. **查表（Part 1）**：確認車型（Car Type）、車身年代（Body Type）、底盤類型（Chassis Type）、是否開輪。
   → 參見 [車型分類框架](../cars/車型分類框架.md)

2. **設基準（Part 2）**：依車型查每一子系統的基準值——胎壓、定位、ARB、彈簧、車高、阻尼、煞車、差速器、齒比、空力。
   → 參見 [QuickTune 基準值總表](./QuickTune基準值總表.md)

3. **疊加情境偏移**：依賽事類型查表加上偏移：
   - 公路 → [公路調校修正表](./公路調校修正表.md)（Part 3）
   - 越野（Dirt / Cross Country）→ [越野調校修正表](./越野調校修正表.md)（Part 4）

4. **Grip / Speed 微調（Part 5）**：依賽道彎道密度做最後的抓地 vs 速度傾向調整。
   → 參見 [抓地與速度取向](./抓地與速度取向.md)

5. **環境修正（Part 6）**：依比賽當下的季節 / 時段 / 天氣加上偏移（**可直接相加疊加**）。
   → 參見 [環境條件修正表](./環境條件修正表.md)

6. **最終校準（Part 7，待補）**：整體平衡與剛性。
   → 參見 [平衡與剛性調校](./平衡與剛性調校.md)（原作者待補）

---

## 數值校驗提醒

> **QuickTune 的所有偏移皆為相對值**，套用時請務必：
>
> 1. **先記錄遊戲內預設值**
> 2. 再以加減方式套入偏移
> 3. 遊戲版本若有更新（Series Update），原廠基準值可能微調，**請先在實車上確認**

---

## 速記流程

```
查表 → 設基準 → 情境偏移 → Grip/Speed 微調 → 環境修正 → （平衡剛性）
```

---

## 延伸閱讀

- [三車種公式速查](./三車種公式速查.md) — QuickTune 體系之外的輕量替代（新手起手值）
- [調校基礎概念](./基礎概念.md) — 傳動、引擎布局、前端重量比

## 來源

- [《QuickTune 完整調校指南》整理版](../../_sources/地平線5_QuickTune完整調校指南_整理版.md) — 附錄：套用流程建議
