---
name: wiki-integrator
description: Forza Horizon 攻略精煉整合助手。將 Docs/_sources/ 中的原始整理版拆片段、分類、比對既有 wiki/ 內容，產出「新增／合併／修訂／略過」計劃供使用者確認後套用，持續去蕪存菁。當使用者說「整合這份攻略進 wiki」「精煉／去蕪存菁」「更新攻略庫」「處理 _sources 裡還沒整合的來源」時觸發。
user-invokable: true
argument-hint: "<_sources 檔名或完整路徑，留白=掃描所有未整合來源>"
---

# wiki-integrator（攻略精煉整合助手）

## 核心職責

讀取 `Docs/_sources/*.md`（或指定檔），拆成知識片段，逐片段判定應歸屬 `Docs/wiki/{category}/` 哪個分類與哪份既有檔，產生整合計劃供使用者確認，再套用變更。

**不做的事**：
- 不直接寫網頁（那是 `wiki-site-builder` 的工作）
- 不從零撰寫主題長文（那是 `wiki-doc-writer` 的工作）
- 不改動 `_sources/` 的原始檔

---

## 基本術語

| 術語 | 說明 |
|------|------|
| **來源**（source） | `_sources/*_整理版.md`，由 `bilibili-to-doc` 或 `knowledge-curator` 產出 |
| **片段**（segment） | 來源內以 H2/H3 為界切出的可獨立處理的知識單元 |
| **分類**（category） | `_category.yml` 定義的 6 類（tuning / upgrades / driving / cars / settings / events） |
| **wiki 檔** | `Docs/wiki/{category}/{slug}.md`，細粒度主題（例：`tuning/差速器.md`） |
| **動作**（action） | 片段對應的處置：`NEW` / `MERGE` / `REVISE` / `DUP` |

---

## 流程

### Phase 0：選定來源

```
若使用者給了檔名 → 直接用
若使用者給了完整路徑 → 直接用
若留白 → 掃 Docs/_sources/ 找出「尚未被任何 wiki/**.md frontmatter.sources 引用」的檔案
       → 列出清單請使用者選一個（一次只處理一份來源，避免爆炸）
```

### Phase 1：讀取與片段化

1. Read 來源全檔。
2. 以 H2 (`##`) 為主切片；若 H2 段落過長（> 80 行）再以 H3 切第二層。
3. 為每個片段擷取：
   - **標題**（H2/H3 原文）
   - **關鍵詞**（人工判讀：涉及的配件、數值、車型、概念）
   - **是否含數值**（胎壓、齒比、阻尼百分比等 → 標記為「高價值片段」）
   - **原文行區間**（用於日後回查）

### Phase 2：分類判定

對每個片段，依 `_category.yml` 的 `keywords` 關鍵字比對 + 內容語意判斷，落到某分類。

**特殊情況**：
- 跨分類片段（例：「後驅甩尾車的差速器調法」橫跨 tuning + driving）→ **主分類取較具體的**（此例為 tuning），另一分類用「相關連結」在文末帶到。
- 無法歸類 → 標記 `UNCATEGORIZED`，在計劃中單列，請使用者決定。

### Phase 3：比對既有 wiki 內容

對每個片段，在目標分類 `Docs/wiki/{category}/` 下：

1. Glob 列出該分類所有 .md。
2. 讀取每檔的 frontmatter（尤其 `title`、`tags`、`related_cars`）與 H2/H3 章節標題。
3. 用下列訊號判定動作：

| 訊號 | 動作 | 說明 |
|------|------|------|
| 找不到任何主題相近的檔 | `NEW` | 建議新建 `wiki/{category}/{slug}.md` |
| 既有檔的某章節與片段主題重疊 ≥ 70% | `MERGE` | 既有檔已提過，把新來源的**增量資訊**補進去（數值、範例、車型） |
| 既有檔的數值／敘述與新片段**不同** | `REVISE` | 兩者衝突，需使用者選擇或併列（見 Phase 5） |
| 既有檔已完整覆蓋此片段，無新資訊 | `DUP` | 略過，但把該 source 加到既有檔的 `sources:` 列表（用於追溯） |

### Phase 4：產出整合計劃

輸出一份 Markdown 計劃文件給使用者看，**不直接動檔**。格式：

```markdown
# 整合計劃：{來源檔名}

**共 N 個片段** · NEW {x} · MERGE {y} · REVISE {z} · DUP {w} · UNCATEGORIZED {u}

---

## 片段 1：{H2 標題} → **NEW**
- 分類：tuning
- 目標：`wiki/tuning/差速器.md`（新建）
- 關鍵詞：差速器, 加速鎖止, 減速鎖止
- 原文行：L245-L312
- 建議 frontmatter：
  ```yaml
  tags: [差速器, 進階]
  pi_class: [A, S1]
  ```

## 片段 2：{H2 標題} → **MERGE**
- 分類：tuning
- 目標：`wiki/tuning/阻尼.md` 的「## 反彈阻尼」章節
- 增量：新來源提到 Series 22 更新後的新上限 ——
  > 原文節錄：反彈阻尼上限已改為 20.0，舊攻略的 15.0 為過時資訊。
- 風險：會動到既有內容，請確認

## 片段 3：{H2 標題} → **REVISE**（衝突！）
- 目標：`wiki/tuning/胎壓.md`
- 衝突點：既有檔說公路胎「前 30 / 後 28」，新來源說「前 28 / 後 26」
- 建議處置：
  - [ ] 選項 A：改用新數值（覆寫）
  - [ ] 選項 B：併列兩種說法 + 各自來源
  - [ ] 選項 C：略過（既有為準）

## 片段 4：... → **DUP**
- 略過，僅在 `wiki/upgrades/PI性價比.md` 的 sources 加上本來源引用

---

## 請你裁示
全部照建議 / 逐項確認 / 調整分類 / 暫停
```

### Phase 5：套用變更

**只有使用者明確同意後才動手**。套用規則：

#### `NEW` 片段
- 建立 `wiki/{category}/{slug}.md`，檔名用繁中（避免 URL 編碼醜，主要 slug 就是檔名扣掉副檔名）
- frontmatter 必填欄位（見下「Frontmatter 規格」）
- 正文改寫：**保留所有數值**，但調整行文、小節結構使與分類整體風格一致
- 文末加「## 來源」引用區塊

#### `MERGE` 片段
- Read 目標檔
- 定位到對應章節，Edit 插入增量內容
- 於插入處加行內引用 `[^src{N}]`（腳註對應到來源）
- 更新 frontmatter `sources:` 陣列（若尚未含本來源則 append）
- 更新 `last_updated` 為今天（YYYY-MM-DD）
- 於 frontmatter `revisions:` append 一行 `{ date: YYYY-MM-DD, note: 從 {來源} 補入 {章節名} 資訊 }`
- 於檔頂引用區塊新增 `> 修訂 {日期}：{一句話說明}`（對應 CLAUDE.md 的可追溯原則）

#### `REVISE` 片段（衝突）
- **預設不自動採用任一方**，依使用者選項處理：
  - 覆寫 → 保留被覆寫的舊值作為註腳 `<!-- 舊值（{舊來源}）：XXX -->`
  - 併列 → 該節改為表格：
    ```markdown
    | 來源 | 數值 | 備註 |
    |------|------|------|
    | 硬核調校指南 | 前 30 / 後 28 | 原作針對 A 級公路調校 |
    | QuickTune 指南 | 前 28 / 後 26 | 原作針對 S1 甩尾 |
    ```
  - 略過 → 不動內容，只在既有檔 sources append 本來源，並在 `revisions` 記錄「已評估但未採納，原因：...」

#### `DUP` 片段
- 僅更新既有檔 frontmatter `sources:`（append 本來源）

#### `UNCATEGORIZED` 片段
- 不動，計劃中列出請使用者下次對話處理

### Phase 6：收尾

1. 更新 `Docs/wiki/{category}/index.md`（若存在）的內容清單 — 新增的檔要列進去
2. 若 `Docs/wiki/*.md` 總數達 5 篇以上而 `Docs/INDEX.md` 不存在 → 主動建立
3. 已存在 `Docs/INDEX.md` → 追加新檔到對應分類下
4. 告知使用者結果：新建 N 檔、修訂 M 檔、衝突待決 K 項

---

## Frontmatter 規格

每份 `wiki/**/*.md` **必須**包含的 frontmatter：

```yaml
---
title: 差速器調校
category: tuning
tags: [差速器, 進階, 後驅]
related_cars: []              # 車型 ID 或通用類型；為空即表示通用
pi_class: [A, S1]             # 適用 PI 等級；空陣列表示通用
game: FH5                     # FH4 / FH5 / FH6
version: Series 22            # 對應版本；不確定填「未標註」
status: stable                # draft / stable / outdated
sources:                      # 相對於專案根的路徑
  - Docs/_sources/地平線5-硬核調校指南_整理版.md
last_updated: 2026-04-21      # 本檔最後實質修改日期
revisions:                    # 修訂歷程，最新在下
  - { date: 2026-04-21, note: 初版 }
---
```

**禁止**：
- 虛構 `sources`（沒看過的來源不能列）
- `last_updated` 亂填
- `version` 猜（真的不確定就填「未標註」）

---

## 檔名（slug）規則

- 粒度：**細**，一個子主題一份檔
- 使用**繁體中文**檔名，不轉拼音（VitePress/GitHub Pages 都支援 UTF-8 URL）
- 避免標點（`，`、`：`、`／`）
- 範例：
  - `wiki/tuning/差速器.md` ✅
  - `wiki/tuning/差速器調校.md` ✅
  - `wiki/tuning/差速器：進階.md` ❌
  - `wiki/cars/肌肉車.md` ✅（車種類型）
  - `wiki/cars/Toyota_Supra_MKIV.md` ✅（單一車型）

---

## 不可違反

1. **數值絕不擅改**：來源說胎壓 30 就寫 30，覺得可能錯也不改，標 `<!-- 待查 -->`
2. **`_sources/` 絕不動**：永久原始檔
3. **衝突不合併**：REVISE 必須經使用者裁示
4. **每次只處理一份來源**：避免計劃過長、上下文爆掉
5. **套用前先出計劃**：禁止跳過 Phase 4 直接改檔
6. **繁中輸出**：正文、frontmatter 的 note 全繁體

---

## 失敗模式與應對

| 情境 | 應對 |
|------|------|
| 來源太長（> 2000 行）讀不完 | 分段讀；片段化先做 H2 級，先給使用者一份「大綱級計劃」再逐段細化 |
| 某片段橫跨多個分類難以判定 | 在計劃中標 `UNCATEGORIZED` 並列出候選分類，讓使用者決定 |
| 新片段數值與既有檔**高度相似但有小差**（例：28 vs 28.5） | 標為 `REVISE`，不自動視為 DUP |
| 既有檔 frontmatter 缺失或格式異常 | 先修復 frontmatter，再整合；修復動作計入 revisions |
| 來源是非調校類（例：純遊戲設定） | 一樣分類到 settings/，只是 tuning/upgrades 類的片段數會是 0 |
| 來源是**系統性參考手冊**（整部書、矩陣式查表、多層偏移）而非教學 | 不要強行拆進既有教學檔，改為**新建一組並列的「參考系列」**，既有細項檔只加「延伸閱讀」指向。範例：QuickTune 完整調校指南 |
| **第 N 家（N ≥ 4）來源**的片段與既有併列**數值有小差** | **不要預設「輕量標記」**（只加 frontmatter source）— 會失真。三種情況：<br>1. 新維度（按車重／按控制器／按階級分）→ 務必 MERGE 進既有檔<br>2. 第 N 列可加入既有併列表 → REVISE 擴列<br>3. 已由獨立檔（如 PI 性價比思路、硬核調校範本）承接 → 才可輕量標記 |
| 多家來源的併列表變得**太寬**（> 4 欄） | 改為「既有表 + 下方分段細分表」或拆到獨立檔，不要硬塞到同一表格 |
| 既有檔已有多家 revisions 紀錄，**新增 revision 的日期與舊的衝突** | 新 revision 用當天日期，既有 revisions 不動；revisions 是 append-only 歷史紀錄 |

---

## Edit 工具字串匹配陷阱（實戰踩雷紀錄）

對既有檔做 Edit 時，`old_string` 必須**逐字元**匹配，以下幾類差異會讓 Edit 失敗：

| 差異類型 | 常見情境 | 對策 |
|---------|---------|------|
| **全形 vs 半形標點** | `（6/7/8+ 檔）`（全形括號）vs `(6/7/8+ 檔)`（半形） | 不要憑印象打字；**Edit 前先 Read** 取得精確原文 |
| **粗體 `**` 位置** | `**拉力車 / 越野車**：...` vs `拉力車 / 越野車：**...**` | 同上，先 Read |
| **空格** | 全形空格 `　` vs 半形空格 ` ` vs 無空格 | 同上 |
| **破折號** | `—`（em dash）vs `--` vs `−`（minus） | 同上 |
| **檔案狀態不一致** | 對同一檔連做多次 Edit 後記錯當前內容 | 若 3 次內 Edit 都失敗，立刻 **Read 當前檔案**再重試 |

**經驗法則**：對既有檔做 ≥ 2 個 Edit 時，先 Read 一次取得基準，再連發 Edit。對全新寫入的檔案可跳過 Read（Write 回傳訊息會說「file state is current」）。

---

## 與其他 skill 的關係

```
bilibili-to-doc ──┐
                  ├─→ _sources/*_整理版.md ──→ wiki-integrator ──→ wiki/**/*.md
knowledge-curator ┘                              ↑  ↓
                                     wiki-doc-writer（跨來源綜合撰寫）
                                                 ↓
                                        wiki-site-builder（發佈網站）
```

- **上游**：`bilibili-to-doc`、`knowledge-curator` 產生 `_sources/*.md` 後，可提示使用者 `/wiki-integrator` 接手
- **並行**：`wiki-doc-writer` 處理需要從零撰寫的跨來源主題長文
- **下游**：`wiki-site-builder` 讀 `wiki/` 發佈到 GitHub Pages
