# FH6 遷移計畫

> 狀態：Phase 1 已完成（2026-05-14, commit `d5ab65f`）；Phase 2/3 等 FH6 packet/來源
> 建立日期：2026-05-14
> 目的：讓本專案（wiki 攻略庫 + 遙測工具）在 FH6 上市時能順利接軌，並保留跨代通用的知識資產。

---

## 背景

- FH6 即將上市，現有內容大部分以 FH5 為基準。
- 目前 wiki frontmatter 雖有 `game: FH5` 欄位但**未實際利用**（多數標 `未標註` 或一致 FH5），網站端也未呈現。
- 遙測工具 `scripts/forza_telemetry/` 寫死 FH5 packet 結構（323 bytes，Sled + Horizon Dash extension）。
- 需要在「FH5 還在用、FH6 開始補資料」的過渡期讓兩代知識共存且能明確區分。

---

## 核心問題

1. **哪些知識大致通用、哪些明確綁版本？** → 需要在 frontmatter 與網站 UI 上粗略區分，但不做逐篇驗證制度。
2. **FH6 的 UDP packet 結構未知** → 工具需要可在 launch 後快速適配。
3. **過渡期內 race-analyst 不能把 FH5 數值當成 FH6 真理** → 需要在 session 層標記遊戲版本，並在引用 FH5 來源時明確標成「起點參考」。

---

## 遷移原則

- **不做逐篇 FH6 驗證**：維護成本太高，不符合本專案的使用方式。
- **保留來源版本，不追求證書式適用範圍**：文章來自 FH5 來源就先標 FH5；FH6 新來源就標 FH6。
- **粗分即可**：只把明顯跨代的駕駛／物理概念標成通用，模糊地帶不要硬判。
- **發現差異再修**：FH6 實測或新來源證明數值不同時，再補段落、表格或警告。
- **FH5 內容不急著清算**：過渡期讓它保留價值，FH6 分析時加註限制即可。

---

## 方案概要

### A. Wiki 資料模型：以 `applies_to` 取代 `game`

frontmatter 新增 `applies_to` 陣列，採低維護粗分類：

| 值 | 意義 | 範例 |
|---|---|---|
| `general` | 純物理/駕駛原理，通常跨遊戲通用 | 走線、weight transfer、understeer/oversteer 概念、煞車原理 |
| `horizon` | Forza Horizon 系列大致通用的遊戲機制；不代表 FH6 已正式驗證 | PI 系統、A/S1/S2 class、Tune UI 結構、UDP Data Out 概念 |
| `fh5` / `fh6` | 某代專屬數值、車庫車單、Series 活動、UI 文案 | QuickTune 基準值、特定車型調校範本、季節活動 |

`applies_to` 為陣列，可組合。`[fh5, fh6]` 表示兩代都有來源或已在實際使用中確認可沿用；**不代表做過逐篇審核**。

**廢止：** `game` 欄位（保留向後相容一段時間，最終由 `applies_to` 取代）。

**部分綁版本的文章**處理方式：
- 主文標 `[general]` 或 `[horizon]`
- 內部 FH5 限定段落用 VitePress container 包：
  ```markdown
  ::: warning FH5 來源數值
  以下基準值來自 FH5。FH6 初期可作為起點參考，但若實測不同，以 FH6 新資料為準。
  :::
  ```
- 不另開檔（保持線性閱讀流暢，避免被迫 fork 整篇）

### B. 網站呈現：標籤徽章 + 全站篩選

VitePress 改動（由 `wiki-site-builder` 接手）：

- 每篇頂部依 `applies_to` 自動生成色帶徽章：
  - `general` 綠 ／ `horizon` 藍 ／ `fh5` 橘 ／ `fh6` 紫
- 頁首或頁尾顯示「來源／適用標記」，避免讀者誤以為所有舊文都已經 FH6 驗證。
- 首頁分區塊：通用概念 / Forza Horizon 共通 / FH5 來源 / FH6 來源。
- 篩選 UI 先不急著做全功能。FH6 內容累積後，再考慮「只看 FH6 來源」「只看通用」等切換。

**不做**：另開 `wiki/fh5/` `wiki/fh6/` 子目錄。理由是內容大量交集，分目錄會逼出複製貼上的反 DRY 操作。

### C. 工具：packet parser 抽象化

[scripts/forza_telemetry/packet.py](scripts/forza_telemetry/packet.py) 重構為兩層：

```
packet/
├── sled.py            # FM7-compatible 232 bytes 核心（跨遊戲共用）
├── horizon_fh5.py     # FH5 Dash extension (244..322)
├── horizon_fh6.py     # FH6 launch 後新增
└── __init__.py        # 統一介面 TelemetrySample
```

關鍵原則：

1. **raw.csv schema 是穩定介面**：summarize.py / race-analyst 只讀 CSV，不碰 packet 結構。FH6 多/少欄位就在 CSV 加/留空，下游不動。
2. **FH6 launch 流程**：抓首個 packet → 印 size → 比對 FH5 layout → 寫 `horizon_fh6.py` → recorder 依據 `--game fh5|fh6|auto` 和封包 sanity check 路由。
3. **`meta.json` 加 `game: fh5|fh6` 欄位**：race-analyst 讀 meta 時決定引用策略。
4. **舊資料向後相容**：既有 session 沒有 `game` 時，預設視為 `fh5`，但 summary / analysis 可註明「舊資料推定」。

recorder 的賽事偵測狀態機（IsRaceOn / LapNumber / DistanceTraveled 為基礎）大機率不用動。

### D. Skills 與規則同步

| 檔案 | 改動 |
|---|---|
| `CLAUDE.md` | 新增「跨代版本標記慣例」一節（主規則） |
| `AGENTS.md` | 更新專案定位：FH5 → Forza Horizon 系列；加入低維護版本標記原則 |
| `.claude/skills/race-analyst/SKILL.md` | 分析前讀 `meta.json.game`；FH6 session 可引用 `general` / `horizon` / `fh6`，FH5 數值只能當起點參考。Claude 為主導者 |
| `.codex/skills/race-analyst/SKILL.md` | 與 Claude 版**雙向同步**——兩邊都會獨立進化（如 Claude 已有 specs/`tune_ranges` 百分位；Codex 已有「外部事實上網查證」段），同步時取兩邊的並集，由 Claude 主導 |
| `.claude/skills/wiki-integrator/SKILL.md` | NEW/MERGE 階段必須設 `applies_to`；綁版本數值用 container |
| `.claude/skills/knowledge-curator/SKILL.md` | `_sources/` 收錄時頂部記錄「原作對應遊戲版本」 |
| `.claude/skills/wiki-site-builder/SKILL.md` | VitePress 徽章 component、全站篩選邏輯 |
| `.claude/skills/wiki-doc-writer/SKILL.md` | 新文預設 `applies_to: [fh5]` 或依主題判斷 |

---

## 執行順序（建議）

### Phase 1（現在～FH6 上市前，無時間壓力）✅ 完成於 2026-05-14（commit `d5ab65f`）

1. ✅ **frontmatter schema 升級**
   - `wiki-integrator` SKILL.md 已加 `applies_to` 規格與 container 用法
   - `scripts/migrate_applies_to.py` 一次性轉換完成（48 檔，0 殘留 `game:` / `version:`）
2. ✅ **粗分類 pass**（採保守策略：分布 42 fh5 / 4 horizon / 2 general）
   - `[general]`：`cars/汽車基礎術語.md`、`cars/車型代號.md`
   - `[horizon]`：`driving/賽車線與彎道基礎.md`、`driving/煞車技巧.md`、`driving/漂移基礎.md`、`driving/進階練習小技巧.md`
   - 其餘維持 `[fh5]`（含 FH5 賽道實例或具體數值的就不硬升級）
3. ✅ **VitePress 徽章 UI**
   - `Docs/wiki/.vitepress/theme/components/AppliesToBadges.vue` + `index.ts` + `style.css`
   - 已驗證 `npm run docs:build` 通過、徽章正確渲染（47/47 內容頁；首頁 layout=home 排除）
   - 篩選 UI 依原則延後（等 FH6 內容累積）
4. ✅ **packet.py 重構**（純結構，不改行為）
   - 拆出 `scripts/forza_telemetry/sled.py`（FM7-compatible 232 bytes 共用核心）
   - 拆出 `scripts/forza_telemetry/horizon_fh5.py`（FH5 Dash extension）
   - `packet.py` 改為輕薄 facade，公開 API（`Packet` / `PACKET_SIZE` / `parse` / `PacketLengthError`）完全不變
   - smoke test 通過：PACKET_SIZE=323、85 fields、recorder / summarize CLI 正常

### Phase 2（FH6 試玩版／beta／launch 當天）

5. 抓 FH6 packet、寫 `horizon_fh6.py`
6. recorder 加 `--game fh5|fh6|auto` 與封包路由邏輯
7. `meta.json` 補 `game` 欄位
8. race-analyst 依 `meta.game` 調整引用語氣：FH6 可用 `general` / `horizon` / `fh6`；FH5 數值只作起點參考

### Phase 3（FH6 launch 後）

9. 第一批 FH6 來源進 `_sources/`，整合到 wiki 時標 `applies_to: [fh6]`
10. 遇到 FH5/FH6 明確差異時，才回頭修相關文章：併列表格、版本警告、或拆成 FH5/FH6 小節
11. 累積一定 FH6 內容後考慮：是否在網站首頁做版本切換 UI（仍是同一份內容，只是預設過濾）

---

## 暫未決定 / 待討論

- [ ] `applies_to` 是否再細分 series 版本（如 `fh5-s40+`）？目前傾向不做，太細會變維護負擔。
- [ ] 工具層是否要支援 FH4（社群仍活躍）？目前傾向**不主動支援**，但 sled.py 抽出後其實已具備能力。
- [ ] 首頁是否需要改版成更明顯的系列入口？站名已可維持「Forza Horizon 攻略庫」。
- [ ] 是否要在 `_sources/` frontmatter 也加 `applies_to`？目前傾向只標「原作對應版本」（單一值），整合到 wiki 時才轉成 `applies_to` 陣列。

---

## 風險與注意

- **粗分類可能不完美**：這是有意取捨。比起做完整驗證，更重要的是保留來源版本，避免把 FH5 數值誤講成 FH6 定論。
- **FH6 packet 若大改**：sled 核心若也變動，抽象設計可能要再調。屆時看實際 packet 再說，不過度設計。
- **跨代衝突數值**：若同一觀念在 FH5/FH6 數值不同，依現有「衝突不合併」原則用表格併列，**不要**自己挑一個。
