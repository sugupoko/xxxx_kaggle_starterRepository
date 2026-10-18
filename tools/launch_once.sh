#!/usr/bin/env bash
# 同じスクリプトの二重起動を防いで detach 起動する（AGENTS.md ルール 15）
#
# なぜ要るか
#   2 日間で **3 回**同じ事故を起こした（学習キュー / GPU 監視 / 学習スクリプト）。
#   いずれも「もう止めた」と思い込んで再投入し、**2 本が同じ GPU と同じ出力先を奪い合った**。
#   1 回は後発が先発の結果を `rm -rf` して振り出しに戻している（実害あり）。
#
#   原因はシェルではなく**こちらの記憶違い**なので、**起動前に必ず現物を見る**形にする。
#
# 使い方:
#   tools/launch_once.sh <実行するスクリプトの絶対パス or 相対パス> [引数...]
#   既に同名スクリプトが走っていれば **起動せず exit 1**（PID を表示する）
#   どうしても 2 本目を出したいときは FORCE=1 を付ける
set -uo pipefail

TARGET="${1:-}"
[ -z "$TARGET" ] && { echo "usage: tools/launch_once.sh <script> [args...]"; exit 2; }
shift || true

ABS="$(cd "$(dirname "$TARGET")" && pwd)/$(basename "$TARGET")"
[ -x "$ABS" ] || { echo "!! 実行できない: $ABS"; exit 2; }
NAME="$(basename "$ABS")"

# 自分自身と grep を除いて、同名スクリプトの bash プロセスを探す
# launch_once.sh 自身（引数に対象名が入る）と自分の PID は除く
RUNNING=$(ps -eo pid,comm,args --no-headers \
          | awk -v n="$NAME" -v me="$$" '$2=="bash" && index($0, n) > 0 \
                && index($0, "launch_once.sh") == 0 && $1 != me {print $1}' \
          | tr '\n' ' ')

if [ -n "${RUNNING// /}" ] && [ "${FORCE:-0}" != "1" ]; then
  echo "🔴 既に走っている: $NAME (PID: $RUNNING)"
  echo "   止めるなら: kill -TERM $RUNNING   （pkill -f は自分を巻き込むので使わない・AGENTS.md ルール 8）"
  echo "   それでも 2 本目を出すなら: FORCE=1 tools/launch_once.sh $TARGET"
  exit 1
fi

cd "$(dirname "$ABS")"
setsid bash -c "exec './$NAME' $*" > /dev/null 2>&1 < /dev/null &
sleep 3
NEW=$(ps -eo pid,comm,args --no-headers \
      | awk -v n="$NAME" '$2=="bash" && index($0, n) > 0 && index($0, "launch_once.sh") == 0 {print $1}' \
      | tr '\n' ' ')
CNT=$(echo "$NEW" | wc -w)
echo "起動: $NAME (PID: $NEW)"
[ "$CNT" -eq 1 ] || echo "⚠️ 同名が $CNT 本ある。確認して！"
