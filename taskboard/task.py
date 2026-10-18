#!/usr/bin/env python3
"""Dependency-free local ticket CLI and static HTML board generator."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TICKETS = ROOT / "tickets"
DETAILS = ROOT / "details"
BOARD = ROOT / "board.html"
STATUSES = ("backlog", "ready", "running", "blocked", "review", "done")
DECISIONS = ("undecided", "adopted", "rejected", "hold")
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
REQUIRED = {"id", "title", "status", "type", "priority", "owner", "created_at", "updated_at", "objective", "done_when"}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_json_exclusive(path: Path, data: dict) -> bool:
    """新規チケットを O_EXCL で作る。既にあれば False を返す（上書きしない）。

    `atomic_json` の `os.replace` は「上書きを不可分にする」だけで、上書き自体は防げない。
    2 セッションが同時に `new` を叩くと両方が同じ最大値を読み、後勝ちで片方が黙って消える
    （3 本同時実行で実際に 2 本消えた）。★番号の衝突と同じ read-then-write。
    ID の確保はファイル作成そのものに任せる ＝ O_EXCL なら OS が不可分に決める。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return True


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_all() -> list[dict]:
    TICKETS.mkdir(parents=True, exist_ok=True)
    rows = []
    ids = set()
    for path in sorted(TICKETS.glob("T*.json")):
        with path.open(encoding="utf-8") as f:
            item = json.load(f)
        missing = REQUIRED - item.keys()
        if missing:
            raise ValueError(f"{path}: missing {sorted(missing)}")
        if item["id"] in ids:
            raise ValueError(f"duplicate id: {item['id']}")
        if item["status"] not in STATUSES:
            raise ValueError(f"{path}: invalid status {item['status']}")
        ids.add(item["id"])
        rows.append(item)
    unknown = sorted({d for x in rows for d in x.get("depends_on", [])} - ids)
    if unknown:
        raise ValueError(f"unknown dependencies: {unknown}")
    return rows


def ticket_path(ticket_id: str) -> Path:
    ticket_id = ticket_id.upper()
    if not re.fullmatch(r"T\d{3,}", ticket_id):
        raise ValueError("ticket id must look like T001")
    return TICKETS / f"{ticket_id}.json"


def load_one(ticket_id: str) -> dict:
    path = ticket_path(ticket_id)
    if not path.exists():
        raise ValueError(f"ticket not found: {ticket_id}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def cmd_new(args: argparse.Namespace) -> None:
    rows = load_all()
    stamp = now()
    num = max([int(x["id"][1:]) for x in rows] or [0])
    for _ in range(1000):
        num += 1
        ticket_id = f"T{num:03d}"
        item = {
            "id": ticket_id, "title": args.title, "status": args.status, "type": args.type,
            "priority": args.priority, "owner": args.owner, "created_at": stamp, "updated_at": stamp,
            "objective": args.objective or "TBD", "done_when": args.done_when or "成果物・評価・台帳更新が完了",
            "run_ids": [], "depends_on": [], "labels": [], "checklist": [], "result": "",
            "decision": "undecided", "links": [], "notes": ""
        }
        # 取られていたら次の番号へ。同時実行でも OS が 1 人だけに勝たせる
        if create_json_exclusive(ticket_path(ticket_id), item):
            break
    else:
        raise ValueError("チケット ID を確保できなかった（tickets/ を確認）")
    DETAILS.mkdir(parents=True, exist_ok=True)
    detail = DETAILS / f"{ticket_id}.md"
    if not detail.exists():
        # 状態・目的・完了条件は **JSON が正**。ここに写すと必ず片方が腐るので書かない
        # （★番号の二重定義、外部ボードの Status 固着と同じ構図）。
        detail.write_text(
            f"# {ticket_id}: {args.title}\n\n"
            f"> 状態・owner・優先度・完了条件・checklist は `tickets/{ticket_id}.json` が正。\n"
            f"> `python3 taskboard/task.py show {ticket_id}` で見る。ここには**書き写さない**。\n"
            f"> このファイルは検討過程・実測値・根拠・判断の正本（`AGENTS.md` §チケット詳細ファイル）。\n\n"
            "## 検討ログ\n\n- チケット作成。\n\n"
            "## 実測\n\n- 未記入（数値は必ず出典のコマンド／ファイルとセットで書く）\n\n"
            "## 解釈・判断\n\n- 未決定\n\n"
            "## 未決事項\n\n- 未記入\n\n"
            "## 次の一手\n\n- 未記入\n"
            f"\n> 次の一手を書き換えたら `task.py update {ticket_id} --first-step \"...\"` も揃える。\n"
            "> board のカードに出るのは `first_step` のほう。\n",
            encoding="utf-8",
        )
    item = load_one(ticket_id)
    item.setdefault("links", []).append(f"taskboard/details/{ticket_id}.md")
    atomic_json(ticket_path(ticket_id), item)
    build(load_all())
    print(ticket_id)


def cmd_update(args: argparse.Namespace) -> None:
    item = load_one(args.id)
    for key in ("title", "status", "type", "priority", "owner", "objective", "done_when", "result", "decision", "notes"):
        value = getattr(args, key, None)
        if value is not None:
            item[key] = value
    # 追記系（重複は足さない）。first_step は「次に叩く 1 コマンド」を 1 本だけ持つ
    for opt, field in (("run_id", "run_ids"), ("link", "links"), ("label", "labels"), ("depends_on", "depends_on")):
        for value in getattr(args, opt, None) or []:
            if value not in item.setdefault(field, []):
                item[field].append(value)
    if getattr(args, "first_step", None) is not None:
        item["first_step"] = args.first_step
    item["updated_at"] = now()
    atomic_json(ticket_path(item["id"]), item)
    build(load_all())
    print(f"updated {item['id']}")


def cmd_step(args: argparse.Namespace) -> None:
    """チェックリストの項目そのものを増減する（`check` は既存項目の on/off だけ）。"""
    item = load_one(args.id)
    checks = item.setdefault("checklist", [])
    if args.action == "add":
        for text in args.text:
            checks.append({"text": text, "done": False})
    else:
        index = args.index - 1
        if index < 0 or index >= len(checks):
            raise ValueError(f"index must be 1..{len(checks)}")
        checks.pop(index)
    item["updated_at"] = now()
    atomic_json(ticket_path(item["id"]), item)
    build(load_all())
    print(f"{item['id']} checklist: {len(checks)} 項目")


def cmd_close(args: argparse.Namespace) -> None:
    item = load_one(args.id)
    item.update(status="done", result=args.result, decision=args.decision, updated_at=now())
    atomic_json(ticket_path(item["id"]), item)
    build(load_all())
    print(f"closed {item['id']}")


def cmd_check(args: argparse.Namespace) -> None:
    item = load_one(args.id)
    checks = item.setdefault("checklist", [])
    index = args.index - 1
    if index < 0 or index >= len(checks):
        raise ValueError(f"check index must be 1..{len(checks)}")
    checks[index]["done"] = not args.undo
    item["updated_at"] = now()
    atomic_json(ticket_path(item["id"]), item)
    build(load_all())
    print(f"{item['id']} check {args.index}: {'open' if args.undo else 'done'}")


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def build(rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda x: (STATUSES.index(x["status"]), PRIORITY_ORDER.get(x["priority"], 9), x["id"]))
    data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    counts = {s: sum(x["status"] == s for x in rows) for s in STATUSES}
    cards = []
    for x in rows:
        checks = x.get("checklist", [])
        done = sum(bool(c.get("done")) for c in checks)
        total = len(checks)
        tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in x.get("labels", []))
        runs = ", ".join(x.get("run_ids", [])) or "—"
        deps = ", ".join(x.get("depends_on", [])) or "—"
        detail_file = DETAILS / f"{x['id']}.md"
        detail_link = f'<a class="detail" href="details/{esc(x["id"])}.md">詳細</a>' if detail_file.exists() else ""
        cards.append(f'''<article class="card p-{esc(x['priority'])}" data-status="{esc(x['status'])}" data-owner="{esc(x['owner'])}" data-type="{esc(x['type'])}" data-priority="{esc(x['priority'])}" data-search="{esc(json.dumps(x, ensure_ascii=False).lower())}">
<div class="cardtop"><b>{esc(x['id'])}</b><span>{detail_link} <span class="priority">{esc(x['priority'])}</span></span></div>
<h3>{esc(x['title'])}</h3><p>{esc(x['objective'])}</p>
<div class="meta"><span>👤 {esc(x['owner'])}</span><span>◈ {esc(x['type'])}</span><span>⚗ {esc(runs)}</span></div>
<div class="progress"><i style="width:{(done/total*100) if total else 0:.0f}%"></i></div><small>{done}/{total} checklist · depends: {esc(deps)}</small>
{('<pre class="first">▶ ' + esc(x['first_step']) + '</pre>') if x.get('first_step') else ''}
{('<ul class="steps">' + ''.join(f'<li class={chr(34)}{chr(100) if c.get(chr(100)+chr(111)+chr(110)+chr(101)) else chr(111)}{chr(34)}>' + esc(c['text']) + '</li>' for c in checks) + '</ul>') if checks else ''}
<div class="tags">{tags}</div><details><summary>完了条件・結果</summary><p><b>Done:</b> {esc(x['done_when'])}</p><p><b>Result:</b> {esc(x.get('result') or '—')}</p><p><b>Decision:</b> {esc(x.get('decision', 'undecided'))}</p><p>{esc(x.get('notes', ''))}</p></details>
</article>''')
    columns = "".join(f'<section class="column"><header><span>{s}</span><b>{counts[s]}</b></header><div class="stack" data-column="{s}"></div></section>' for s in STATUSES)
    template = '''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Local Taskboard</title>
<style>:root{--bg:#0b1020;--panel:#131a2c;--card:#1a2338;--text:#e8edf7;--muted:#8f9bb3;--accent:#7dd3fc}*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#080c18,#111932);color:var(--text);font:14px system-ui,sans-serif}nav{position:sticky;top:0;z-index:2;padding:18px 24px;background:#0b1020e8;backdrop-filter:blur(12px);border-bottom:1px solid #27324b}h1{margin:0 0 12px;font-size:21px}.controls{display:flex;gap:8px;flex-wrap:wrap}input,select{background:#121a2d;color:var(--text);border:1px solid #34415f;border-radius:8px;padding:9px 11px}input{min-width:260px}.summary{color:var(--muted);margin-left:auto;padding:9px}.board{display:grid;grid-template-columns:repeat(6,minmax(260px,1fr));gap:12px;padding:16px;overflow-x:auto}.column{background:#0d1425;border:1px solid #222e48;border-radius:12px;min-height:70vh}.column>header{display:flex;justify-content:space-between;padding:12px;text-transform:uppercase;color:var(--accent);border-bottom:1px solid #222e48}.column>header b{background:#24314d;border-radius:99px;padding:1px 8px}.stack{padding:9px}.card{background:var(--card);border:1px solid #2a3858;border-left:4px solid #64748b;border-radius:10px;padding:12px;margin-bottom:9px;box-shadow:0 5px 15px #0003}.p-critical{border-left-color:#fb7185}.p-high{border-left-color:#fbbf24}.p-medium{border-left-color:#60a5fa}.p-low{border-left-color:#94a3b8}.cardtop,.meta{display:flex;gap:8px;justify-content:space-between;color:var(--muted)}h3{font-size:15px;margin:8px 0}.card p{color:#c7d0e2;line-height:1.45}.priority,.tag{font-size:11px;background:#283653;border-radius:99px;padding:2px 7px}.meta{justify-content:flex-start;flex-wrap:wrap;font-size:12px}.progress{height:4px;background:#303a51;margin:10px 0 5px;border-radius:9px;overflow:hidden}.progress i{display:block;height:100%;background:#34d399}.tags{display:flex;gap:4px;flex-wrap:wrap;margin-top:8px}details{margin-top:8px;color:var(--muted)}.first{background:#0f1a2e;border:1px solid #2f4468;border-radius:6px;padding:6px 8px;margin:8px 0 0;white-space:pre-wrap;word-break:break-all;font-size:11px;color:#7dd3fc}.steps{margin:8px 0 0;padding-left:18px;font-size:12px;color:#c7d0e2}.steps li.d{color:#6b7a94;text-decoration:line-through}.hidden{display:none!important}@media(max-width:900px){.board{grid-template-columns:repeat(6,280px)}.summary{width:100%;margin:0}}</style></head><body>
<nav><h1>Local Taskboard</h1><div class="controls"><input id="q" placeholder="検索: run, label, owner..."><select id="owner"><option value="">all owners</option></select><select id="type"><option value="">all types</option></select><select id="priority"><option value="">all priorities</option><option>critical</option><option>high</option><option>medium</option><option>low</option></select><span class="summary" id="summary"></span></div></nav>
<main class="board">__COLUMNS__</main><div id="cards" hidden>__CARDS__</div><script id="tickets" type="application/json">__DATA__</script>
<script>const cards=[...document.querySelectorAll('.card')],qs=id=>document.getElementById(id);for(const k of ['owner','type']){[...new Set(cards.map(c=>c.dataset[k]))].sort().forEach(v=>qs(k).add(new Option(v,v)))}function render(){document.querySelectorAll('.stack').forEach(x=>x.innerHTML='');let n=0;for(const c of cards){const ok=(!qs('q').value||c.dataset.search.includes(qs('q').value.toLowerCase()))&&(!qs('owner').value||c.dataset.owner===qs('owner').value)&&(!qs('type').value||c.dataset.type===qs('type').value)&&(!qs('priority').value||c.dataset.priority===qs('priority').value);c.classList.toggle('hidden',!ok);if(ok){document.querySelector(`[data-column="${c.dataset.status}"]`).append(c);n++}}qs('summary').textContent=`${n} / ${cards.length} tickets`}document.querySelectorAll('input,select').forEach(x=>x.addEventListener('input',render));render()</script></body></html>'''
    BOARD.write_text(template.replace("__COLUMNS__", columns).replace("__CARDS__", "".join(cards)).replace("__DATA__", data), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    show = sub.add_parser("show"); show.add_argument("id")
    new = sub.add_parser("new"); new.add_argument("--title", required=True); new.add_argument("--type", default="task"); new.add_argument("--priority", choices=PRIORITY_ORDER, default="medium"); new.add_argument("--owner", default="unassigned"); new.add_argument("--status", choices=STATUSES, default="backlog"); new.add_argument("--objective"); new.add_argument("--done-when")
    up = sub.add_parser("update"); up.add_argument("id");
    for k in ("title", "type", "owner", "objective", "done_when", "result", "notes"): up.add_argument(f"--{k.replace('_','-')}")
    up.add_argument("--status", choices=STATUSES); up.add_argument("--priority", choices=PRIORITY_ORDER); up.add_argument("--decision", choices=DECISIONS)
    up.add_argument("--first-step", help="次に叩く 1 コマンド / 開く 1 ファイル")
    for k in ("run-id", "link", "label", "depends-on"): up.add_argument(f"--{k}", action="append")
    step = sub.add_parser("step"); step.add_argument("action", choices=("add", "rm")); step.add_argument("id")
    step.add_argument("text", nargs="*"); step.add_argument("--index", type=int, default=0)
    close = sub.add_parser("close"); close.add_argument("id"); close.add_argument("--result", required=True); close.add_argument("--decision", choices=DECISIONS[1:], required=True)
    check = sub.add_parser("check"); check.add_argument("id"); check.add_argument("index", type=int); check.add_argument("--undo", action="store_true")
    sub.add_parser("build")
    args = p.parse_args()
    try:
        if args.cmd == "new": cmd_new(args)
        elif args.cmd == "update": cmd_update(args)
        elif args.cmd == "close": cmd_close(args)
        elif args.cmd == "check": cmd_check(args)
        elif args.cmd == "step": cmd_step(args)
        elif args.cmd == "build": build(load_all()); print(BOARD)
        elif args.cmd == "show": print(json.dumps(load_one(args.id), ensure_ascii=False, indent=2))
        else:
            for x in load_all(): print(f"{x['id']}\t{x['status']:<8}\t{x['priority']:<8}\t{x['owner']:<10}\t{x['title']}")
    except (ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr); raise SystemExit(2)


if __name__ == "__main__": main()
