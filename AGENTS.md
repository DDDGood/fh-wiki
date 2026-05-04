# Codex 專案指南

這份文件是給 Codex / coding agent 的專案入口。它不是 `CLAUDE.md` 的逐字搬運，而是把目前專案的結構、工作流與安全規則整理成我之後進來能快速接上的版本。

## 專案定位

這個 repo 是一個 Forza Horizon 5 的繁體中文攻略與遙測分析專案，主要有兩條線：

1. **攻略知識庫**：把 Bilibili、YouTube、PDF、論壇、Reddit 等來源整理成繁體中文 `_sources/`，再精煉整合到 `Docs/wiki/`。
2. **FH5 遙測工具**：透過 UDP Data Out 錄製賽事資料，產生 `raw.csv`、`meta.json`、`summary.md`，再用 wiki 知識產出賽事分析與調校建議。

專案的寫作語言預設是**繁體中文**。車廠、車型、遊戲專有名詞保留原拼寫，例如 BRZ、Evora、Viper、S1、A 組。

## 重要目錄

```text
D:\Projects\Forza Horizon\
├── AGENTS.md                    # Codex 專案指南
├── CLAUDE.md                    # Claude 專案指南與歷史規範
├── Docs\
│   ├── _raw\                    # 原始素材暫存，如 SRT、PDF、圖片
│   ├── _sources\                # 經整理的完整來源文件，保留細節，不直接精煉
│   └── wiki\                    # 精煉後的 VitePress wiki 內容
├── scripts\forza_telemetry\     # FH5 UDP recorder / summarizer / GUI
├── data\forza_telemetry\
│   ├── cars\                    # 車輛資料庫，例：1564.yml，會進版控
│   └── sessions\                # 遙測 session，raw/meta/summary/analysis，通常 gitignored
├── memory\                      # 長期回饋與工作記憶
└── .claude\skills\              # Claude skills，Codex 可參考其工作流程
```

## 攻略資料流

```text
外部來源 / SRT / PDF / 網頁
  -> Docs/_raw/                # 原始素材
  -> Docs/_sources/*_整理版.md  # 完整繁中整理版，保留所有數值
  -> Docs/wiki/**/*.md         # 細粒度 wiki，帶 frontmatter 與來源追溯
  -> VitePress / GitHub Pages
```

核心原則：

- `_raw/` 是原始素材，不是最終知識。
- `_sources/` 是永久來源層，**不要在 wiki 整合時改動**。
- `Docs/wiki/` 是精煉後的知識層，應有 frontmatter、來源、修訂紀錄。
- 數值不可擅改。胎壓、外傾角、阻尼、差速器百分比、車高、齒比等都要照來源保留。
- 主題重疊不是拒收理由；新的數值、角度、適用情境或 UI 怪癖都可能有價值。

## 遙測資料流

```text
FH5 Data Out UDP
  -> scripts/forza_telemetry/recorder.py
  -> data/forza_telemetry/sessions/{timestamp}_car{ordinal}_PI{pi}/raw.csv
  -> meta.json
  -> scripts/forza_telemetry/summarize.py
  -> summary.md
  -> race analysis / analysis.md
```

常用指令：

```powershell
python -m scripts.forza_telemetry --help
python -m scripts.forza_telemetry --verbose
python -m scripts.forza_telemetry.summarize
python -m scripts.forza_telemetry.summarize --all
```

`summary.md` 是快速索引，不一定是真相。若要給具體調校或駕駛建議，重要數字最好回 `raw.csv` 驗證，尤其是推頭/轉向過度集中在哪些彎、煞車與油門行為、或 summary 指標看起來和直覺相反時。

## 車輛資料庫

`data/forza_telemetry/cars/{ordinal}.yml` 記錄常用車的元資料與目前調校。它是個人車庫，不屬於 `Docs/wiki/`。

規則：

- 新增車輛時從 `_template.yml` 複製，例如 `1564.yml`。
- 調校歷史靠 git log，不在 YAML 裡維護 history 陣列。
- session 結束時 recorder 會把當時的車輛資料凍結到 `meta.json` 的 `car.db`。
- 單位依 `data/forza_telemetry/cars/README.md`：胎壓 psi、彈簧 kgf/mm、車高 cm、角度用度、煞車/差速器用百分比數字但不寫 `%`。

## Claude Skills 對應工作流

Codex 沒有直接執行 `.claude/skills` 的機制，但可以把它們當作專案 SOP 參考。目前已另外建立 Codex 版 `.codex/skills/race-analyst/`，用於分析 telemetry session。

| Skill | 何時參考 | 重點 |
|---|---|---|
| `bilibili-to-doc` | 處理 `Docs/_raw/*.srt` | 清掉 SRT 時間軸、BGM、口癖，輸出完整繁中整理版 |
| `knowledge-curator` | 使用者提供外部來源要評估是否收錄 | 先做來源簡介與審查，不要直接存入；保留所有新增細節 |
| `wiki-integrator` | 把 `_sources/` 的單一來源整合進 wiki | 先產生 NEW/MERGE/REVISE/DUP 計劃，使用者確認後才改 wiki |
| `wiki-doc-writer` | 從多份 `_sources/` 寫一篇新主題長文 | 來源盤點、大綱、確認後撰寫；數值要有來源註腳 |
| `wiki-site-builder` | 建置或維護 VitePress / GitHub Pages | 不動內容，只管網站骨架、側邊欄、部署 |
| `race-analyst` | 分析 `summary.md` / session | 必讀相關 wiki，產出駕駛建議、調校建議、下次測試清單 |

## Wiki Frontmatter

新增或大修 `Docs/wiki/**/*.md` 時，維持這類 frontmatter：

```yaml
---
title: 差速器調校
category: tuning
tags: [差速器, 進階, 後驅]
related_cars: []
pi_class: [A, S1]
game: FH5
version: 未標註
status: stable
sources:
  - Docs/_sources/地平線5-硬核調校指南_整理版.md
last_updated: 2026-05-04
revisions:
  - { date: 2026-05-04, note: 初版 }
---
```

不可虛構 `sources`，不確定版本就填 `未標註`。遇到來源數值衝突，預設併列或標記待確認，不自行挑一邊。

## 可量化規則

若 wiki 新增「可觀測症狀 -> 處方」的規則，使用統一 callout，方便日後和 `summarize.py` 對齊：

```markdown
> 🔬 **可量化規則**
>
> 條件：{可觀測指標} {比較運算} {門檻}
> 處方：{調校或駕駛動作}
> 遙測對應：{已偵測 — summarize.py 缺陷 N / 未偵測 / 未偵測（DEFERRED）}
```

整合來源時若發現 wiki 規則和 `summarize.py` 門檻不一致，記錄為後續同步任務；不要在內容整合任務中順手大改分析器。

## 編輯守則

- 優先使用 `rg` / `rg --files` 搜尋。
- 文件與對話預設繁體中文。
- 不要刪除 `_raw/` 素材，除非使用者明確確認。
- 不要改 `_sources/` 來配合 wiki；它是來源層。
- 對既有 wiki 做多處修改前，先讀當前檔案，避免全形/半形標點、空格、粗體位置導致 patch 失準。
- 遙測 session 體積大且通常 gitignored，不要把 `data/forza_telemetry/sessions/` 當成要整理進版控的內容。
- `.bat` 檔盡量維持 ASCII，避免 Windows codepage 造成亂碼或指令誤讀。

## 驗證與環境注意

常見 smoke test：

```powershell
python -c "from scripts.forza_telemetry import packet, session, recorder; print('OK')"
python -m scripts.forza_telemetry --help
python -m scripts.forza_telemetry.summarize --help
```

若要建置網站，依 `wiki-site-builder` 的 VitePress 流程使用：

```powershell
npm run docs:dev
npm run docs:build
```

目前曾遇到 `git status` 被 Git 的 `safe.directory` 檢查擋住，原因是 repo owner 與執行使用者 SID 不同。不要擅自修改使用者的全域 git 設定；若需要 git 狀態或提交，先告知使用者需要設定：

```powershell
git config --global --add safe.directory 'D:/Projects/Forza Horizon'
```
