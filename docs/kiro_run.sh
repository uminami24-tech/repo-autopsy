#!/bin/bash
# Kiro CLI を非対話で実行し、指示と出力を docs/kiro-log.md に追記するラッパー
# usage: kiro_run.sh "<ラベル>" <promptfile> [追加オプション...]
cd /workspace/kiro-repo-autopsy || exit 1
LABEL="$1"; PF="$2"; shift 2
LOG=docs/kiro-log.md
RAW=$(mktemp)
START=$(date +%s)
/home/box/.local/bin/kiro-cli chat --no-interactive --trust-all-tools --trust-workspace "$@" "$(cat "$PF")" >"$RAW" 2>&1
RC=$?
END=$(date +%s)
{
  echo; echo "## $LABEL"; echo
  echo "- 実行時刻: $(date '+%Y-%m-%d %H:%M')（日本時間） / 所要 $((END-START)) 秒 / 終了コード $RC / オプション: $*"
  echo; echo "### Kiroへの指示"; echo; echo '````text'; cat "$PF"; echo '````'
  echo; echo "### Kiroの出力（ANSI除去）"; echo; echo '````text'
  sed -r 's/\x1B\[[0-9;?]*[a-zA-Z]//g' "$RAW"
  echo '````'
} >> "$LOG"
sed -r 's/\x1B\[[0-9;?]*[a-zA-Z]//g' "$RAW" | tail -40
rm -f "$RAW"
