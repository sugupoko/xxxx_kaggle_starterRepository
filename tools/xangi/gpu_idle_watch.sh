#!/usr/bin/env bash
# GPU が空いたら Discord に 1 回だけ知らせる
#
# なぜ要るか
#   2026-08-09 に **2 回 GPU を長時間遊ばせた**（17:22→20:15 の 3 時間、00:59→05:58 の 5 時間）。
#   キューは `ALL DONE` で素直に止まるだけなので、**終わったことが誰にも伝わらない**。
#   日報に TODO として書いたが実装しなかったので、また踏んだ。
#
# 設計（「鳴らして人が何かできるか」に従う）
#   - GPU アイドルは**鳴らす価値がある**。人間が次の実験を指示できる＝人が動ける
#   - ただし**鳴らしすぎない**。連続 IDLE_CHECKS 回アイドルで **1 回だけ**送る。
#     学習が再開したらフラグを戻し、次のアイドルでまた 1 回送る（＝再武装）
#   - **完了ログの最後の行を添える**ので、何が終わったのかが分かる
#
# 使い方:
#   setsid nohup tools/xangi/gpu_idle_watch.sh > /dev/null 2>&1 < /dev/null &
#   停止: kill -TERM "$(cat tools/xangi/.gpu_idle_watch.pid)"
#         （pkill -f gpu_idle_watch.sh は使わない。自分のシェルにもマッチして自殺する: AGENTS.md ルール 8）
#         停止後は pgrep -af gpu_idle_watch で残存が無いことを確認する
#   🔶 PID ファイルはリポジトリ内にあるので、2 体の bot がリポジトリを共有していると相手からも見える。
#      ただし PID は起動したコンテナの中でしか意味を持たない（相手のコンテナでは kill できない）。
#
# 環境変数（tools/xangi/xangi.env があれば読む）:
#   GPU_IDLE_CHANNEL（通知先。未設定なら DISCORD_CHANNEL。どちらも無ければ起動しない）
#   XANGI_CMD（省略時 $XANGI_ROOT/bin/xangi-cmd）
#   INTERVAL(秒/既定300) IDLE_CHECKS(既定3 = 15分アイドルで鳴らす)
#   GPU_IDLE_PROC_PATTERN（学習プロセスの判定。pgrep -f のパターン/既定 'train\.py'）
#   GPU_IDLE_LOG_GLOB（「何が終わったか」を拾うログ/既定 <repo>/workspace/*/results/nohup_*.log）
#   GPU_IDLE_LOG_PATTERN（ログから拾う行/既定 '学習終了|ALL DONE|終了 \(exit'）
#   GPU_IDLE_STATE（最後に通知した時刻の記録/既定 tools/xangi/.gpu_idle_watch.state）
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"   # <repo>/tools/xangi
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO" || exit 1

XANGI_LIB_DIR="$SCRIPT_DIR"
# shellcheck source=tools/xangi/_lib.sh
source "$SCRIPT_DIR/_lib.sh"
xangi_load_env
if [ -n "${GPU_IDLE_CHANNEL:-}" ]; then
  xangi_require GPU_IDLE_CHANNEL
  CHANNEL="$GPU_IDLE_CHANNEL"
else
  [ -z "${DISCORD_CHANNEL:-}" ] && { echo "GPU_IDLE_CHANNEL か DISCORD_CHANNEL を設定してください（通知先の Discord チャンネル ID）" >&2; exit 2; }
  xangi_require DISCORD_CHANNEL
  CHANNEL="$DISCORD_CHANNEL"
fi
XCMD="$(xangi_cmd_path)" || exit 2

INTERVAL="${INTERVAL:-300}"                        # 5 分ごとに見る
IDLE_CHECKS="${IDLE_CHECKS:-3}"                    # 15 分アイドルで鳴らす
PROC_PATTERN="${GPU_IDLE_PROC_PATTERN:-train\.py}"
LOG_GLOB="${GPU_IDLE_LOG_GLOB:-$REPO/workspace/*/results/nohup_*.log}"
LOG_PATTERN="${GPU_IDLE_LOG_PATTERN:-学習終了|ALL DONE|終了 \(exit}"
STATE="${GPU_IDLE_STATE:-$SCRIPT_DIR/.gpu_idle_watch.state}"
PIDFILE="$SCRIPT_DIR/.gpu_idle_watch.pid"

printf '%s\n' "$$" > "$PIDFILE"
trap 'rm -f "$PIDFILE"; exit 0' TERM INT

idle=0
armed=1        # 1 = まだ鳴らしていない（鳴らしたら 0 にして、学習再開で 1 に戻す）

log() { echo "[$(date -u -Iseconds)] $*"; }

while true; do
  if pgrep -f "$PROC_PATTERN" > /dev/null; then
    idle=0
    if [ "$armed" -eq 0 ]; then
      armed=1
      log "学習を検知 → 再武装"
    fi
  else
    idle=$((idle + 1))
    if [ "$idle" -ge "$IDLE_CHECKS" ] && [ "$armed" -eq 1 ]; then
      # 直近の nohup ログから「何が終わったか」を拾う（glob は意図的にクォートしない）
      # shellcheck disable=SC2086
      last=$(ls -t $LOG_GLOB 2>/dev/null | head -1)
      tailmsg=""
      if [ -n "$last" ]; then
        tailmsg=$(grep -E "$LOG_PATTERN" "$last" 2>/dev/null | tail -3 | sed 's/^/    /')
        tailmsg="直近のログ \`$(basename "$last")\`:"$'\n'"\`\`\`"$'\n'"$tailmsg"$'\n'"\`\`\`"
      fi
      msg="🟡 **GPU が $((idle * INTERVAL / 60)) 分アイドルです**（学習プロセスなし）。次を積むか指示をください。"$'\n'"$tailmsg"
      if "$XCMD" discord_send --channel "$CHANNEL" --message "$msg" > /dev/null 2>&1; then
        log "通知を送信（idle=$idle）"
      else
        log "!! 通知の送信に失敗"
      fi
      armed=0
      echo "$(date -u -Iseconds) notified" > "$STATE"
    fi
  fi
  # バックグラウンド sleep + wait にして、TERM がすぐ効くようにする（xangi_health_daemon.sh と同じ理由）
  sleep "$INTERVAL" & wait $! || true
done
