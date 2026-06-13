#!/usr/bin/env bash
# pod内エントリ（汎用テンプレ）: Kaggle dataset 取得 → 展開を自動検出 → 1ジョブ学習 → /workspace/out_<TAG> へ集約。
#
# レイヤの違い:
#   startup.sh = pod ブートストラップ（鍵注入・private clone・自動停止）
#   pod_run.sh = その上で動く「1ジョブ分の学習エントリ」
#
# 多pod並列では各 pod で本スクリプトを **1回だけ** デタッチ起動する（再 launch 厳禁・README §11）:
#   setsid bash pod_run.sh >/workspace/run.log 2>&1 </dev/null &
#   # 数秒後に別 ssh call で: head -1 /workspace/run.log  → '[pod] ... start' を確認
#
# 環境変数で受ける（ハードコード回避）:
#   KSLUG     必須  Kaggle dataset の <user>/<slug>（user は kaggle.json の実 username。README §9.5 罠5）
#   TAG       必須  出力識別子（/workspace/out_<TAG> に集約）
#   TRAIN_CMD 必須  学習コマンド文字列。実行時に DATA_ROOT / TAG / OUT が環境変数で渡る
#   FIND_HINT 任意  データルート検出の目印ファイル名（既定: train.csv）
#   PIP_PKGS  任意  追加 pip パッケージ（スペース区切り。既定なし）
# kaggle.json は事前に /root/.kaggle/kaggle.json へ注入済み前提（scp / startup.sh 経由）。
set -uo pipefail

: "${KSLUG:?set KSLUG=<user>/<slug>}"
: "${TAG:?set TAG=<run tag>}"
: "${TRAIN_CMD:?set TRAIN_CMD=<training command>}"
FIND_HINT="${FIND_HINT:-train.csv}"

WS=/workspace; DS="$WS/data"; OUT="$WS/out_${TAG}"
mkdir -p "$DS" "$OUT" /root/.kaggle
chmod 600 /root/.kaggle/kaggle.json 2>/dev/null || true
echo "[pod] $(date) start TAG=$TAG KSLUG=$KSLUG"

# PEP668: runpod-torch template は --break-system-packages 必須（README §9.5 罠1）
pip install -q --break-system-packages kaggle ${PIP_PKGS:-} 2>&1 | tail -1

# dataset DL（作成直後は処理待ちで 404 → リトライ。README §9.5 罠4）
dl_ok=0
for i in 1 2 3 4 5 6; do
  if python -m kaggle datasets download -d "$KSLUG" -p "$WS" --force; then dl_ok=1; break; fi
  echo "[pod] kaggle DL retry $i (dataset 処理待ちの可能性)"; sleep 20
done
[ "$dl_ok" -eq 1 ] || { echo "[pod] FATAL: kaggle download に失敗（$KSLUG）"; exit 1; }

# WS 直下の zip を DS へ展開
ZIP=$(ls "$WS"/*.zip 2>/dev/null | head -1)
[ -n "${ZIP:-}" ] && unzip -o -q "$ZIP" -d "$DS"
# Kaggle の展開挙動は一定しない（README §9.5 罠2）: 内部に二重 zip が残っていたらもう1段
for inner in "$DS"/*.zip; do
  [ -e "$inner" ] || break
  unzip -o -q "$inner" -d "$DS" && rm -f "$inner"
done
echo "[pod] data extracted: $(ls "$DS" | head) ($(du -sh "$DS" | cut -f1))"

# データルートを決め打ちせず自動検出（Kaggle が foo/ にネストしても追従。README §9.5 罠2）
HIT=$(find "$DS" -name "$FIND_HINT" | head -1)
[ -z "$HIT" ] && { echo "[pod] FATAL: 目印 '$FIND_HINT' が $DS 配下に無い"; ls -R "$DS" | head -40; exit 1; }
DATA_ROOT=$(dirname "$HIT")
echo "[pod] DATA_ROOT=$DATA_ROOT"

# 学習（TRAIN_CMD に DATA_ROOT / TAG / OUT を環境変数で渡す）
env DATA_ROOT="$DATA_ROOT" TAG="$TAG" OUT="$OUT" bash -c "$TRAIN_CMD" 2>&1 | tee "$OUT/train_${TAG}.log"

echo "[pod] $(date) DONE TAG=$TAG -> $OUT"
ls -la "$OUT"
