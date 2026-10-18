#!/usr/bin/env bash
# RunPod 残高・無駄消費の定点観測（cron / 定期実行用）。README.md §8。
#
# 出す情報は数行に畳む。LLM に計算させず、この出力を正本としてそのまま流す（通知に貼る等）。
#   - 残高 clientBalance / 稼働レート currentSpendPerHr
#   - 前回チェックからの増減（state に残高と時刻を持つ）
#   - ⚠️ 停止したまま残っている pod（= ディスク保管料の垂れ流し。停止しただけでは課金は止まらない）
#
# ★ `pod list` は EXITED を出さない（README §9）。無駄の検知には必ず --all を使う。
# ★ 時刻は `date -u -d '+9 hours'` で JST を明示計算する。TZ=Asia/Tokyo は使わない
#   （zoneinfo の無いコンテナでは黙って UTC のまま表示され、9 時間ズレる）。
# ★ 鍵の値は一切出力しない。RUNPOD_API_KEY は環境変数か リポジトリ直下の .runpod.env から読む。
#
# 使い方:
#   bash tools/runpod/rp_credit_watch.sh
# 環境変数（任意）:
#   RUNPODCTL      runpodctl の実行ファイル（既定: PATH 上の runpodctl。テスト時は stub を差せる）
#   RP_WARN_USD    🟡 注意の閾値（既定 20）
#   RP_CRIT_USD    🔴 警告の閾値（既定 10）
# 状態ファイル（tools/runpod/.gitignore で除外済み）: tools/runpod/.rp_credit_watch.json
set -uo pipefail
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
STATE="$HERE/.rp_credit_watch.json"
RPCTL="${RUNPODCTL:-runpodctl}"

WARN_USD="${RP_WARN_USD:-20}"    # 🟡 これを割ったら注意
CRIT_USD="${RP_CRIT_USD:-10}"    # 🔴 これを割ったら警告

command -v "$RPCTL" >/dev/null || { echo "🔴 RunPod: runpodctl が見つからない（PATH か RUNPODCTL を確認）"; exit 1; }
if [ -z "${RUNPOD_API_KEY:-}" ] && [ -f "$REPO/.runpod.env" ]; then
  # shellcheck disable=SC1091
  set -a; source "$REPO/.runpod.env" >/dev/null; set +a
fi
[ -n "${RUNPOD_API_KEY:-}" ] || { echo "🔴 RunPod: APIキー未設定（環境変数 or .runpod.env を確認）"; exit 1; }

ME="$("$RPCTL" me 2>&1)" || { echo "🔴 RunPod: 残高取得に失敗（$(printf '%s\n' "$ME" | head -1)）"; exit 1; }
# pod 一覧の失敗は「0 台」と誤認させない。PODS_ERR を立てて Python 側で 🔴 表示する
PODS_ERR=""
PODS="$("$RPCTL" pod list --all 2>&1)" || { PODS_ERR="$(printf '%s\n' "$PODS" | head -1)"; PODS='[]'; }

JST="$(date -u -d '+9 hours' '+%m/%d %H:%M')"
STATE="$STATE" JST="$JST" WARN="$WARN_USD" CRIT="$CRIT_USD" ME="$ME" PODS="$PODS" PODS_ERR="$PODS_ERR" python3 - <<'PY'
import json, os, sys, time

me = json.loads(os.environ["ME"])            # 想定外の応答なら落とす（fail-fast）
pods_err = os.environ["PODS_ERR"]
try:
    pods = json.loads(os.environ["PODS"])
except json.JSONDecodeError:
    pods_err = pods_err or "pod list の応答が JSON でない"
    pods = []
if isinstance(pods, dict):
    pods = pods.get("pods", []) or []

bal  = float(me.get("clientBalance") or 0)
rate = float(me.get("currentSpendPerHr") or 0)
now  = time.time()

# --- 前回との差分 ---
prev = {}
try:
    with open(os.environ["STATE"]) as f:
        prev = json.load(f)
except FileNotFoundError:
    pass                                       # 初回
except json.JSONDecodeError:
    print("[warn] state ファイルが壊れているので差分を出さない（次回から復帰）", file=sys.stderr)
delta_s = ""
if prev.get("balance") is not None and prev.get("ts"):
    d  = bal - float(prev["balance"])
    dt = (now - float(prev["ts"])) / 60.0
    if dt >= 1:
        delta_s = f" ｜ 前回比 {d:+.2f}$({dt:.0f}分)"

# --- 稼働 / 停止したまま残っている pod ---
run, idle = [], []
for p in pods:
    st = (p.get("desiredStatus") or p.get("status") or "?").upper()
    (run if st == "RUNNING" else idle).append(p)

flag = "🟢"
if bal < float(os.environ["CRIT"]): flag = "🔴"
elif bal < float(os.environ["WARN"]): flag = "🟡"
if idle or pods_err: flag = "🔴"

print(f'{flag} RunPod {os.environ["JST"]} JST ｜ 残高 **${bal:.2f}** ｜ 稼働 {len(run)}台 ${rate:.2f}/h{delta_s}')

if pods_err:
    print(f"⚠️ pod 一覧の取得に失敗（{pods_err}）。停止 pod の有無は未確認。コンソールで確認すること")
if idle:
    print(f"⚠️ **停止したまま残ってる pod が {len(idle)}台**（ディスク保管料が出続けます）")
    for p in idle[:5]:
        st = (p.get("desiredStatus") or p.get("status") or "?").upper()
        print(f'  - `{p.get("id")}` {p.get("name") or ""} [{st}] → `runpodctl pod delete {p.get("id")}`')
if bal < float(os.environ["CRIT"]):
    print(f'⚠️ 残高が ${os.environ["CRIT"]} を下回っています。チャージしないと Volume/pod が消えます')
elif bal < float(os.environ["WARN"]):
    print(f'残高が ${os.environ["WARN"]} 未満になりました。そろそろチャージの検討を')
if rate > 0 and bal > 0:
    h = bal / rate
    if h < 24:
        print(f"⚠️ このレートだと残り **{h:.1f}時間** で残高ゼロです")

with open(os.environ["STATE"], "w") as f:
    json.dump({"balance": bal, "ts": now, "rate": rate, "idle": len(idle)}, f)
PY
