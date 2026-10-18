#!/usr/bin/env bash
# 監視デーモン（LLM 不使用）。2つを見張る:
#   ① 定点観測 cron の生存        → 異常時だけ通報（HEALTH_CHANNEL へ）
#   ② Claude のレート制限（使用率） → しきい値を跨いだ時だけ通報 + 日次スナップショット（USAGE_CHANNEL へ）
#
# なぜ cron ではなくデーモンなのか:
#   xangi の cron は「前回の agent 実行が終わらないと以降の発火が永久に skip される」
#   （XANGI_CRON_SPEC.md §5.2）。その cron 自身に生存監視をやらせると、
#   監視役が詰まったときに誰も気づけない。だから監視だけは LLM を通さない経路に置く。
#   仕様書 §6 の「判断が要る所だけ LLM、監視と報告は素のスクリプト」がこれ。
#
# 弱点（承知の上）:
#   nohup 常駐なので xangi の再起動で死ぬ。監視レーンの cron 冒頭と startup 型スケジュールの
#   両方から起動し直す運用とセットで使う（§4.5）。多重起動は flock で防いでいるので毎回叩いてよい。
#
# 使い方:
#   setsid nohup tools/xangi/xangi_health_daemon.sh >/tmp/xangi_health_daemon.boot.log 2>&1 </dev/null &
#   tools/xangi/xangi_health_daemon.sh --once     # 1 周だけ回して終了（動作確認用）
#   停止: kill -TERM "$(cat /tmp/xangi_health_daemon.pid)"   # pkill -f は使わない（AGENTS.md ルール 8）
#
# 環境変数（tools/xangi/xangi.env があれば読む。雛形は xangi.env.example）:
#   XANGI_ROOT(必須。xangi を clone したディレクトリ) XANGI_CMD(省略時 $XANGI_ROOT/bin/xangi-cmd)
#   HEALTH_CHANNEL(cron異常の投稿先。ENABLE_CRON_CHECK=1 なら必須)
#   USAGE_CHANNEL(レート制限の投稿先。ENABLE_USAGE=1 なら必須)
#   ENABLE_CRON_CHECK(①を有効化/既定1) ENABLE_USAGE(②を有効化/既定1)
#   HEALTH_INTERVAL(秒/既定900) HEALTH_REALERT_H(再通知間隔/既定6)
#   USAGE_DAILY_HOUR(日次スナップショットのJST時刻/既定-1=無効) USAGE_GAUGE_MIN(ゲージ通知の間隔/既定30・0で無効)
#   USAGE_BOARD(常設ボード/既定0) LANE_MIN_INTERVAL(バックストップの最短間隔秒/既定5400)
#
# 前提: ① はコア側の tools/kaggle_disc_watch.py / tools/kaggle_code_watch.py を xangi cron で回していること
#       （state は tools/.kaggle_*_watch.json）。回していないなら ENABLE_CRON_CHECK=0 にする。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # <repo>/tools/xangi
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
XANGI_LIB_DIR="$SCRIPT_DIR"
# shellcheck source=tools/xangi/_lib.sh
source "$SCRIPT_DIR/_lib.sh"
xangi_load_env
xangi_require XANGI_ROOT          # kaggle_watch_health.py も env で受け取る（export 済み）
XCMD="$(xangi_cmd_path)" || exit 2
SCHEDULES="$XANGI_ROOT/.xangi/schedules.json"
CHECK="$SCRIPT_DIR/kaggle_watch_health.py"
USAGE="$SCRIPT_DIR/claude_usage.py"

ENABLE_CRON_CHECK="${ENABLE_CRON_CHECK:-1}"
ENABLE_USAGE="${ENABLE_USAGE:-1}"
[ "$ENABLE_CRON_CHECK" = "1" ] && xangi_require HEALTH_CHANNEL
[ "$ENABLE_USAGE" = "1" ] && xangi_require USAGE_CHANNEL

INTERVAL="${HEALTH_INTERVAL:-900}"
CHANNEL="${HEALTH_CHANNEL:-}"
REALERT_H="${HEALTH_REALERT_H:-6}"
USAGE_CHANNEL="${USAGE_CHANNEL:-}"
USAGE_DAILY_HOUR="${USAGE_DAILY_HOUR:--1}"   # 30分ゲージ通知があるので既定オフ
USAGE_BOARD="${USAGE_BOARD:-0}"             # 常設ボード。1 で有効（ゲージ通知と役割が重なるため既定オフ）

# ロック・ログ・通知抑制の状態は /tmp（コンテナローカル）に置く。
# 2 体の bot が同じリポジトリを共有していても、デーモンは bot（コンテナ）ごとに 1 本ずつ動かすため。
LANE_STATE_DIR="/tmp/xangi_lane_backstop"
LANE_MIN_INTERVAL="${LANE_MIN_INTERVAL:-5400}"   # 同じレーンを起こし直すまでの最短間隔(秒)

LOCK="/tmp/xangi_health_daemon.lock"
PIDFILE="/tmp/xangi_health_daemon.pid"
LOG="/tmp/xangi_health_daemon.log"
STATE="/tmp/xangi_health_daemon.state"        # "<最後に通知した内容のhash> <通知したepoch>"
USAGE_DAILY_STATE="/tmp/xangi_usage_daily.state"  # 日次スナップショットを投げた JST の日付

ONCE=0
[ "${1:-}" = "--once" ] && ONCE=1

log() { printf '%s | %s\n' "$(date -u '+%Y-%m-%d %H:%M:%SZ')" "$*" >>"$LOG"; }

# ---- 多重起動防止 -----------------------------------------------------------
# 既に走っていれば何もせず終了する。cron の冒頭から毎回叩かれる前提。
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "already running"
  exit 0
fi

send() {
  # Discord へ通知。xangi が死んでいると当然失敗するが、その時は bot 全体が沈黙しているので
  # 人間側が先に気づく。失敗してもデーモンは落とさない。
  # $2 = 投稿先チャンネル（省略時は cron 監視用）, $3 = メンションするか（既定 true）
  "$XCMD" discord_send --channel "${2:-$CHANNEL}" --message "$1" --mention "${3:-true}" >>"$LOG" 2>&1 \
    || log "send failed (xangi 側が応答しない?)"
}

# ---- ②' 常設ボード ---------------------------------------------------------
# 「今どれくらい使っているか」を常に見えるようにするための1通。毎回投稿すると
# チャンネルが流れるので、**1通を編集し続ける**（送りっぱなしにしない）。
BOARD_ID_FILE="$SCRIPT_DIR/.claude_usage_board.json"
BOARD_MARK="Claude 使用量ボード"

xok() { printf '%s' "$1" | grep -q '"ok":true'; }

discover_board_id() {
  # discord_send は message id を返さないので、履歴から目印で引き当てる
  "$XCMD" discord_history --channel "$USAGE_CHANNEL" --count 10 2>>"$LOG" | python3 -c '
import json, re, sys
try:
    r = json.load(sys.stdin)["result"]
except (ValueError, KeyError, TypeError) as e:
    print(f"discord_history の応答を解釈できない: {type(e).__name__}", file=sys.stderr)
    sys.exit(1)
for line in r.split("\n"):
    if "'"$BOARD_MARK"'" in line:
        m = re.search(r"\(ID:(\d+)\)", line)
        if m:
            print(m.group(1))
            break
'
}

update_board() {
  local body id res
  body="$(cd "$REPO" && python3 "$USAGE" --board 2>>"$LOG")"
  [ -z "$body" ] && return 0   # 取得失敗時は前の表示を残す（消さない）

  id="$(cat "$BOARD_ID_FILE" 2>/dev/null)"
  if [ -n "$id" ]; then
    res="$("$XCMD" discord_edit --channel "$USAGE_CHANNEL" --message-id "$id" --content "$body" 2>&1)"
    if xok "$res"; then return 0; fi
    log "board edit 失敗（消された?）。作り直す"
  fi

  res="$("$XCMD" discord_send --channel "$USAGE_CHANNEL" --message "$body" --mention false 2>&1)"
  if ! xok "$res"; then log "board send 失敗"; return 0; fi
  id="$(discover_board_id)"
  if [ -n "$id" ]; then
    printf '%s\n' "$id" >"$BOARD_ID_FILE"
    log "board 作成 id=$id"
  else
    log "board の message id を履歴から特定できず（次の周回で作り直す）"
  fi
}

# ---- ②'' 定期通知（ゲージだけ） ---------------------------------------------
# 人間の指定（2026-08-09）: 30分おきにゲージだけ通知する。
# デーモンの周期は 15 分なので、前回投稿からの経過で間引く。
GAUGE_STATE="$SCRIPT_DIR/.claude_usage_gauge.json"   # 最後にゲージを投稿した epoch
GAUGE_INTERVAL_MIN="${USAGE_GAUGE_MIN:-30}"          # 0 で無効

post_gauge() {
  local last now body
  [ "$GAUGE_INTERVAL_MIN" = "0" ] && return 0

  last="$(cat "$GAUGE_STATE" 2>/dev/null || echo 0)"
  now="$(date -u +%s)"
  # 周期が 15 分なので、しきい値は 1 分ぶん緩めて取りこぼしを防ぐ
  [ "$(( now - last ))" -lt "$(( GAUGE_INTERVAL_MIN * 60 - 60 ))" ] && return 0

  # 取得できなかった回は投稿しない（古い値を通知しても誤解を招くだけ）
  body="$(cd "$REPO" && python3 "$USAGE" --gauge 2>>"$LOG")" || return 0
  [ -z "$body" ] && return 0

  send "\`\`\`
$body
\`\`\`" "$USAGE_CHANNEL" false
  printf '%s\n' "$now" >"$GAUGE_STATE"
  log "gauge posted"
}

# ---- ② Claude のレート制限 -------------------------------------------------
# しきい値の判定・重複抑制・キャッシュはすべて claude_usage.py 側が持っている。
# ここは「出力があったら投げる」だけ（無出力＝正常＝無投稿）。
check_usage() {
  local out today

  out="$(cd "$REPO" && python3 "$USAGE" --check 2>>"$LOG")"
  if [ -n "$out" ]; then
    send "$out" "$USAGE_CHANNEL" true
    log "usage alert: $(printf '%s' "$out" | head -1)"
  fi

  # 日次スナップショット（JST）。コンテナ時計は UTC なので +9h して日付を出す
  [ "$USAGE_DAILY_HOUR" = "-1" ] && return 0
  if [ "$(date -u -d '+9 hours' +%-H)" = "$USAGE_DAILY_HOUR" ]; then
    today="$(date -u -d '+9 hours' +%Y-%m-%d)"
    if [ "$(cat "$USAGE_DAILY_STATE" 2>/dev/null)" != "$today" ]; then
      out="$(cd "$REPO" && python3 "$USAGE" 2>>"$LOG")"
      if [ -n "$out" ]; then
        send "📊 **Claude 使用量（$today 時点）**
\`\`\`
$out
\`\`\`" "$USAGE_CHANNEL" false
        printf '%s\n' "$today" >"$USAGE_DAILY_STATE"
        log "usage daily snapshot posted ($today)"
      fi
    fi
  fi
}

# ---- ①' レーンのバックストップ ---------------------------------------------
# 通報するだけでは cron は復活しない。xangi の cron (node-cron) は WSL2 の壁時計
# ジャンプでスロットを捨てるうえ、VM ごと凍っていた時間帯のスロットは端から消える
# (XANGI_CRON_SPEC.md §10.2.2)。そこで **発火窓の中でレーンが古くなっていたら、
# デーモン側から `xangi-cmd trigger` で直接ターンを起こす**。
# こちらは単調時計に頼らず「起きたときの壁時計」だけを見るので、凍っても取りこぼさない。
#
# プロンプトと投稿先は `.xangi/schedules.json` を唯一の正とする（二重管理しない）。
# ウォッチャーは差分だけを出す設計なので、cron が先に走っていれば state が新しく、
# ここは何もしない＝二重投稿にならない。
lane_field() {
  # $1=cron式 $2=取り出すキー
  python3 - "$SCHEDULES" "$1" "$2" 2>>"$LOG" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except (OSError, ValueError) as e:
    print(f"schedules.json を読めない: {sys.argv[1]} ({type(e).__name__})", file=sys.stderr)
    sys.exit(0)
for s in data if isinstance(data, list) else []:
    if s.get("expression") == sys.argv[2] and s.get("enabled"):
        print(s.get(sys.argv[3]) or "", end="")
        break
PY
}

drive_lanes() {
  local out expr label key last now prompt channel res

  out="$(cd "$REPO" && python3 "$CHECK" --stale-lanes 2>>"$LOG")"
  [ -z "$out" ] && return 0

  mkdir -p "$LANE_STATE_DIR"
  now="$(date -u +%s)"
  while IFS=$'\t' read -r expr label; do
    [ -z "$expr" ] && continue
    key="$LANE_STATE_DIR/$(printf '%s' "$expr" | md5sum | cut -d' ' -f1)"
    last="$(cat "$key" 2>/dev/null || echo 0)"
    if [ $(( now - ${last:-0} )) -lt "$LANE_MIN_INTERVAL" ]; then
      log "lane backstop: [$label] は直近に起こした。待つ"
      continue
    fi
    channel="$(lane_field "$expr" channelId)"
    prompt="$(lane_field "$expr" message)"
    if [ -z "$channel" ] || [ -z "$prompt" ]; then
      log "lane backstop: [$label] が schedules.json に無い/無効。skip"
      continue
    fi
    # 起動を試みる前に時刻を記録する。trigger が成功したのに記録前に落ちると、
    # 復帰後に同じレーンを連打してしまうため（鳴らし過ぎより取りこぼしの方がマシ、
    # ではなく **連打の方が実害が大きい**: 1 回ごとに LLM ターンが走る）。
    printf '%s\n' "$now" >"$key"
    res="$("$XCMD" trigger --channel "$channel" --message "$prompt" \
           --source kaggle-lane-backstop --platform discord 2>&1)"
    if xok "$res"; then
      log "lane backstop: [$label] を起こした"
    else
      log "lane backstop: [$label] 起動失敗: $(printf '%s' "$res" | head -1)"
    fi
  done <<EOF
$out
EOF
}

check_once() {
  local out hash now last_hash last_at age_h

  out="$(cd "$REPO" && python3 "$CHECK" --auto 2>>"$LOG")"
  now="$(date -u +%s)"

  if [ -z "$out" ]; then
    # 正常。直前まで異常だったなら復旧を 1 回だけ知らせる
    if [ -s "$STATE" ]; then
      send "✅ **定点観測 cron が復旧しました**（生存監視デーモンより）"
      log "recovered"
      : >"$STATE"
    fi
    return 0
  fi

  # 異常。同じ内容を鳴らし続けないよう、内容が変わったときと REALERT_H 時間経過時だけ通知する。
  # 【重要】本文には「最終実行から 15.4 時間経過」のように**増え続ける数字**が入っている。
  # そのまま md5 を取ると数分ごとにハッシュが変わり、抑制が永久に効かず毎周回鳴る
  # （2026-08-09 に実際に発生: 15分間隔で連投した）。数字を潰してから比較する。
  hash="$(printf '%s' "$out" | sed 's/[0-9][0-9.]*/N/g' | md5sum | cut -d' ' -f1)"
  last_hash=""; last_at=0
  if [ -s "$STATE" ]; then
    read -r last_hash last_at <"$STATE" || true
  fi
  age_h=$(( (now - ${last_at:-0}) / 3600 ))

  if [ "$hash" != "$last_hash" ] || [ "$age_h" -ge "$REALERT_H" ]; then
    send "$out
（生存監視デーモンの自動検知。復旧手順は \`tools/xangi/XANGI_CRON_SPEC.md\` §5.2 ＝ schedule_remove → schedule_add で ID を作り直す）"
    printf '%s %s\n' "$hash" "$now" >"$STATE"
    log "alerted: $(printf '%s' "$out" | head -1)"
  else
    log "still unhealthy (通知は抑制。前回から ${age_h}h)"
  fi
}

# ---- 本体 ------------------------------------------------------------------
cycle() {
  if [ "$ENABLE_CRON_CHECK" = "1" ]; then
    drive_lanes
    check_once
  fi
  if [ "$ENABLE_USAGE" = "1" ]; then
    check_usage
    post_gauge
    [ "$USAGE_BOARD" = "1" ] && update_board
  fi
  return 0
}

log "daemon start (pid=$$ ppid=$PPID interval=${INTERVAL}s cron_check=$ENABLE_CRON_CHECK usage=$ENABLE_USAGE cron_ch=$CHANNEL usage_ch=$USAGE_CHANNEL daily_jst=${USAGE_DAILY_HOUR}h once=$ONCE)"

if [ "$ONCE" = "1" ]; then
  cycle
  log "daemon exit (--once)"
  exit 0
fi

printf '%s\n' "$$" >"$PIDFILE"
SLEEP_PID=""
trap 'log "daemon stop (signal)"; [ -n "$SLEEP_PID" ] && kill "$SLEEP_PID" 2>/dev/null; rm -f "$PIDFILE"; exit 0' TERM INT

while true; do
  cycle
  # ログが太りすぎたら切り詰める（常駐なので放置すると無限に伸びる）
  if [ -f "$LOG" ] && [ "$(stat -c %s "$LOG")" -gt 1048576 ]; then
    tail -n 500 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  fi
  # `sleep "$INTERVAL"` を直に呼ぶと、bash は**フォアグラウンドの子が終わるまで trap を実行しない**。
  # つまり TERM を送っても最大 INTERVAL 秒（15分）止まらず、その間 flock を握ったままなので
  # 起動し直しても `already running` で弾かれる＝スクリプトを直しても反映できない。
  # バックグラウンド sleep ＋ wait なら wait が trap で中断されるので即座に止まる（2026-08-09 修正）。
  sleep "$INTERVAL" & SLEEP_PID=$!
  wait "$SLEEP_PID" 2>/dev/null || true
  SLEEP_PID=""
done
