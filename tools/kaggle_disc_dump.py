#!/usr/bin/env python3
"""Kaggle Discussion 全文ダンプ（精査用のコーパスを作る）

kaggle CLI の topic-messages は本文をフルで返す（watcher は表示用に切っているだけ）。
これを全トピック分まとめて JSON + Markdown に落とす。

  KAGGLE_WATCH_SLUG=<slug> python3 tools/kaggle_disc_dump.py --out survey/discussions
"""
import argparse, csv, io, json, os, re, subprocess, sys, time
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
URL = f"https://www.kaggle.com/competitions/{SLUG}/discussion/"


def run(args, retries=3):
    pypath = [p for p in (KAGGLE_SITE, os.environ.get("PYTHONPATH", "")) if p]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(pypath))
    if KAGGLE_CONFIG_DIR:
        env["KAGGLE_CONFIG_DIR"] = KAGGLE_CONFIG_DIR
    for i in range(retries):
        try:
            p = subprocess.run([KAGGLE] + args, capture_output=True, text=True,
                               env=env, timeout=180)
        except subprocess.TimeoutExpired:
            time.sleep(3 * (i + 1)); continue
        if p.returncode == 0:
            return p.stdout
        print(f"[warn] rc={p.returncode} {' '.join(args[:4])}: {p.stderr.strip()[:160]}",
              file=sys.stderr)
        time.sleep(3 * (i + 1))
    return ""


def parse_csv(text):
    if not text.strip():
        return []
    lines = text.replace("\r\n", "\n").split("\n")
    for i, ln in enumerate(lines):
        if "," in ln and ln.split(",")[0].strip() in ("id", "ref"):
            text = "\n".join(lines[i:]); break
    else:
        return []
    try:
        return list(csv.DictReader(io.StringIO(text)))
    except csv.Error as e:
        print(f"[warn] csv parse failed: {e}", file=sys.stderr)
        return []


TAG_A = re.compile(r'<a\s[^>]*href=["\']?([^"\'\s>]+)["\']?[^>]*>(.*?)</a>', re.S | re.I)
BLOCK = re.compile(r"</(p|div|li|h[1-6]|tr|pre|blockquote)>", re.I)
BR = re.compile(r"<br\s*/?>", re.I)
LI = re.compile(r"<li[^>]*>", re.I)
TAG = re.compile(r"<[^>]+>")


def strip_html(s):
    s = s or ""
    s = TAG_A.sub(lambda m: f"{TAG.sub('', m.group(2)).strip()} <{m.group(1)}>", s)
    s = BR.sub("\n", s)
    s = LI.sub("\n- ", s)
    s = BLOCK.sub("\n", s)
    s = TAG.sub("", s)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&#x27;", "'")):
        s = s.replace(a, b)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def fetch_topics(max_pages):
    topics = {}
    for page in range(1, max_pages + 1):
        rows = parse_csv(run(["competitions", "topics", "list", SLUG,
                              "--sort-by", "new", "-p", str(page), "-v", "-q"]))
        got = 0
        for r in rows:
            tid = (r.get("id") or "").strip()
            if not tid.isdigit():
                continue
            got += 1
            try:
                cnt = int(float(r.get("commentCount") or 0))
            except ValueError:
                cnt = 0
            topics[tid] = {"id": tid,
                           "title": (r.get("title") or "").strip(),
                           "count": cnt,
                           "votes": (r.get("votes") or "").strip(),
                           "date": (r.get("postDate") or "").strip()[:19]}
        print(f"[page {page}] +{got} (total {len(topics)})", file=sys.stderr)
        if got == 0:
            break
    return topics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="survey/discussions")
    ap.add_argument("--max-pages", type=int, default=30)
    ap.add_argument("--sleep", type=float, default=0.4)
    a = ap.parse_args()

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    topics = fetch_topics(a.max_pages)
    print(f"[topics] {len(topics)}", file=sys.stderr)

    for i, (tid, t) in enumerate(sorted(topics.items(), key=lambda kv: kv[1]["date"]), 1):
        n = max(t["count"] + 5, 10)
        rows = parse_csv(run(["competitions", "topic-messages", SLUG, tid,
                              "--sort-by", "old", "-n", str(n), "-v", "-q"]))
        t["messages"] = [{"id": (r.get("id") or "").strip(),
                          "author": (r.get("authorName") or "").strip(),
                          "date": (r.get("postDate") or "")[:19],
                          "votes": (r.get("votes") or "").strip(),
                          "text": strip_html(r.get("content", ""))} for r in rows]
        t["url"] = URL + tid
        print(f"[{i}/{len(topics)}] {tid} {len(t['messages'])}msg  {t['title'][:60]}",
              file=sys.stderr)
        time.sleep(a.sleep)

    ordered = sorted(topics.values(), key=lambda v: v["date"])
    (out / "discussions.json").write_text(json.dumps(ordered, ensure_ascii=False, indent=1))

    md = [f"# {SLUG} — Discussion 全文ダンプ", f"topics: {len(ordered)}", ""]
    for t in ordered:
        md.append(f"\n\n## [{t['id']}] {t['title']}")
        md.append(f"{t['url']}  | posted {t['date']} | votes {t['votes']} | comments {t['count']}")
        for m in t.get("messages", []):
            md.append(f"\n### — {m['author'] or '(anon)'} ({m['date']}) [+{m['votes']}]")
            md.append(m["text"])
    (out / "discussions.md").write_text("\n".join(md))

    nmsg = sum(len(t.get("messages", [])) for t in ordered)
    print(f"[done] {len(ordered)} topics / {nmsg} messages -> {out}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
