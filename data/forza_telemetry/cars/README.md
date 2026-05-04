# 車輛資料庫

每台常開的車一份 `{ordinal}.yml`，記錄車名、用途、目前調校。
遙測 recorder 在 session 結束時會自動讀取此處資料，凍結進該場 session 的 `meta.json` → `car.db`。

## 為什麼資料放這裡而非 `_sources/` 或 `wiki/`？

- 此資料是**個人車庫**，不是攻略內容；不適合進 Docs/wiki。
- 與 telemetry sessions 為兄弟目錄，loader 用 `output_root.parent / "cars"` 解析路徑，直觀。
- `data/forza_telemetry/` 整體被 `.gitignore` 排除（sessions 體積大），但 `cars/` 透過 `!data/forza_telemetry/cars/` 例外規則納入版控——**git log 即調校演進史**。

## 怎麼新增一台車

1. 從 session 資料夾名稱或 `meta.json` 的 `car.ordinal` 找到 ordinal（例：`car1564_PI700` → ordinal=1564）。
2. 複製 `_template.yml` 為 `1564.yml`，填好元資料與當前 tune。
3. commit。下一場該車的 session，`meta.json` 與 `summary.md` 就會顯示車名。

## 怎麼更新 tune

- 直接改檔 → commit。**不要在檔內維護 history 陣列**（會腐爛）。
- 想看演進史：`git log -p data/forza_telemetry/cars/1564.yml`
- 想看「上週那場跑了什麼 tune」：開該 session 的 `meta.json` 看 `car.db.tune`（自動凍結的快照）。

## 單位

| 欄位 | 單位 |
|------|------|
| 胎壓 | psi |
| 彈簧 | kgf/mm |
| 車高 | cm |
| 外傾/前束/後傾 | 度 |
| 空力 | 遊戲內顯示值 |
| 剎車/差速器 | 百分比（不寫 % 符號） |

遊戲內請統一這些單位，否則檔案數值與遊戲對不起來。

## 缺檔的行為

`{ordinal}.yml` 不存在時，recorder 不會報錯，meta.json 就只有 UDP 抓得到的基本欄位（ordinal/class/PI/drivetrain/cylinders），summary.md 顯示 ordinal 數字。寫一個檔就會接上來。
