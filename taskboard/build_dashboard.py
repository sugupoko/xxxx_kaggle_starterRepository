#!/usr/bin/env python3
"""タスク・実験の全体状況ダッシュボード（taskboard/dashboard.html）を生成する。

board.html（チケット一覧）とは役割が違う:
  board.html      … チケット 1 枚ずつの詳細を引く「台帳ビュー」
  dashboard.html  … いま何が動いていて、何が詰まっていて、どのレバーが効いたかを
                    一望する「状況ビュー」

⚠️ この 2 つの原則を構造として強制している（AGENTS.md §全体像を見るとき）:
  1. **教師（ラベル）・fold・val 件数が違う run は同じ表に並べない。** 指標は
     「その教師に対する順位」でしかない。run は (教師, fold, val 件数) の土俵ごとに別表にする。
  2. **seed 幅より小さい差を「勝ち」と呼ばない。** SEED_BAND（同一 config・seed 違いの
     実測幅）を設定すると、土俵内の最良値から帯の中にある run を「差なし」と表示する。

run は workspace/**/training_log.json をその場で走査する（中間ファイルを挟まない）。
キー名はコンペの学習コードに合わせて下の定数を直す。run が 0 件でも落ちない。

  python3 taskboard/build_dashboard.py
"""
from __future__ import annotations

import html
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = HERE / "dashboard.html"

# ── 学習コードの training_log.json に合わせて直す ─────────────────────────
METRIC_KEY = "best_score"        # 主指標（float）。無い run は集計対象外
HIGHER_IS_BETTER = True
TEACHER_KEY = "labels_csv"       # 教師（ラベル）ファイル。パスなら basename で比較する
FOLD_KEY = "fold"
N_VAL_KEY = "n_val"              # val 件数
EXP_KEY = "experiment"
SEED_BAND: float | None = None   # 同一 config・seed 違いの実測幅。複数あれば広いほうを入れる
# ──────────────────────────────────────────────────────────────────────────

STAGES = ["backlog", "ready", "running", "blocked", "review", "done"]
PRIO_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
STALE_DAYS = 1                   # running / review がこれ以上更新されないと要注意に出す

log = logging.getLogger("dashboard")


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def collect_tickets() -> list[dict]:
    tickets = []
    for f in sorted((HERE / "tickets").glob("T*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        ck = d.get("checklist") or []
        tickets.append(dict(
            id=d["id"], title=d.get("title", ""), status=d["status"], prio=d.get("priority", "medium"),
            owner=d.get("owner") or "unassigned", done=sum(1 for c in ck if c.get("done")), tot=len(ck),
            upd=d.get("updated_at") or "", raw=json.dumps(d, ensure_ascii=False)))
    return tickets


def collect_runs() -> list[dict]:
    runs = []
    for p in sorted((REPO / "workspace").glob("**/training_log.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            # 書き込み途中の run があり得る。落とさず、どれを飛ばしたかは必ず出す
            log.warning("skip (JSON 不正): %s: %s", p.relative_to(REPO), e)
            continue
        if not isinstance(d, dict) or not isinstance(d.get(METRIC_KEY), (int, float)):
            continue
        runs.append(dict(
            exp=d.get(EXP_KEY) or p.parent.name, folder=p.relative_to(REPO / "workspace").parts[0],
            score=float(d[METRIC_KEY]), teacher=Path(str(d.get(TEACHER_KEY, "?"))).name,
            fold=d.get(FOLD_KEY, "?"), n_val=d.get(N_VAL_KEY, "?"), path=str(p.relative_to(REPO))))
    return runs


def stale_days(t: dict, now: datetime) -> int:
    if not t["upd"]:
        return 0
    return (now - datetime.fromisoformat(t["upd"])).days


def alerts_for(tickets: list[dict], now: datetime) -> list[tuple[dict, str]]:
    out = []
    for t in tickets:
        d = stale_days(t, now)
        if t["status"] == "running" and d >= STALE_DAYS:
            out.append((t, f"running のまま {d} 日更新なし。実プロセス・状態ファイル・ログを見て review か ready へ"))
        elif t["status"] == "review" and d >= STALE_DAYS:
            out.append((t, f"review のまま {d} 日。採否を決めて done か backlog へ"))
        elif t["status"] == "blocked":
            out.append((t, "blocked。解除条件が notes / 詳細に書かれているか確認"))
        elif t["prio"] == "critical" and t["status"] in ("backlog", "ready") and t["done"] == 0:
            out.append((t, f"critical なのに未着手（{d} 日）"))
        elif t["status"] == "ready" and '"first_step"' not in t["raw"]:
            out.append((t, "ready なのに first_step が無い（着手できない）"))
    return sorted(out, key=lambda a: (PRIO_RANK.get(a[0]["prio"], 9), a[0]["id"]))


def run_tables(runs: list[dict]) -> str:
    groups: dict[tuple, list] = {}
    for r in runs:
        groups.setdefault((r["teacher"], r["fold"], r["n_val"]), []).append(r)
    if not groups:
        return (f'<p class="muted">training_log.json に <code>{esc(METRIC_KEY)}</code> を持つ run がまだ無い'
                f'（キー名は build_dashboard.py 冒頭の定数で合わせる）。</p>')
    parts = []
    for (tea, fold, n), rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        rs.sort(key=lambda r: r["score"], reverse=HIGHER_IS_BETTER)
        best = rs[0]["score"]
        rows = []
        for r in rs:
            delta = r["score"] - best
            if SEED_BAND is None:
                verdict = "—"
            elif r is rs[0]:
                verdict = "最良"
            elif abs(delta) <= SEED_BAND:
                verdict = "差なし（seed 幅内）"
            else:
                verdict = "劣る"
            rows.append(f'<tr><td class="mono">{esc(r["exp"])}</td><td class="mono num">{r["score"]:.5f}</td>'
                        f'<td class="mono num">{delta:+.5f}</td><td>{esc(verdict)}</td>'
                        f'<td class="mono small">{esc(r["path"])}</td></tr>')
        parts.append(
            f'<h3>土俵: 教師 <code>{esc(tea)}</code> / fold {esc(fold)} / val {esc(n)} 件 — {len(rs)} 本</h3>'
            '<div class="scroll"><table><thead><tr><th>run</th><th>score</th><th>最良との差</th>'
            f'<th>判定</th><th>出典</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
    note = ("" if SEED_BAND is not None else
            '<p class="muted">SEED_BAND 未設定のため「差なし」判定は出していない。同一 config・seed 違いの実測幅を入れること。</p>')
    return note + "".join(parts)


def untracked(tickets: list[dict], runs: list[dict]) -> list[tuple[str, int]]:
    """完了 run はあるのに、どのチケットからも参照されていない実験フォルダ。"""
    blob = " ".join(t["raw"] for t in tickets)
    folders = Counter(r["folder"] for r in runs)
    return [(f, n) for f, n in sorted(folders.items()) if f not in blob and f.split("_")[0] not in blob]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    now = datetime.now(timezone.utc)
    tickets, runs = collect_tickets(), collect_runs()
    st = Counter(t["status"] for t in tickets)
    owners = sorted({t["owner"] for t in tickets})
    mx = max(st.values(), default=0) or 1

    pipe = "".join(
        f'<div class="prow"><div class="plab">{s}</div><div class="ptrack">'
        f'<div class="pbar" style="width:{st[s] / mx * 100:.1f}%"></div><span class="pval">{st[s]}</span></div></div>'
        for s in STAGES)
    own_rows = "".join(
        f'<tr><td>{esc(o)}</td>' + "".join(f'<td class="mono num">{sum(1 for t in tickets if t["owner"] == o and t["status"] == s)}</td>' for s in STAGES) + '</tr>'
        for o in owners)
    alert_html = "".join(
        f'<li><b class="mono">{esc(t["id"])}</b> <span class="pill">{esc(t["prio"])}</span> {esc(t["title"])}'
        f'<div class="why">{esc(why)}</div></li>' for t, why in alerts_for(tickets, now)
    ) or '<li class="ok">状態と実態のズレは検出されなかった</li>'
    orphans = untracked(tickets, runs)
    orphan_html = ("".join(f'<li class="mono">{esc(f)}（run {n} 本）</li>' for f, n in orphans)
                   or '<li class="ok">すべての実験フォルダがどれかのチケットから参照されている</li>')

    doc = f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>タスク・実験ダッシュボード</title>
<style>
:root{{--bg:#f7f8fa;--panel:#fff;--text:#1d2433;--muted:#5b6578;--line:#dde2ea;--bar:#2a78d6;--warn:#b45309;--ok:#15803d}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0e1320;--panel:#161d2e;--text:#e6ebf5;--muted:#9aa5bb;--line:#2a3550;--bar:#6da7ec;--warn:#fbbf24;--ok:#4ade80}}}}
*{{box-sizing:border-box}}body{{margin:0;padding:24px 16px;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,sans-serif}}
main{{max-width:1100px;margin:0 auto;display:grid;gap:16px}}.card{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px}}
h1{{font-size:20px;margin:0}}h2{{font-size:16px;margin:0 0 10px}}h3{{font-size:14px;margin:16px 0 6px}}.muted,.sub{{color:var(--muted)}}
.prow{{display:flex;align-items:center;gap:10px;margin:4px 0}}.plab{{width:80px;color:var(--muted)}}.ptrack{{flex:1;display:flex;align-items:center;gap:8px}}
.pbar{{height:14px;background:var(--bar);border-radius:3px;min-width:2px}}.pval{{font-variant-numeric:tabular-nums}}
table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid var(--line);padding:5px 8px;text-align:left}}.num{{text-align:right}}
.mono{{font-family:ui-monospace,monospace;font-variant-numeric:tabular-nums}}.small{{font-size:12px;color:var(--muted)}}.scroll{{overflow-x:auto}}
ul{{padding-left:18px;margin:0}}li{{margin:6px 0}}.why{{color:var(--warn);font-size:13px}}.ok{{color:var(--ok)}}
.pill{{font-size:11px;border:1px solid var(--line);border-radius:99px;padding:1px 7px}}
</style></head><body><main>
<div><h1>タスク・実験ダッシュボード</h1><p class="sub">生成 {now:%Y-%m-%d %H:%M} UTC ・ チケット {len(tickets)} 件 ・ run {len(runs)} 本</p></div>
<section class="card"><h2>パイプライン</h2>{pipe}</section>
<section class="card"><h2>要注意（状態と実態のズレ・詰まり）</h2><ul>{alert_html}</ul></section>
<section class="card"><h2>担当別</h2><div class="scroll"><table><thead><tr><th>owner</th>{"".join(f"<th class='num'>{s}</th>" for s in STAGES)}</tr></thead><tbody>{own_rows}</tbody></table></div></section>
<section class="card"><h2>run（土俵ごとに別表）</h2><p class="sub">教師・fold・val 件数が違う run は同じ物差しではないので並べない。</p>{run_tables(runs)}</section>
<section class="card"><h2>チケットから参照されていない実験フォルダ</h2><ul>{orphan_html}</ul></section>
</main></body></html>"""
    OUT.write_text(doc, encoding="utf-8")
    log.info("wrote %s", OUT.relative_to(REPO))


if __name__ == "__main__":
    main()
