---
原始標題: HOW TO TUNE in Forza Horizon 5 in 2025 | OP Car Tutorial (Build & Setup)
作者: Johnson Racing（合作：VNXLS、Silva）
日期: 2025-07-25
影片長度: 26:10
來源URL: https://youtu.be/PGdLKPFye0M
原始檔: Docs/_raw/PGdLKPFye0M.en-orig.srt（YouTube 自動英文字幕）
整理日期: 2026-05-04
語言: 英文 → 繁體中文整理
說明: 已移除問候、訂閱呼籲、重複口癖，保留全部 build 步驟、PI 操作技巧、具體數值、反直覺主張與作者本人立場。
---

# 【FH5 2025 調校教學】Ferrari FXX S1 全能向 AWD OP build 完整教學（整理版）

> 作者本人標誌：「favorite German potato」。本期是與職業／榜首級 driver **VNXLS** 合作（另有 Silva 協助）的 build 教學，主打「不浪費時間講無用理論，直接邊操作邊講為什麼」。
>
> 「Forza 有它自己的物理規則」是本影片貫穿全程的前提——很多反直覺的設定都源自此。

---

## 序：本期 build 對象與目標

- **車型**：Ferrari FXX
- **目標 PI 級**：S1 900（即把 stock 的 S2 級 FXX **降 PI 進 S1**，做成全能向 AWD 怪物）
- **適用情境**：S1 全能向（all-rounder），影片自承這是線上賽中**多數玩家**的目標
- **作者選 FXX 的理由**：抓地強、好開、極速也快——既有 grip 又有速度的少數兼顧車
- **聲明**：本影片是系列首集，作者徵求觀眾留言指定下一集的車輛類型
- **配合資源**：作者另有「best cars and tunes 2025」影片與**超過 350 台車的 setup spreadsheet**，FXX 這台 build 由 VNXLS 上傳了 share code 收錄其中

---

## Part 1：Upgrades（改裝）階段

### 1.1 Conversions（引擎／驅動／自然進氣 swap）

**第一步永遠是先看 conversions tab**，看有沒有有趣的引擎、驅動形式或自然進氣／渦輪 swap，因為**換不同 swap 也意味著後續 upgrade 路徑會不同**。

#### 引擎 swap 的核心觀念：FH5 PI 系統會誤判某些 swap

> **這是本影片最重要的引擎類洞察之一**：

- 遊戲的 PI 系統**偏愛某些 swap**，使它們在 PI 性價比上**遠勝原廠引擎或其他選項**
- 根因：遊戲對某些引擎的 **power band（出力曲線）誤判**——它不知道最佳上檔時機，因此低估這些引擎的真實實力
- **F4TR 引擎範例**（重要）：
  - 紅線從 **8.29K** 才開始
  - 但實際上你 **5.5K** 就要上檔（因為扭力來得早、後段虛轉）
  - 遊戲（自排）會等到很晚才上檔
  - **結論：在 FH5 中，手排顯著優於自排**，因為遊戲不懂這些引擎的真實出力曲線

#### FXX 在 conversions 上的特殊情況

FXX 有兩個引擎 swap 選項：

- **Racing V12**
- **6.3 L Hybrid V12**

但因為 **FXX stock 已是 S2 級**，要做 S1 build 必須**降** PI——**不能再花 PI 換引擎**，所以**保留 stock 引擎**。

> 假設要做 S2 build：作者明確推薦 **Racing V12**，理由：「**只花 6 PI、減 100 kg**」，作者形容為「insane」「tasty exchange」。
>
> 副作用：「幾乎所有高 PI build 在遊戲裡聽起來都一樣」——因為大家都換 Racing V12。

#### 已知的「PI 高效引擎 swap」清單

> 影片明列三個最 PI efficient 的 swap，可作為其他 build 的參考：

1. **Racing V12**（FXX 等用）
2. **F4TR engine**（紅線錯位的那顆）
3. **6.2 L V8 Corvette engine**

### 1.2 驅動形式 swap：AWD swap on FXX

> 作者承認 AWD swap 在 FH5 是**爭議話題**：許多玩家想保持原廠純粹（純血派／purist），而 AWD swap 在硬核圈被視為「異端」。

**FXX 原廠 RWD**，AWD swap 規則：

- **節省 10 PI**（遊戲認為 swap 完車變重所以「補貼」你）
- **車變重**
- **但實質好處**：起跑更好、低速加速更好、操控更易掌握

**AWD swap 對 FXX 為何適用**：
- AWD 車整體**較好駕駛**
- 適合 FH5「越野元素 + 自由探索」的整體基調，自由探索時尤其方便

**負面**：
- 重量增加 → 入彎反應與整體加速**略差**
- 但作者結論：**值得**

#### 重要免責：RWD 純跑圈仍可能更快

> 排行榜上仍有大量 RWD 在前列——它們純跑圈的 lap time 可能更快，**但更難開**，需要好的縱向控制（vertical control）。
>
> 此外線上賽被推到草地上時，AWD 草地脫困比 RWD 容易——這是 free-for-all 線上比賽的隱性收益。

#### AWD swap 的 PI 變化作為車型判斷

> **rule of thumb**（作者明說）：

| swap 後 PI 變化 | 含意 |
|----------------|------|
| **PI 大跌** | 通常代表 swap 後**更快** |
| **PI 微跌**（如 FXX 只回 10 PI 左右） | **看賽道**——不一定 |
| **PI 上升** | 通常 swap 後**更慢** |

### 1.3 自然進氣／渦輪 swap

FXX 不能改 aspiration（沒選項），影片明說「下一集 OP car tutorial 講」——本期跳過。

> 觀眾留言區可指定下一集車種。

### 1.4 Tires & Rims（輪胎與輪框 / mechanical grip）

#### 胎種選擇

S1 全能向 AWD 車的胎種選擇就三類：

1. **Semi-slicks**（半光頭）
2. **Slicks**（光頭）
3. **Rally tires**（拉力胎）

> FXX 原廠是 **race tires**——FH5 中**只有正規賽車**才有的特殊胎，**不在玩家自定義範圍內**。

#### 為何 S1 全能向 AWD **絕大多數選 Rally tires**

- 理論上 slicks 抓地最好
- 但**最高比例的 all-rounder 玩家用 Rally**——理由是**性價比最佳**
- Rally 抓地仍夠用，**且 PI 效率極高**
- **FXX 上裝 Rally 直接拿回 41 PI**
- 額外好處：**草地抓地大幅提升**——線上賽被推出賽道、過彎切草都受惠

#### 例外：少數車種仍適合 semi/slicks

> 影片明列：

- **4GT**（推測為 Ford GT，影片字幕誤辨）
- **McLaren 620R**
- **Corvette**

這幾台用 semis 或 slicks 反而合適。

#### 前輪寬度（front tire width）

- FXX 上**不需要**——花 6 PI 換不到顯著好處
- **何時值得**：車**達不到足夠橫向 G 值**時——尤其**沒有下壓力的車**才需要前寬胎
- FXX 顯然不在此列

#### 後輪寬度（rear tire width）

- **AWD build 必拿**
- **0 PI 成本**
- 顯著提升 traction 與後軸穩定性
- 「Easy pick」

### 1.5 Drivetrain（傳動）

#### 差速器升級

> **永遠安裝**——不論你不想改差速器都裝它，因為：
>
> - 安裝後才能在 fine-tune 選單**精細調整**差速器設定
> - **0 PI 成本**

差速器類型選擇（影片給出明確的「該選哪個」表）：

| 驅動形式 | 推薦差速器類型 | 理由 |
|---------|---------------|------|
| **AWD**（如本期 FXX） | **Drift diff** | **最高的 max center balance**——多數 AWD 用此 |
| **RWD** | **Rally diff** | grip → oversteer 的**過渡更平滑** |
| **FWD** | **Off-road diff** | 推頭略微減少 |
| 任何車 | **Race diff**（不要選） | grip → 失抓**沒有平滑過渡**——影片明說「幾乎用不到」 |

> 作者本人對「Drift diff 安裝在 AWD 公路車」也覺得反直覺，但「This is Forza」——遊戲規則就這樣。

#### 變速箱升級

選項：原廠、多種 race 變速箱、drift 變速箱。

**通則**：

- 多數車**不需要 race trans**——一個 sport 或 street 變速箱就夠，因為**安裝後 final drive 即可調整**
- 但 **FXX 沒有 sport/street 選項**，必須上 race
- 而且 **AWD swap 自動附帶 6 速 race transmission**，已可細調**每一檔**

**8 速 vs 6 速 vs 7 速 的 PI 凹點**（重要）：

- FXX 上 **8 速 race transmission 多回 1 PI**（代價：略增重量）
- **7 速 race trans 拿不到這 1 PI**
- **9 速 race trans 已經太重**
- **逐車試**——這是 case by case 的決定，有些車能多回 PI、有些不行

> 「永遠睜大眼睛找這種 spicy extra PI」是作者強調的工程心態。

### 1.6 Platform & Handling（平台與操控）

FXX 在此 tab **只有一個選項**：**springs and dampers**——原因是它已內建 race anti-roll bars、race brakes 等。

#### 反直覺：FXX 應該裝**Off-road springs and dampers**（重要）

> 「Yes, it sounds weird, but hey, again, this is Forza」——作者明說。

裝 off-road springs/dampers 對 FXX 的好處：

1. **最大車高（ride height）大幅提高的選項**——FXX 強到撐得起這激進設定
2. 比 race 版**略軟一點**的彈簧
3. **減 1 kg 重量**
4. **回 1 PI**

理由：FXX 抓地過剩、本身穩定性過剩，會**略推頭**。**拉高車高 + 軟化彈簧** 改善整體 rotation；FXX 穩定性夠，這激進設定**沒有負面影響**。

> Drift springs/dampers：**永遠忽略**。選擇就在 race vs off-road 之間，依車而異。

### 1.7 確認 PI：是否還在 S1 範圍內？需要繼續凹

到此 FXX 還**沒到 S1 900**，PI 還太高，需要繼續「minmax」。

#### 1.7a 輪框樣式（Rim Style）

- 找**最重的輪框**——最重款比原廠**重 22 kg**
- 純為了**降 PI／凹數據**——只看 stats
- 樣式哪個都可，挑你喜歡的

#### 1.7b 輪框尺寸（Rim Size）

- **後輪框尺寸放大** → 降 PI（代價：略增重量）
- 對操控**沒有實質好處**——純凹數值

#### 1.7c 回到 Platform & Handling 看 driveline（傳動軸）

- 安裝 **race driveline**：
  - 減重
  - 略增 PI
- 如果還在 PI 範圍內就拿——FXX 算過剛好還能塞下

#### 1.7d 再回 Tires & Rims 看 track width（輪距）

- **前輪距**：基本拉滿了，每段都吃一點點 PI
- **後輪距**：**0 PI 成本**——直接裝
- **效果**：理論上「車更穩」，但實際**「homeopathy 等級」**——「沒有科學證據」「你必須相信它」

### 1.8 Upgrades 階段小結

> 「Halfway done」——upgrades 是 tuning setup 中**較重要**的一半，但 fine-tune 是讓車**真正變 OP** 的最終雕琢。

---

## Part 2：Fine-tune（細調）階段

> **核心心態**：「FH5 的好 tune 與現實**不太相關**，遇到怪設定別意外。」

### 2.1 Tires（胎壓）

**通則**：

- **不同胎種偏好不同胎壓**
- **承載較多重量的軸**（前或後）→ **胎壓較低**

**Rally tires 的 sweet spot**（重要）：

- **1.5 ~ 1.6 bar**（公制）
- **21 ~ 高 23 PSI**（英制）
- **不能太軟**：太軟胎會過熱、變海綿感
- **不能太硬**

**FXX 具體值**：

- **基準 1.6 bar 雙軸**
- 但兩軸有微調差異：
  - **前胎**：從 1.6 起算 **+2 click**
  - **後胎**：從 1.6 起算 **+5 click**
- 換 PSI 看時數值會不同（影片現場展示時切換 PSI 介面，作者吐槽：「**唯一公制不勝過英制的數值**」）

> 「How did we find out? Trial and error.」——所有微調值都是試出來的。

### 2.2 齒比（Gearing）

**前提**：上一階段裝了 **8 速 race trans 多回 1 PI**，所以可細調 final drive + **每一檔**。

**通則**：

- 多數情況**只調 final drive 就夠**
- 但「我們是完美主義者」，FXX 上每一檔都調
- **降 final drive 值** → 齒比變長 → 理論上**極速增、加速減**
- **升 final drive 值** → 齒比變短 → 加速增、極速減

**全能向通則**：「**齒比要盡量短，但只在需要時才放長**」（as short as possible, as long as needed）。

**FXX 引擎特性**（重要）：

- **動力出力峰值在紅線附近** —— 大約 **8.5K ~ 9K RPM**
- **絕對不要太早上檔**
- 齒比要配合，使**出彎加速時能持續用到峰值動力**

**FXX 具體齒比設定**：

- **Final drive 拉長到 ~2.55**——換更高極速，但**效果不顯著**
- 為補償加速，**每一檔略微縮短**（值微增）
- **第 8 檔故意調到車跑不到** —— 實際只用前 7 檔
- **多數情況連第 7 檔都用不到**

### 2.3 Alignment（四輪定位）

#### Camber（外傾角）

**通則**：

- **前 camber 略大於後 camber**（因為前軸負責轉向）
- **驗證方法 1：用 telemetry**
  - 過彎時觀察 camber 數值
  - **理想狀況：彎尾段時，外側輪 camber 盡量靠近 0**——此時與地面接觸最大
- **驗證方法 2：胎溫**
  - 外側熱、內側冷 → camber **不夠**
  - 內側熱、外側冷 → camber **太多**
  - 理想：**內外溫差最小、telemetry 顯示 0**

**症狀對應**：

| 動作 | 症狀變化 |
|------|---------|
| **減前 camber** | turn-in 反應變慢 |
| **減後 camber** | 慢彎 traction 增加，但快彎/長彎可能不穩 |

**特殊技巧——用 rear camber 處理推頭**：
- 嚴重推頭時，**rear camber 可比 front 略高**（即倒裝）

**通用範圍**：**-1.0 ~ 0**

**FXX 具體值**：

- **前 camber：-0.3**
- **後 camber：-0.1**

> 這組是 all-rounder 的 middle ground。

#### Toe（束角）

**作者立場**：

- **最後再調**——當其他都試過仍解不了某個駕駛特徵時的**最後手段**（last resort）
- 仍推頭 → **前 toe +0.1 ~ +0.2**
- 想增後軸穩定 → **減後 toe**
- **FXX 沒動 toe**（保持原廠）

#### Caster（主銷後傾）

**通則**：

- **值高 → 轉向後車身回正快、直線穩定性好**
- **FH5 多數設高值**，因為更利於 tap-steering（點轉）
- 高 caster 配 FH5 普遍偏低的 camber → 透過**轉向時自動傾斜增加接地面**改善過彎抓地
- **降 caster** 是**激進手段**：能改善「不想轉的車」的 turn-in，但會**犧牲彎中速度**——適合「boaty cars」與**RWD 速度向 build**
- **通用範圍 6.5 ~ 7.0**

**FXX 具體值**：落在 **6.5 ~ 7.0** 區間。

### 2.4 Anti-roll bars（防傾桿，ARB）

**核心原理**（重要）：

> **FH5 中防傾桿越軟 → 抓地越多。**

**FXX 處境分析**：

- AWD swap 後
- **沒**裝前寬胎，**有**裝最寬的後輪寬胎
- → 車已**有推頭傾向**，需要削掉

**AWD 起手公式**（重要）：

- **前 ARB：1**（最軟）
- **後 ARB：65**

> 「即使聽起來很奇怪也照做」——這是 AWD 的標準起手值。

**症狀調整**：

- 過 over steer → **後 ARB 降** 或 **前 ARB 升**

**多數 AWD build 的 go-to 最終值**：**1 / 65**（多數情況不需要動）

> 影片在不同段落間互相印證 1/65 vs 165——這裡指**前 1 / 後 65** 是 AWD 起手與多數車的最終值。

### 2.5 Springs（彈簧）

**通則**：

- 彈簧硬度控制重量轉移（加速、煞車、過彎時）
- **預設配比應對齊 garage 顯示的車身重量分布**
- **重的軸 → 彈簧硬**

**FXX 重量分布**：在 garage 看，**46% front weight**（即後重前輕）→ **後彈簧 > 前彈簧**。

**症狀對應**：

| 症狀 | 處方 |
|------|------|
| 出彎 over steer 或整體 traction 差 | **前彈簧加硬 + 後彈簧軟化** |
| 推頭 | 反向（前軟後硬） |

**通則**：**整體傾向偏軟**。

**FXX 具體值**：

- **前彈簧：83**
- **後彈簧：133**

> 「看起來硬，但因為我們用的是 off-road 底盤，原廠就比 race 軟很多」——所以 83/133 在 off-road 底盤上其實是適中。

> 這組值也驗證了「多數 AWD build 前彈簧 < 後彈簧」的通則。

### 2.6 Ride height（車高）

**極端設定（FXX 適用）**：

- **前車高：最高值**（max）—— 為了 turn-in 反應最快
- **後車高：最低值**（min）—— 用一點穩定性換**極速 + 略好的 rotation**

> **適用條件**：**只在 stability 與 downforce 都夠的車**才適用。FXX 兩者都過剩，所以撐得起這設定。

> 視覺上 FXX 因此「看起來很怪」（前高後低），這是 OP build 的代價之一。

### 2.7 Dampers（阻尼）

**核心**：

- **bump damping** 對抗彈簧**壓縮**
- **rebound damping** 對抗彈簧**伸展**

**通則**：

- **rebound 通常落在中段**
- **bump 偏低**
- **rebound 通常 > bump**

**FXX 具體值**：

| 阻尼 | 前 | 後 |
|------|-----|-----|
| **Bump** | **3.0** | **3.6** |
| **Rebound** | **16** | **10** |

**設計邏輯**：

- 後 bump 略高於前 bump → **多一點初始 rotation，但 turn-in 不更不穩**；加速時更穩
- 整套適合**慢彎良好表現 + 中速彎仍保有速度**
- 若降前 rebound → 入彎更易 oversteer，但出彎更穩——FXX 不需這調整

### 2.8 Aero（下壓力）

**通則**（高 PI 級全能向）：

- **前下壓力：最大**（max downforce）—— 高速彎能拉到最大彎中速度
- **後下壓力**：**依手感配合**——
  - 太低 → over steer
  - 太高 → 推頭 + 多餘 drag → 極速減
- 少數車 RWD 速度向 build 仍可考慮**完全減後翼**，但已不像 FH4 時代普遍

**FXX 具體值**：

- **前**：max
- **後**：**155**

> 注意：齒比（2.2）已**配合此 aero 設定**做過優化。

### 2.9 Brakes（煞車）

#### 煞車壓力

純個人偏好，沒有對錯。**底線**：

- 太低 → 車根本停不下來
- **能 lock up 就夠高了**

#### 煞車平衡（重要——爭議點）

> **作者明確主張**：「**FH5 滑桿至今未修，數值仍然反向**」（the values are actually still inverted）。

依作者主張的設定：

- **多數情況 shift 到「rear」方向、值約 54%**（54% rear，因為反向 = 實際偏前）
- 目的：煞車時車身**更靈動**、**更利 trail braking**
- 想要更穩 → 反向

> ⚠️ **這不是主張衝突，是 UI 方向差異**：FH5 煞車平衡滑桿在**中英文版顯示方向相反**。4 家英文社群作者（Johnson Racing、HokiHoshi 2025/2021/2021 漂移）都按英文 UI 描述「shift to rear」；4 家中文社群作者按中文 UI 描述「偏前」——**兩邊講的都對，是同一個操作**。讀者用中文版時，把英文教學的方向反過來讀即可（英文「54% rear」≈ 中文 UI 偏前 46% 左右）。

### 2.10 Differential（差速器）

> **回顧**：上一階段裝了 **drift diff**——它有以下「perks」：

- 後輪在煞車時**較不易 lock up**——尤其前重車（hot hatch、舊肌肉車）
- 允許**更高 center balance** 設定，**不犧牲起跑與低速 traction**

#### Center balance（中央差速器）

- **0% = 動力全給前** → 變前驅
- **100% = 動力全給後** → 變後驅
- **fun fact**：即使設 0% 或 100%，**另一軸仍會收到一些動力**（FH5 實作怪癖）

**FXX 的 center balance**：

- **100%**（極端）
- 理由：FXX 後輪夠寬、抓地夠，能吃下這 setting；剩下「漏」到前軸的動力已足以讓 AWD 起跑優勢成立

**AWD grippy car 通則**：

- **起手 80%**，再試多高能撐
- FXX 撐得到 100%

#### Acceleration（加速鎖定）（重要——反直覺）

> **理論上**：高 accel → 內外輪同速 → 應**多推頭**。
>
> **FH5 實作卻相反**：

- **前差加速高 → 反而減少彎中推頭**（FH5 似乎搞反了）
- **後差加速高 → 多 oversteer**（這個是符合直覺的）

**90% 的 AWD 全能向 build**：

- **前後 acceleration 都拉 100%**
- FXX 即此

> 「若不是 100% 也只是略低」「不要怕用極端值」。

#### Deceleration（減速鎖定）

- **多數情況保持極低**——讓鬆煞車時車能漂亮 rotate
- **FXX 前後 decel 都 0**
- 若車**鬆油時容易甩**，**rear decel 5 ~ 10** 找穩定性

---

## Part 3：作者立場與重要觀點

### 3.1 五角圖數據（speed / handling / braking）「完全沒參考價值」

> 作者明說：「I haven't tackled the car stats... and the reason is very, very simple. **Stats don't matter in this game at all**.」

理由：遊戲的 stats 計算考慮了**根本沒道理**的特性，故那五角圖**不能用來判斷 build 好壞**。

### 3.2 FH5 與現實物理的關係

> 「Great tuning setups in Forza Horizon 5 aren't really closely connected to reality.」

這也是為何 build 中會出現許多反直覺設定：

- 越野彈簧裝公路車
- Drift diff 給 AWD
- 前差加速 100% 反而減推頭
- 煞車滑桿反向
- 重輪框故意拿來凹數據

### 3.3 收尾

- 作者邀請觀眾**直接複製這個 tune** 或**做小幅調整適合自己風格**
- **VNXLS 已上傳 share code**（可在作者 setup spreadsheet 取得）
- 作者另一支「best cars and tunes 2025」涵蓋全 PI 級的「OP cars」清單

---

## Part 4：FXX S1 全能向 AWD OP build 完整數值速查表

| 大項 | 細項 | FXX 數值 |
|------|------|---------|
| **Conversions** | 引擎 | 保留 stock V12（PI 限制故不換）|
| **Conversions** | 驅動 | **AWD swap**（節省 10 PI）|
| **Conversions** | 自然進氣 | （不可改）|
| **Tires** | 胎種 | **Rally tires**（節省 41 PI）|
| **Tires** | 前輪寬度 | **不裝**（6 PI 成本不划算）|
| **Tires** | 後輪寬度 | **裝最寬**（0 PI 成本）|
| **Drivetrain** | 差速器 | **Drift diff** |
| **Drivetrain** | 變速箱 | **8 速 race transmission**（多回 1 PI）|
| **Drivetrain** | 傳動軸 | **Race driveline** |
| **Platform & Handling** | 彈簧／阻尼 | **Off-road springs and dampers**（最大車高 + 軟化 + 減 1 kg + 回 1 PI）|
| **Tires & Rims** | 輪框樣式 | 最重款（重 22 kg）|
| **Tires & Rims** | 輪框尺寸 | 後輪框放大（凹 PI）|
| **Tires & Rims** | 前輪距 | 拉滿 |
| **Tires & Rims** | 後輪距 | 裝（0 PI）|
| **Fine-tune：胎壓** | 前 | **1.6 bar + 2 clicks** |
| **Fine-tune：胎壓** | 後 | **1.6 bar + 5 clicks** |
| **Fine-tune：齒比** | Final drive | **~2.55**（拉長）|
| **Fine-tune：齒比** | 第 8 檔 | **故意調到無法用**（實際只 7 檔）|
| **Fine-tune：齒比** | 上檔 RPM | 接近紅線 8.5K~9K |
| **Camber** | 前 | **-0.3** |
| **Camber** | 後 | **-0.1** |
| **Toe** | 前後 | **0**（不動）|
| **Caster** | — | **6.5 ~ 7.0** 區間 |
| **ARB** | 前 | **1**（最軟）|
| **ARB** | 後 | **65** |
| **彈簧** | 前 | **83** |
| **彈簧** | 後 | **133** |
| **車高** | 前 | **最高值** |
| **車高** | 後 | **最低值** |
| **阻尼 Bump** | 前 | **3.0** |
| **阻尼 Bump** | 後 | **3.6** |
| **阻尼 Rebound** | 前 | **16** |
| **阻尼 Rebound** | 後 | **10** |
| **下壓力** | 前 | **最大** |
| **下壓力** | 後 | **155** |
| **煞車壓力** | — | 個人偏好（能 lock up 就夠）|
| **煞車平衡** | — | **54% rear（英文 UI）≈ 中文版 UI 約 46%（偏前）**；中英文 UI 方向相反，參見 2.9 |
| **差速器 Center balance** | — | **100%** |
| **差速器 Acceleration** | 前 | **100%** |
| **差速器 Acceleration** | 後 | **100%** |
| **差速器 Deceleration** | 前 | **0%** |
| **差速器 Deceleration** | 後 | **0%** |

---

## Part 5：可推廣到其他 build 的通則（非 FXX 限定）

### 5.1 一般 build 流程心法

1. 先看 **conversions**（引擎、驅動、自然進氣）
2. **Tires & Rims**（mechanical grip）
3. **Drivetrain**（差速器先裝、變速箱依車試）
4. **Platform & Handling**（依抓地過剩 vs 不夠選 race vs off-road springs）
5. 回頭調**輪框樣式／尺寸／傳動軸／輪距**凹剩餘 PI

### 5.2 PI 凹點清單

| 技巧 | 適用 |
|------|------|
| Rally tires | 多數 AWD 全能向 |
| 後輪寬胎 | 多數 build（0 PI）|
| AWD swap | RWD 車當 PI 大跌時通常更快 |
| 重輪框 + 後輪框放大 | 通用 |
| 8 速 race trans 試是否回 PI | 逐車試 |
| Off-road springs/dampers 替代 race | 抓地過剩、需要降 PI 的公路車 |
| Race driveline | 末段如果還在 PI 範圍內可拿 |

### 5.3 差速器選型快表

| 驅動 | 差速器 |
|------|--------|
| AWD | Drift diff |
| RWD | Rally diff |
| FWD | Off-road diff |
| 任何車 | 不要 race diff |

### 5.4 ARB 起手值

| 驅動 | 前 / 後 ARB 起手 |
|------|------------------|
| AWD（grippy）| **1 / 65** |

### 5.5 反直覺 FH5 規則彙整

1. **手排 > 自排**（很多引擎 power band 被誤判，F4TR 等特別嚴重）
2. **越野彈簧裝抓地過剩公路車** 反而提升 rotation
3. **Drift diff 給 AWD** 是常見最佳選
4. **前差加速高 → 反而減彎中推頭**
5. **煞車滑桿中英文 UI 方向相反**（不是 bug 也不是爭議，是 UI 在地化差異——英文教學的「往 rear」=中文版的「偏前」）
6. **車身 stats 五角圖不可信**

---

## Part 6：影片風格與作者背景

- 作者自稱 **「favorite German potato」**——主頻道風格
- 與職業／榜首級 driver **VNXLS** 合作完成 build；**Silva** 提供協助
- 維護一份 **超過 350 台車** 的 setup spreadsheet，share code 公開
- 本期是「OP car tutorial」系列首集，**徵求觀眾留言指定下集車種**

---

## 來源

- **原始影片**：https://youtu.be/PGdLKPFye0M
- **作者**：Johnson Racing（YouTube）
- **合作 driver**：VNXLS（VNXLS 上傳 share code）
- **發布日期**：2025-07-25
