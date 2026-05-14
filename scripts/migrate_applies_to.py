"""一次性遷移：將 Docs/wiki/**/*.md 的 frontmatter 從舊欄位 `game` 轉成新欄位 `applies_to`。

操作：
1. `game: FH5` → `applies_to: [fh5]`（同樣處理 FH4 / FH6 / fh5 等大小寫）
2. 移除舊欄位 `version` 與 `status`（已廢止；版本資訊改由 container 標）
3. 沒有 `game` 欄位的檔案，在 `pi_class:` 後（或 `sources:` 前）插入 `applies_to: [fh5]`

執行：
    python -m scripts.migrate_applies_to             # 預覽（dry-run）
    python -m scripts.migrate_applies_to --apply     # 實際寫入

執行後請用 `git diff` 檢查，再決定是否提交。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

WIKI_ROOT = Path(__file__).resolve().parent.parent / "Docs" / "wiki"

GAME_RE = re.compile(r"^game:\s*(\S+)\s*$", re.IGNORECASE)
VERSION_RE = re.compile(r"^version:\s*.*$")
STATUS_RE = re.compile(r"^status:\s*.*$")
APPLIES_TO_RE = re.compile(r"^applies_to:\s*\[")
PI_CLASS_RE = re.compile(r"^pi_class:\s*\[.*\]\s*$")
SOURCES_RE = re.compile(r"^sources:\s*$")
FRONTMATTER_DELIM = "---"


def to_applies_to(game_value: str) -> str:
    g = game_value.strip().lower()
    # 接受 fh5 / FH5 / "FH5" / fh-5 等變體
    g = g.strip("'\"")
    g = g.replace("-", "").replace(" ", "")
    if g in {"fh4", "fh5", "fh6"}:
        return f"applies_to: [{g}]"
    if g == "horizon":
        return "applies_to: [horizon]"
    if g == "general":
        return "applies_to: [general]"
    # 不認得就保守標 fh5，後續人工分類 pass 再調
    return "applies_to: [fh5]"


def migrate_file(path: Path) -> tuple[list[str], list[str], list[str]]:
    """回傳 (新內容行, 已改動描述, 警告)。若無改動，返回的 1st 與檔內容一致。"""
    text = path.read_text(encoding="utf-8")
    if not text.startswith(FRONTMATTER_DELIM):
        return text.splitlines(keepends=True), [], [f"無 frontmatter，跳過：{path}"]

    lines = text.splitlines(keepends=True)
    # 找 frontmatter 範圍
    if not lines[0].startswith(FRONTMATTER_DELIM):
        return lines, [], [f"frontmatter 起始異常：{path}"]
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].startswith(FRONTMATTER_DELIM):
            end_idx = i
            break
    if end_idx is None:
        return lines, [], [f"frontmatter 未閉合：{path}"]

    fm_lines = lines[1:end_idx]
    rest = lines[end_idx:]

    changes: list[str] = []
    warnings: list[str] = []
    new_fm: list[str] = []
    has_applies_to = False
    has_game = False
    pi_class_idx = None

    for idx, line in enumerate(fm_lines):
        stripped = line.rstrip("\n").rstrip("\r")
        if APPLIES_TO_RE.match(stripped):
            has_applies_to = True
            new_fm.append(line)
            continue
        m = GAME_RE.match(stripped)
        if m:
            has_game = True
            replacement = to_applies_to(m.group(1))
            new_fm.append(replacement + "\n")
            changes.append(f"  game: {m.group(1)} → {replacement}")
            continue
        if VERSION_RE.match(stripped):
            changes.append(f"  移除 {stripped}")
            continue
        if STATUS_RE.match(stripped):
            changes.append(f"  移除 {stripped}")
            continue
        if PI_CLASS_RE.match(stripped):
            pi_class_idx = len(new_fm)
        new_fm.append(line)

    if not has_applies_to and not has_game:
        # 沒 game 也沒 applies_to → 補一條預設
        insert_at = (pi_class_idx + 1) if pi_class_idx is not None else len(new_fm)
        # 找 sources: 的位置作 fallback
        if pi_class_idx is None:
            for i, line in enumerate(new_fm):
                if SOURCES_RE.match(line.rstrip("\n")):
                    insert_at = i
                    break
        new_fm.insert(insert_at, "applies_to: [fh5]\n")
        changes.append("  + 補入 applies_to: [fh5]（原無 game 欄位）")

    if has_applies_to and has_game:
        warnings.append(f"同時有 game 與 applies_to，已優先保留 applies_to（{path.name}）")

    new_lines = [lines[0]] + new_fm + rest
    return new_lines, changes, warnings


def main() -> int:
    apply = "--apply" in sys.argv

    files = sorted(WIKI_ROOT.rglob("*.md"))
    if not files:
        print(f"找不到任何 wiki/ md 檔。WIKI_ROOT = {WIKI_ROOT}")
        return 1

    total_changed = 0
    all_warnings: list[str] = []
    for path in files:
        new_lines, changes, warnings = migrate_file(path)
        all_warnings.extend(warnings)
        if not changes:
            continue
        total_changed += 1
        rel = path.relative_to(WIKI_ROOT.parent.parent)
        print(f"\n{rel}")
        for c in changes:
            print(c)
        if apply:
            path.write_text("".join(new_lines), encoding="utf-8")

    print(f"\n========= 結果 =========")
    print(f"檔案掃描：{len(files)}")
    print(f"有變更：{total_changed}")
    if all_warnings:
        print(f"\n警告：")
        for w in all_warnings:
            print(f"  - {w}")
    if not apply:
        print(f"\n⚠️ 預覽模式，未寫入。確認 OK 後加 --apply 再跑一次：")
        print(f"   python -m scripts.migrate_applies_to --apply")
    else:
        print(f"\n✅ 已寫入 {total_changed} 個檔。請 git diff 檢查。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
