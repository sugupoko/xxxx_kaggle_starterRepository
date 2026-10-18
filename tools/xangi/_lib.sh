# shellcheck shell=bash
# tools/xangi/*.sh の共通処理（source して使う。単体では実行しない）。
#
#   XANGI_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "$XANGI_LIB_DIR/_lib.sh"
#   xangi_load_env                 # tools/xangi/xangi.env（または $XANGI_ENV_FILE）を読む
#   xangi_require XANGI_ROOT       # 未設定・雛形のまま（<...> / /path/to/...）なら理由を出して exit 2
#   XCMD="$(xangi_cmd_path)"       # $XANGI_CMD、無ければ $XANGI_ROOT/bin/xangi-cmd
#
# なぜ必須チェックを厳しくするか:
#   既定値に特定コンテナの絶対パスや Discord チャンネル ID を埋めていた頃、
#   別の bot のコンテナでそのまま動いて**別チャンネルへ黙って投稿する**状態になっていた。
#   既定値は持たず、足りなければ起動時に落とす（CLAUDE.md「エラーハンドリングの原則」= fail-fast）。

xangi_load_env() {
  local f="${XANGI_ENV_FILE:-$XANGI_LIB_DIR/xangi.env}"
  if [ -f "$f" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$f"
    set +a
  elif [ -n "${XANGI_ENV_FILE:-}" ]; then
    echo "XANGI_ENV_FILE=$XANGI_ENV_FILE が見つからない" >&2
    exit 2
  fi
}

xangi_require() {
  local name val
  for name in "$@"; do
    val="${!name:-}"
    case "$val" in
      "")
        echo "環境変数 $name を設定してください（tools/xangi/README.md の「環境変数」/ xangi.env.example）" >&2
        exit 2 ;;
      "<"*|/path/to/*)
        echo "環境変数 $name が雛形の値のまま（$val）。実際の値に置き換えてください" >&2
        exit 2 ;;
    esac
    export "${name?}"
  done
}

xangi_cmd_path() {
  if [ -n "${XANGI_CMD:-}" ]; then
    printf '%s\n' "$XANGI_CMD"
  else
    xangi_require XANGI_ROOT
    printf '%s\n' "$XANGI_ROOT/bin/xangi-cmd"
  fi
}

# JST の日時（コンテナに Asia/Tokyo の zoneinfo が無いと TZ=Asia/Tokyo は黙って UTC になる。
# 9 時間ズレて日付を取り違えるので、必ず UTC から +9h で出す）
xangi_jst() {
  date -u -d '+9 hours' "${1:-+%Y-%m-%d %H:%M:%S JST}"
}
