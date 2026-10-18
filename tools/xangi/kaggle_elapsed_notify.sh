#!/usr/bin/env bash
# コア側の tools/kaggle_elapsed_time.py（提出の経過時間監視・Discord 機能なし）を常駐させ、
# その標準出力から「完了 / エラー」の行だけを xangi 経由で Discord へ流すラッパ。
#
# なぜラッパなのか:
#   以前は kaggle_elapsed_time.py 自体が xangi-cmd を叩いていたが、コア側はテンプレート化の際に
#   Discord 依存を外した（xangi はオプション）。コアを書き換えずに通知だけ足すため、stdout を読む。
#
# 使い方（リポジトリのどこからでも可。kaggle_elapsed_time.py はリポジトリ直下を cwd にして動く）:
#   setsid nohup tools/xangi/kaggle_elapsed_notify.sh <competition-slug> >/dev/null 2>&1 </dev/null &
#   停止: kill -TERM -"$(cat tools/xangi/.kaggle_elapsed_notify.pid)"
#         先頭の `-` = プロセスグループごと（setsid 起動なのでこのスクリプトの PID = PGID）。
#         PID だけに TERM を送っても、bash はフォアグラウンドのパイプライン（python）が終わるまで
#         止まらない。pkill -f は使わない（AGENTS.md ルール 8）。停止後は pgrep -af kaggle_elapsed で確認
#   手順の正本: tools/xangi/KAGGLE_ELAPSED_TIME.md
#
# 通知の契約はコア側 tools/notify.sh と同じ:
#   XANGI_CMD（または XANGI_ROOT）と NOTIFY_CHANNEL の**両方**があるときだけ送る。
#   無ければログ（tools/xangi/kaggle_elapsed_time.log）に残すだけで、監視自体は動く。
#
# 環境変数: NOTIFY_CHANNEL / XANGI_CMD / XANGI_ROOT
#           KAGGLE_CONFIG_DIR（kaggle.json が HOME の外にある環境だけ）
#           KAGGLE_SITE_PACKAGES（kaggle パッケージが user-site から外れる環境だけ）
set -uo pipefail

COMP="${1:?usage: $0 <competition-slug>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"   # <repo>/tools/xangi
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
XANGI_LIB_DIR="$SCRIPT_DIR"
# shellcheck source=tools/xangi/_lib.sh
source "$SCRIPT_DIR/_lib.sh"
xangi_load_env

LOG="$SCRIPT_DIR/kaggle_elapsed_time.log"
PIDFILE="$SCRIPT_DIR/.kaggle_elapsed_notify.pid"
LOCK="$SCRIPT_DIR/.kaggle_elapsed_notify.lock"

XCMD=""
if [ -n "${NOTIFY_CHANNEL:-}" ]; then
  xangi_require NOTIFY_CHANNEL
  if [ -n "${XANGI_CMD:-}" ] || [ -n "${XANGI_ROOT:-}" ]; then
    XCMD="$(xangi_cmd_path)" || exit 2
  fi
fi
[ -n "${KAGGLE_SITE_PACKAGES:-}" ] && export PYTHONPATH="$KAGGLE_SITE_PACKAGES:${PYTHONPATH:-}"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "already running（$PIDFILE を確認）" >&2
  exit 0
fi
printf '%s\n' "$$" >"$PIDFILE"

log() { printf '%s | %s\n' "$(date -u '+%Y-%m-%d %H:%M:%SZ')" "$*" >>"$LOG"; }

notify() {
  [ -z "$XCMD" ] && return 0
  "$XCMD" discord_send --channel "$NOTIFY_CHANNEL" --message "$1" --mention false >>"$LOG" 2>&1 \
    || log "[notify] discord_send failed"
}

cd "$REPO" || exit 1
log "start comp=$COMP notify=$([ -n "$XCMD" ] && echo on || echo off)"

# kaggle_elapsed_time.py の COMPETITION はファイル冒頭の定数。コアを書き換えずに上書きするため、
# モジュールとして import してから属性を差し替えて main() を呼ぶ（main は呼び出し時に COMPETITION を読む）。
# -u: 標準出力をバッファしない（パイプ越しだと行が溜まって通知が遅れる）
python3 -u -c '
import sys
sys.path.insert(0, "tools")
import kaggle_elapsed_time as k
k.COMPETITION = sys.argv[1]
k.main()
' "$COMP" 2>&1 | while IFS= read -r line; do
  printf '%s\n' "$line" >>"$LOG"
  case "$line" in
    *"✅ 完了"*)   notify "✅ **Kaggle 提出完了**（$COMP）
$line" ;;
    *"❌ エラー"*) notify "❌ **Kaggle 提出エラー**（$COMP）
$line" ;;
  esac
done
rc=${PIPESTATUS[0]}
log "kaggle_elapsed_time.py が終了した (rc=$rc)"
rm -f "$PIDFILE"
exit "$rc"
