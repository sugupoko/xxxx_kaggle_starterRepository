#!/usr/bin/env bash
# ★番号の採番と整合チェック（AGENTS.md ルール 3-b）
#
#   tools/star.sh next [n]   n 個の★番号を排他ロック付きで払い出す（既定 1）
#   tools/star.sh max        現在の最大値を表示するだけ（払い出さない）
#   tools/star.sh check      日報と索引の整合を検査する（異常があれば exit 1）
#
# 採番が壊れた歴史（実際に 2 回起きた）:
#   - 旧ルールは「今日の日報だけを grep して最大値を取る」だったため、
#     日付が変わって空ファイルを作った瞬間に前日の最大値が視界から消え、
#     翌日の日報が ★6 個を前日の日報と二重に定義した。
#   - grep は read-then-write なので、同時セッションでは原理的に競り勝てない。
#   → カウンタファイルを flock で排他して払い出す方式に変更した。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REPORT_DIR="daily_reports"
# 台帳置き場（AGENTS.md §実験管理の正本）。knowledge/ 直下の wiki とは分けて置く
LEDGER_DIR="knowledge/ledgers"
COUNTER="$LEDGER_DIR/.star_counter"
LOCK="$LEDGER_DIR/.star_counter.lock"
MAP="$LEDGER_DIR/daily_reports_map.md"

# 日報全体の★最大値。参照も含めた high-water mark を取る（低く見積もらないため）
# 日報が 0 本 / ★が 0 個のときに pipefail + set -e で黙って落ちないよう、grep の rc を自分で見る
scan_max() {
  local files=() hits rc=0
  shopt -s nullglob
  files=("$REPORT_DIR"/*.md)
  shopt -u nullglob
  (( ${#files[@]} )) || return 0
  # grep は 1 件も無いと exit 1（＝正常）。2 以上（読めない等）だけを失敗として扱う
  hits="$(grep -ho '★[0-9]\+' "${files[@]}")" || rc=$?
  (( rc <= 1 )) || { echo "日報の走査に失敗 (grep rc=$rc)" >&2; exit 1; }
  [ -n "$hits" ] || return 0
  printf '%s\n' "$hits" | grep -o '[0-9]\+' | sort -n | tail -1
}

cmd_max() {
  local cur=0 scanned
  [ -s "$COUNTER" ] && cur="$(tr -dc '0-9' < "$COUNTER")"
  scanned="$(scan_max)"; scanned="${scanned:-0}"
  (( scanned > cur )) && cur="$scanned"
  echo "$cur"
}

cmd_next() {
  local n="${1:-1}"
  case "$n" in ''|*[!0-9]*) echo "usage: star.sh next [個数]" >&2; exit 2;; esac
  (( n >= 1 )) || { echo "個数は 1 以上" >&2; exit 2; }

  mkdir -p "$LEDGER_DIR"
  exec 9>"$LOCK"
  flock 9                                   # ここから他セッションは待たされる

  local cur=0 scanned
  [ -s "$COUNTER" ] && cur="$(tr -dc '0-9' < "$COUNTER")"
  scanned="$(scan_max)"; scanned="${scanned:-0}"
  # 手書きで★を足された場合の保険。カウンタは実測を下回らない
  (( scanned > cur )) && cur="$scanned"

  local start=$((cur + 1)) end=$((cur + n))
  printf '%s\n' "$end" > "$COUNTER"
  flock -u 9

  if (( n == 1 )); then echo "★${start}"; else echo "★${start}〜★${end}"; fi
}

cmd_check() {
  python3 - "$REPORT_DIR" "$MAP" "$COUNTER" <<'PY'
import glob, os, re, sys

report_dir, map_path, counter_path = sys.argv[1:4]
reports = sorted(glob.glob(os.path.join(report_dir, "*.md")))

ANY = re.compile(r"★(\d+)")
# 定義・再掲の書式。行頭（リストマーカー・見出し・太字の直後まで）に限る。
# 本文中の「（★33: 中央値 13.1mm）」のような参照を定義と誤認しないためのアンカー。
DEF = re.compile(r"^[ \t]*(?:[-*+]\s*)?(?:#{1,6}\s*)?\*{0,2}★(\d+)[.．:：]")
CHECKBOX = re.compile(r"^\s*-\s*\[[ xX]\]")  # 「次にやること」の TODO 行は定義ではない
RECAP = re.compile(r"^[ \t]*[-*+]\s")        # 「## 判断・知見」への再掲はリスト行で書く

defs, seen = {}, set()
for path in reports:
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            seen.update(int(m.group(1)) for m in ANY.finditer(line))
            if CHECKBOX.match(line):
                continue
            m = DEF.match(line)
            if m:
                defs.setdefault(int(m.group(1)), {}).setdefault(path, []).append(
                    (lineno, line.strip()[:64], bool(RECAP.match(line)))
                )

errors = warns = 0

# 1. ファイルをまたぐ二重定義 — 採番事故そのもの
for num in sorted(defs):
    if len(defs[num]) >= 2:
        errors += 1
        print(f"❌ ★{num}: {len(defs[num])} ファイルで定義されている")
        for path, occ in defs[num].items():
            lineno, text, _ = occ[0]
            print(f"     {path}:{lineno}  {text}")

# 2. 同一ファイル内の重複。リスト行は「## 判断・知見」への再掲なので数えない
for num in sorted(defs):
    if len(defs[num]) != 1:
        continue
    (path, occ), = defs[num].items()
    body = [(ln, txt) for ln, txt, recap in occ if not recap]
    if len(body) >= 2:
        warns += 1
        print(f"⚠️  ★{num}: {os.path.basename(path)} 内で {len(body)} 回定義されている（§ で区別するしかない）")
        for ln, txt in body:
            print(f"     L{ln}  {txt}")

# 3. カウンタが実測を下回っていないか
counter = 0
if os.path.exists(counter_path):
    raw = "".join(c for c in open(counter_path, encoding="utf-8").read() if c.isdigit())
    counter = int(raw) if raw else 0
observed = max(seen) if seen else 0
if counter < observed:
    errors += 1
    print(f"❌ カウンタ {counter} が日報の実測最大 ★{observed} を下回っている（次の払い出しが衝突する）")

# 4. 欠番
missing = [n for n in range(1, observed + 1) if n not in seen]
if missing:
    warns += 1
    print(f"⚠️  欠番 {len(missing)} 個: {', '.join('★%d' % n for n in missing[:20])}"
          + (" ..." if len(missing) > 20 else ""))

# 5. 索引漏れ — 運用ルール「新しい★を書いたら daily_reports_map.md に 1 行足す」の履行確認
if os.path.exists(map_path):
    text = open(map_path, encoding="utf-8").read()
    mapped = set()
    for a, b in re.findall(r"★(\d+)\s*[〜~ー−–—-]\s*★(\d+)", text):
        mapped.update(range(int(a), int(b) + 1))
    mapped.update(int(x) for x in ANY.findall(text))
    unindexed = sorted(n for n in defs if n not in mapped)
    if unindexed:
        warns += 1
        print(f"⚠️  索引漏れ {len(unindexed)} 個（{os.path.basename(map_path)} に未記載）: "
              + ", ".join("★%d" % n for n in unindexed))

print(f"\n定義 {len(defs)} 件 / 最大 ★{observed} / カウンタ {counter} — エラー {errors}・警告 {warns}")
sys.exit(1 if errors else 0)
PY
}

case "${1:-}" in
  next)  shift; cmd_next "$@" ;;
  max)   cmd_max ;;
  check) cmd_check ;;
  *) sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
