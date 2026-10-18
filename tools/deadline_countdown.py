#!/usr/bin/env python3
"""コンペ締切までの残り日数とフェーズを出力する（LLM に日付計算をさせないため）。

出力はそのまま日報や定期リマインド（チャット投稿）に流せる形にしてある。
フェーズ境界は CLAUDE.md「フェーズ別ガード」の 30% / 70%。
日付は survey/competition/overview.md の「6. タイムライン」を正本として渡す。

  python3 tools/deadline_countdown.py --start 2026-08-06 --deadline 2026-10-22
  python3 tools/deadline_countdown.py --start 2026-08-06 --deadline 2026-10-22 --entry 2026-10-15
  # 環境変数でも渡せる: COMP_START / COMP_DEADLINE / COMP_ENTRY_DEADLINE

日付は JST で取る。コンテナの時計は UTC のことが多く、TZ=Asia/Tokyo も zoneinfo が無いと効かない。
UTC のまま日付を取ると JST 00〜09 時台で 1 日ずれる。
"""
import argparse
import os
from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

PHASES = [
    (0.30, "序盤", "1つの strong baseline / 動く submission pipeline", "アンサンブル・TTA・重い aug・ハイパラ tuning"),
    (0.70, "中盤", "多様性のある 3-5 single models / エラー分析 / データ追加", "アンサンブル本格化・過度な hyperparam search"),
    (float("inf"), "終盤", "アンサンブル / TTA / post-processing / 最終 submission 選定", "新アーキ着手・大きな前処理変更・新規外部データ"),
]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=os.environ.get("COMP_START"),
                    help="着手日（進捗%%の起点）YYYY-MM-DD")
    ap.add_argument("--deadline", default=os.environ.get("COMP_DEADLINE"),
                    help="最終提出締切 YYYY-MM-DD")
    ap.add_argument("--entry", default=os.environ.get("COMP_ENTRY_DEADLINE"),
                    help="Entry & Team Merger 締切 YYYY-MM-DD（任意）")
    args = ap.parse_args()
    if not args.start or not args.deadline:
        ap.error("--start と --deadline（または COMP_START / COMP_DEADLINE）が必要")
    return args


def main() -> None:
    args = parse_args()
    start = date.fromisoformat(args.start)
    final = date.fromisoformat(args.deadline)
    entry = date.fromisoformat(args.entry) if args.entry else None
    assert final > start, f"締切 {final} が着手日 {start} 以前になっている"

    today = datetime.now(JST).date()
    total = (final - start).days
    elapsed = (today - start).days
    ratio = elapsed / total
    phase, phase_do, phase_dont = next((n, d, x) for upper, n, d, x in PHASES if ratio < upper)

    d_final = (final - today).days
    print(f"⏳ **最終提出 {final} まで 残り {d_final} 日**")
    if entry is not None:
        d_entry = (entry - today).days
        if d_entry >= 0:
            print(f"（Entry & Team Merger {entry} まで 残り {d_entry} 日）")
        else:
            print(f"（Entry & Team Merger {entry} は締切済み）")
    print(f"経過 {elapsed}/{total} 日 = **{ratio * 100:.0f}%** → フェーズ: **{phase}**")
    print(f"やる: {phase_do}")
    print(f"やらない: {phase_dont}")
    if d_final <= 7:
        print("※ 締切時刻のタイムゾーンを確認すること（Kaggle は 23:59 UTC = 翌 08:59 JST が多い）")


if __name__ == "__main__":
    main()
