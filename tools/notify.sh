# shellcheck shell=bash
# 通知の共通関数（source して使う）。xangi はオプション。
#
#   XANGI_CMD と NOTIFY_CHANNEL の両方が設定されているときだけ xangi 経由でチャットへ送る。
#   どちらかが無ければ、通知内容を stdout とログ（$LOG があれば）に出すだけ。
#   → xangi を使わない環境でも、呼び出し側のスクリプトはそのまま動く。
#   xangi の導入・設定は tools/xangi/README.md を参照。
#
# 使い方:
#   source "$(dirname "${BASH_SOURCE[0]}")/notify.sh"
#   notify_send <source-id> "<見出し>" "<本文>"
#
# source-id: xangi trigger の --source（[A-Za-z0-9_.:-]{1,64}）。64 文字を超えると
#   **提出は成功しているのに通知だけ黙って落ちる**ので、ここで切り詰める。

notify_send() {
  local source_id message
  source_id="$(printf '%s' "$1" | tr -c 'A-Za-z0-9_.:-' '_' | cut -c1-64)"
  message="$2

$3"
  if [ -n "${XANGI_CMD:-}" ] && [ -n "${NOTIFY_CHANNEL:-}" ]; then
    if [ -n "${LOG:-}" ]; then
      "$XANGI_CMD" trigger --channel "$NOTIFY_CHANNEL" --source "$source_id" \
        --message "$message" >> "$LOG" 2>&1
    else
      "$XANGI_CMD" trigger --channel "$NOTIFY_CHANNEL" --source "$source_id" \
        --message "$message"
    fi
    local rc=$?
    # 通知の失敗は握りつぶさずログに残す（提出自体の成否とは独立）
    [ "$rc" -eq 0 ] || printf '[notify] xangi trigger failed rc=%s\n' "$rc" | tee -a "${LOG:-/dev/null}" >&2
  fi
  printf '===== NOTIFY =====\n%s\n==================\n' "$message" | tee -a "${LOG:-/dev/null}"
}
