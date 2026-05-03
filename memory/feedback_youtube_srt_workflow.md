---
name: YouTube 字幕下載是基礎技能
description: 處理 YouTube 來源時直接用 yt-dlp 下載 SRT，不需詢問使用者，也不要建議使用者手動下載
type: feedback
---

當使用者提供 YouTube URL 想評估／收錄到攻略庫時，**直接用本機 `yt-dlp` 下載字幕檔到 `Docs/_raw/`**，不要：
- 不要先說「YouTube 抓不到」就放棄
- 不要建議使用者手動下載 SRT 後再給你
- 不要因為「無法 WebFetch 影片」就只給標題層級審查

**Why**：使用者明確指示「YouTube 字幕下載要記得，以後作為基礎技能，不要再問」。先前回合我用 WebFetch 撞牆後直接呈現空殼審查，使用者反問「你沒辦法直接抓到字幕？」才轉用 yt-dlp。這個錯誤不能再犯。

**How to apply**：

本機環境：`yt-dlp 2026.02.21` 已安裝在 `/c/Users/D Good/AppData/Local/Programs/Python/Python313/Scripts/yt-dlp`，可直接呼叫。

下載指令範本（單支）：
```bash
yt-dlp --write-auto-subs --sub-langs "en-orig" --sub-format srt --convert-subs srt --skip-download \
  -o "Docs/_raw/%(id)s.%(ext)s" "https://www.youtube.com/watch?v=VIDEO_ID"
```

字幕語言選擇：
- 英文影片：`en-orig`（YouTube 自動字幕的原始英文）
- 中文影片（繁/簡）：`zh-Hant` 或 `zh-Hans`（看作者上傳哪種；可先用 `--list-subs` 確認）
- 不確定：先 `yt-dlp --list-subs --skip-download URL` 列出再選

批次處理多支用 bash for 迴圈，輸出統一在 `Docs/_raw/<id>.<lang>.srt`。

下載完成 → SRT 已是 `bilibili-to-doc` skill 的標準輸入格式，可直接交棒處理（包括英文 SRT，bilibili-to-doc 雖名稱含 bilibili 但本質是 SRT 處理 skill；若需要英譯中由我自行翻譯，不是 skill 內建）。
