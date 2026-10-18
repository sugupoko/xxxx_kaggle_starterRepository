#!/usr/bin/env bash
# OpenRouter 残高の定点観測（cron / 定期実行用・使う場合のみ）。README.md 参照。
# tools/runpod/rp_credit_watch.sh と同じ思想：出す情報は数行に畳み、LLM に計算させず
# この出力を正本としてそのまま流す（通知に貼る等）。
#
#   - 残高 = total_credits - total_usage（これがゼロ以下になると 402 で弾かれる）
#   - キー枠残 limit_remaining（キー単位の上限。実際に使えるのは 残高 と この小さい方）
#   - 本日の使用額、前回チェックからの増減（state に残高と時刻を持つ）
#
# ★ 鍵は環境変数 OPENROUTER_API_KEY か リポジトリ直下の .openrouter.env から読む（*.env は gitignore 済み）。
#   値は絶対に出力へ混ぜない（通知に流れる）。curl にはプロセス置換でヘッダを渡し、argv にも出さない。
# ★ 時刻は `date -u -d '+9 hours'` で JST を明示計算する。TZ=Asia/Tokyo は使わない
#   （zoneinfo の無いコンテナでは黙って UTC のまま表示され、9 時間ズレる）。
#
# 環境変数（任意）: OR_WARN_USD（🟡 既定 20） / OR_CRIT_USD（🔴 既定 5）
# 状態ファイル（tools/openrouter/.gitignore で除外済み）: tools/openrouter/.or_credit_watch.json
set -uo pipefail
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
STATE="$HERE/.or_credit_watch.json"
API="https://openrouter.ai/api/v1"

WARN_USD="${OR_WARN_USD:-20}"    # 🟡 これを割ったら注意
CRIT_USD="${OR_CRIT_USD:-5}"     # 🔴 これを割ったら警告

if [ -z "${OPENROUTER_API_KEY:-}" ] && [ -f "$REPO/.openrouter.env" ]; then
  # shellcheck disable=SC1091
  set -a; source "$REPO/.openrouter.env" >/dev/null; set +a
fi
[ -n "${OPENROUTER_API_KEY:-}" ] || { echo "🔴 OpenRouter: APIキー未設定（環境変数 or .openrouter.env を確認）"; exit 1; }

# 認証ヘッダは printf（builtin）→ プロセス置換で渡す。curl の argv / ps に鍵が出ない
or_get() { curl -sS -m 20 -H @<(printf 'Authorization: Bearer %s\n' "$OPENROUTER_API_KEY") "$API/$1"; }

CRED="$(or_get credits)" || { echo "🔴 OpenRouter: 残高取得に失敗（curl エラー）"; exit 1; }
# キー情報は補助。失敗しても残高は出すが、取れなかったことは明示する
KEY_ERR=""
KEY="$(or_get auth/key)" || { KEY_ERR="curl エラー"; KEY='{}'; }

JST="$(date -u -d '+9 hours' '+%m/%d %H:%M')"
STATE="$STATE" JST="$JST" WARN="$WARN_USD" CRIT="$CRIT_USD" CRED="$CRED" KEY="$KEY" KEY_ERR="$KEY_ERR" python3 - <<'PY'
import json, os, sys, time

def load(name):
    """API 応答の data を返す。JSON でない / data が無いときは None（呼び出し側で扱う）。"""
    try:
        obj = json.loads(os.environ[name])
    except json.JSONDecodeError:
        return None
    return obj.get("data") if isinstance(obj, dict) else None

cred, key = load("CRED"), load("KEY")
if not cred:
    print("🔴 OpenRouter: 残高APIが想定外の応答を返しました（キーの失効・権限を確認）")
    raise SystemExit(1)
key_err = os.environ["KEY_ERR"] or ("" if key is not None else "想定外の応答")
key = key or {}

credits = float(cred.get("total_credits") or 0)
usage   = float(cred.get("total_usage") or 0)
bal     = credits - usage
now     = time.time()

klimit = key.get("limit")
krem   = key.get("limit_remaining")
daily  = key.get("usage_daily")

# --- 前回との差分（= この間に溶かした額）---
prev, delta_s, burn = {}, "", None
try:
    with open(os.environ["STATE"]) as f:
        prev = json.load(f)
except FileNotFoundError:
    pass                                       # 初回
except json.JSONDecodeError:
    print("[warn] state ファイルが壊れているので差分を出さない（次回から復帰）", file=sys.stderr)
if prev.get("balance") is not None and prev.get("ts"):
    d  = bal - float(prev["balance"])
    dt = (now - float(prev["ts"])) / 60.0
    if dt >= 1:
        delta_s = f" ｜ 前回比 {d:+.2f}$({dt:.0f}分)"
        if d < 0:
            burn = -d / (dt / 60.0)     # $/h

# 実際に使える額 = 残高とキー枠残の小さい方
eff = bal if krem is None else min(bal, float(krem))
flag = "🟢"
if eff < float(os.environ["CRIT"]): flag = "🔴"
elif eff < float(os.environ["WARN"]): flag = "🟡"

line = f'{flag} OpenRouter {os.environ["JST"]} JST ｜ 残高 **${bal:.2f}**'
if krem is not None:
    line += f' ｜ キー枠残 ${float(krem):.2f}'
    if klimit: line += f'/${float(klimit):.0f}'
if daily is not None:
    line += f' ｜ 本日 ${float(daily):.2f}'
print(line + delta_s)

if key_err:
    print(f"⚠️ キー情報の取得に失敗（{key_err}）。キー枠残は未確認")
if bal <= 0:
    print(f"⚠️ **残高がゼロ以下です**（購入 ${credits:.2f} / 使用 ${usage:.2f}）。チャージするまで新規リクエストは 402 で弾かれます")
elif bal < float(os.environ["CRIT"]):
    print(f'⚠️ 残高が ${os.environ["CRIT"]} を下回っています。チャージしないと 402 で止まります')
elif bal < float(os.environ["WARN"]):
    print(f'残高が ${os.environ["WARN"]} 未満になりました。そろそろチャージの検討を')
elif krem is not None and float(krem) < float(os.environ["WARN"]):
    print(f'キーの上限枠が残り ${float(krem):.2f} です（残高より先にこちらで止まります）')

if burn and bal > 0:
    h = bal / burn
    if h < 24:
        print(f"⚠️ このペース(${burn:.2f}/h)だと残り **{h:.1f}時間** で残高ゼロです")

with open(os.environ["STATE"], "w") as f:
    json.dump({"balance": bal, "ts": now, "credits": credits, "usage": usage,
               "key_remaining": krem}, f)
PY
