#!/usr/bin/env python3
"""Claude Code サブスクリプションのレート制限（使用率）を取得する。

Claude Code の `/usage` が叩いているのと同じ OAuth エンドポイント
`GET https://api.anthropic.com/api/oauth/usage` を、ローカルの認証情報で呼ぶ。
CLI に `claude usage` 相当のサブコマンドは無いので、ここは自前で叩くしかない。

  python3 tools/xangi/claude_usage.py            # 人が読む要約
  python3 tools/xangi/claude_usage.py --brief    # 1行（Discordの定期投稿向け）
  python3 tools/xangi/claude_usage.py --json     # 生JSON
  python3 tools/xangi/claude_usage.py --check    # しきい値を跨いだ時だけ出力（常駐監視用）
  python3 tools/xangi/claude_usage.py --board    # Discord に貼って編集更新する常設ボード用

`--check` は状態ファイル（既定 `tools/xangi/.claude_usage_state.json`）に「最後に鳴らした
しきい値」と「枠のリセット時刻」を持ち、**同じ段を二度鳴らさない**。枠がリセット
されたら状態を捨てて、必要なら復帰を1回だけ知らせる。正常時は無出力＝無投稿。

実測でわかった落とし穴が2つある（どちらも対処済み）:

1. **`resets_at` はリクエストごとに揺れる**（`...59.420076` / `...59.521764`）。しかも値が
   分の境界に張り付いているので、**分単位に丸めても揺れが境界をまたぐ**
   （`17:09:59.42` → `17:10:00.79`）。epoch 秒にして ±5分の許容差で比較する。
2. **このエンドポイント自体がレート制限される**（連続で叩くと HTTP 429）。
   そのため既定 300 秒のローカルキャッシュを挟み、429 や通信断は「一時的」として
   **無投稿のまま**キャッシュで凌ぐ。
3. **アクセストークンの期限切れは故障ではない**（`UsageIdle`）。トークンは `claude` が
   動くたびに更新されるので、期限切れ＝「誰も bot を使っていない」。誰かが話しかければ
   自動で直る。ここを通報対象にしていたため、2026-08-09 未明に同じエラーを
   15 分おきに 6 連投した。**人が動く余地の無い事象は鳴らさない。**
   本物のエラー（401・API 変更等）だけ、`ERROR_REALERT_H` 時間の抑制つきで通報する。

【秘匿情報】アクセストークンは読むだけで、標準出力にも例外にも絶対に出さない。

環境変数（すべて任意）:
  CLAUDE_CREDENTIALS  … 認証情報ファイルを直接指定（実行ユーザーの HOME の外にある環境向け）
  CLAUDE_CONFIG_DIR   … Claude Code の設定ディレクトリ（`<dir>/.credentials.json` を見る）
  CLAUDE_USAGE_DIR    … 状態・キャッシュの置き場（既定はこのスクリプトと同じ tools/xangi/）。
                        2 体の bot が同じリポジトリを共有し、両方でこれを回すなら bot ごとに分ける
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"

# 認証情報の置き場所。xangi の実行ユーザーの HOME と Claude の認証の置き場がズレる環境があった
# （HOME は別ユーザーなのに認証は別の HOME 側にある）。その場合は env で明示する。上から順に見る。
def _cred_paths() -> list[Path]:
    paths = []
    if os.environ.get("CLAUDE_CREDENTIALS"):
        paths.append(Path(os.environ["CLAUDE_CREDENTIALS"]))
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        paths.append(Path(os.environ["CLAUDE_CONFIG_DIR"]) / ".credentials.json")
    paths.append(Path.home() / ".claude" / ".credentials.json")
    return paths


CRED_PATHS = _cred_paths()

# 状態とキャッシュは tools/xangi/ 配下に置く（.gitignore 済み）。
# /tmp だとコンテナ再起動で消え、そのたびに同じ段を鳴らし直してしまう（2026-08-08 に実際に発生）。
STATE_DIR = Path(os.environ.get("CLAUDE_USAGE_DIR") or Path(__file__).resolve().parent)
DEFAULT_STATE = STATE_DIR / ".claude_usage_state.json"
CACHE = STATE_DIR / ".claude_usage_cache.json"
CACHE_MAX_AGE = 300.0  # 秒。API 側が 429 を返すので、これより短い間隔では叩かない
WINDOW_TOLERANCE_S = 300.0  # リセット時刻がこの範囲で揺れても「同じ枠」とみなす
ERROR_REALERT_H = 12.0      # 同じ取得エラーを再通知するまでの時間

# 鳴らすしきい値（%）。低い方から順に、跨いだ最大の段だけを通知する
THRESHOLDS = {
    "seven_day": [50, 70, 80, 90, 95],   # 週次。枯れると数日止まる＝重い
    "five_hour": [50, 70, 80, 90, 95],   # 5時間枠。すぐ回復するが、消費の速さを見たいので週次と同じ刻み
}
LABELS = {"seven_day": "週次(7日)", "five_hour": "5時間枠"}


class UsageError(RuntimeError):
    """人が動かないと直らない失敗。メッセージにトークンを含めないこと。"""


class UsageTransient(RuntimeError):
    """一時的な失敗（429・通信断）。キャッシュで凌ぎ、無投稿のままにする。"""


class UsageIdle(RuntimeError):
    """アクセストークンの期限切れ。**通報してはいけない失敗。**

    トークンは `claude` が動くたびに更新される。つまり期限切れ＝「誰も bot を
    使っていない」であって、故障ではない。誰かが話しかけた瞬間に自動で直る。
    2026-08-09 未明、これを通報対象にしていたため使用率チャンネルへ同じエラーを
    15分おきに6連投した。人が動く余地が無い事象を鳴らしても通知を汚すだけ。
    """


def load_token() -> str:
    for p in CRED_PATHS:
        try:
            oauth = json.loads(p.read_text())["claudeAiOauth"]
        except (OSError, ValueError, KeyError):
            continue
        if oauth.get("expiresAt", 0) / 1000 <= time.time():
            # 故障ではなく「bot が使われていない」だけ。通報せず直近値で凌ぐ
            raise UsageIdle("アクセストークン期限切れ（bot が使われれば自動更新される）")
        return oauth["accessToken"]
    raise UsageError("認証情報が見つからない（.credentials.json）")


def _read_cache() -> tuple[dict, float] | None:
    try:
        c = json.loads(CACHE.read_text())
        return c["data"], float(c["at"])
    except (OSError, ValueError, KeyError):
        return None


def _fetch_live(timeout: float = 30.0) -> dict:
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {load_token()}",
            "anthropic-beta": "oauth-2025-04-20",
            "anthropic-version": "2023-06-01",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (408, 429, 500, 502, 503, 504):
            raise UsageTransient(f"HTTP {e.code}") from None
        raise UsageError(f"HTTP {e.code}（認証切れか API 変更）") from None
    except (OSError, http.client.HTTPException, ValueError) as e:
        # 通信断・タイムアウト（URLError / TimeoutError は OSError の子）・不正な応答。
        # 例外文にトークンが混ざらないよう型名だけ出す
        raise UsageTransient(f"通信失敗: {type(e).__name__}") from None


def fetch(max_age: float = CACHE_MAX_AGE) -> tuple[dict, str]:
    """(データ, 出所) を返す。出所は "live" / "cache" / "stale"。

    - "cache": max_age 以内のキャッシュを正常に再利用した（API 側の 429 対策）
    - "stale": 取得に失敗し、期限切れのキャッシュで凌いだ ← これだけが異常系
    """
    cached = _read_cache()
    if cached and time.time() - cached[1] <= max_age:
        return cached[0], "cache"

    try:
        data = _fetch_live()
    except (UsageTransient, UsageIdle):
        if cached:
            return cached[0], "stale"
        raise

    try:
        CACHE.write_text(json.dumps({"at": time.time(), "data": data}))
    except OSError as e:
        # キャッシュが書けなくても今回の値は返せる。ただし次回また API を叩く（429 の元）ので記録する
        print(f"キャッシュを書けない: {CACHE} ({type(e).__name__})", file=sys.stderr)
    return data, "live"


def jst(iso: str | None) -> str:
    if not iso:
        return "-"
    return datetime.fromisoformat(iso).astimezone(JST).strftime("%m/%d %H:%M")


def until(iso: str | None) -> str:
    if not iso:
        return ""
    delta = datetime.fromisoformat(iso) - datetime.now(timezone.utc)
    h, m = divmod(max(0, int(delta.total_seconds())) // 60, 60)
    return f"あと{h}時間{m:02d}分" if h else f"あと{m}分"


def bar(pct: float, width: int = 20) -> str:
    filled = int(round(pct / 100 * width))
    return "█" * filled + "░" * (width - filled)


def lanes(data: dict) -> dict[str, dict]:
    """通知対象のレーンだけを取り出す（値が無いレーンは落とす）。"""
    out = {}
    for key in ("five_hour", "seven_day"):
        v = data.get(key)
        if isinstance(v, dict) and v.get("utilization") is not None:
            out[key] = v
    return out


def render(data: dict) -> str:
    rows = []
    for key, v in lanes(data).items():
        pct = float(v["utilization"])
        rows.append(f"{LABELS[key]:<9} {bar(pct)} {pct:5.1f}%  リセット {jst(v['resets_at'])} {until(v['resets_at'])}")

    # モデル別などのスコープ枠は、使われている時だけ出す（常時0%だと邪魔なので）
    for lim in data.get("limits") or []:
        if lim.get("kind") == "weekly_scoped" and float(lim.get("percent") or 0) > 0:
            name = ((lim.get("scope") or {}).get("model") or {}).get("display_name") or "scoped"
            rows.append(f"{name:<9} {bar(float(lim['percent']))} {float(lim['percent']):5.1f}%  リセット {jst(lim.get('resets_at'))}")

    extra = data.get("extra_usage") or {}
    tail = "追加クレジット: 無効（上限に当たったら止まる）" if not extra.get("is_enabled") else "追加クレジット: 有効"
    return "\n".join(rows) + "\n" + tail


BOARD_MARK = "📟 **Claude 使用量ボード**"


def board(data: dict, source: str) -> str:
    """Discord に貼りっぱなしにして編集で更新する用の本文。

    先頭行の BOARD_MARK は、履歴からこのメッセージを探し当てるための目印なので変えない。
    """
    now = datetime.now(JST).strftime("%m/%d %H:%M")
    rows = []
    for key, v in lanes(data).items():
        pct = float(v["utilization"])
        rows.append(f"{LABELS[key]:<9} {bar(pct)} {pct:5.1f}%  リセット {jst(v['resets_at'])} {until(v['resets_at'])}")

    fh = (data.get("five_hour") or {})
    note = ""
    if fh.get("resets_at"):
        reset = datetime.fromisoformat(fh["resets_at"])
        elapsed = 5 - (reset - datetime.now(timezone.utc)).total_seconds() / 3600
        elapsed = min(max(elapsed, 0.0), 5.0)
        pace = float(fh.get("utilization") or 0)
        # 時間の消化に対して枠の消費が速いかどうか＝このまま行くと枠を使い切るか
        verdict = "余裕あり" if pace <= elapsed / 5 * 100 else "時間より速く消費中"
        note = f"\n5時間枠の進み: 時間 {elapsed / 5 * 100:.0f}% 消化 / 枠 {pace:.0f}% 消費 → {verdict}"

    warn = "　⚠️ 取得に失敗したため直近値を表示中" if source == "stale" else ""
    return (
        f"{BOARD_MARK}　最終更新 {now} JST{warn}\n"
        f"```\n" + "\n".join(rows) + note + "\n```\n"
        f"-# 15分ごとに自動更新されます。しきい値を超えた時は別途通知します"
    )


def gauge(data: dict) -> str:
    """ゲージ2行だけ。定期通知用（人間の指定: 余計な解説を足さない）。"""
    return "\n".join(
        f"{LABELS[k]:<9} {bar(float(v['utilization']))} {float(v['utilization']):5.1f}%"
        f"  リセット {jst(v['resets_at'])} {until(v['resets_at'])}"
        for k, v in lanes(data).items()
    )


def brief(data: dict) -> str:
    parts = [f"{LABELS[k]} {float(v['utilization']):.0f}%（リセット {jst(v['resets_at'])}）"
             for k, v in lanes(data).items()]
    return " / ".join(parts)


def reset_epoch(iso: str | None) -> float | None:
    """枠の同一性判定用にリセット時刻を epoch 秒で返す。"""
    if not iso:
        return None
    return datetime.fromisoformat(iso).timestamp()


def same_window(a: float | None, b: float | None) -> bool:
    """2つのリセット時刻が「同じ枠」を指しているか。

    API はリクエストごとにリセット時刻を揺らして返す。しかも値が `...:59.42` のように
    分の境界に張り付いているため、**分単位に丸めても揺れが境界をまたぐ**
    （`17:09:59.42` → `17:10:00.79` で 17:09 と 17:10 に割れる）。
    2026-08-08 にこれで「週次がリセットされました」の誤報を2回出した。
    枠の間隔は5時間・7日なので、**許容差を持たせて比較する**のが正しい。
    """
    if a is None or b is None:
        return a is b
    return abs(a - b) <= WINDOW_TOLERANCE_S


def crossed(pct: float, key: str) -> int | None:
    """跨いだ最大のしきい値を返す。どれも跨いでいなければ None。"""
    hit = [t for t in THRESHOLDS[key] if pct >= t]
    return max(hit) if hit else None


def check(data: dict, state_path: Path) -> str:
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError):
        state = {}

    messages: list[str] = []
    # レーン以外のキー（エラー抑制の記録など）は落とさずに引き継ぐ
    new_state: dict[str, dict] = {k: v for k, v in state.items() if k not in LABELS}

    # 直前までエラーを通報していたなら、復旧を1回だけ知らせる
    if new_state.pop("_error", None):
        messages.append("✅ **Claude 使用量の取得が復旧しました**")

    for key, v in lanes(data).items():
        pct = float(v["utilization"])
        resets = v.get("resets_at")
        window = reset_epoch(resets)
        prev = state.get(key) or {}

        # 枠が入れ替わった（リセットされた）なら、前回の通知履歴は無効
        if not same_window(prev.get("window"), window):
            if prev.get("level"):
                messages.append(f"✅ **{LABELS[key]}がリセットされました**（現在 {pct:.0f}%）")
            prev = {}

        level = crossed(pct, key)
        new_state[key] = {"window": window, "level": level}

        if level and level != prev.get("level"):
            icon = "🚨" if level >= 90 else ("⚠️" if level >= 70 else "📊")
            messages.append(
                f"{icon} **{LABELS[key]}が {level}% を超えました** — 現在 {pct:.1f}%\n"
                f"```\n{bar(pct)} {pct:.1f}%\nリセット {jst(resets)} JST（{until(resets)}）\n```"
            )

    state_path.write_text(json.dumps(new_state))
    return "\n".join(messages)


def note_error(state_path: Path, message: str) -> str:
    """取得エラーの通報。**同じ原因を鳴らし続けない**ための抑制つき。

    2026-08-09 に、抑制が無いまま15分周期で同じエラーを6連投した反省から。
    内容が変わった時と、ERROR_REALERT_H 時間経過した時だけ鳴らす。
    """
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError):
        state = {}

    prev = state.get("_error") or {}
    now = time.time()
    quiet = prev.get("message") == message and (now - float(prev.get("at", 0))) < ERROR_REALERT_H * 3600

    state["_error"] = {"message": message, "at": prev.get("at", now) if quiet else now}
    try:
        state_path.write_text(json.dumps(state))
    except OSError as e:
        # 書けないと次の周回で同じエラーを再通報する（抑制が効かない）。黙らせずに残す
        print(f"状態ファイルを書けない: {state_path} ({type(e).__name__})", file=sys.stderr)

    if quiet:
        return ""
    return (f"❌ **Claude 使用量の取得に失敗**: {message}\n"
            f"-# 同じ原因では {ERROR_REALERT_H:g} 時間に1回だけ通知します")


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--json", action="store_true", help="生JSONをそのまま出す")
    g.add_argument("--brief", action="store_true", help="1行にまとめる")
    g.add_argument("--check", action="store_true", help="しきい値を跨いだ時だけ出力（常駐監視用）")
    g.add_argument("--board", action="store_true", help="常設ボード用の本文（Discordで編集更新する）")
    g.add_argument("--gauge", action="store_true", help="ゲージ2行だけ（定期通知用）")
    ap.add_argument("--state", type=Path, default=DEFAULT_STATE, help="--check の状態ファイル")
    ap.add_argument("--max-age", type=float, default=CACHE_MAX_AGE,
                    help=f"この秒数以内のキャッシュは再利用する（既定 {CACHE_MAX_AGE:g}）")
    ap.add_argument("--force", action="store_true", help="キャッシュを無視して必ず取得しにいく")
    args = ap.parse_args()

    try:
        data, source = fetch(max_age=0.0 if args.force else args.max_age)
    except UsageError as e:
        # 人が動かないと直らない失敗だけ通報する。ただし連投はしない
        if args.check:
            out = note_error(args.state, str(e))
            if out:
                print(out)
        else:
            print(f"❌ Claude 使用量の取得に失敗: {e}", file=sys.stderr)
        return 1
    except (UsageTransient, UsageIdle) as e:
        # 429・通信断・トークン期限切れ。いずれも人が動く余地が無いので通報しない
        if not args.check:
            print(f"⏳ いま取得できず（{e}）。少し置いて再実行して", file=sys.stderr)
        return 1

    stale = "（直近の取得値）" if source != "live" else ""

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif args.board:
        print(board(data, source))
    elif args.gauge:
        # 古い値で通知しても誤解を招くだけなので、取得できていない回は黙る
        if source == "stale":
            return 1
        print(gauge(data))
    elif args.brief:
        print(brief(data) + stale)
    elif args.check:
        # 期限切れキャッシュで判定すると、古い値でしきい値を鳴らしてしまう
        if source == "stale":
            return 0
        out = check(data, args.state)
        if out:
            print(out)
    else:
        print(render(data) + (f"\n※ {CACHE_MAX_AGE:g}秒以内に取得した値を再利用中" if source == "cache"
                             else ("\n⚠️ 取得に失敗したため直近値を表示中" if source == "stale" else "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
