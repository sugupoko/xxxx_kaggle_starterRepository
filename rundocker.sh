#!/bin/bash
set -euo pipefail

IMAGE_NAME="claude"

# 作業フォルダ：引数で渡せばそれを、無ければ「今いるフォルダ」を使う
#   ※ 相対パスのまま -v に渡すと docker が「named volume」と解釈して無言で
#     別物（空ボリューム）が起動するため、存在チェックして必ず絶対パス化する。
HOST_DIR="${1:-$PWD}"
if [ ! -d "${HOST_DIR}" ]; then
  echo "[ERROR] 作業フォルダが見つかりません: ${HOST_DIR}" >&2
  exit 1
fi
HOST_DIR="$(cd "${HOST_DIR}" && pwd)"

CONTAINER_HOME="/home/user"   # Dockerfile の USERNAME に合わせる

# ── Claude：認証＆設定は共通フォルダをそのままマウント（ネイティブ＝更新も安定）──
#   ・~/.claude-docker を /home/user/.claude にマウントし、CLAUDE_CONFIG_DIR もそこに。
#   ・認証(.credentials.json)はこの共通実体を直接読み書き → トークン更新も書き戻る。
SHARED_CLAUDE="${SHARED_CLAUDE:-$HOME/.claude-docker}"
CLAUDE_CFG="${CONTAINER_HOME}/.claude"

CLAUDE_OPTS=(-e CLAUDE_CONFIG_DIR="${CLAUDE_CFG}")
if [ -n "${SHARED_CLAUDE}" ]; then
  mkdir -p "${SHARED_CLAUDE}"
  CLAUDE_OPTS+=(-v "${SHARED_CLAUDE}:${CLAUDE_CFG}")
fi

# ── 会話ログをフォルダごとに分ける仕掛け ──────────────────────────────────────
#   Claude は「起動したディレクトリ単位」で会話履歴を保存する。そこで作業フォルダを
#   コンテナ内では一意なパス /work/<フォルダ名> として開く → フォルダごとに履歴が別。
#   （認証/設定は共通の .claude を見るので、ログだけが分かれる）
NAME="$(basename "${HOST_DIR}")"
WORKDIR_IN="/work/${NAME}"

# ── Kaggle 認証：WSL に1回置いて毎回マウント共有（存在するときだけ・読み取り専用）──
SHARED_KAGGLE="${SHARED_KAGGLE:-$HOME/.kaggle}"
KAGGLE_OPTS=()
if [ -d "${SHARED_KAGGLE}" ]; then
  KAGGLE_OPTS=(-v "${SHARED_KAGGLE}:${CONTAINER_HOME}/.kaggle:ro")
fi

# ── Hugging Face トークン：WSL 側のファイルに1回置いて、毎回 HF_TOKEN として渡す ──
#   事前準備（必ず「ホスト側」で1回だけ実行する。コンテナ内で実行すると ~ が
#   リポジトリ直下＝作業フォルダになり、トークンが repo に実体化してしまう）:
#     read -rs TOKEN && printf '%s' "$TOKEN" > ~/.hf_token && unset TOKEN && chmod 600 ~/.hf_token
#   （read -s なら生トークンがシェル履歴に残らない。エディタで直接作成してもよい。
#     `echo 'hf_xxx' > ~/.hf_token` のような直書きは履歴に残るので禁止）
#   huggingface_hub / transformers / datasets は HF_TOKEN を自動で認証に使う。
HF_TOKEN_FILE="${HF_TOKEN_FILE:-$HOME/.hf_token}"
HF_OPTS=()
if [ -f "${HF_TOKEN_FILE}" ]; then
  HF_OPTS=(-e "HF_TOKEN=$(tr -d '[:space:]' < "${HF_TOKEN_FILE}")")
fi

# ── kaggle CLI：フォルダごとにインストール（~/.local に入る）──────────────────
#   KAGGLE_INSTALL=skip   : 未導入なら最新を入れる／導入済みならスキップ（既定・速い）
#   KAGGLE_INSTALL=always : 毎回 pip install -U で最新へ更新（要ネット・数秒）
#   KAGGLE_INSTALL=no     : インストールしない
KAGGLE_INSTALL="${KAGGLE_INSTALL:-skip}"
case "${KAGGLE_INSTALL}" in
  always) START_CMD="pip install -U kaggle; exec bash" ;;
  no)     START_CMD="exec bash" ;;
  *)      START_CMD="python -c 'import kaggle' 2>/dev/null || pip install -U kaggle; exec bash" ;;
esac

# ── GPU：nvidia-smi がある時だけ --gpus all を付ける（GPU 無し環境でも起動できる）──
GPU_OPTS=()
if command -v nvidia-smi >/dev/null 2>&1; then
  GPU_OPTS+=(--gpus all)
else
  echo "[info] nvidia-smi が見つからないため GPU 無しで起動します（CPU のみ）。" >&2
fi

# ── GUI（X11 / WSLg）：実体が在る時だけマウント（非WSL/Mac では自動スキップ）──
#   ※ -v は存在しないホストパスを空ディレクトリで自動生成してしまうため、
#     先に存在確認してから足す（配布先のゴミ生成を防ぐ）。
GUI_OPTS=()
[ -d /tmp/.X11-unix ] && GUI_OPTS+=(-v /tmp/.X11-unix:/tmp/.X11-unix)
[ -d /mnt/wslg ]      && GUI_OPTS+=(-v /mnt/wslg:/mnt/wslg)
for v in DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR PULSE_SERVER; do
  [ -n "${!v:-}" ] && GUI_OPTS+=(-e "${v}=${!v}")
done

# ── 追加ドライブのマウント ───────────────────────────────────────────────────
#   EXTRA_MOUNTS が指定されればそれを、無ければ存在する /mnt/<1文字>（WSLの
#   ドライブ: /mnt/c, /mnt/d ...）を自動でマウントする。ホスト固有のドライブ名
#   をスクリプトに直書きしない＝そのまま配布できる。
#     例) EXTRA_MOUNTS="/data /mnt/d" bash rundocker.sh
DRIVE_OPTS=()
if [ -n "${EXTRA_MOUNTS:-}" ]; then
  for p in ${EXTRA_MOUNTS}; do
    [ -e "$p" ] && DRIVE_OPTS+=(-v "${p}:${p}")
  done
else
  for d in /mnt/?; do
    [ -d "$d" ] && DRIVE_OPTS+=(-v "${d}:${d}")
  done
fi

# --ipc=host はホストの /dev/shm をそのまま共有するため --shm-size は不要（指定しても無効）
docker run --rm -it \
  "${GPU_OPTS[@]}" \
  -e LANG=ja_JP.UTF-8 -e LC_ALL=ja_JP.UTF-8 \
  -e HOME="${CONTAINER_HOME}" \
  "${GUI_OPTS[@]}" \
  "${DRIVE_OPTS[@]}" \
  --ipc=host \
  -v "${HOST_DIR}:${CONTAINER_HOME}" \
  -v "${HOST_DIR}:${WORKDIR_IN}" \
  "${CLAUDE_OPTS[@]}" \
  "${KAGGLE_OPTS[@]}" \
  --workdir "${WORKDIR_IN}" \
  "${IMAGE_NAME}" \
  bash -lc "${START_CMD}"
