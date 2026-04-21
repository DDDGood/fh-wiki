#!/usr/bin/env bash
# check_integration.sh — 掃描 Docs/_sources/ 中尚未被 Docs/wiki/ 整合的原始攻略檔
#
# 用法：
#   bash scripts/check_integration.sh
#
# 判定邏輯：
#   對每個 _sources/*.md，在 wiki/ 下 grep 「_sources/{檔名}」。
#   引用數為 0 表示尚未整合。

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCES_DIR="$ROOT/Docs/_sources"
WIKI_DIR="$ROOT/Docs/wiki"

if [ ! -d "$SOURCES_DIR" ]; then
  echo "找不到 $SOURCES_DIR"
  exit 1
fi

UNMERGED=0
MERGED=0
TOTAL=0

echo "掃描 _sources/ 整合狀態..."
echo

for f in "$SOURCES_DIR"/*.md; do
  [ -e "$f" ] || continue
  TOTAL=$((TOTAL+1))
  name=$(basename "$f")
  refs=$(grep -rl "_sources/$name" "$WIKI_DIR" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$refs" -eq 0 ]; then
    printf "  ❌ 未整合                      %s\n" "$name"
    UNMERGED=$((UNMERGED+1))
  else
    printf "  ✅ 已整合（%2d 個 wiki 檔引用）  %s\n" "$refs" "$name"
    MERGED=$((MERGED+1))
  fi
done

echo
echo "小計：$TOTAL 份來源 · 已整合 $MERGED · 待整合 $UNMERGED"

if [ "$UNMERGED" -gt 0 ]; then
  echo
  echo "下一步：在 Claude Code 中執行 /wiki-integrator <檔名> 處理未整合的來源。"
fi
