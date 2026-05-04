# Forza Horizon 5 Telemetry Recorder

把 FH5 即時遊戲遙測（UDP Data Out）錄製成結構化 CSV + JSON，供後續分析調校。
**核心目標**：產生乾淨、可追溯、可給 LLM 分析的賽事資料。

---

## 目錄

- [為什麼存在](#為什麼存在)
- [架構總覽](#架構總覽)
- [資料流](#資料流)
- [狀態機](#狀態機)
- [封包格式](#封包格式)
- [賽事 vs 自由探索偵測](#賽事-vs-自由探索偵測)
- [Rewind 偵測](#rewind-偵測)
- [輸出格式](#輸出格式)
- [車輛資料庫](#車輛資料庫)
- [使用方式](#使用方式)
- [CLI 參數](#cli-參數)
- [FH5 行為怪癖（實證發現）](#fh5-行為怪癖實證發現)
- [Phase 路線圖](#phase-路線圖)
- [測試與除錯](#測試與除錯)
- [外部參考](#外部參考)
- [維護紀錄](#維護紀錄)

---

## 為什麼存在

FH5 內建 **Data Out** 功能可以透過 UDP 廣播車輛即時狀態（60 Hz）。原本是給儀表板、震動座椅、直播 overlay 用的，但這些資料對**調校分析**也極有價值——輪溫分布、懸吊行程、滑移角、煞車壓力 trace 等等，憑感覺猜不準的東西全在裡面。

**問題**：原始 UDP 封包是高頻、無結構的洪流，直接給 LLM 看完全不能用。

**這個工具的職責**：
1. 監聽 UDP，自動辨識**何時**在賽事中（不錄自由探索）
2. 自動分段：一場賽事 = 一個資料夾
3. 標記倒轉資料（`is_rewind` 欄位）並保留全部 packet；分析階段（`summarize.py`）用 CRT-bucket dedupe 自動排除「rewind 前的失敗嘗試」，只保留玩家最終定案的線
4. 輸出 LLM 友好的 metadata，省去手動標註

---

## 架構總覽

```
d:\Projects\Forza Horizon\
├── scripts\forza_telemetry\
│   ├── __init__.py
│   ├── __main__.py       錄製 CLI 入口（argparse、banner、signal handling）
│   ├── packet.py         Car Dash 封包格式定義 + struct 解析
│   ├── session.py        Session 資料夾、CSV writer、meta.json、rewind 偵測
│   ├── recorder.py       UDP listener + 賽事偵測狀態機
│   ├── summarize.py      raw.csv → summary.md 分析報告
│   ├── cars.py           車輛資料庫 loader（讀 cars/{ordinal}.yml）
│   ├── gui.py            Tkinter GUI（狀態 / 賽事資料 / 車輛資料三分頁）
│   └── README.md         本文件
├── data\forza_telemetry\
│   ├── sessions\                錄製的 session 資料夾（gitignored）
│   │   └── {timestamp}_car{ord}_PI{pi}\
│   │       ├── raw.csv          原始 60Hz 遙測（87 欄）
│   │       ├── meta.json        車輛、圈數、rewinds 統計（含 car.db 快照）
│   │       ├── summary.md       summarize.py 產出的人類可讀分析
│   │       └── analysis.md      race-analyst skill 產出的調校/駕駛建議
│   └── cars\                    車輛資料庫（**進版控**，git log 即調校史）
│       ├── _template.yml        範本（複製為 {ordinal}.yml）
│       ├── README.md            欄位定義 + 維護指引
│       └── {ordinal}.yml        每台車一份，個人填寫
├── .claude\skills\race-analyst\ 讀 summary.md + wiki/ → analysis.md 的 Claude skill
├── start-telemetry.bat          雙擊啟動 console recorder
└── start-telemetry-gui.bat      雙擊啟動 GUI（單視窗 + 自動啟動 recorder）
```

**依賴**：純 stdlib（`socket`、`struct`、`csv`、`json`、`pathlib`、`dataclasses`、`argparse`、`datetime`、`collections.deque`、`enum`、`logging`、`signal`）。**Python 3.10+**（用了 `X | None` 型別語法）。

---

## 資料流

```
FH5
  │  UDP 60 Hz, 324 bytes/封包
  ▼
[ recorder.py: UDP listener ]
  │  bytes
  ▼
[ packet.py: parse → namedtuple ]
  │  Packet
  ▼
[ recorder.py: state machine ]
  │  if RECORDING → forward packet
  ▼
[ session.py: classify rewind + write row ]
  │
  ▼
data/forza_telemetry/sessions/{folder}/raw.csv
                                       /meta.json (寫於 finalize)
```

---

## 狀態機

定義在 [recorder.py](recorder.py)。

```
                        IsRaceOn 0→1
              ┌──────────────────────────┐
              │                          ▼
        ┌─────────┐                 ┌──────────┐
        │  IDLE   │                 │ BUFFERING│
        │         │                 │ (記憶體) │
        └─────────┘                 └──────────┘
              ▲                       │      │
              │                       │      │
   idle timeout                       │      │ 30 秒內未偵測到賽事旗標
   (預設 300 秒，兜底)                │      │ 或 IsRaceOn 1→0
   或 is_continuation()=False         │      ▼
              │                       │  (丟棄 buffer 回 IDLE)
        ┌─────────┐                   │
        │RECORDING│ ◀─────────────────┘
        │ (寫CSV)│   偵測到賽事旗標
        └─────────┘   (LapNumber>0 或 RacePosition>0)
            ▲│      → 把 buffer 倒進 raw.csv
            ││
       IsRaceOn 1→0 │ (暫停 / 倒轉動畫 / 賽事結束)
       → 標記 idle，繼續寫封包
            │▼
       IsRaceOn 0→1 → Session.is_continuation(p)?
            │  ├─ True  : 同 session 繼續（暫停/倒轉恢復）
            │  └─ False : finalize 舊 session，啟動新 RECORDING
            ▼
        (持續 RECORDING)
```

### 為什麼要 buffer-and-commit？

賽前倒數那幾秒 `IsRaceOn` 已經是 1，但賽事旗標（`LapNumber`、`RacePosition`）可能還沒亮。直接靠旗標判斷會漏掉開賽前的關鍵幾秒。

解法：先在記憶體 ring buffer 暫存（不寫檔），等旗標亮起後一次倒進 CSV，這樣**起跑線前後都完整保留**，又不會誤錄自由探索。

### 為什麼是「內容判斷」而不是「cooldown 計時」

舊版用 cooldown（IsRaceOn=0 持續 N 秒就 finalize）有兩個問題：
1. **長暫停會切 session**：使用者去廁所 5 分鐘 → session 切兩個資料夾
2. **長 rewind 會切 session**：rewind 動畫 + 重播 > 8 秒 → 切兩個資料夾

新版用 `Session.is_continuation(p)`（[session.py](session.py)）：當 `IsRaceOn` 重新變 1 時，比對封包內容判斷這是「同一場賽事繼續」還是「新賽事開始」。

| 訊號 | 暫停恢復 | 倒轉恢復 | 新賽事 / 重新挑戰 |
|------|---------|---------|-------------------|
| `CarOrdinal` | 不變 | 不變 | 通常不變 |
| `LapNumber` | 不變 | 通常不變（除非倒轉跨圈） | **歸 0**（`< max_lap_number`） |
| `CurrentRaceTime` | 從中斷時的數值繼續 | 比中斷時低（倒回去某時間點） | **歸 0** |

判斷規則（任一滿足即視為新賽事）：
- 換車（`CarOrdinal` 變了）
- 圈數倒退（`LapNumber < max_lap_number`）
- CRT 歸零但之前有賽事時間（`CRT < 1.0` 且 `max_crt >= 1.0`）

否則視為同 session 繼續（包含暫停、rewind、過場）。

### Idle Timeout 是「兜底」不是主要機制

`--idle-timeout-seconds`（預設 300 秒）只在**真的被遺棄**的情境觸發：
- 使用者完賽後跳到主選單，遊戲不再產生 IsRaceOn=1 封包
- 使用者關掉遊戲但 recorder 還在跑

賽事中暫停或倒轉**不會觸發**（因為內容判斷負責），所以暫停 30 秒、5 分鐘、30 分鐘都不會切 session。

---

## 封包格式

定義在 [packet.py](packet.py)。

### 大小

| 段 | bytes | 說明 |
|----|------|------|
| Sled | 232 | FM7 起就存在的核心物理資料（offset 0..231） |
| HorizonPlaceholder | 12 | FH 系列特有的填充（offset 232..243），純 padding |
| Dash extension | 79 | FH 特有的位置/賽事/輸入資料（offset 244..322） |
| **可解析總長** | **323** | namedtuple 涵蓋的範圍 |
| Padding | 1 | 遊戲實際送 324 bytes，最後 1 byte 是填充 |

我們的 parser 用 `len(data) >= 323` 防禦寫法，**323 與 324 兩種長度都接受**。

### 欄位類型摘要（重點）

| 欄位 | 類型 | 注意事項 |
|------|------|---------|
| `IsRaceOn` | int32 | 1 = 駕駛中（含自由探索），0 = 選單/過場 |
| `TimestampMS` | uint32 | 遊戲啟動以來的**牆上時鐘**毫秒，**倒轉時不倒退** |
| `CurrentRaceTime` | float | 賽事用秒數計時器，**自由探索也會跑** |
| `LapNumber` | uint16 | **0-indexed**（lap 0 = 第 1 圈，lap 4 = 第 5 圈）；自由探索 / 倒轉動畫 / 賽事結束都 reset 為 0 |
| `RacePosition` | uint8 | 自由探索全為 0；多人/AI 賽事 ≥ 1 |
| `BestLap` / `LastLap` / `CurrentLap` | float | 賽事內計時 |
| `Speed` | float | m/s（× 3.6 = km/h） |
| `Power` / `Torque` | float | watts / Newton·m |
| `TireTempFL/FR/RL/RR` | float | 攝氏度 |
| `NormalizedSuspensionTravel*` | float | 0.0 = 完全伸長，1.0 = 完全壓縮 |
| `TireSlipRatio*` / `TireSlipAngle*` | float | 0 = 100% 抓地，\|x\| > 1 = 失抓 |
| `Steer` / `NormalizedDrivingLine` / `NormalizedAIBrakeDifference` | **int8（signed）** | 容易被誤判為 uint8 |
| `WheelOnRumbleStrip*` | int32 | 注意是 int32 不是 float（容易被某些 parser 寫錯） |

完整 85 個欄位定義見 [`packet.py`](packet.py) 的 `_LAYOUT`。

### 與其他 parser 的偏差

我們交叉比對過 [holgerkenn/Forza-IoT-Relay](https://github.com/holgerkenn/Forza-IoT-Relay/blob/master/forza.h)、[raweceek-temeletry/forza-horizon-5-UDP](https://github.com/raweceek-temeletry/forza-horizon-5-UDP)、[austinbaccus/forza-telemetry](https://github.com/austinbaccus/forza-telemetry)。

⚠️ austinbaccus 版有兩個我們**沒採用**的問題：
1. `IsRaceOn` 讀成 float（應為 int32）
2. `CarOrdinal/CarClass/PI/...` 讀成 uint8（4 bytes 對齊但只取 1 byte → CarOrdinal 2429 會被截成 125）

我們的 layout 與 holgerkenn / raweceek / 官方 FM Data Out 規格一致。

---

## 賽事 vs 自由探索偵測

定義在 `recorder.is_competitive_event()`。

```python
def is_competitive_event(p: pkt.Packet) -> bool:
    return p.LapNumber > 0 or p.RacePosition > 0
```

### 為什麼是這兩個欄位

| 欄位 | 自由探索 | 賽事 / Rivals |
|------|---------|---------------|
| `LapNumber` | 永遠 0 | 過起跑線後 ≥ 1 |
| `RacePosition` | 永遠 0 | 多人/AI 賽事 ≥ 1 |

兩個任一 > 0 就足以判定。

### 為什麼不用 `CurrentRaceTime`

**直觀上** 它叫 "RaceTime"、應該是賽事計時器才對。
**實際上**（2026-05-03 實證）它在自由探索也會跑——是「session/driving clock」而非「race-specific clock」。
拿來當 race detection 會 100% false positive。

### 覆蓋範圍

| 事件類型 | 觸發 | 說明 |
|---------|------|------|
| PGG / Festival Playlist 一般賽 | ✅ | RacePosition > 0 |
| Rivals 計時挑戰 | ✅ | LapNumber > 0 |
| Tour / Open Championship | ✅ | 兩者皆 > 0 |
| Trial（PvE） | ✅ | RacePosition > 0 |
| Story Mission（多數） | ✅ | RacePosition > 0 |
| 自由探索 | ❌ 不錄 | 兩者皆 0（正確） |
| Speed Trap / Drift Zone / Danger Sign / Trailblazer（PR Stunts） | ⚠️ 待驗證 | 可能不觸發；對調校分析價值低（太短、無重複性），可接受不錄 |
| Eliminator | ⚠️ 待驗證 | 不確定 RacePosition 是否設置 |

實機驗證後若有遺漏的事件類型，更新此表。

---

## Rewind 偵測

定義在 `session._classify_rewind()`。

```python
REWIND_THRESHOLD_S = 0.1  # CurrentRaceTime 倒退超過 0.1 秒視為倒轉
```

### 演算法

維護兩個高水位：
- `_prev_crt`：上一筆封包的 `CurrentRaceTime`
- `_max_crt`：本 session 看到過的最大 `CurrentRaceTime`

```
非倒轉狀態：
  if crt < prev_crt - 0.1:
    # 偵測到倒退 → 進入倒轉
    記錄倒轉次數、累計倒退秒數 (max_crt - crt)
    is_rewind = 1
  else:
    更新 max_crt
    is_rewind = 0

倒轉狀態：
  if crt >= max_crt:
    # 已經重新開過倒轉前的時間點 → 退出倒轉
    is_rewind = 0
  else:
    # 還在重播倒回去的那段
    is_rewind = 1
```

### 為什麼是 `CurrentRaceTime`，不是 `TimestampMS`

| 候選 | 表現 |
|------|------|
| `TimestampMS` | ❌ 是遊戲啟動以來的**牆上時鐘**，倒轉時繼續向前。實證 4028 個轉場 0 次倒退 |
| `DistanceTraveled` | ❌ 自由探索全為 0；停車不動時也不變（無法偵測停車後倒轉） |
| `CurrentRaceTime` | ✅ 賽事中倒轉會讓它倒退（這是它**唯一**會倒退的場景） |

### 為什麼只在 `IsRaceOn=1` 的封包上比較

實證（2026-05-03 五圈 PGG 賽事 + 1 次故意倒轉）發現 FH5 倒轉行為：

```
正常賽事中             :  IsRaceOn=1, CRT=85.10, Lap=3
倒轉動畫開始（瞬間）   :  IsRaceOn=0, CRT=0,     Lap=0   ← 遊戲把整段倒轉動畫當作「無賽事」
倒轉動畫進行中（~6秒） :  IsRaceOn=0, CRT=0,     Lap=0
倒轉動畫結束（瞬間）   :  IsRaceOn=1, CRT=80.13, Lap=3   ← 跳到倒回去的時間點
動畫後繼續開           :  IsRaceOn=1, CRT 繼續遞增
```

**賽事結束的 packet 模式完全相同**（IsRaceOn 1→0、CRT 歸零、Lap 歸零），只差在 IsRaceOn 不會再回 1。

所以 rewind 偵測**忽略 `IsRaceOn=0` 封包**，只比較 IsRaceOn=1 封包之間的 CRT 變化：
- 真倒轉：當 `IsRaceOn` 重新變 1 時，CRT 比上一個 IsRaceOn=1 封包低 → 偵測到 ✓
- 賽事結束：`IsRaceOn` 永遠不再變 1 → 不會誤觸發 ✓
- 暫停選單：理論上應該也是 `IsRaceOn=0` + 不歸零 CRT 的模式，所以不影響（待實機驗證）

### 已知限制

1. **倒轉動畫期間（~5-8 秒、IsRaceOn=0）的封包資料**全為 0（CRT、Lap、Speed、tire data 全部）。這些列在 raw.csv 中保留但不能拿來分析，**用 `IsRaceOn=1` 過濾**即可排除。

2. **賽事中暫停選單的 CRT 行為**未實機驗證。理論上若也是「IsRaceOn=0、CRT=0」模式，會被 rewind 偵測自動忽略。若不是這樣（例如 CRT 凍結但 IsRaceOn 仍為 1），暫停期間封包仍會寫入 raw.csv，但不會誤判為 rewind。

3. **CurrentRaceTime 歸零回到非零**：在 IsRaceOn=1 封包之間若出現此模式，會被當成 rewind（保守判斷）。

### 分析層的 rewind 處理（`summarize.py`）

`is_rewind` 欄位是**錄製層**的標記——保留所有資料給審計用。**分析層不直接過濾 `is_rewind`**，而是用 `dedupe_attempts()`：

```
對每個 1/60 秒 CRT 桶，只保留 arrival_ts 最大的 packet（= 玩家最終定案的版本）。
```

**為什麼不簡單過濾 `is_rewind=='0'`**：那會**搞反**——`is_rewind=1` 標的是 redo 段（玩家最終選擇的線），`is_rewind=0` 包含 rewind 前的失敗嘗試。直接過濾 `is_rewind=='0'` = 保留失敗、丟棄成功。

**CRT-bucket dedupe 的好處**：
- 同一彎倒轉 N 次 → 自動只保留第 N+1 次成功的版本
- 跨彎倒轉（玩家倒回到較早段重做後續多個彎）→ 每個 CRT 桶獨立判定，沒重做的段落維持原樣
- 輸出依 CRT 排序，下游分析的「1 packet = 1/60s」假設仍成立

實測：11 rewind / ~80s 失敗的 session 排除後，許多被失敗段遮蔽的真實調校線索（整體推頭、差速器鬆、懸吊太軟）才浮現出來。

---

## 輸出格式

### 資料夾命名

```
data/forza_telemetry/sessions/{YYYY-MM-DD_HH-MM-SS}_car{CarOrdinal}_PI{PerformanceIndex}/
```

例：`2026-05-03_19-30-15_car2429_PI920/`

### `raw.csv`

每行一個封包。第一行是 header。

| 欄位 | 來源 | 說明 |
|------|------|------|
| `arrival_ts` | 本機 wall clock | `time.time()` 浮點 |
| `is_rewind` | 衍生 | 0/1，rewind 偵測結果 |
| `IsRaceOn` ... `NormalizedAIBrakeDifference` | packet | 共 85 欄，順序見 `packet.FIELD_NAMES` |

**總欄位數 = 87**（arrival_ts + is_rewind + 85 個封包欄位）。

一場 5 分鐘賽事 ≈ 18,000 行 ≈ 6-8 MB CSV。

### `meta.json`

寫於 session finalize（IsRaceOn 持續掉 cooldown 秒後）。

```json
{
  "started_at": "2026-05-03T19:30:15+08:00",
  "ended_at":   "2026-05-03T19:34:48+08:00",
  "duration_seconds": 273.0,
  "packet_count": 16380,
  "car": {
    "ordinal": 2429,
    "class": 6,
    "performance_index": 920,
    "drivetrain_type": 2,
    "num_cylinders": 6,
    "db": {
      "name": "Subaru BRZ 2013",
      "purpose": "軌跡",
      "tune": { "tires": { "pressure_front": 22.0, ... }, ... }
    }
  },
  "race": {
    "total_laps": 3,
    "best_lap_seconds": 87.234,
    "last_lap_seconds": 88.012
  },
  "rewinds": {
    "count": 2,
    "total_seconds_rewound": 5.84,
    "affected_packet_count": 350
  }
}
```

**欄位語意**：
- `car`：第一個封包的識別（賽事中換車不會重新建 session，所以以第一筆為準）
- `car.db`：finalize 時從 `data/forza_telemetry/cars/{ordinal}.yml` 凍結進來的快照（**選填**，沒設檔就沒這欄）。包含車名、用途、當時的完整 tune——之後改 tune 不會回溯改動歷史 session
- `race.total_laps`：本 session 看到的最大 `LapNumber`
- `race.best_lap_seconds`：`BestLap` 的歷史最小非零值
- `race.last_lap_seconds`：最後一筆封包的 `LastLap`
- `rewinds.affected_packet_count`：所有 `is_rewind=1` 的列數

---

## 車輛資料庫

> 設計細節與單位約定：[`data/forza_telemetry/cars/README.md`](../../data/forza_telemetry/cars/README.md)

UDP 封包只給 `CarOrdinal` 數字（例：1564），人類看不出是什麼車；若想跨場比對「同車不同 tune」也需要記錄當時的調校。
解法：在 `data/forza_telemetry/cars/{ordinal}.yml` 一車一檔，記錄車名、用途、當前 tune。

### 流程

1. 第一次跑某台車 → session 資料夾出現 `car{N}_PI{M}` → 複製 `_template.yml` 為 `{N}.yml` 填好。
2. 之後每場 session finalize 時，recorder 自動把該檔內容**凍結**進 `meta.json` 的 `car.db`（包含 tune 完整結構）。
3. summary.md 顯示 `**Subaru BRZ 2013**（軌跡）— ordinal 1564, PI 700, class A`，不再只看到數字。
4. race-analyst skill 直接從 meta.json 讀當時的 tune，給建議時知道「目前後 ARB 是 25」。

### 為什麼沒有 history 陣列

調校歷史交給 git——`git log -p data/forza_telemetry/cars/1564.yml` 即演進史。
要看「上週那場用什麼 tune」開該 session 的 `meta.json` 看 `car.db.tune`（自動凍結）。

陣列在檔內維護的版本最後總是只更新最後一筆，前面的 entry 變半真半假，反而誤導分析。git + session snapshot 兩條路都有原子保證。

### 缺檔行為

`{ordinal}.yml` 不存在不會報錯，meta.json 就只有 UDP 抓得到的基本車輛欄位，summary.md 顯示 ordinal 數字。寫一個檔就接上來，舊 session 的 meta.json 不會回溯加上（這是設計意圖：歷史不可變）。

---

## 使用方式

### GUI 模式（推薦）

雙擊 `start-telemetry-gui.bat` → 單一視窗，內含：

- **狀態分頁**：即時顯示 recorder state（IDLE / BUFFERING / **RECORDING**）、封包速率、IsRaceOn、車輛 ordinal/PI、即時車速、當前 session 累積封包數、idle 計時。
- **賽事資料分頁**：左側列出所有 sessions（依時間倒序），右側以 **markdown 渲染** 預覽選中 session 的 summary.md（headers 變色變大、`**bold**` / `` `code` `` / 表格 / 程式區塊都套樣式）。字體可調：`+` / `−` / `重置` 按鈕，或 `Ctrl+滑鼠滾輪` / `Ctrl+= / Ctrl+- / Ctrl+0`。按鈕：重整 / 開資料夾 / 重生 summary / 刪除。
- **車輛資料分頁**：列出 `cars/*.yml`，新增（從範本複製並開啟系統預設編輯器）/ 編輯（雙擊或按鈕）/ 開資料夾 / 刪除。

下方控制列恆顯：

| 按鈕 | 用途 |
|------|------|
| ▶ 啟動 / ⏹ 停止 recorder | 開關背景錄製執行緒 |
| ● 強制錄製 | 覆蓋自動偵測，下個封包進入 RECORDING（測直線、bench-mark 直接開錄不用等賽事旗標） |
| ■ 強制停止 | 立即 finalize 當前 session，回 IDLE |

GUI 與 recorder 是同一個 process，**recorder 跑在背景 thread**——關 GUI 視窗 = 停止錄製。

**配色**：預設深色（VS Code Dark+ 風格）。要淺色：

```powershell
python -m scripts.forza_telemetry.gui --auto-start --theme light
```

### Console 模式

雙擊 `start-telemetry.bat` 走純 console 流程（無 GUI、log 直接輸出）：

1. 黑色 console 顯示中文 banner + FH5 設定提示
2. 進 FH5 → HUD → Data Out：
   - Data Out: ON
   - Data Out IP: `127.0.0.1`
   - Data Out Port: `5300`
   - Data Out Packet Format: **Car Dash**（不要選 Sled）
3. 跑賽事，自動錄製
4. 停止：Ctrl+C（安全停止）或直接關閉視窗（強制停止）

兩種模式行為一致——GUI 只是把 console 模式包進視窗加上互動操作，**錄製邏輯共用同一份 Recorder**。

### 命令列啟動

```powershell
cd "d:\Projects\Forza Horizon"
python -m scripts.forza_telemetry --verbose
```

### 跨機器使用

如果 FH5 跑在另一台機器（例如 Xbox），把 `Data Out IP` 設為 recorder 所在機器的區網 IP（例如 `192.168.1.50`），recorder 端用預設 `--bind 0.0.0.0` 即可。

### 完整工作流

```
1. 雙擊 start-telemetry.bat               → 開始錄製
2. 跑賽事（暫停/倒轉/長 idle 都不會切 session）
3. 賽事結束（IsRaceOn 持續 0、進主選單等）→ recorder 自動 finalize
                                            └→ 同時自動產生 summary.md
4. 打開 Claude Code 跟它說「分析這場資料」 → race-analyst skill 產生 analysis.md
5. 照 analysis.md 的「下次測試清單」改一個變數，回到 1
```

> **不需要手動跑 summarize**——recorder 預設會在每場 finalize 時自動產生 summary.md。
> 加 `--no-auto-summarize` 旗標可關閉。

### summarize.py 手動用法

只在以下情境需要：
- 你關閉了 auto-summarize 想補生
- 改了 summarize.py 想重新跑全部 session
- 用舊版 recorder 錄製的資料沒有 summary.md

```powershell
# 最新 session
python -m scripts.forza_telemetry.summarize

# 指定 session 資料夾或名稱
python -m scripts.forza_telemetry.summarize 2026-05-03_18-14-32_car2179_PI700

# 重新生成所有 session 的 summary
python -m scripts.forza_telemetry.summarize --all
```

---

## CLI 參數

定義在 [`__main__.py`](__main__.py)。

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `--port` | `5300` | UDP 監聽埠，須與 FH5 設定一致 |
| `--bind` | `0.0.0.0` | 綁定位址（所有介面） |
| `--output-dir` | `data/forza_telemetry/sessions` | session 資料夾根目錄 |
| `--buffer-seconds` | `30.0` | BUFFERING 等待賽事旗標的最長時間 |
| `--idle-timeout-seconds` | `300.0` | 兜底：IsRaceOn 持續 0 這麼久才強制 finalize（暫停/倒轉用內容判斷處理，不靠這個） |
| `--no-auto-summarize` | (off, 預設啟用) | 關閉每場 finalize 後自動產生 summary.md |
| `--verbose` / `-v` | off | 詳細 log（狀態切換、第一筆封包資訊） |

---

## FH5 行為怪癖（實證發現）

⚠️ **這些是大多數線上 telemetry 教學沒提到的**。多數教學專注於即時儀表板，不在乎 race vs free roam 的區分，所以這些怪癖沒人寫。

### 1. `CurrentRaceTime` 在自由探索也會跑

**現象**：自由探索開車時 `CurrentRaceTime` 從 0 開始遞增，看起來與賽事完全一樣。
**影響**：不能用於 race detection。
**對策**：用 `LapNumber > 0 OR RacePosition > 0` 取代。
**實證**：2026-05-03 自由探索 65 秒，`CurrentRaceTime` 範圍 0..93.58。

### 2. `TimestampMS` 在倒轉時不倒退

**現象**：`TimestampMS` 是「遊戲啟動以來的毫秒數」，是牆上時鐘性質。倒轉時繼續向前增加。
**影響**：不能用於 rewind detection。
**對策**：改用 `CurrentRaceTime`（賽事中倒轉會讓它倒退）。
**實證**：2026-05-03 自由探索（含一次倒轉）4028 個轉場，`TimestampMS` 0 次倒退。

### 3. `DistanceTraveled` 在自由探索全為 0

**現象**：自由探索全程 `DistanceTraveled = 0.0`，遊戲不更新此欄位。
**影響**：不能作為 fallback rewind detection 訊號。
**對策**：見上，用 `CurrentRaceTime`。

### 4. 「IsRaceOn=0」狀態下 CRT、Lap、Speed 等欄位全部歸零

**現象**：任何讓 `IsRaceOn` 掉成 0 的事件（**選單、倒轉動畫、賽事結束、過場**）都會導致該段封包的 `CurrentRaceTime`、`LapNumber`、`Speed`、輪溫等欄位全部歸零。
**影響**：
- rewind 偵測若不過濾，會把每個 IsRaceOn=0 transition 誤判為倒轉（包含賽事結束）
- 直接統計 `LapNumber` 最大值會被歸零事件影響（其實不會，因為 max 不會降，但 lap 計數時要小心）
**對策**：
- rewind 偵測**只在 IsRaceOn=1 封包之間**做比較
- `_max_lap_number` 也只在 IsRaceOn=1 時更新

### 5. 自由探索的 `IsRaceOn = 1`

**現象**：只要在開車（不在選單），`IsRaceOn` 都是 1，無論是賽事還是自由探索。
**影響**：`IsRaceOn` 只能用來判斷「車在動」，不能判斷「在比賽」。
**對策**：見「賽事 vs 自由探索偵測」章節。

### 6. 第一筆封包可能 `CarOrdinal=0, PI=0`

**現象**：剛啟動 recorder 時若玩家在主選單/車庫/賽前 lobby，第一筆封包車輛欄位都是 0。
**影響**：若用第一筆建 session 資料夾名，會出現 `car0_PI0/`。
**對策**：buffer-and-commit 機制讓 session 資料夾用「進入 RECORDING 時的第一筆」命名，這時通常已經選好車了。實機若仍出問題，再改成「最後一筆有效資料」。

### 7. `LapNumber` 是 0-indexed

**現象**：5 圈賽事看到 `LapNumber` 範圍是 `{0, 1, 2, 3, 4}`，最大值 4 對應第 5 圈。
**影響**：直接把 `max(LapNumber)` 當總圈數會少 1。
**對策**：`total_laps = max_lap_number + 1`，在 meta.json 中同時保留 `max_lap_number` 方便驗證。

### 8. `TireTempRearLeft` 與 `TireTempRearRight` 全程相等

**現象**：實證一場 6731 packet 的 AWD 賽事，左右後輪溫度**完全位元級相同**（差值精確 0.0000）。但同個 session 的左右**前**輪正常獨立、左右**後輪滑移率**也正常獨立。
**可能原因**（未確認）：
- FH5 對某些車輛/組別用單一「後輪平均溫度」廣播兩次
- 我們的 parser 在 offset 276-283 之間有 4 byte 偏差（但 slip ratio 鄰近欄位正常 → 不太可能）
- AWD 車型的後輪建模特殊
**對策**：分析時把後輪當「單值」用，不要報告 L-R 後差。等收集到 RWD 與不同車型資料後再 root-cause。

### 9. `Brake` 欄位偶發性不傳送（觀察中）

**現象**：同一玩家（G29 方向盤+踏板，ABS 設定，**非** Auto Brake）、同一車輛、同一段時間內：
- 第 1 場 lapped 賽事：Brake 全程 = 0，但實測最大減速 3.79G、`NormalizedAIBrakeDifference` 範圍 0-55（單向）
- 第 2 場 single_run 賽事：Brake 0-255 正常、HandBrake 也有資料、NABD 範圍 -127 to +109（雙向）

兩場之間玩家**沒**重啟遊戲、**沒**改設定、**沒**重新插拔硬體。

**可能原因**（未確認）：
- FH5 Data Out 對方向盤輸入路徑有偶發性 bug（`Brake` / `Clutch` / `HandBrake` 三欄一起壞）
- 某些賽事類型 / 賽前提示視窗的副作用
- G HUB 與遊戲之間某個 race condition

**對策**：
- summarize.py 自動偵測「Brake max=0 但 max_decel_g > 1.5G」→ 標記為 ⚠️ 異常，分析時改用速度反推
- **持續收集多場資料**才能 root-cause（同類型賽事是否都壞？切換賽事類型會觸發嗎？）

### 10. 封包大小：323 vs 324 bytes

**現象**：FM Data Out 規格是 311 bytes（FM7 Dash），FH 加上 12-byte HorizonPlaceholder + 4 bytes = 變化版本。實證 FH5 送 324 bytes。
**對策**：parser 用 `>=` 接收，323 / 324 都吃。

---

## Phase 路線圖

| Phase | 狀態 | 內容 |
|-------|------|------|
| **Phase 1** | ✅ 2026-05-03 完成 | MVP：UDP listener、狀態機、raw.csv、meta.json、rewind 偵測、bat 啟動器、內容判斷暫停/倒轉、collision guard |
| **Phase 2** | ✅ 2026-05-03 完成 | `summarize.py`：raw.csv → summary.md（多圈/單趟賽事統一分析、TL;DR、輪胎/滑移/懸吊/換檔/輸入/G-force/減速事件七大區塊） + `race-analyst` skill：讀 summary.md 比對 wiki/ 給駕駛+調校建議 |
| **Phase 3** | ⏳ 規劃中 | Tune Card 系統（使用者車型穩定下來再做） + 跨 session 對比（v1 vs v2 調校差） |
| **Phase 4** | ⏳ 規劃中 | 熱鍵手動模式（自由探索測試直線時開關錄製、標記 invalid 段） + 賽道座標指紋自動辨識 |

⚠️ **Phase 2 從原規劃調整**：
- ❌ 取消「分圈切檔」（多此一舉，summary 階段用 LapNumber 分組就夠）
- ❌ 取消「事件類型自動辨識欄位」（summarize 直接看 max_lap_number 判斷 lapped vs single_run）
- ✅ 新增 `summarize.py` 與 `race-analyst` skill（原本是 Phase 3 內容）

未規劃但已討論：
- Tkinter GUI（替代 bat，視覺化狀態 + Stop 按鈕）
- 自動 trigger summarize（recorder 結束時自動跑）

---

## 測試與除錯

### Smoke test

```powershell
# 1. 模組可載入
python -c "from scripts.forza_telemetry import packet, session, recorder; print('OK')"

# 2. CLI --help
python -m scripts.forza_telemetry --help

# 3. 端對端（合成封包）
# 見 git log 找 'smoke test' 相關 commit 的內聯 python -c 範例
```

### 第一次跑時應該看到的 log

```
HH:MM:SS INFO forza_telemetry | listening on 0.0.0.0:5300 (state=idle)
HH:MM:SS INFO forza_telemetry | first packet OK: len=324, IsRaceOn=1, CarOrdinal=2429, PI=920
HH:MM:SS INFO forza_telemetry | state -> BUFFERING (waiting for competitive flag)
HH:MM:SS INFO forza_telemetry | state -> RECORDING (flushed N buffered packets, folder=...)
HH:MM:SS INFO forza_telemetry | state -> IDLE (cooldown elapsed, NNNN packets written, folder=...)
```

「first packet OK」這行應該驗證：
- `len=324` 或 `len=323`
- `CarOrdinal` 在 100-9999 之間（不是 0、不是七位數）
- `PI` 在 100-999 之間（不是 0、不是 1065353216 之類的 float bit pattern）

若 `CarOrdinal=0, PI=0` 持續出現，玩家可能還在主選單，跑去開車就會更新。

### 常見問題

| 症狀 | 原因 | 解法 |
|------|------|------|
| 雙擊 bat 後黑窗閃退 | Python 不在 PATH | `where python` 確認，或改 bat 用 `py -3` |
| `'M' 不是內部命令` 等亂碼錯誤 | bat 含中文，cmd 用 OEM codepage 解析失敗 | bat 應為純 ASCII（已修正，不該再發生） |
| Banner 中文亂碼 | console 沒切 UTF-8 | bat 開頭的 `chcp 65001` 應確保正確；Python 端也用 `sys.stdout.reconfigure('utf-8')` |
| 跑賽事但完全不錄 | FH5 沒設 Car Dash 格式 / 防火牆擋 UDP | 確認設定；Windows 防火牆允許 python.exe 接 UDP 5300 |
| Session 內 packet 數遠少於預期 | 跨機器網路丟包 | 用本機（127.0.0.1）測試對照；不要用 Wi-Fi |
| 自由探索被誤錄 | `is_competitive_event` 邏輯錯誤 | 檢查 `LapNumber/RacePosition` 在那個 session 是否真的有非零值 |

### 從現有 raw.csv 重新驗證偵測邏輯

```python
import csv
from pathlib import Path
from scripts.forza_telemetry import packet as pkt
from scripts.forza_telemetry.recorder import is_competitive_event

with Path('data/forza_telemetry/sessions/{your_session}/raw.csv').open() as f:
    rows = list(csv.DictReader(f))

# 應該全部為 True，否則代表這個 session 一開始就不該被錄
for r in rows[:10]:
    fake = pkt.Packet(**{name: 0 for name in pkt.FIELD_NAMES})._replace(
        LapNumber=int(r['LapNumber']),
        RacePosition=int(r['RacePosition']),
    )
    print(is_competitive_event(fake))
```

---

## 外部參考

權威來源（按可信度由高到低）：

1. **官方** — Forza Motorsport Data Out Documentation（Forza Support）
   <https://support.forza.net/>
2. **C struct（精確）** — holgerkenn/Forza-IoT-Relay `forza.h`
   <https://github.com/holgerkenn/Forza-IoT-Relay/blob/master/forza.h>
3. **TypeScript parser（FH5 專用）** — raweceek-temeletry/forza-horizon-5-UDP
   <https://github.com/raweceek-temeletry/forza-horizon-5-UDP>
4. **C# 參考實作（部分欄位類型有誤，僅供交叉比對）** — austinbaccus/forza-telemetry
   <https://github.com/austinbaccus/forza-telemetry>
5. **官方論壇討論** — UDP telemetry packet details
   <https://forums.forza.net/t/udp-telemetry-packet-details/629111>

社群工具（可借鏡其封包處理方式）：
- **SimHub**：開源賽車儀表板，原生支援 Forza Data Out
- **fabiomix/forza-horizon-telemetry**：Python 收集器
- **csutorasa/go-forza-telemetry**：Go parser

---

## 維護紀錄

新增條目請放在表格最上方。

| 日期 | 變更 | 原因 / 證據 |
|------|------|------------|
| 2026-05-04 | `start-telemetry-gui.bat` 移除中文 REM（cp950 解析錯誤再次踩坑） | 雙擊噴 `'?' 不是內部或外部命令`——`chcp 65001` 在 REM 解析後才執行已來不及。重申 CLAUDE.md 早記過的規則：**所有 .bat 必須純 ASCII** |
| 2026-05-04 | GUI 加深色主題（VS Code Dark+ 配色）+ summary 預覽改用 markdown 渲染（自製 tag-based renderer，支援 headers / bold / code / table / hr / 條列）+ 字體大小可調（按鈕、Ctrl+滾輪、Ctrl+=/-/0），CLI 可 `--theme light` 切換 | 使用者反映原本白底 + 純文字 summary 不好讀；無外部依賴用 ttk `clam` theme + tk.Text tags 達成 |
| 2026-05-04 | 新增 Tkinter GUI（`gui.py` + `start-telemetry-gui.bat`）：三分頁（狀態/賽事/車輛）、即時 snapshot 輪詢、強制錄製/強制停止、session 與 car 檔的 CRUD。recorder 加 `snapshot()` / `force_record()` / `force_stop()` 與封包速率追蹤 | 原本只有 console + 雙擊 bat，看不到當前狀態、無法快速瀏覽歷史 session、編輯 cars/*.yml 要打開檔案總管。GUI 把這些整合到單視窗，但保留 console 模式（兩者共用同一個 Recorder） |
| 2026-05-04 | 新增車輛資料庫：`cars.py` loader + `data/forza_telemetry/cars/{ordinal}.yml` + session finalize 凍結 `car.db` 進 meta.json + summarize 顯示車名 + .gitignore 解除 cars/ 排除 | ordinal 數字無法人類辨識（car1564 是什麼？），且需要把每場 session 對應到當時的調校狀態才能做跨場比對。tune 歷史交給 git log，不在檔內維護陣列 |
| 2026-05-03 | summarize.py 新增 `detect_crashes()` + 全域過濾：3 個獨立訊號（lateral G > 5×3 連續 / longitudinal G > 6 / 速度 50km/h 內掉 10 packet）+ ±0.5s 視窗排除 | Sprint 場 max lateral G **13.1G→4.15G**、max decel **20G→4.88G**——撞車 spike 嚴重污染 G-force / decel events / 懸吊觸底 / 滑移統計，過濾後數字才有調校意義 |
| 2026-05-03 | summarize.py 過彎分析：加 `CORNER_MAX_RADIUS_M = 250` sweeper 過濾 | 環道彎數 18→14（剔除 4 個 sweeper），平均 Peak G 從 2.12 升到 2.54——把高速微彎從「彎中操控統計」剔除避免污染推頭比例與速度損失均值 |
| 2026-05-03 | summarize.py 新增 §8「過彎分析」：彎道偵測（hysteresis、outlier cap、apex/crash 過濾）、L/R bias、彎中油門 / 速度損失 / 推頭過度比例、最重煞車 top 3 | 使用者要驗證「車的調校最優化 + 改善駕駛習慣」，需要彎道粒度的訊號；track_bias 是關鍵發現——它讓「右前胎熱 +13.5°C」從調校警報變成「賽道造成的正常現象」 |
| 2026-05-03 | summarize.py TL;DR 重構：症狀 + 調校處方 + 駕駛處方三段式，用 finding-level prescriptions 結構自動聚合、去重、按嚴重度排序 | 使用者新手身分，原本的「📋 觀察 +23°C」要求他自己對應到「降胎壓」很有摩擦——直接給「降前胎壓 1-2 psi」「拉長齒比」這種動詞開頭、可直接執行的清單，達成「一眼就知道下一步」 |
| 2026-05-03 | Brake=0 異常診斷改用速度反推 decel（threshold 1.0G）取代 IMU AccelerationZ | IMU 在低噪訊單樣本下會 under-report（0.81G），速度反推 5-packet 視窗能抓到 3.82G 真實峰值；先前因此誤判為「無明顯減速」 |
| 2026-05-03 | summarize.py：Brake=0 異常診斷加上 decel 交叉驗證；新增 quirks #9（Brake 偶發性不傳送，觀察中） | 同玩家同設備兩場，一場 Brake 全 0、一場正常，原本「疑似 Braking Assist」的訊息誤導，改成「FH5 Data Out 不穩定行為，本場分析不可信」 |
| 2026-05-03 | recorder finalize 時自動 trigger summarize（`--no-auto-summarize` 可關） | 否則使用者每場都要記得手動跑，違反「越用越好用」原則 |
| 2026-05-03 | 新增 `summarize.py`（多圈/單趟統一）+ `race-analyst` skill | Phase 2 完成；用使用者實際 5 圈賽事資料生 228 行 summary.md，TL;DR 自動標記前胎過熱/前輪滑移/換檔早 |
| 2026-05-03 | 文件記錄 FH5 怪癖 #8：`TireTempRearLeft == TireTempRearRight` | 一場 6731 packet AWD 賽事中後輪溫度位元級相同；前輪正常獨立、滑移率正常獨立。原因待 RWD 賽事資料確認 |
| 2026-05-03 | Session 資料夾命名加 collision 防護（`_2`/`_3` 後綴） | 同秒內結束 + 開新 session 會撞名 → 後者覆蓋前者 raw.csv（測試暴露） |
| 2026-05-03 | 移除 `--cooldown-seconds`、新增 `--idle-timeout-seconds`（預設 300）；新增 `Session.is_continuation()` 用內容判斷取代時間判斷 | 舊版 cooldown 8s 會把 > 8s 暫停或長 rewind 切成多個 session。新版用 `CarOrdinal/LapNumber/CurrentRaceTime` 三欄判斷「同 session 繼續」vs「新賽事」，5 種情境全部驗證通過（含使用者實際 5 圈賽事 CSV replay） |
| 2026-05-03 | `total_laps = max_lap_number + 1`、新增 `max_lap_number` 欄位 | 5 圈賽事實證 `LapNumber` 0-indexed（最大 4 對應第 5 圈） |
| 2026-05-03 | rewind 偵測加上 `IsRaceOn=1` 過濾條件 | 5 圈賽事實證：FH5 倒轉動畫期間 IsRaceOn=0 + CRT=0 + Lap=0；賽事結束模式相同。原本邏輯誤把這兩個都當倒轉（誤計 2 次、累計 197s）。修正後 1 次、4.97s ≈ 實際 5 秒倒轉 |
| 2026-05-03 | `_max_lap_number` 只在 IsRaceOn=1 時更新 | 同上，避免歸零事件干擾 |
| 2026-05-03 | rewind 偵測：`TimestampMS` 改為 `CurrentRaceTime` | 實證 FH5 倒轉時 `TimestampMS` 不倒退（4028/4028 單調遞增） |
| 2026-05-03 | `is_competitive_event` 拿掉 `CurrentRaceTime > 0.1` | 實證自由探索 `CurrentRaceTime` 也會跑（範圍 0..93.58 over 65s） |
| 2026-05-03 | `cooldown-seconds` 預設 5 → 8 | 為長 rewind 動畫留餘裕 |
| 2026-05-03 | bat 改純 ASCII，banner 移到 Python | bat 含中文觸發 cmd OEM codepage 解析錯誤 |
| 2026-05-03 | 加入 rewind 偵測（初版用 TimestampMS） | 防止倒轉重播污染統計 |
| 2026-05-03 | Phase 1 MVP 完成 | UDP listener + 三狀態機 + raw.csv + meta.json |

---

## 寫入此文件的時機

每次發生以下情況，**順手更新本文件**：

- 改了狀態機、偵測邏輯、CLI 參數、輸出格式 → 更新對應章節 + 維護紀錄
- 發現新的 FH5 行為怪癖 → 加進「FH5 行為怪癖」章節
- 加入新 Phase 的功能 → 更新路線圖
- 跑了實機測試發現外部文件描述與實際不符 → 加進實證資料

**改進是漸進的**：每次小修，不必一次大重構。但**該寫的就要寫**，不然下次自己（或下個 Claude）打開這個資料夾要花一小時 reverse engineer。
