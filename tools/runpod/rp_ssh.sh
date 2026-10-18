#!/usr/bin/env bash
# RunPod 一時SSH鍵ワークフロー（生成→登録→利用→破棄）。README.md §11。
#
# 背景: WSL などで ~/.ssh が 9p/drvfs マウントだと chmod が効かず 777 のまま →
#   OpenSSH が "UNPROTECTED PRIVATE KEY" で鍵を拒否する。よって秘密鍵は
#   /tmp（ext4 等の通常 FS）に置き chmod 600 する。鍵は使い捨て（その都度生成し、終わったら破棄）。
#
# 使い方:
#   source .runpod.env                                   # RUNPOD_API_KEY
#   bash tools/runpod/rp_ssh.sh setup                    # 一時鍵生成 + 公開鍵をRunPodに登録(★pod作成の前に)
#   bash tools/runpod/rp_ssh.sh exec <ip> <port> 'cmd'   # 一時鍵でssh実行
#   bash tools/runpod/rp_ssh.sh put  <localfile> <ip> <port> <remotepath>  # stdin経由で投入(秘匿ファイルをargvに出さない)
#   bash tools/runpod/rp_ssh.sh scp  <localfile> <ip> <port> <remotepath>  # scp送信
#   bash tools/runpod/rp_ssh.sh get  <ip> <port> <remotepath> <localdir>   # scp回収
#   bash tools/runpod/rp_ssh.sh clean                    # /tmp鍵をrm + RunPodから登録解除
#
# ★pod作成の前に setup（RunPodは作成時にアカウントのSSH公開鍵をpodへ注入するため）。
# ★鍵の値は出力しない。fingerprintのみ表示。使い終わったら必ず clean。
# ★setup/clean は rp_key_guard.sh の flock 下でだけ実行される（稼働中 pod の鍵を差し替えない）。
#   直接呼んでも guard へ exec し直すので安全。複数 pod を並列で回すときは guard の begin/end を使う。
#
# 環境変数（任意）:
#   RUNPODCTL        runpodctl の実行ファイル（既定: PATH 上の runpodctl）
#   RP_SSH_KEY       一時秘密鍵の置き場（既定: /tmp/.rp_ephemeral_key。リポジトリ外に置くこと）
#   RP_KNOWN_HOSTS   一時 known_hosts（既定: /tmp/.rp_known_hosts）

set -euo pipefail
RPCTL="${RUNPODCTL:-runpodctl}"
KEY="${RP_SSH_KEY:-/tmp/.rp_ephemeral_key}"
KNOWN="${RP_KNOWN_HOSTS:-/tmp/.rp_known_hosts}"
COMMENT=rp-ephemeral
SSHOPT=(-i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
        -o UserKnownHostsFile="$KNOWN" -o ConnectTimeout=12)
SCPOPT=(-i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
        -o UserKnownHostsFile="$KNOWN")

usage(){ sed -n '2,26p' "$0"; }
need_args(){ [ "$1" -ge "$2" ] || { echo "[rp_ssh] 🔴 引数不足: $cmd" >&2; usage >&2; exit 2; }; }

cmd="${1:-help}"
[ $# -gt 0 ] && shift

# ★ setup/clean は必ず共有ロックを通す。lock 未保持なら guard へ exec し直す（直接呼び出しの救済）。
case "$cmd" in
  setup|clean)
    if [ -z "${RP_KEY_LOCK_HELD:-}" ]; then
      exec bash "$(cd "$(dirname "$(readlink -f "$0")")" && pwd)/rp_key_guard.sh" "$cmd" --via "$(readlink -f "$0")"
    fi ;;
esac

case "$cmd" in
  setup)
    command -v "$RPCTL" >/dev/null || { echo "[rp_ssh] 🔴 runpodctl が見つからない（RUNPODCTL を確認）" >&2; exit 2; }
    [ -f "$KEY" ] || ssh-keygen -t ed25519 -f "$KEY" -N "" -C "$COMMENT" -q
    chmod 600 "$KEY"; chmod 644 "$KEY.pub"
    "$RPCTL" ssh add-key --key-file "$KEY.pub" >/dev/null
    echo "[setup] ephemeral key ready (perms $(stat -c%a "$KEY")), registered to RunPod:"
    ssh-keygen -lf "$KEY.pub" ;;            # fingerprint のみ（鍵の値は出さない）
  exec)
    need_args $# 3
    ip=$1; port=$2; shift 2
    ssh "${SSHOPT[@]}" -p "$port" "root@$ip" "$@" ;;
  put)
    need_args $# 4
    lf=$1; ip=$2; port=$3; rp=$4
    [ -f "$lf" ] || { echo "[rp_ssh] 🔴 ローカルファイルが無い: $lf" >&2; exit 2; }
    # 中身は stdin で渡す（argv / プロセス一覧に出さない）。受け側は mode 600 で作る
    ssh "${SSHOPT[@]}" -p "$port" "root@$ip" \
      "mkdir -p \"\$(dirname '$rp')\" && (umask 077; cat > '$rp')" < "$lf"
    echo "[put] $lf -> $ip:$rp" ;;
  scp)
    need_args $# 4
    lf=$1; ip=$2; port=$3; rp=$4
    scp "${SCPOPT[@]}" -P "$port" "$lf" "root@$ip:$rp" ;;
  get)
    need_args $# 4
    ip=$1; port=$2; rp=$3; ld=$4; mkdir -p "$ld"
    scp "${SCPOPT[@]}" -P "$port" -r "root@$ip:$rp" "$ld" ;;
  clean)
    # ローカル鍵は必ず消す。RunPod 側の登録解除の失敗は握りつぶさず、警告して非 0 で返す
    rc=0
    if ! "$RPCTL" ssh remove-key --name "$COMMENT" >/dev/null; then
      echo "[clean] ⚠️ RunPod からの鍵登録解除に失敗（未登録 or API エラー）。'$RPCTL ssh list-keys' で '$COMMENT' が残っていないか確認すること" >&2
      rc=1
    fi
    rm -f "$KEY" "$KEY.pub" "$KNOWN"
    echo "[clean] ephemeral key removed locally$([ "$rc" -eq 0 ] && echo ' + deregistered from RunPod')"
    exit "$rc" ;;
  help|-h|--help) usage ;;
  *) echo "[rp_ssh] 🔴 不明なサブコマンド: $cmd" >&2; usage >&2; exit 2 ;;
esac
