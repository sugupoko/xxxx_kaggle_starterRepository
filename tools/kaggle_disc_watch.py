#!/usr/bin/env python3
"""Kaggle Discussion 定点観測ウォッチャー（差分だけ stdout に吐く）

- state に無い topic_id      → 🆕 新トピック（冒頭 240 字）
- commentCount が増えた topic → 💬 新着返信×N（増分だけ、各 200 字）
差分が無ければ標準出力は完全に空（定期実行の出力をチャットへ流す運用なら、無投稿になる）。

  KAGGLE_WATCH_SLUG=<slug> python3 tools/kaggle_disc_watch.py          # 差分を出力
  KAGGLE_WATCH_SLUG=<slug> python3 tools/kaggle_disc_watch.py --seed   # state を作り直すだけ（出力なし）
"""
import csv
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# 監視するコンペ slug（必須）。例: KAGGLE_WATCH_SLUG=<competition-slug>
SLUG = os.environ.get("KAGGLE_WATCH_SLUG", "")
KAGGLE = os.environ.get("KAGGLE_BIN", "kaggle")
# kaggle.json / kaggle パッケージが実行ユーザーの HOME の外にある環境だけ指定する
# （切り離して走らせると user-site が外れて ModuleNotFoundError になることがある）
KAGGLE_CONFIG_DIR = os.environ.get("KAGGLE_CONFIG_DIR", "")
KAGGLE_SITE = os.environ.get("KAGGLE_SITE_PACKAGES", "")
if not SLUG:
    sys.exit("KAGGLE_WATCH_SLUG（コンペ slug）を設定してください")

PAGES = int(os.environ.get("DISC_PAGES", "3"))  # 20件/ページ × 3 = 最新60トピック
NEW_TOPIC_CHARS = 240
REPLY_CHARS = 200
MAX_REPLIES_PER_TOPIC = 5  # 1トピックあたりの表示上限（暴発防止）

STATE = Path(__file__).resolve().parent / ".kaggle_disc_watch.json"
URL = f"https://www.kaggle.com/competitions/{SLUG}/discussion/"


def run(args):
    pypath = [p for p in (KAGGLE_SITE, os.environ.get("PYTHONPATH", "")) if p]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(pypath))
    if KAGGLE_CONFIG_DIR:
        env["KAGGLE_CONFIG_DIR"] = KAGGLE_CONFIG_DIR
    p = subprocess.run([KAGGLE] + args, capture_output=True, text=True, env=env, timeout=120)
    if p.returncode != 0:
        print(f"[warn] kaggle {' '.join(args)} -> rc={p.returncode}: {p.stderr.strip()[:200]}",
              file=sys.stderr)
        return ""
    return p.stdout


def parse_csv(text):
    """Kaggle CLI の CSV 出力を dict のリストに。ヘッダ前の雑多な行は読み飛ばす。"""
    if not text.strip():
        return []
    lines = text.replace("\r\n", "\n").split("\n")
    for i, ln in enumerate(lines):
        if "," in ln and ln.split(",")[0].strip() in ("id", "ref"):
            text = "\n".join(lines[i:])
            break
    else:
        return []
    try:
        return list(csv.DictReader(io.StringIO(text)))
    except csv.Error as e:
        print(f"[warn] csv parse failed: {e}", file=sys.stderr)
        return []


TAG_A = re.compile(r'<a\s[^>]*href=["\']?([^"\'\s>]+)["\']?[^>]*>(.*?)</a>', re.S | re.I)
TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")


def strip_html(s):
    s = TAG_A.sub(lambda m: f"{TAG.sub('', m.group(2)).strip()}({m.group(1)})", s or "")
    s = TAG.sub(" ", s)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                 ("&#39;", "'")):
        s = s.replace(a, b)
    return WS.sub(" ", s).strip()


def clip(s, n):
    s = strip_html(s)
    return s if len(s) <= n else s[:n] + "…"


def fetch_topics():
    topics = {}
    for page in range(1, PAGES + 1):
        rows = parse_csv(run(["competitions", "topics", "list", SLUG,
                              "--sort-by", "new", "-p", str(page), "-v", "-q"]))
        if not rows:
            break
        for r in rows:
            tid = (r.get("id") or "").strip()
            # Kaggle CLI may append a pagination marker such as
            # "Next Page Token = 2" after the CSV body. DictReader can
            # interpret it as a row, but real discussion IDs are numeric.
            if not tid.isdigit():
                continue
            try:
                cnt = int(float(r.get("commentCount") or 0))
            except ValueError:
                cnt = 0
            topics[tid] = {"title": (r.get("title") or "").strip(),
                           "count": cnt,
                           "date": (r.get("postDate") or "").strip()[:19]}
    return topics


def fetch_messages(tid, n, newest_first):
    rows = parse_csv(run(["competitions", "topic-messages", SLUG, tid,
                          "--sort-by", "new" if newest_first else "old",
                          "-n", str(n), "-v", "-q"]))
    return rows[:n]


def main():
    seed = "--seed" in sys.argv
    try:
        prev = json.loads(STATE.read_text())
    except (OSError, ValueError):
        prev = None

    topics = fetch_topics()
    if not topics:
        print("[warn] no topics fetched (API error?) - state kept", file=sys.stderr)
        return 0

    if seed or prev is None:
        STATE.write_text(json.dumps({t: v["count"] for t, v in topics.items()}))
        print(f"[seed] {len(topics)} topics", file=sys.stderr)
        return 0

    out = []
    for tid, v in sorted(topics.items(), key=lambda kv: kv[1]["date"]):
        if tid not in prev:
            msgs = fetch_messages(tid, 1, newest_first=False)
            body = clip(msgs[0].get("content", ""), NEW_TOPIC_CHARS) if msgs else ""
            date = (msgs[0].get("postDate", "")[:19] if msgs else v["date"])
            out.append(f"🆕 **新トピック** [{v['title']}]\n  {URL}{tid}\n  ({date}) {body}")
        else:
            delta = v["count"] - int(prev[tid])
            if delta > 0:
                shown = min(delta, MAX_REPLIES_PER_TOPIC)
                msgs = fetch_messages(tid, shown, newest_first=True)
                lines = [f"  ・({m.get('postDate','')[:19]}) {clip(m.get('content',''), REPLY_CHARS)}"
                         for m in msgs]
                more = f"\n  （他 {delta - shown} 件）" if delta > shown else ""
                out.append(f"💬 **新着返信×{delta}** [{v['title']}]\n  {URL}{tid}\n"
                           + "\n".join(lines) + more)

    if out:
        print("\n\n".join(out))

    STATE.write_text(json.dumps({t: v["count"] for t, v in topics.items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
