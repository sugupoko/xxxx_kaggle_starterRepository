#!/usr/bin/env python3
"""Kaggle 定点観測 cron の生存チェック。

xangi の cron は `executeJob()` の再発火ガード（runningJobs に同じ ID が居ると skip）
のせいで、一度実行が終わらないと**以降の発火が永久にスキップされる**。
沈黙と「新着なし」の区別がつかない無投稿設計（XANGI_CRON_SPEC.md §4.2）と
組み合わさると、誰も気づけないまま何日も情報を落とす。実際 2026-08-08 に
disc/code の両レーンが止まり、2 日ぶんの Kaggle 新着を落とした。

このスクリプトはウォッチャーの state ファイルの更新時刻を見て、
**古すぎるレーンがあるときだけ** 標準出力に警告を出す（正常なら無出力＝無投稿）。

  XANGI_ROOT=<xangi のディレクトリ> python3 tools/xangi/kaggle_watch_health.py            # 既定しきい値 3 時間
  XANGI_ROOT=<xangi のディレクトリ> python3 tools/xangi/kaggle_watch_health.py --hours 6
  XANGI_ROOT=<xangi のディレクトリ> python3 tools/xangi/kaggle_watch_health.py --auto     # 時間帯でしきい値を切り替える（常駐デーモン用）

前提:
- 監視対象はコア側のウォッチャー `tools/kaggle_disc_watch.py` / `tools/kaggle_code_watch.py` の
  state ファイル（`tools/.kaggle_disc_watch.json` / `tools/.kaggle_code_watch.json`）。
- 登録状況は `$XANGI_ROOT/.xangi/schedules.json` を見る。**`XANGI_ROOT` は必須**
  （`xangi_health_daemon.sh` から呼ぶときは自動で渡る）。
- JST は `timezone(timedelta(hours=9))` で出す。`TZ=Asia/Tokyo` は zoneinfo の無いコンテナで
  黙って UTC になる（9 時間ズレる）ので使わない。

`--auto` を付けると **JST の時刻を見てしきい値を変える**。監視レーンは 7〜12 時 JST しか
発火しないので、深夜に「state が 15 時間古い」と言われても正常であり、固定しきい値では
夜通し誤検知するか、逆に鈍くしすぎて 1 日気づけないかのどちらかになる。

  JST 08:00〜13:59 … しきい値 1.5h（この時間帯は 30 分毎に発火しているはず）
  それ以外          … しきい値 26h（丸 1 日ぶんの発火窓を落としたら異常）

**「発火できなかった時間」は沈黙に数えない**（2026-08-09 追加）。state の古さだけを見ると、
xangi を再起動した直後やレーンを登録した直後に「15 時間サイレント」と鳴ってしまう。
実際 2026-08-09 10:19 JST のコンテナ再起動では、デーモン起動 9 秒後に誤報が飛んだ。
cron は xangi プロセスの中でしか動かないので、**プロセスが止まっていた間・レーンが存在しなかった間は
そもそも発火しようがない**。そこで実効の沈黙時間を

    min(state の古さ, xangi の稼働時間, レーン登録からの経過時間)

として判定する。抑制したときは stdout には出さず **stderr に理由を書く**（デーモンが
`2>>` でログに残すので、あとから「なぜ鳴らなかったか」を追える）。

詳細は tools/xangi/XANGI_CRON_SPEC.md §5.2 / §5.3 / §10.4。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# <repo>/tools/xangi/kaggle_watch_health.py → ウォッチャーの state はコア側の <repo>/tools/ にある
WATCH_STATE_DIR = Path(__file__).resolve().parents[1]


def schedules_path() -> Path:
    """xangi のスケジュール定義。xangi の起動ディレクトリはリポジトリの外なので env で受け取る。"""
    root = os.environ.get("XANGI_ROOT", "")
    if not root:
        sys.exit("環境変数 XANGI_ROOT（xangi を clone したディレクトリ）を設定してください")
    return Path(root) / ".xangi" / "schedules.json"

JST = timezone(timedelta(hours=9))

# 監視レーンが発火している時間帯（JST の時）と、その内外でのしきい値
ACTIVE_JST_HOURS = range(8, 14)
ACTIVE_THRESHOLD_H = 1.5
IDLE_THRESHOLD_H = 26.0


def auto_threshold() -> tuple[float, str]:
    """いまの JST 時刻に応じたしきい値と、その根拠の短い説明を返す。"""
    hour = datetime.now(JST).hour
    if hour in ACTIVE_JST_HOURS:
        return ACTIVE_THRESHOLD_H, f"JST {hour}時＝発火窓の中"
    return IDLE_THRESHOLD_H, f"JST {hour}時＝発火窓の外"

# state ファイル名 → (レーン表示名, 期待する cron 式)
# cron 式は xangi に登録した式と**文字列で完全一致**させる（schedules.json の照合に使う）。
LANES = {
    ".kaggle_disc_watch.json": ("Kaggle Discussion", "0,30 7-12 * * *"),
    ".kaggle_code_watch.json": ("パブリックコード", "15,45 7-12 * * *"),
}


def load_schedules() -> list[dict]:
    """読めなければ空リスト。その場合は各レーンが「登録が無い」として問題に挙がるので、隠れはしない。"""
    path = schedules_path()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        print(f"schedules.json を読めない: {path} ({type(e).__name__})", file=sys.stderr)
        return []
    return data if isinstance(data, list) else []


# ---- 「そもそも発火できたのか」を測るための材料 ------------------------------
# xangi 本体のコマンドライン。cron スケジューラはこのプロセスの中に居るので、
# これが動いていなかった時間は沈黙に数えない。
XANGI_CMD_HINT = "dist/index.js"


def _boot_epoch() -> float | None:
    """/proc/stat の btime（システム起動時刻の epoch 秒）。"""
    try:
        for line in Path("/proc/stat").read_text().splitlines():
            if line.startswith("btime "):
                return float(line.split()[1])
    except OSError as e:
        # 抑制材料が取れないだけ。None を返すと「抑制しない＝鳴らす」側に倒れる
        print(f"/proc/stat を読めない（xangi 稼働時間による抑制は無効）: {type(e).__name__}", file=sys.stderr)
    return None


def _proc_start_epoch(pid: str, boot: float) -> float | None:
    """/proc/<pid>/stat の starttime（起動からの clock tick）を epoch 秒に直す。"""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        # comm 部分に空白や ')' が入りうるので、最後の ')' より後ろだけを split する
        fields = stat[stat.rindex(")") + 2:].split()
        start_ticks = int(fields[19])  # stat の 22 番目（1-indexed）= starttime
    except (OSError, ValueError, IndexError):
        return None
    return boot + start_ticks / os.sysconf("SC_CLK_TCK")


def xangi_uptime_h() -> float | None:
    """xangi 本体が起動してからの時間。見つからなければ None（＝抑制しない）。"""
    boot = _boot_epoch()
    if boot is None:
        return None

    earliest: float | None = None
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = entry.joinpath("cmdline").read_bytes().decode("utf-8", "replace")
        except OSError:
            continue  # 読む前に消えたプロセス
        if XANGI_CMD_HINT not in cmdline:
            continue
        started = _proc_start_epoch(entry.name, boot)
        # ラッパの sh と node の両方が引っかかる。**古い方**を採って抑制を最小限にする
        if started is not None and (earliest is None or started < earliest):
            earliest = started

    if earliest is None:
        return None  # xangi が居ない＝発火しないのは異常。抑制せず鳴らす
    return max(0.0, (time.time() - earliest) / 3600.0)


def lane_registered_h(schedules: list[dict], expr: str) -> float | None:
    """その cron 式が schedules.json に登録されてからの時間。"""
    created = [s.get("createdAt") for s in schedules if s.get("expression") == expr]
    stamps = []
    for c in created:
        if not isinstance(c, str):
            continue
        try:
            stamps.append(datetime.fromisoformat(c.replace("Z", "+00:00")).timestamp())
        except ValueError:
            continue
    if not stamps:
        return None
    # 同じ式が複数登録されていたら**古い方**を採る（xangi_uptime_h と同じく抑制を最小限に）
    return max(0.0, (time.time() - min(stamps)) / 3600.0)


def print_stale_lanes() -> int:
    """発火窓の中で state が古くなっているレーンを `式<TAB>表示名` で列挙する。

    通報用の判定（`--auto`）と違い、**xangi の稼働時間による抑制をかけない**。
    抑制は「鳴らすべきか」の判断であって、「取りに行くべきか」の判断ではないため。
    xangi が凍っていて発火できなかったのなら、なおさら取りに行く必要がある。

    呼び出し側（`xangi_health_daemon.sh` の drive_lanes）が、この出力を見て
    `xangi-cmd trigger` でレーンのプロンプトを走らせる。詳細は
    XANGI_CRON_SPEC.md §10.2.3。
    """
    hour = datetime.now(JST).hour
    if hour not in ACTIVE_JST_HOURS:
        return 0  # 発火窓の外では取りに行かない

    now = time.time()
    for fname, (label, expr) in LANES.items():
        state = WATCH_STATE_DIR / fname
        if not state.exists():
            continue
        if (now - state.stat().st_mtime) / 3600.0 > ACTIVE_THRESHOLD_H:
            print(f"{expr}\t{label}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=3.0,
                    help="state がこの時間より古ければ異常とみなす（既定 3）")
    ap.add_argument("--auto", action="store_true",
                    help="JST の時間帯でしきい値を自動選択する（--hours より優先）")
    ap.add_argument("--stale-lanes", action="store_true",
                    help="発火窓の中で古くなっているレーンを TSV で列挙する（バックストップ用）")
    args = ap.parse_args()

    if args.stale_lanes:
        return print_stale_lanes()

    if args.auto:
        threshold, why = auto_threshold()
    else:
        threshold, why = args.hours, "固定しきい値"

    now = time.time()
    problems: list[str] = []
    schedules = load_schedules()
    uptime_h = xangi_uptime_h()

    for fname, (label, expr) in LANES.items():
        state = WATCH_STATE_DIR / fname

        if not state.exists():
            problems.append(f"❌ [{label}] state ファイルが無い（{state}）。--seed して作り直す")
            continue

        age_h = (now - state.stat().st_mtime) / 3600.0

        # 発火できなかった時間は沈黙に数えない（冒頭 docstring 参照）
        effective_h, capped_by = age_h, None
        for cap_h, cap_why in (
            (uptime_h, "xangi 起動から"),
            (lane_registered_h(schedules, expr), "レーン登録から"),
        ):
            if cap_h is not None and cap_h < effective_h:
                effective_h, capped_by = cap_h, cap_why

        if effective_h > threshold:
            problems.append(
                f"❌ [{label}] 最終実行から {age_h:.1f} 時間経過（しきい値 {threshold:g}h / {why}）。"
                f"cron が沈黙している可能性。schedule_remove → schedule_add で ID を作り直す"
            )
        elif age_h > threshold:
            print(
                f"[{label}] state は {age_h:.1f}h 古いが、{capped_by} {effective_h:.1f}h しか経っていないので"
                f"（しきい値 {threshold:g}h）まだ沈黙とは判定しない",
                file=sys.stderr,
            )

        # スケジュール自体が消えている / 無効化されていないか
        hit = [s for s in schedules if s.get("expression") == expr]
        if not hit:
            problems.append(f"❌ [{label}] cron 式 `{expr}` の登録が schedules.json に無い")
        elif not any(s.get("enabled") for s in hit):
            problems.append(f"❌ [{label}] cron `{hit[0].get('id')}` が無効化されている（schedule_toggle）")

    if problems:
        print("⚠️ **定点観測 cron の異常**")
        for p in problems:
            print(f"  {p}")
        return 0  # 異常も「正常に検知した」ので exit 0（cron 側は stdout の有無だけ見る）

    return 0  # 正常なら無出力


if __name__ == "__main__":
    sys.exit(main())
