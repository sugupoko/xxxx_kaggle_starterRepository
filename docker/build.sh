#!/usr/bin/env bash
#==============================================================================#
# build.sh — 配布用 Docker イメージ "claude" をビルドする（初学者向け）
#
# これは何?
#   docker/Dockerfile から、学習〜提出まで動く「閉じた環境」のイメージを作る。
#   一度ビルドすれば、あとは rundocker.sh で起動するだけ。
#
# 使い方:
#   bash docker/build.sh                 # イメージ名 claude でビルド（標準）
#   IMAGE_NAME=myimg bash docker/build.sh  # 別名にしたいとき
#   NO_CACHE=1 bash docker/build.sh      # キャッシュを使わず作り直すとき
#
# ビルド後:
#   bash rundocker.sh                    # リポジトリ直下でコンテナ起動
#==============================================================================#
set -euo pipefail

# --- このスクリプトの場所（= docker/）。どこから呼んでも動くようにする ---
HERE="$(cd "$(dirname "$0")" && pwd)"

# --- 設定（環境変数で上書き可） ---
IMAGE_NAME="${IMAGE_NAME:-claude}"

# --- docker が無ければ親切に案内して終了 ---
if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] docker コマンドが見つかりません。" >&2
  echo "        Docker Desktop（Win/Mac）または Docker Engine（Linux）を入れてください。" >&2
  exit 1
fi

# --- ホストの UID/GID を引き継ぐ ---------------------------------------------
#   rundocker.sh は作業フォルダをコンテナの /home/user にマウントする。
#   コンテナ内ユーザーの UID/GID をホストと一致させておくと、
#   生成ファイルの所有者がホスト側ユーザーになり「root が作ったファイルを
#   消せない」事故を防げる。
#   （Docker Desktop[Win/Mac] では無視されるが、Linux ホストで効く。害は無い）
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

# --- キャッシュ無効化オプション ---
CACHE_OPTS=()
if [ -n "${NO_CACHE:-}" ]; then
  CACHE_OPTS+=(--no-cache)
fi

echo "=================================================="
echo " image   : ${IMAGE_NAME}"
echo " context : ${HERE}"
echo " UID:GID : ${HOST_UID}:${HOST_GID}"
[ -n "${NO_CACHE:-}" ] && echo " cache   : disabled (--no-cache)"
echo "=================================================="

docker build \
  -t "${IMAGE_NAME}" \
  -f "${HERE}/Dockerfile" \
  --build-arg UID="${HOST_UID}" \
  --build-arg GID="${HOST_GID}" \
  "${CACHE_OPTS[@]}" \
  "${HERE}"

echo
echo "[OK] build finished: ${IMAGE_NAME}"
echo "次:  リポジトリ直下で  bash rundocker.sh  と打つとコンテナに入れます。"
