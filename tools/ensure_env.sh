#!/usr/bin/env bash
# Python 実行環境を保証する（無ければ入れる・あれば即返る）。
#
# ★なぜ要るか（実際に 2 回踏んだ）
#   bot のプロセスやコンテナを再起動すると **`~/.local` がまるごと消える**環境がある。
#   ベースイメージ側（例: /opt/conda の torch・sklearn・pandas）は生き残るが、
#   `pip install --user` で入れたもの（pytorch_lightning / timm / omegaconf / rich 等）が全滅する。
#   その状態で長時間ジョブを投げると **import で即死**し、
#   「投げたつもりで 1 秒で死んでいた」ことに気づくまで時間を溶かす。
#
#   `setsid` はプロセス再起動をまたげない。だから
#   **「落ちない仕組み」ではなく「落ちても自分で直す仕組み」**にする。
#
# 使い方:
#   source tools/ensure_env.sh      # run_*.sh の先頭で呼ぶ（これが本命）
#   tools/ensure_env.sh             # 単体でも動く
#   tools/ensure_env.sh --check     # 入れずに確認だけ（exit 1 なら不足あり）
#
# 設計:
#   - **全部入っていれば pip を一度も叩かない**（import チェックだけ ≒ 1 秒）
#   - 足りないものだけ入れる。ネットワークが無ければ諦めて exit 1（黙って進まない）
#   - `~/.local/bin` を PATH に足す（kaggle / jupytext が入るのはここ）

set -uo pipefail

# import 名:pip 名。コンペの依存に合わせて編集する（reference/ のスタックを既定にしてある）
_ENSURE_ENV_PKGS=(
  "pytorch_lightning:pytorch_lightning"
  "timm:timm"
  "omegaconf:omegaconf"
  "rich:rich"                 # PL の RichProgressBar が要求する
  "albumentations:albumentations"
  "sklearn:scikit-learn"
  "pandas:pandas"
  "numpy:numpy"
  "scipy:scipy"
  "torch:torch"               # 入れ直しは重いので通常は /opt/conda 側が生きている前提
)

export PATH="$HOME/.local/bin:$PATH"

_ensure_env_missing() {
  local miss=() imp pip
  for spec in "${_ENSURE_ENV_PKGS[@]}"; do
    imp="${spec%%:*}"; pip="${spec##*:}"
    python3 -c "import $imp" >/dev/null 2>&1 || miss+=("$pip")
  done
  printf '%s\n' "${miss[@]:-}"
}

_ensure_env_main() {
  local miss
  mapfile -t miss < <(_ensure_env_missing)
  # 空行だけの配列を除去
  local real=()
  for m in "${miss[@]}"; do [ -n "$m" ] && real+=("$m"); done

  if [ "${1:-}" = "--check" ]; then
    if [ ${#real[@]} -eq 0 ]; then echo "env OK"; return 0; fi
    echo "不足: ${real[*]}" >&2; return 1
  fi

  if [ ${#real[@]} -eq 0 ]; then
    return 0                                    # 何もしない（速い）
  fi

  echo "[ensure_env] 不足を検出: ${real[*]} → pip install --user" >&2
  if ! pip install --user -q "${real[@]}" >&2; then
    echo "[ensure_env] !! インストールに失敗した（ネットワーク？）。処理を中止する。" >&2
    return 1
  fi
  mapfile -t miss < <(_ensure_env_missing)
  real=(); for m in "${miss[@]}"; do [ -n "$m" ] && real+=("$m"); done
  if [ ${#real[@]} -ne 0 ]; then
    # まだ足りない = **dist-info だけ残って中身が壊れている**ケース。
    # 通常の pip は「入っている」と判断して何もしないので、ここだけ強制で入れ直す。
    echo "[ensure_env] まだ足りない: ${real[*]} → --force-reinstall で再試行" >&2
    pip install --user -q --force-reinstall --no-deps "${real[@]}" >&2 || true
    mapfile -t miss < <(_ensure_env_missing)
    real=(); for m in "${miss[@]}"; do [ -n "$m" ] && real+=("$m"); done
    if [ ${#real[@]} -ne 0 ]; then
      echo "[ensure_env] !! 復旧できなかった: ${real[*]}" >&2
      return 1
    fi
  fi
  echo "[ensure_env] 復旧した" >&2
  return 0
}

# source されたとき、呼び出し元の $1 を拾ってしまうと事故る（例: run.sh train → "train" が渡る）。
# source なら引数なし、直接実行なら引数を渡す、と明示的に分ける。
if [ "${BASH_SOURCE[0]}" != "${0}" ]; then
    _ensure_env_main            # source された
else
    _ensure_env_main "${1:-}"   # 直接実行された
fi
