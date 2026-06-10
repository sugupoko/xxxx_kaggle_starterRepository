#!/usr/bin/env bash
# RunPod 疎通テスト: 最安GPUで 起動→RUNNING待ち→接続情報表示。Network Volume なし（月額回避）。
# --stop-after で自動停止の保険つき。鍵は リポジトリ直下 .runpod.env から読む（RUNPOD_API_KEY）。
# 使い方:
#   bash tools/runpod/smoke_test.sh                       # 起動（★課金開始。数分で teardown すれば数円）
#   bash tools/runpod/smoke_test.sh "NVIDIA A100-SXM4-80GB"  # GPU指定
#   bash tools/runpod/smoke_test.sh teardown <POD_ID>     # 停止＋削除
set -euo pipefail; set +x
HERE="$(cd "$(dirname "$0")" && pwd)"
# .runpod.env を探す（フォルダ位置に依存しないよう上方向に探索）
ENVF=""
for d in "$HERE/../.." "$HERE/.." "$HERE" "$PWD"; do
  [ -f "$d/.runpod.env" ] && { ENVF="$d/.runpod.env"; break; }
done
[ -n "$ENVF" ] && { set -a; source "$ENVF"; set +a; }
[ -n "${RUNPOD_API_KEY:-}" ] || { echo "[FATAL] RUNPOD_API_KEY 未設定（.runpod.env に貼る）"; exit 1; }
RPCTL="${RPCTL:-runpodctl}"
# python3 優先（bare `python` が無い環境向けフォールバック）
PY="$(command -v python3 || command -v python || true)"
[ -n "$PY" ] || { echo "[FATAL] python3 が見つからない"; exit 1; }

if [ "${1:-}" = "teardown" ]; then
  PID="${2:?usage: smoke_test.sh teardown <POD_ID>}"
  echo "[stop] $PID";   $RPCTL pod stop "$PID"   || true
  echo "[delete] $PID"; $RPCTL pod delete "$PID" || true
  echo "[done] teardown 完了。残高:"; $RPCTL me -o json | grep -E 'clientBalance|currentSpendPerHr'
  exit 0
fi

GPU="${1:-NVIDIA RTX A5000}"
POD_NAME="smoke-test-$(date +%s)"   # ★一意な名前（固定名だと再実行時に既存podと衝突して誤検出する）
STOP_AT="$(date -u -d '+2 hours' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || true)"
echo "[create] name=$POD_NAME gpu='$GPU' stop-after=${STOP_AT:-none}  (★課金開始)"
# ★公式テンプレ必須（bare --image だと常駐プロセスが無く即EXITEDになる。GUIはテンプレ使用）
ARGS=(pod create --name "$POD_NAME" --gpu-id "$GPU" --cloud-type SECURE
      --template-id "${TEMPLATE_ID:-runpod-torch-v280}" --container-disk-in-gb 20)
[ -n "$STOP_AT" ] && ARGS+=(--stop-after "$STOP_AT")
# ★create 出力から pod ID を即確保（EXITED になると `pod list` に出ず「課金中なのに ID 不明」になる）
CREATE_OUT="$($RPCTL "${ARGS[@]}" 2>&1)" || { echo "$CREATE_OUT"; echo "[FATAL] pod create 失敗"; exit 1; }
echo "$CREATE_OUT"
PID="$(printf '%s\n' "$CREATE_OUT" | grep -oE '\b[a-z0-9]{13,14}\b' | head -1 || true)"

echo; echo "[wait] RUNNING までポーリング（最大3分）..."
for i in $(seq 1 18); do
  sleep 10
  if [ -z "$PID" ]; then
    PID="$($RPCTL pod list -o json 2>/dev/null | "$PY" -c '
import sys,json
for p in json.load(sys.stdin):
    if p.get("name")==sys.argv[1]: print(p.get("id")); break' "$POD_NAME" 2>/dev/null || true)"
    [ -z "$PID" ] && continue
  fi
  ST="$($RPCTL pod get "$PID" -o json 2>/dev/null | "$PY" -c 'import sys,json;print(json.load(sys.stdin).get("desiredStatus",""))' 2>/dev/null || true)"
  echo "  [$i] pod=$PID status=$ST"
  [ "$ST" = "RUNNING" ] && break
  [ "$ST" = "EXITED" ] && { echo "[warn] pod が EXITED（bare image 等が原因。README §9）。teardown して原因確認を"; break; }
done

echo; echo "=== pod 状態確認（★\`pod list\` は RUNNING しか表示しない。EXITED でも pod は残る） ==="
if [ -n "$PID" ]; then
  $RPCTL pod get "$PID" || true
else
  echo "(pod ID 取得できず) EXITED 等で list に出ない可能性あり。全状態を必ず確認すること:"
  echo "  - python3 $HERE/runpod_ops.py list   # SDK は EXITED 含む全 pod を返す"
  echo "  - RunPod コンソール（ブラウザ）の Pods 画面"
  echo "  - $RPCTL me   # spend が出ていれば pod がどこかに残っている"
fi

echo; echo "=== 接続情報（Web Terminal / Jupyter はブラウザの RunPod コンソールから） ==="
[ -n "$PID" ] && $RPCTL ssh info "$PID" 2>&1 | head -10 || echo "(pod ID 取得できず。上記の全状態確認を実施)"
echo; echo "次: ブラウザで pod に入り 'nvidia-smi' 確認 → 終わったら:"
echo "  bash tools/runpod/smoke_test.sh teardown ${PID:-<POD_ID>}"
