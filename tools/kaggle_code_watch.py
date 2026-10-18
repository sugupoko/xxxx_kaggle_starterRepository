#!/usr/bin/env python3
"""Kaggle パブリックコード（公開ノートブック）定点観測ウォッチャー

- state に無い ref                      → 🆕 新規ノートブック
- 票が VOTE_DELTA_REPORT 以上伸びた ref → 📈 注目度急上昇
差分が無ければ標準出力は完全に空。

  KAGGLE_WATCH_SLUG=<slug> python3 tools/kaggle_code_watch.py          # 差分を出力
  KAGGLE_WATCH_SLUG=<slug> python3 tools/kaggle_code_watch.py --seed   # state を作り直すだけ（出力なし）
"""
import csv
import io
import json
import os
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

RECENT_PAGES = 3  # 直近更新順（新規公開の検知）: 20件/ページ
TOP_PAGES = 2     # 票数順（伸びの検知）
VOTE_DELTA_REPORT = int(os.environ.get("VOTE_DELTA_REPORT", "10"))

STATE = Path(__file__).resolve().parent / ".kaggle_code_watch.json"


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
    if not text.strip():
        return []
    lines = text.replace("\r\n", "\n").split("\n")
    for i, ln in enumerate(lines):
        if "," in ln and ln.split(",")[0].strip() in ("ref", "id"):
            text = "\n".join(lines[i:])
            break
    else:
        return []
    try:
        return list(csv.DictReader(io.StringIO(text)))
    except csv.Error as e:
        print(f"[warn] csv parse failed: {e}", file=sys.stderr)
        return []


def fetch(sort_by, pages):
    out = {}
    for page in range(1, pages + 1):
        rows = parse_csv(run(["kernels", "list", "--competition", SLUG,
                              "--sort-by", sort_by, "-p", str(page), "-v"]))
        if not rows:
            break
        for r in rows:
            ref = (r.get("ref") or "").strip()
            if not ref:
                continue
            try:
                votes = int(float(r.get("totalVotes") or 0))
            except ValueError:
                votes = 0
            out[ref] = {"title": (r.get("title") or "").strip(),
                        "author": (r.get("author") or "").strip(),
                        "votes": votes,
                        "date": (r.get("lastRunTime") or "").strip()[:19]}
    return out


def main():
    seed = "--seed" in sys.argv
    try:
        prev = json.loads(STATE.read_text())
    except (OSError, ValueError):
        prev = None

    kernels = fetch("dateRun", RECENT_PAGES)
    for ref, v in fetch("voteCount", TOP_PAGES).items():
        kernels.setdefault(ref, v)

    if not kernels:
        print("[warn] no kernels fetched (API error?) - state kept", file=sys.stderr)
        return 0

    if seed or prev is None:
        STATE.write_text(json.dumps({k: v["votes"] for k, v in kernels.items()}))
        print(f"[seed] {len(kernels)} kernels", file=sys.stderr)
        return 0

    new, hot = [], []
    for ref, v in kernels.items():
        url = f"https://www.kaggle.com/code/{ref}"
        if ref not in prev:
            new.append((v["votes"], f"🆕 **新規ノートブック** [{v['title']}] by {v['author']}\n"
                                    f"  {url}\n  (更新 {v['date']} / 👍{v['votes']})"))
        else:
            d = v["votes"] - int(prev[ref])
            if d >= VOTE_DELTA_REPORT:
                hot.append((d, f"📈 **注目度急上昇 (+{d}票 → 計{v['votes']})** [{v['title']}] "
                               f"by {v['author']}\n  {url}"))

    out = [s for _, s in sorted(new, reverse=True)] + [s for _, s in sorted(hot, reverse=True)]
    if out:
        print("\n\n".join(out))

    STATE.write_text(json.dumps({k: v["votes"] for k, v in kernels.items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
