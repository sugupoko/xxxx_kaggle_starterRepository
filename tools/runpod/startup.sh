#!/usr/bin/env bash
# RunPod pod内 起動スクリプト（汎用・移植用）。鍵は一切持たない＝git commit しても安全。
# 鍵は RunPod Secrets → pod env で {{ RUNPOD_SECRET_xxx }} 注入。詳細は README.md §5。
#
# 想定 env（必要なものだけ。無ければそのステップをスキップ）:
#   GH_TOKEN, GIT_REPO          ... private repo を clone する場合
#   KAGGLE_USERNAME, KAGGLE_KEY ... Kaggle データDL する場合
#   HF_TOKEN                    ... HuggingFace DL する場合（huggingface_hub が env から読む）
# ※ RUNPOD_API_KEY は pod 内には置かない（ローカルの runpodctl 用）。

set -euo pipefail
set +x   # ★鍵をログに出さない（コマンドエコー無効）

# ---- 1. Kaggle 認証（env があれば生成） ----
if [ -n "${KAGGLE_USERNAME:-}" ] && [ -n "${KAGGLE_KEY:-}" ]; then
  mkdir -p "$HOME/.kaggle"
  printf '{"username":"%s","key":"%s"}' "$KAGGLE_USERNAME" "$KAGGLE_KEY" > "$HOME/.kaggle/kaggle.json"
  chmod 600 "$HOME/.kaggle/kaggle.json"
  echo "[ok] ~/.kaggle/kaggle.json (600)"
fi

# ---- 2. HuggingFace cache を Network Volume に逃がす（再起動後の再DL回避） ----
export HF_HOME="${HF_HOME:-/workspace/cache/hf}"
mkdir -p "$HF_HOME"; echo "[ok] HF_HOME=$HF_HOME"

# ---- 3. 課金漏れ防止: 終了/中断時に必ず pod 停止（pod側 --stop-after と二重防御） ----
cleanup() {
  if [ -n "${RUNPOD_POD_ID:-}" ] && command -v runpodctl >/dev/null 2>&1; then
    echo "[cleanup] stopping pod $RUNPOD_POD_ID"; runpodctl stop pod "$RUNPOD_POD_ID" || true
  fi
}
trap cleanup EXIT

# ---- 4. private repo を clone/更新（HTTPS + Fine-grained PAT。SSH鍵不要） ----
CODE_DIR=""
if [ -n "${GH_TOKEN:-}" ] && [ -n "${GIT_REPO:-}" ]; then
  CODE_DIR="/workspace/$(basename "$GIT_REPO" .git)"
  if [ -d "$CODE_DIR/.git" ]; then
    git -C "$CODE_DIR" pull --ff-only || true
  else
    git clone "https://x:${GH_TOKEN}@${GIT_REPO}" "$CODE_DIR"
  fi
  git -C "$CODE_DIR" remote set-url origin "https://${GIT_REPO}" 2>/dev/null || true  # トークン除去
  echo "[ok] code at $CODE_DIR"
fi

# ---- 5. 学習本体（実タスクに差し替え） ----
# データ/ckpt は Network Volume(/workspace) に。ckpt 再開を必ず実装（中断耐性）。
echo "[run] starting training..."
# cd "$CODE_DIR/<exp_path>" && bash run.sh

echo "[done] finished; trap will stop the pod."
