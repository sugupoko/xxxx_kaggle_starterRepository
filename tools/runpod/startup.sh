#!/usr/bin/env bash
# RunPod pod内 起動スクリプト（汎用・移植用）。鍵は一切持たない＝git commit しても安全。
# 鍵は RunPod Secrets → pod env 注入（Web UI起動時のみ解決）または scp 注入。詳細は README.md §5 / §9.5。
#
# 想定 env（必要なものだけ。無ければそのステップをスキップ）:
#   GH_TOKEN, GIT_REPO          ... private repo を clone する場合
#   KAGGLE_USERNAME, KAGGLE_KEY ... Kaggle データDL する場合
#   HF_TOKEN                    ... HuggingFace DL する場合（huggingface_hub が env から読む）
# ※ RUNPOD_API_KEY は pod 内には置かない（ローカルの runpodctl 用）。

set -euo pipefail
set +x   # ★鍵をログに出さない（コマンドエコー無効）

# ---- 0. Secrets 未解決ガード（CLI/SDK 起動だと {{ RUNPOD_SECRET_x }} が解決されずリテラルのまま届く） ----
for v in GH_TOKEN GIT_REPO KAGGLE_USERNAME KAGGLE_KEY HF_TOKEN; do
  case "${!v:-}" in
    "{{ RUNPOD_SECRET_"*)
      echo "[warn] $v が未解決の Secret 参照のまま（CLI/SDK 起動では解決されない）。スキップする（README §5/§9.5）" >&2
      unset "$v"
      ;;
  esac
done

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
    echo "[cleanup] stopping pod $RUNPOD_POD_ID"
    # ★新体系 `pod stop`（旧 `stop pod` は deprecated。README §3）。失敗は握り潰さず大きく警告
    if ! runpodctl pod stop "$RUNPOD_POD_ID"; then
      {
        echo "=================================================================="
        echo "⚠️⚠️ [cleanup] pod stop 失敗！ pod が止まっていない可能性（課金継続中かも）"
        echo "    手動で確認・停止せよ:"
        echo "      runpodctl pod get $RUNPOD_POD_ID"
        echo "      runpodctl pod stop $RUNPOD_POD_ID"
        echo "=================================================================="
      } >&2
    fi
  fi
}
trap cleanup EXIT

# ---- 4. private repo を clone/更新（HTTPS + Fine-grained PAT。SSH鍵不要） ----
# ★トークンは URL に埋め込まない: (a) プロセス一覧・エラー出力に露出する
#   (b) remote URL からトークンを除去すると再起動時の pull が必ず失敗する
#   → credential helper なら argv にトークンが出ず、トークン無し URL のまま clone/pull が通る
CODE_DIR=""
if [ -n "${GH_TOKEN:-}" ] && [ -n "${GIT_REPO:-}" ]; then
  git config --global credential.helper '!f() { echo "username=x-access-token"; echo "password=${GH_TOKEN}"; }; f'
  CODE_DIR="/workspace/$(basename "$GIT_REPO" .git)"
  if [ -d "$CODE_DIR/.git" ]; then
    # ★失敗を握り潰さない（古いコードのまま無音で学習が走る事故を防ぐ）
    git -C "$CODE_DIR" pull --ff-only || { echo "[FATAL] git pull 失敗（$GIT_REPO）。中断する" >&2; exit 1; }
  else
    git clone "https://${GIT_REPO}" "$CODE_DIR" || { echo "[FATAL] git clone 失敗（GH_TOKEN/GIT_REPO を確認）" >&2; exit 1; }
  fi
  echo "[ok] code at $CODE_DIR"
fi

# ---- 5. 学習本体（実タスクに差し替え） ----
# データ/ckpt は Network Volume(/workspace) に。ckpt 再開を必ず実装（中断耐性）。
echo "[run] starting training..."
# cd "$CODE_DIR/<exp_path>" && bash run.sh

echo "[done] finished; trap will stop the pod."
