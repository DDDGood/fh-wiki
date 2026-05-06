# Forza Horizon 攻略庫索引

> 本索引列出 `Docs/wiki/` 下所有精煉攻略，依 `_category.yml` 分類排序。
> 靜態網站部署後亦可透過側邊欄瀏覽；此檔供離線／GitHub 直接查閱之用。

**最後更新**：2026-05-06（駕駛分類新增「常見彎型走線」「賽道地形與路面」兩檔；賽車線與彎道基礎新增 §五 Early Apex；補列小包子 FH5 進階技術系列來源）

---

## 🔧 車輛調校（tuning）

### 教學型攻略

| 檔案 | 一句話 |
|------|--------|
| [基礎概念](wiki/tuning/基礎概念.md) | 傳動／引擎布局／前端重量比／PI 等級／轉向過度 vs 不足；附 Lotus Evora 案例 |
| [三車種公式速查](wiki/tuning/三車種公式速查.md) ⭐ | 公路 / 拉力越野 / 漂移三組可直接套用的數值公式（新手起手值） |
| [胎壓](wiki/tuning/胎壓.md) | 多家胎壓起手值；暖胎原理；按車重／胎質分級；中文 vs 英文社群 5+ 家併列 |
| [齒比](wiki/tuning/齒比.md) | 固定比值公式、終減速比調整法、十速當六七檔用、功率帶原理、漂移齒比收緊法 |
| [四輪定位](wiki/tuning/四輪定位.md) | Camber / Toe / Caster 多家數值併列；camber 雙驗法（胎溫 + 彎尾段 live camber） |
| [防傾桿](wiki/tuning/防傾桿.md) | 6 車種細分；禁忌前硬後軟；165 共識；依引擎佈局的 RWD 起點 |
| [彈簧與車高](wiki/tuning/彈簧與車高.md) | 驅動方式細分；推頭口訣；FH5 抬高車高反提升抓地反直覺；前軸重量比 % 配比 |
| [阻尼](wiki/tuning/阻尼.md) | 回彈/衝擊多家數值；硬核公式法（回彈 × 0.25/0.4）；FXX S1 AWD 範例 |
| [下壓力](wiki/tuning/下壓力.md) | 前滿後取捨；後驅 PI 階級區分；漂移前大後小 |
| [煞車調校](wiki/tuning/煞車調校.md) | 依控制器類型；漂移力度多家併列；中英文 UI 方向相反警示 |
| [差速器](wiki/tuning/差速器.md) | 多家併列；遙測實驗驗證；依馬力精細範圍；前差加速彎中效果 FH5 實作爭議 |
| [漂移重量比公式](wiki/tuning/漂移重量比公式.md) | 依車輛前後重量比推算防傾桿/彈簧/阻尼 |
| [過彎三段診斷與症狀對策](wiki/tuning/三段彎道診斷.md) | 入彎／中段／出彎症狀分流診斷；對應處方表 |

### 🛠️ 驗證工具

| 檔案 | 一句話 |
|------|--------|
| [遙測使用指南](wiki/tuning/遙測使用指南.md) | Telemetry 4 大頁面；胎溫色區；懸掛壓縮判讀；camber 過彎範圍 |

### 📚 QuickTune 進階參考系列

系統性調校體系（依車型 × 車身 × 底盤的完整偏移量）：

| 檔案 | 一句話 |
|------|--------|
| [QuickTune 基準值總表](wiki/tuning/QuickTune基準值總表.md) | Part 2：10 個調校參數的基準值表 |
| [公路調校修正表](wiki/tuning/公路調校修正表.md) | Part 3：公路賽道情境偏移 |
| [越野調校修正表](wiki/tuning/越野調校修正表.md) | Part 4：Dirt / Cross Country 偏移 |
| [抓地與速度取向](wiki/tuning/抓地與速度取向.md) | Part 5：Grip / Speed 微調 |
| [環境條件修正表](wiki/tuning/環境條件修正表.md) | Part 6：季節 / 時段 / 天氣 |
| [平衡與剛性調校](wiki/tuning/平衡與剛性調校.md) | Part 7：🚧 原作者待補 |
| [QuickTune 套用流程](wiki/tuning/QuickTune套用流程.md) | 附錄：完整套用順序 |

### 📖 硬核流派

| 檔案 | 一句話 |
|------|--------|
| [硬核調校範本](wiki/tuning/硬核調校範本.md) | 硬核流派三車種完整矩陣（含直線加速） |

---

## ⚙️ 車輛改裝（upgrades）

### 配件細項

| 檔案 | 一句話 |
|------|--------|
| [改造選擇](wiki/upgrades/改造選擇.md) | 置換引擎、傳動方式、進氣（渦輪種類）、寬體；含高 CP 引擎統一速查表 |
| [空力與外觀配件](wiki/upgrades/空力與外觀配件.md) | 保險桿、尾翼、擾流板、引擎蓋、側翼；可調前 aero 是最強升級 |
| [輪胎配件](wiki/upgrades/輪胎配件.md) | 輪胎材料、胎寬、輪轂、輪距；公路用拉力胎策略；按 PI 級的橫向 G 力指標 |
| [底盤配件](wiki/upgrades/底盤配件.md) | 煞車、懸掛、防傾桿、防滾架、減重；off-road 懸吊跨界給抓地過剩公路車 |
| [引擎配件](wiki/upgrades/引擎配件.md) | 動力配件三類、凸輪軸與飛輪、HokiHoshi 升級順序、F4TR 紅線錯位 cross-link |
| [傳動配件](wiki/upgrades/傳動配件.md) | 離合器、變速箱、傳動軸、差速器（必裝雙向）；依驅動形式的 diff 選型表 |

### 專題

| 檔案 | 一句話 |
|------|--------|
| [PI 性價比思路](wiki/upgrades/PI性價比思路.md) ⭐ | 硬核 PI 優化視角：三層 CP 分類、子系統 PI 排序、改裝順序、單人 vs 多人哲學 |

---

## 🏁 駕駛操作（driving）

| 檔案 | 一句話 |
|------|--------|
| [賽車線與彎道基礎](wiki/driving/賽車線與彎道基礎.md) | Racing Line / Geometric vs Ideal Line / Apex / Late Apex / **Early Apex** / Healthy Oversteer / Slip vs Steering Angle |
| [常見彎型走線](wiki/driving/常見彎型走線.md) ⭐ | 直角彎 / U 弯（大/小+雙彎心）/ V 弯 / 掉頭彎走法 + FH5 賽道實例（黃金驛站、瞭望台、吉娃娃、大教堂、火山衝刺賽）+ 檔位建議 |
| [煞車技巧](wiki/driving/煞車技巧.md) | 入彎煞車三大壞習慣 / 重煞→平順鬆煞 / 重量轉移路徑前→外→後 / Trail Braking / Forza 輔助線紅區判斷煞車點 |
| [賽道地形與路面](wiki/driving/賽道地形與路面.md) | 上下側傾（飛坡、坡頂鬆油）/ 左右側傾（傾斜彎道借力，側向 G 2→2.5）/ 路面物體硬軟件 / 凹陷凸起 + FH5 賽道實例（大教堂、穆萊赫、墨西哥環道、翡翠環道） |
| [漂移基礎](wiki/driving/漂移基礎.md) | 前置設定 + 駕駛技巧 + 排錯（HokiHoshi 2021 漂移完整指南濃縮） |
| [RWD 駕駛技巧](wiki/driving/RWD駕駛技巧.md) | meta 背景 / Launch / 過彎重量管理 / 不要彎太多 |
| [越野駕駛技巧](wiki/driving/越野駕駛技巧.md) | Grip zone / 受控 oversteer 入彎 / 跨彎重量管理 |
| [進階練習小技巧](wiki/driving/進階練習小技巧.md) | Drafting / Throttle/Steering Feathering（含彎心場景：手柄半開／鍵盤連點）/ 慢車練習法 / Rivals 自我幽靈練習 |

---

## 🚗 車輛介紹（cars）

| 檔案 | 一句話 |
|------|--------|
| [車型分類框架](wiki/cars/車型分類框架.md) | QuickTune 體系的車型 × 車身年代 × 底盤類型分類 |
| [汽車基礎術語](wiki/cars/汽車基礎術語.md) | 驅動／引擎／功率術語（FF/FR/MR、torque/HP/BHP、功率帶、Build 類型） |
| [車型代號](wiki/cars/車型代號.md) | Chassis Codes（車的「世代身分證」） |

---

## 🎮 遊戲設定（settings）

| 檔案 | 一句話 |
|------|--------|
| [駕駛輔助與輸入設定](wiki/settings/駕駛輔助與輸入設定.md) | ABS / TCS / ESC / 換檔模式 / 控制器死區；FH5 手排顯著快於自排原因 |

---

## 🏆 活動與賽事（events）

_尚無內容。_

---

## 原始來源

精煉內容皆可追溯至 [`Docs/_sources/`](_sources/)。已整合來源（不分先後）：

### 中文社群
- [地平線5 調校教學](_sources/地平線5_調校教學_整理版.md) — 16 檔基礎覆蓋
- [地平線5_萌新攻略第九期_自定義調校數值公式](_sources/地平線5_萌新攻略第九期_自定義調校數值公式_整理版.md) — 公式派
- [地平線5_QuickTune完整調校指南](_sources/地平線5_QuickTune完整調校指南_整理版.md) — 系統性矩陣（QuickTune 系列檔）
- [地平線5-硬核調校指南](_sources/地平線5-硬核調校指南_整理版.md) — 硬核派完整矩陣

#### 小包子 FH5 技術進階系列
- [小包子 FH5 技術進階1：四大主流胎系特性](_sources/小包子_FH5_技術進階1_四大主流胎系特性_整理版.md) — 熱熔／直線／拉力／漂移四胎系特性與代表車輛
- [小包子 FH5 技術進階5：彎道講解1 早晚彎心與直角彎](_sources/小包子_FH5_技術進階5_彎道講解1_早晚彎心與直角彎_整理版.md) — 早彎心三段分法、外內外物理原理、直角彎拆解
- [小包子 FH5 技術進階6：彎道講解2 UV型彎過法](_sources/小包子_FH5_技術進階6_彎道講解2_UV型彎過法_整理版.md) — 大 U 雙彎心、小 U 含檔位動作分解、V 弯不超車、掉頭彎失誤
- [小包子 FH5 技術進階7 番外：地形對車輛的影響](_sources/小包子_FH5_技術進階7_番外_地形對車輛的影響_整理版.md) — 上下/左右側傾、路面硬軟件、凹陷凸起 + 5 處 FH5 賽道實例

### 英文社群（HokiHoshi）
- [HokiHoshi FH5 2025 改裝速成](_sources/HokiHoshi_FH5_2025改裝速成_整理版.md)
- [HokiHoshi FH5 2025 調校速成](_sources/HokiHoshi_FH5_2025調校速成_整理版.md)
- [HokiHoshi FH5 2023 新手車輛知識與術語](_sources/HokiHoshi_FH5_2023新手車輛知識與術語_整理版.md)
- [HokiHoshi FH5 2021 改裝零件指南](_sources/HokiHoshi_FH5_2021改裝零件指南_整理版.md)
- [HokiHoshi FH5 2021 調校教學](_sources/HokiHoshi_FH5_2021調校教學_整理版.md)
- [HokiHoshi FH5 2021 漂移完整指南](_sources/HokiHoshi_FH5_2021漂移完整指南_整理版.md)
- [HokiHoshi FH5 2021 RWD 完整指南](_sources/HokiHoshi_FH5_2021RWD完整指南_整理版.md)
- [HokiHoshi FH4 2019 駕駛學校 走線與技巧](_sources/HokiHoshi_FH4_2019駕駛學校_走線與技巧_整理版.md) — 跨代通用駕駛理論：Geometric vs Ideal Line、Trail Braking、Rally 駕駛、Rivals 自我幽靈

### 英文社群（其他）
- [Mustuff124 FH5 2023 調校全面教學](_sources/Mustuff124_FH5_2023調校全面教學_整理版.md) — 多家比對的具體例補強
- [Johnson Racing FH5 2025 FXX S1 AWD OP 教學](<_sources/Johnson Racing_FH5_2025_FXX_S1_AWD_OP教學_整理版.md>) — 反直覺實作集（off-road 懸吊跨界、FH5 自排誤判 power band、前差加速彎中效果衝突）
