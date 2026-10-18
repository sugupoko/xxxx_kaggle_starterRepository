#!/usr/bin/env bash
# RunPod 共有 SSH 鍵の setup/clean を直列化する唯一の入口。README.md §11。
#
# 防ぎたい事故: 別のランチャが起動時に clean+setup を実行し、**稼働中 pod の鍵を差し替えて落とす**
#   （学習結果とは無関係の orchestration failure。並列 pod 運用で実際に起きた）。
#
# 保証:
#   ① setup/clean は flock 下でのみ実行。rp_ssh.sh が lock 未保持なら自分でここへ exec し直す。
#   ② in-flight（稼働中として mark された pod）が 1 台でもあれば setup/clean を拒否（exit 3）。
#   ③ begin は **setup と全 tag の mark を同一 lock 内で原子的に**行う。途中で失敗したら
#      **書けた分を巻き戻して非 0 で落ちる**（set -e ＋ 明示 gate ＋ rollback）。
#   ④ mark には **owner token** を書く。end/unmark は **owner が一致する tag しか外せない**。
#      → 別 attempt の同名 tag を巻き添えで解除できない。
#
# 使い方:
#   bash tools/runpod/rp_key_guard.sh begin  --owner <token> <tag>...   # setup + mark（原子的）
#   bash tools/runpod/rp_key_guard.sh end    --owner <token> <tag>...   # unmark。0 台になったら clean
#   bash tools/runpod/rp_key_guard.sh unmark --owner <token> <tag>...   # unmark のみ（clean しない）
#   bash tools/runpod/rp_key_guard.sh force-unmark <tag>...             # 死んだプロセスの mark を人が手で剥がす
#   bash tools/runpod/rp_key_guard.sh status                            # in-flight 一覧
#   （setup / clean は rp_ssh.sh から exec されて来る経路）
#
# 状態ファイル（tools/runpod/.gitignore で除外済み）: .rp_key.lock / .rp_inflight/
# 依存: flock（util-linux）
set -euo pipefail
SELF="$(readlink -f "$0")"; HERE="$(dirname "$SELF")"     # symlink 経由でも lock/registry は同一実体
LOCK="$HERE/.rp_key.lock"; INFLIGHT="$HERE/.rp_inflight"
command -v flock >/dev/null || { echo "[guard] 🔴 flock が無い（util-linux）。排他できないので何もしない"; exit 4; }
mkdir -p "$INFLIGHT"
ACTION="${1:-status}"
[ $# -gt 0 ] && shift
VIA=""; OWNER=""; TAGS=()
while [ $# -gt 0 ]; do case "$1" in
  --via)   VIA="${2:?--via には値が要る}";   shift 2;;
  --owner) OWNER="${2:?--owner には値が要る}"; shift 2;;
  *)       TAGS+=("$1"); shift;;
esac; done
RP_SSH="${VIA:-${RP_SSH:-$HERE/rp_ssh.sh}}"

n_inflight(){ find "$INFLIGHT" -maxdepth 1 -type f -printf . | wc -c; }
list_inflight(){ find "$INFLIGHT" -maxdepth 1 -type f -printf '    %f' -exec sed -n 's/^owner=/ (owner=/p' {} \; | sed 's/$/)/'; }
owner_of(){ [ -f "$INFLIGHT/$1" ] || return 0; sed -n 's/^owner=//p' "$INFLIGHT/$1"; }
run_key(){ RP_KEY_LOCK_HELD=1 bash "$RP_SSH" "$1"; }        # lock 保持中だけ実体を叩く
need_owner(){ [ -n "$OWNER" ] || { echo "[guard] 🔴 $ACTION には --owner <token> が要る"; exit 2; }; }
need_tags(){ [ ${#TAGS[@]} -gt 0 ] || { echo "[guard] 🔴 $ACTION には tag が要る"; exit 2; }; }

exec 9>"$LOCK"
flock -w 120 9 || { echo "[guard] 🔴 lock 取得に失敗（120s）。何もしない"; exit 4; }

case "$ACTION" in
  status)
    echo "[guard] in-flight $(n_inflight) 台:"; list_inflight ;;

  begin)   # ★原子: in-flight==0 → setup → 全 tag mark。どこかで失敗したら巻き戻して非 0
    need_owner; need_tags
    n=$(n_inflight)
    if [ "$n" -ne 0 ]; then echo "[guard] 🔴 拒否: in-flight が $n 台ある。setup しない"; list_inflight; exit 3; fi
    run_key setup || { echo "[guard] 🔴 setup 失敗。mark しない"; exit 5; }
    written=()
    for t in "${TAGS[@]}"; do
      if printf 'owner=%s\nsince=%s\n' "$OWNER" "$(date -u -Iseconds)" > "$INFLIGHT/$t"; then written+=("$t")
      else
        echo "[guard] 🔴 mark 書込み失敗: $t → 書けた分を巻き戻す"
        for w in "${written[@]:-}"; do [ -n "$w" ] && rm -f "$INFLIGHT/$w"; done
        run_key clean || echo "[guard] ⚠️ 巻き戻しの clean も失敗。鍵が残っている可能性あり"
        exit 6
      fi
    done
    echo "[guard] ✅ setup 済 + mark ${TAGS[*]}（owner=$OWNER・計 $(n_inflight)）" ;;

  end)     # ★owner 一致 tag だけ解除。全部外れて in-flight が 0 になった時だけ clean
    need_owner; need_tags
    skipped=0
    for t in "${TAGS[@]}"; do
      o="$(owner_of "$t")"
      if [ -z "$o" ]; then echo "[guard] $t は未 mark（何もしない）"
      elif [ "$o" != "$OWNER" ]; then echo "[guard] ⚠️ $t は別 attempt の所有（owner=$o）。解除しない"; skipped=$((skipped+1))
      else rm -f "$INFLIGHT/$t"; fi
    done
    n=$(n_inflight)
    if [ "$n" -ne 0 ]; then echo "[guard] in-flight が $n 台残るので clean しない"; list_inflight
      [ "$skipped" -eq 0 ] || exit 8
      exit 0; fi
    run_key clean || { echo "[guard] 🔴 clean 失敗（鍵が RunPod に残っている可能性）"; exit 7; }
    echo "[guard] ✅ unmark ${TAGS[*]} + clean（in-flight 0）" ;;

  unmark)  need_owner; need_tags
    for t in "${TAGS[@]}"; do
      o="$(owner_of "$t")"
      if [ -n "$o" ] && [ "$o" != "$OWNER" ]; then echo "[guard] ⚠️ $t は別 attempt の所有（owner=$o）。解除しない"
      else rm -f "$INFLIGHT/$t"; fi
    done
    echo "[guard] unmark 完了（残 $(n_inflight)）" ;;

  force-unmark)  # 死んだプロセスの mark を人が手で剥がす用。自動経路からは呼ばない
    need_tags
    for t in "${TAGS[@]}"; do echo "[guard] ⚠️ 強制解除: $t（owner=$(owner_of "$t")）"; rm -f "$INFLIGHT/$t"; done ;;

  setup|clean)   # rp_ssh.sh から exec されて来る経路（＝直接呼び出しの受け皿）
    n=$(n_inflight)
    if [ "$n" -ne 0 ]; then echo "[guard] 🔴 拒否: in-flight が $n 台ある。$ACTION は実行しない"; list_inflight; exit 3; fi
    run_key "$ACTION" ;;

  *) echo "usage: rp_key_guard.sh {begin|end|unmark --owner <token> <tag>...|force-unmark <tag>...|setup|clean|status}"; exit 2 ;;
esac
