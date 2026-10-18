#!/usr/bin/env bash
# Kaggle Code Competition へ実際に提出し、自分の提出の採点確定まで見張る。
# 「確認してから提出」フローの後半（前半は tools/kaggle_submit_watch.sh）。
#
#   🔴 人間の OK が出てから実行する。OK 無しに走らせない。
#   🔴 提出枠を 1 つ消費する。大会の日次上限は API から取得できないので残り枠を推測しない。
#   🔴 提出は冪等ではない。このスクリプトが失敗しても**再実行する前に**
#      `kaggle competitions submissions <comp>` で入っていないことを確認する（AGENTS.md ルール 7）。
#
# 使い方:
#   bash tools/kaggle_submit_now.sh <username/kernel-slug> <competition-slug> "<message>" <kernel-version>
#
# 第 4 引数 `<kernel-version>` は必須。
#   Code Competition の CLI 提出は `-f`（出力ファイル名）と `-v`（kernel の版番号）の**両方**が要る。
#   片方だけだと
#     "Code competition submissions require both the output file name and the version number"
#   で失敗する。
#   版番号は `kaggle kernels push` の出力 "Kernel version N successfully pushed." が唯一の一次情報
#   （API・`kernels list`・`kernels status` のどれにも版番号は出てこない）。push 時に控えること。
#
# 環境変数（すべて任意）:
#   NOTIFY_CHANNEL / XANGI_CMD   … 両方あれば xangi でチャットへ通知（tools/notify.sh・tools/xangi/README.md）
#   KAGGLE_CONFIG_DIR            … kaggle.json の置き場が HOME の外にある環境で指定
#   KAGGLE_EXTRA_PATH            … kaggle CLI が PATH に無い環境で、その bin ディレクトリ
#   KAGGLE_EXTRA_PYTHONPATH      … kaggle パッケージの site-packages が user-site から外れる環境で指定
#   POLL_SEC / MAX_ITER / WORK_DIR / SUBMIT_FILE（既定 submission.csv）
#
# 詳細: tools/kaggle_code_competition_submission.md
set -uo pipefail

KERNEL="${1:?usage: $0 <username/kernel-slug> <competition-slug> <message> <kernel-version>}"
COMP="${2:?competition slug required}"
MESSAGE="${3:?submission message required}"
VERSION="${4:?kernel version required (push ログの \"Kernel version N successfully pushed\" の N)}"

POLL_SEC="${POLL_SEC:-120}"
MAX_ITER="${MAX_ITER:-360}"
SUBMIT_FILE="${SUBMIT_FILE:-submission.csv}"

# 切り離して走らせると PATH / HOME がずれて `kaggle: command not found` で即死することがある（実際に踏んだ）。
[ -n "${KAGGLE_EXTRA_PATH:-}" ] && export PATH="$KAGGLE_EXTRA_PATH:$PATH"
[ -n "${KAGGLE_EXTRA_PYTHONPATH:-}" ] && export PYTHONPATH="$KAGGLE_EXTRA_PYTHONPATH:${PYTHONPATH:-}"
command -v kaggle >/dev/null || { echo "kaggle CLI が見つからない（KAGGLE_EXTRA_PATH を確認）" >&2; exit 2; }

SLUG_SAFE="$(printf '%s' "$KERNEL" | tr '/' '_')"
SOURCE_ID="ksub_$SLUG_SAFE"
WORK="${WORK_DIR:-/tmp/kaggle_submit_watch/$SLUG_SAFE}"
LOG="$WORK/submit.log"
EXIT_FILE="$WORK/submit.exit"
NOTIFIED="$WORK/submit_notified"
mkdir -p "$WORK"

# shellcheck source=tools/notify.sh
source "$(dirname "${BASH_SOURCE[0]}")/notify.sh"

log() { printf '[%s] %s\n' "$(date -Iseconds)" "$*" >> "$LOG"; }
trap 'printf "%s\n" "$?" > "$EXIT_FILE"' EXIT

notify() {
  [ -e "$NOTIFIED" ] && return 0
  : > "$NOTIFIED"
  notify_send "$SOURCE_ID" "$1" "$2

kernel: $KERNEL / competition: $COMP
ログ: $LOG

判定は**結果を見る前に固定した基準**（PREREG の判定帯）にそのまま当てること。
数値を見てから基準を作り直さない。確定したら日報・submit/SUBMISSIONS.md を更新する。"
}

# ── 提出前スナップショット（自分の提出を後から特定するため）──────────────
BEFORE="$(kaggle competitions submissions "$COMP" 2>&1 | awk 'NR>2 {print $1}' | head -1)"
log "submit START kernel=$KERNEL version=$VERSION before_top_ref=$BEFORE"

kaggle competitions submit "$COMP" -k "$KERNEL" -f "$SUBMIT_FILE" -v "$VERSION" \
  -m "$MESSAGE" >> "$LOG" 2>&1
rc=$?
if [ "$rc" -ne 0 ]; then
  log "submit FAILED rc=$rc"
  # CLI がエラーを返しても API 側では提出が作られていることがある（400 を返しつつ作成した実例あり）
  notify "🔴 **提出コマンドが失敗した**（rc=$rc）" "$(tail -20 "$LOG")

🔴 **再実行しない。** 先に \`kaggle competitions submissions $COMP\` で入っていないことを確認する。"
  exit "$rc"
fi
log "submit accepted"

# ── 採点確定まで見張る ───────────────────────────────────────────────────
# 🔴 事故 1: 旧実装は `kaggle competitions submissions` の**表**を
#    awk で切って `$NF` を score にしていた。**表には status 列と score 列しか出ず、
#    採点不能だと score 列が空になるので `$NF` が `SubmissionStatus.COMPLETE` を掴む**。
#    実際に「採点確定: Public LB = SubmissionStatus.COMPLETE」という**誤報**を出した。
#    `status` は失敗でも `COMPLETE` を返すので、**status では成否を判定できない**。
#    ここでは生フィールド `public_score` / `error_description` / `total_bytes` を直読みする。
# 🔴 事故 2: 旧実装は `competition_submissions(comp)[0]` = **最新の提出**を見ていた。
#    2 本を続けて出すと、**先に出した側の watcher が後の提出のスコアを自分のものとして報告する**。
#    実際に先の提出の watcher が後の提出のスコアを掴み、別モデルの LB として誤報した。
#    `BEFORE` との比較だけでは「自分より後の提出」を除外できない。
#    → **自分の提出 ref を description 一致で 1 回だけ特定して固定し、以後その ref だけを見る。**
resolve_ref() {
  MESSAGE="$MESSAGE" BEFORE="$BEFORE" python3 - "$COMP" <<'PYS'
import os, sys
from kaggle.api.kaggle_api_extended import KaggleApi
a = KaggleApi(); a.authenticate()
msg = os.environ["MESSAGE"]; before = os.environ.get("BEFORE", "")
subs = a.competition_submissions(sys.argv[1])
for s in subs:                                  # 新しい順。description 完全一致を優先
    if (s.description or "") == msg:
        print(s.ref); break
else:
    for s in subs:                              # 保険: BEFORE より新しい先頭
        if str(s.ref) != before:
            print(s.ref); break
PYS
}

probe_ref() {
  python3 - "$COMP" "$1" <<'PYS'
import sys
from kaggle.api.kaggle_api_extended import KaggleApi
a = KaggleApi(); a.authenticate()
want = str(sys.argv[2])
for s in a.competition_submissions(sys.argv[1]):
    if str(s.ref) == want:
        def f(v): return "" if v is None else str(v)
        print("\t".join([f(s.ref), f(s.status), f(s.public_score), f(s.total_bytes), f(s.error_description)]))
        break
PYS
}

MY_REF=""
for ((t = 1; t <= 10; t++)); do
  MY_REF="$(resolve_ref 2>>"$LOG" | head -1)"
  [ -n "$MY_REF" ] && [ "$MY_REF" != "$BEFORE" ] && break
  MY_REF=""; sleep 10
done
if [ -z "$MY_REF" ]; then
  log "自分の提出 ref を特定できなかった"
  notify "🔴 **自分の提出 ref を特定できなかった**" "message=\`$MESSAGE\` / before_top=\`$BEFORE\`
採点は手で `competition_submissions` を読んで確認すること。"
  exit 35
fi
printf '%s\n' "$MY_REF" > "$WORK/ref"
log "自分の提出 ref を固定: $MY_REF (before_top=$BEFORE)"

for ((i = 1; i <= MAX_ITER; i++)); do
  IFS=$'\t' read -r ref status score bytes err < <(probe_ref "$MY_REF" 2>>"$LOG")
  log "[$i] ref=$ref status=$status score=${score:-<none>} bytes=${bytes:-0} err=${err:-<none>}"

  if [ "${ref:-}" = "$MY_REF" ] && ! printf '%s' "$status" | grep -q 'PENDING'; then
    # 🔴 成否は score の有無で決める。status は見ない。
    if [ -n "${err:-}" ] || [ -z "${score:-}" ]; then
      notify "🔴 **採点されなかった**（score なし）" \
             "ref=\`$ref\` / status=\`$status\` / total_bytes=\`${bytes:-0}\`
error_description: \`${err:-<none>}\`

🔴 status が COMPLETE でも**採点されていない**。帯は適用できない（LB が存在しない）。"
      exit 34
    fi
    notify "🎉 **採点確定: Public LB = \`$score\`**" \
           "ref=\`$ref\` / status=\`$status\` / total_bytes=\`$bytes\` / error_description=なし"
    exit 0
  fi
  sleep "$POLL_SEC"
done
line="ref=${ref:-} status=${status:-} score=${score:-<none>}"

log "TIMEOUT waiting for score"
notify "🟡 **提出したが 12 時間たっても採点が確定しない**" "最後の行: \`$line\`"
exit 32
