#!/usr/bin/env bash
# Kaggle Code Competition の kernel 完走を待ち、submission.csv を検証して報告する。
#
#   ★ このスクリプトは「提出しない」。「確認してから提出」フローの前半。
#     人間の OK が出てから tools/kaggle_submit_now.sh を実行する。
#
# 使い方:
#   bash tools/kaggle_submit_watch.sh <username/kernel-slug> <competition-slug> "<message>"
#   （`kaggle kernels push` の直後に、切り離して走らせる: setsid bash ... > /dev/null 2>&1 < /dev/null &）
#
# 環境変数（すべて任意）:
#   NOTIFY_CHANNEL / XANGI_CMD   … 両方あれば xangi でチャットへ通知（tools/notify.sh・tools/xangi/README.md）
#   KAGGLE_CONFIG_DIR / KAGGLE_EXTRA_PATH / KAGGLE_EXTRA_PYTHONPATH … tools/kaggle_submit_now.sh と同じ
#   EXPECTED_ROWS                … 期待行数（指定すると一致を検査する）
#   VALUE_RANGE                  … 予測値の許容範囲 "min,max"（既定 "0,1"。空文字で検査しない）
#   POLL_SEC / MAX_ITER / WORK_DIR
#
# 詳細: tools/kaggle_code_competition_submission.md
set -uo pipefail

KERNEL="${1:?usage: $0 <username/kernel-slug> <competition-slug> <message>}"
COMP="${2:?competition slug required}"
MESSAGE="${3:?submission message required}"

POLL_SEC="${POLL_SEC:-60}"
MAX_ITER="${MAX_ITER:-720}"        # 60s * 720 = 12 時間で打ち切り
export EXPECTED_ROWS="${EXPECTED_ROWS:-}"
export VALUE_RANGE="${VALUE_RANGE-0,1}"

# 切り離して走らせると PATH / HOME がずれて `kaggle: command not found` で即死することがある（実際に踏んだ）。
[ -n "${KAGGLE_EXTRA_PATH:-}" ] && export PATH="$KAGGLE_EXTRA_PATH:$PATH"
[ -n "${KAGGLE_EXTRA_PYTHONPATH:-}" ] && export PYTHONPATH="$KAGGLE_EXTRA_PYTHONPATH:${PYTHONPATH:-}"
command -v kaggle >/dev/null || { echo "kaggle CLI が見つからない（KAGGLE_EXTRA_PATH を確認）" >&2; exit 2; }

SLUG_SAFE="$(printf '%s' "$KERNEL" | tr '/' '_')"
WORK="${WORK_DIR:-/tmp/kaggle_submit_watch/$SLUG_SAFE}"
LOG="$WORK/watch.log"
EXIT_FILE="$WORK/watch.exit"
OUTDIR="$WORK/kaggle_output"
REPORT="$WORK/report.md"
NOTIFIED="$WORK/notified"          # 二重発火防止
mkdir -p "$WORK" "$OUTDIR"

# shellcheck source=tools/notify.sh
source "$(dirname "${BASH_SOURCE[0]}")/notify.sh"

log() { printf '[%s] %s\n' "$(date -Iseconds)" "$*" >> "$LOG"; }

# 成功・失敗どちらでも必ず終了状態を残す
trap 'printf "%s\n" "$?" > "$EXIT_FILE"' EXIT

notify() {
  # $1 = 見出し, $2 = 本文
  [ -e "$NOTIFIED" ] && { log "notify skipped (already notified)"; return 0; }
  : > "$NOTIFIED"
  notify_send "kwatch_$SLUG_SAFE" "$1" "$2

kernel: $KERNEL / competition: $COMP
提出メッセージ案: $MESSAGE
検証レポート: $REPORT
ログ: $LOG

【重要】このスクリプトは提出していない。人間の OK を得てから
  bash tools/kaggle_submit_now.sh '$KERNEL' '$COMP' '$MESSAGE' <kernel-version>
を実行すること（<kernel-version> は push ログの \"Kernel version N successfully pushed\" の N）。OK 無しに提出しない。"
}

log "START kernel=$KERNEL comp=$COMP"

# ── 1. kernel の完走を待つ ───────────────────────────────────────────────
for ((i = 1; i <= MAX_ITER; i++)); do
  status="$(kaggle kernels status "$KERNEL" 2>&1)"
  log "[$i] $status"

  if printf '%s' "$status" | grep -qi 'complete'; then
    log "kernel COMPLETE"
    break
  fi
  if printf '%s' "$status" | grep -qiE 'error|cancel'; then
    log "kernel FAILED"
    notify "🔴 **kernel が失敗した**（提出していない）" \
      "status: \`$status\`
Kaggle UI のログを確認してほしい。**勝手に再 push はしない。**"
    exit 30
  fi
  if [ "$i" -eq "$MAX_ITER" ]; then
    log "TIMEOUT"
    notify "🟡 **kernel が 12 時間たっても完走しない**（提出していない）" \
      "最後の status: \`$status\`"
    exit 32
  fi
  sleep "$POLL_SEC"
done

# ── 2. 出力を取得 ────────────────────────────────────────────────────────
kaggle kernels output "$KERNEL" -p "$OUTDIR" >> "$LOG" 2>&1
CSV="$OUTDIR/submission.csv"
if [ ! -f "$CSV" ]; then
  log "submission.csv not found"
  notify "🔴 **kernel は完走したが \`submission.csv\` が無い**（提出していない）" \
    "取得先: \`$OUTDIR\`"
  exit 31
fi

# ── 3. 形式検証（行数・ID 重複・数値型・NaN/Inf・値域・定数列）────────────────────────────────────────
VERDICT_FILE="$WORK/verdict.txt"
python3 - "$CSV" "$REPORT" "$VERDICT_FILE" >> "$LOG" 2>&1 <<'PY'
import os, sys
import pandas as pd, numpy as np

csv_path, report_path, verdict_path = sys.argv[1], sys.argv[2], sys.argv[3]
df = pd.read_csv(csv_path)
id_col = df.columns[0]
val = df[df.columns[1:]]
fails, lines = [], []

lines.append(f"- 行数: **{len(df)}** / 列数: {len(df.columns)}")
lines.append(f"- ID 列: `{id_col}` / ラベル列: {list(val.columns)}")

if len(df) < 1:
    fails.append("行数が 0")
expected = os.environ.get("EXPECTED_ROWS", "")
if expected and len(df) != int(expected):
    fails.append(f"行数 {len(df)} が期待値 {expected} と一致しない")
if df[id_col].duplicated().any():
    fails.append(f"ID 重複 {int(df[id_col].duplicated().sum())} 件")

nonnum = [c for c in val.columns if not np.issubdtype(val[c].dtype, np.number)]
if nonnum:
    fails.append(f"数値でない列: {nonnum}")
else:
    arr = val.to_numpy(dtype=float)
    n_nan = int(np.isnan(arr).sum()); n_inf = int(np.isinf(arr).sum())
    lines.append(f"- NaN: {n_nan} / Inf: {n_inf}")
    if n_nan or n_inf:
        fails.append(f"NaN {n_nan} / Inf {n_inf}")
    lo, hi = float(np.nanmin(arr)), float(np.nanmax(arr))
    lines.append(f"- 値域: **[{lo:.4f}, {hi:.4f}]**")
    rng = os.environ.get("VALUE_RANGE", "")
    if rng:
        vmin, vmax = (float(x) for x in rng.split(","))
        if lo < vmin or hi > vmax:
            fails.append(f"値域が [{vmin},{vmax}] を外れる: [{lo}, {hi}]")
    const = [c for c in val.columns if val[c].nunique(dropna=False) <= 1]
    if const:
        fails.append(f"定数列（重み未ロード / Dataset 未 mount の疑い）: {const}")
    lines.append("")
    lines.append("| label | mean | min | max |")
    lines.append("|---|---:|---:|---:|")
    for c in val.columns:
        lines.append(f"| {c} | {val[c].mean():.3f} | {val[c].min():.3f} | {val[c].max():.3f} |")

body = "\n".join(lines)
verdict = "PASS" if not fails else "FAIL"
with open(report_path, "w", encoding="utf-8") as f:
    f.write(f"# submission.csv 検証: {verdict}\n\n{body}\n")
    if fails:
        f.write("\n## 失格項目\n" + "\n".join(f"- 🔴 {x}" for x in fails) + "\n")
with open(verdict_path, "w", encoding="utf-8") as f:
    f.write(verdict + "\n")
print(f"validation verdict={verdict} fails={fails}")
PY

# python が落ちた場合も FAIL 扱いにする（無検証で提出へ進ませない）
VERDICT="$(cat "$VERDICT_FILE" 2>/dev/null | tr -d '[:space:]')"
[ -z "$VERDICT" ] && VERDICT="FAIL"
BODY="$(cat "$REPORT" 2>/dev/null)"
[ -z "$BODY" ] && BODY="（検証スクリプトが失敗した。$LOG を確認してほしい）"

if [ "$VERDICT" = "PASS" ]; then
  log "validation PASS"
  notify "✅ **kernel 完走・\`submission.csv\` 検証 PASS**。提出の OK をください" "$BODY"
  exit 0
else
  log "validation FAIL"
  notify "🔴 **\`submission.csv\` の検証に失格項目がある**（提出していない）" "$BODY"
  exit 33
fi
