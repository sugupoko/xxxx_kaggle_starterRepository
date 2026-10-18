#!/usr/bin/env bash
# xangi 本体の supervisor（落ちたら起こし直す常駐）。
#
# なぜ要るのか:
#   `xangi-cmd system_restart` は自プロセスへ SIGTERM を送るだけで、復活は
#   pm2 / Docker の restart policy 任せ（xangi の `src/cli/system-cmd.ts`）。だがコンテナの
#   PID 1 が素の bash で、xangi が `npm start` の子として手動起動されているだけだと、
#   **落ちたら誰も起こさない**。実際 2026-08-06 に自己再起動で約1分ダウンさせた。
#   その後「再起動が要る修正」を入れても人間が手で立て直すまで反映できず、
#   node-cron の修正が 2 日間死蔵された（XANGI_CRON_SPEC.md §10.2.3）。
#
# これを PID 1 直下に常駐させると:
#   - xangi が落ちても数秒で復活する
#   - `system_restart` が「片道切符」でなくなる
#   pm2 / systemd / Docker の restart policy が使える環境なら、そちらを使えばこれは要らない。
#
# 使い方:
#   setsid nohup tools/xangi/xangi_supervisor.sh >/dev/null 2>&1 </dev/null &
#   tools/xangi/xangi_supervisor.sh --stop     # supervisor を止める（xangi は残す）
#
# 環境変数: XANGI_ROOT（必須。xangi を clone したディレクトリ）
#           RESTART_DELAY(秒/既定 3) BOOT_DELAY(初回の kill までの待ち/既定 0)
#   tools/xangi/xangi.env があれば読む（xangi.env.example）。
#
# ロック・PID・停止フラグ・ログは **$XANGI_ROOT/logs/** に置く（リポジトリ側ではない）。
# 2 体の bot が同じリポジトリを別コンテナから共有していても、xangi の実体は bot ごとに別なので、
# supervisor の排他も bot（= XANGI_ROOT）単位で取る必要がある。

set -u

XANGI_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tools/xangi/_lib.sh
source "$XANGI_LIB_DIR/_lib.sh"
xangi_load_env
xangi_require XANGI_ROOT

RESTART_DELAY="${RESTART_DELAY:-3}"
BOOT_DELAY="${BOOT_DELAY:-0}"

RUN_DIR="$XANGI_ROOT/logs"
LOCK="$RUN_DIR/xangi-supervisor.lock"
PIDFILE="$RUN_DIR/xangi-supervisor.pid"
STOP="$RUN_DIR/xangi-supervisor.stop"
LOG="$RUN_DIR/xangi-supervisor.log"

mkdir -p "$RUN_DIR"
log() { printf '%s | %s\n' "$(date -u '+%Y-%m-%d %H:%M:%SZ')" "$*" >>"$LOG"; }

# この XANGI_ROOT で動いている xangi のプロセスだけを列挙する。
# `pkill -f` は使わない（AGENTS.md ルール 8: 自分のシェルにもマッチして自殺する / 同じコンテナの
# 別の xangi まで巻き込む）。cwd が XANGI_ROOT のものだけに絞り、自分自身は除外する。
xangi_pids() {
  local pattern="$1" p cwd root
  root="$(cd "$XANGI_ROOT" && pwd -P)"
  for p in $(pgrep -f "$pattern" 2>/dev/null); do
    [ "$p" = "$$" ] && continue
    cwd="$(readlink "/proc/$p/cwd" 2>/dev/null)" || continue   # 読む前に消えたプロセス
    [ "$cwd" = "$root" ] && printf '%s\n' "$p"
  done
}

if [ "${1:-}" = "--stop" ]; then
  : >"$STOP"
  pid="$(cat "$PIDFILE" 2>/dev/null)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid"
    echo "supervisor (pid=$pid) に停止を指示した（xangi 本体は動いたまま。xangi が終了しても再起動しない）"
  else
    echo "supervisor は動いていない（$PIDFILE に生きた PID が無い）。停止フラグだけ置いた"
  fi
  exit 0
fi

# 多重起動防止。既に居るなら何もしない
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "already running"
  exit 0
fi
rm -f "$STOP"
printf '%s\n' "$$" >"$PIDFILE"

log "supervisor start (pid=$$ ppid=$PPID dir=$XANGI_ROOT boot_delay=${BOOT_DELAY}s)"

# 起動報告が Discord に届く猶予をとってから、古い xangi を落とす。
# （この待ちが無いと、supervisor を仕込んだターンの応答ごと切れる）
[ "$BOOT_DELAY" -gt 0 ] && sleep "$BOOT_DELAY"

# 旧プロセスの掃除（この XANGI_ROOT のものだけ）
old="$(xangi_pids 'dist/index\.js')"
if [ -n "$old" ]; then
  log "既存の xangi を停止する: $(echo $old)"
  # shellcheck disable=SC2086
  kill -TERM $old 2>/dev/null
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    [ -z "$(xangi_pids 'dist/index\.js')" ] && break
    sleep 1
  done
  old="$(xangi_pids 'dist/index\.js')"
  # shellcheck disable=SC2086
  [ -n "$old" ] && { log "TERM で止まらないので KILL: $(echo $old)"; kill -9 $old 2>/dev/null; }
fi
old="$(xangi_pids 'npm start')"
# shellcheck disable=SC2086
[ -n "$old" ] && kill -TERM $old 2>/dev/null
# cwd が違う xangi は止めない（別の bot かもしれない）。ただし同じトークンの二重起動だと
# 1 通に 2 回応答するので、残っていることだけはログに出す
others="$(pgrep -f 'dist/index\.js' 2>/dev/null | grep -vx "$$")"
[ -n "$others" ] && log "注意: cwd が $XANGI_ROOT 以外の dist/index.js が動いている（止めていない）: $(echo $others)"

trap 'log "supervisor stop (signal)"; rm -f "$PIDFILE"; exit 0' TERM INT

cd "$XANGI_ROOT" || { log "cd 失敗: $XANGI_ROOT"; exit 1; }

while [ ! -f "$STOP" ]; do
  log "xangi を起動する"
  node --env-file=.env dist/index.js >>"$RUN_DIR/xangi-restart.log" 2>&1
  log "xangi が終了した (rc=$?)。${RESTART_DELAY}s 後に再起動する"
  sleep "$RESTART_DELAY"
done

rm -f "$PIDFILE"
log "supervisor stop (--stop)"
