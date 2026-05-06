# 車輛資料庫

每台常開的車一份 `{ordinal}.yml`，記錄車名、用途、目前調校。
遙測 recorder 在 session 結束時會自動讀取此處資料，凍結進該場 session 的 `meta.json` → `car.db`。

## 為什麼資料放這裡而非 `_sources/` 或 `wiki/`？

- 此資料是**個人車庫**，不是攻略內容；不適合進 Docs/wiki。
- 與 telemetry sessions 為兄弟目錄，loader 用 `output_root.parent / "cars"` 解析路徑，直觀。
- `data/forza_telemetry/` 整體被 `.gitignore` 排除（sessions 體積大），但 `cars/` 透過 `!data/forza_telemetry/cars/` 例外規則納入版控——**git log 即調校演進史**。

## 怎麼新增一台車

1. 從 session 資料夾名稱或 `meta.json` 的 `car.ordinal` 找到 ordinal（例：`car1564_PI700` → ordinal=1564）。
2. 複製 `_template.yml` 為 `1564.yml`，填好元資料、specs（從遊戲「車輛資料」頁抄六個數字）、當前 tune。
3. commit。下一場該車的 session，`meta.json` 與 `summary.md` 就會顯示車名，race-analyst 也會在 analysis 開頭印「車輛規格基準」段落。

## 怎麼更新 tune

- 直接改檔 → commit。**不要在檔內維護 history 陣列**（會腐爛）。
- 想看演進史：`git log -p data/forza_telemetry/cars/1564.yml`
- 想看「上週那場跑了什麼 tune」：開該 session 的 `meta.json` 看 `car.db.tune`（自動凍結的快照）。

## 單位

| 區塊 | 欄位 | 單位 |
|------|------|------|
| tune | 胎壓 | psi |
| tune | 彈簧 | kgf/mm |
| tune | 車高 | cm |
| tune | 外傾/前束/後傾 | 度 |
| tune | 空力 | 遊戲內顯示值 |
| tune | 剎車/差速器 | 百分比（不寫 % 符號） |
| **specs** | 馬力 | **hp**（遊戲設定走 imperial） |
| **specs** | 車重 | kg |
| **specs** | 極速 | km/h |
| **specs** | 0-100 | 秒 |
| **specs** | 側向 G | G（無單位） |

遊戲內請統一這些單位，否則檔案數值與遊戲對不起來。

**為什麼用 imperial（hp + psi）而非 metric（kW + bar）**：
- 胎壓在遊戲 metric 模式會變 bar，要每次 `× 14.5` 心算回 psi 太麻煩——這是 tune 時天天動的數值，便利性優先
- wiki 所有現有調校內容都用 psi、sim 社群通用單位
- hp 也是 sim 社群口語常用（「0.4 hp/kg 推重比」）

**扭力故意省欄位**：推重比 hp/kg 已涵蓋動力強弱訊號；FH5 imperial 顯示扭力是 kg·m，不是分析常用單位。

## 為什麼有 `tune_ranges` 區塊（選填）

FH5 的滑桿端點**因車而異**，差距極大：
- Ford Focus RS 2017：彈簧上限 265 kgf/mm
- 另一台車（待補）：上限 165 kgf/mm

所以「彈簧 200 kgf/mm 算硬還是軟」根本沒有絕對答案——一台車的「硬」是另一台車的「中段」。
若 race-analyst 拿到 `tune_ranges`，會用 `(current - min) / (max - min)` 算百分位、輸出「目前彈簧在範圍 38%（偏軟那端）」這類精確診斷，而不是模糊地說「降 1-2 級」。

**只填因車而異那幾項即可**：彈簧 / 車高 / 空力。其他（damping、ARB、差速器、剎車、外傾）多半通用範圍，race-analyst 用 SKILL.md 寫死的通用值兜底。

**不填會怎樣**：race-analyst 退回「往軟方向調 1-2 級」這種小步幅度建議，仍然能跑，只是粒度粗一點。所以這個欄位**不急、踩到坑再加**就好。

## 缺檔的行為

`{ordinal}.yml` 不存在時，recorder 不會報錯，meta.json 就只有 UDP 抓得到的基本欄位（ordinal/class/PI/drivetrain/cylinders），summary.md 顯示 ordinal 數字。寫一個檔就會接上來。
