#!/usr/bin/env bash
# ローカル対戦評価のエントリ（cwd 非依存・失敗しない実行ラッパ）。
#
# 使い方:
#   bash run_local.sh --policy search --opponents random,negamax --games 50
#   引数はそのまま evaluate.py に渡る（--policy / --opponents / --games / --seed / --depth / --run-name）。
#
# - cd "$(dirname "$0")" で実験フォルダに移動してから呼ぶ（repo の run.sh 規約と同じ。cwd 事故防止）
# - kaggle_environments 未導入なら requirements.txt を自動導入（"module not found" で詰まないため）
set -euo pipefail
cd "$(dirname "$0")"

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "[ERROR] python が見つかりません。Python 3.10+ を入れてください" >&2
  exit 1
fi

# 依存チェック（失敗しないための事前確認）
if ! "$PY" -c "import kaggle_environments" >/dev/null 2>&1; then
  echo "[setup] kaggle_environments 未インストール → requirements.txt を導入します"
  "$PY" -m pip install -r requirements.txt
fi

exec "$PY" evaluate.py "$@"
