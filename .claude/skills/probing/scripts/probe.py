#!/usr/bin/env python3
"""LB probing helper — language-neutral. Used by the /probing skill.

Subcommands:
  diagnose : from the problem setup (format / metric / metadata / quota),
             print WHICH probing techniques are feasible and their cost
  gen      : build constant-prediction submission CSVs from a sample template
  invert   : given a metric + observed public-LB scores, solve for the
             hidden test statistic (pos_ratio / mean / var / class ratio /
             subset cardinality)

The math + decision logic are derived in survey/papers/lb_probing.md. Keep this
script the single source of truth so formulas/criteria are not re-derived by hand.

Examples
--------
# 0) what probing is even possible here?
python probe.py diagnose --format code --metric dice --group-key-visible yes --quota 5

# 1) make constant submissions at p=0.1 and p=0.9 (LogLoss value probing)
python probe.py gen --sample sample_submission.csv --col target \
    --values 0.1 0.9 --outdir probing/subs

# 2a) value probing: invert returned LB scores
python probe.py invert --metric logloss  --pairs 0.1=0.10536
python probe.py invert --metric rmse     --pairs 0.0=3.21 1.0=2.87
python probe.py invert --metric accuracy --pairs class0=0.62

# 2b) structural probing: how many test samples belong to a subset (e.g. group_id)?
#     base = baseline score, full = score when ALL rows are flipped (calibration),
#     probe = score when ONLY the subset is flipped.
python probe.py invert --metric subset_count --n 110 --base 0.500 --full 1.000 --probe 0.682
"""
import argparse
import csv
import math
import sys
from pathlib import Path

EPS = 1e-15  # Kaggle clips probabilities to [EPS, 1-EPS]


# --------------------------------------------------------------------------- #
# diagnose — judge feasible probing from the problem setup
# --------------------------------------------------------------------------- #
# metrics whose public score is a plain mean over per-sample scores -> enables
# structural / subset-cardinality probing (score moves in ~1/N quantized steps).
# NOTE: global F1/Fbeta are NOT per-sample means (computed from a global confusion
# matrix) -> they go to CONFUSION_METRICS, not here.
PER_SAMPLE_MEAN_METRICS = {"dice", "map", "accuracy", "iou", "mae", "logloss"}
# metrics derived from a global confusion matrix -> confusion-equation probing
# (submit all-positive / all-negative, solve for the positive count P)
CONFUSION_METRICS = {"f1", "fbeta", "f2", "precision", "recall"}
# value-probing recipe per metric
VALUE_PROBE = {
    "logloss":  ("pos_ratio (binary) / per-class ratios (multi)", "1 per class, p!=0.5"),
    "rmse":     ("mean(y), Var(y)",                                "2 (e.g. c=0,1)"),
    "mae":      ("median(y)",                                      "binary search O(log n)"),
    "accuracy": ("per-class ratio",                                "1 per class"),
}


def cmd_diagnose(args):
    fmt = args.format
    metric = args.metric.lower()
    meta = args.group_key_visible == "yes"
    quota = args.quota

    print(f"=== probing feasibility — format={fmt} metric={metric} "
          f"group-key-visible={meta} quota/day={quota} ===\n")

    feasible = []

    # 1) feedback channel ----------------------------------------------------
    if fmt == "docker":
        print("[!] Docker/algorithm-container submission: no fast scalar LB feedback.")
        print("    -> probing is IMPRACTICAL. Stop here unless a public LB exists.\n")
        return
    if fmt not in ("csv", "code"):
        print(f"[!] unknown format '{fmt}', assuming a public LB exists.\n")

    # 2) AUC special-case ----------------------------------------------------
    if metric == "auc":
        print("[x] AUC is rank-based: a constant submission gives no gradient.")
        print("    Global value probing is essentially INFEASIBLE for AUC.")
    # 3) value probing -------------------------------------------------------
    elif metric in VALUE_PROBE:
        info, cost = VALUE_PROBE[metric]
        print(f"[OK] VALUE probing: recover {info}  (cost: {cost})")
        feasible.append("value")
    elif metric in CONFUSION_METRICS:
        print("[OK] CONFUSION probing: recover positive count P / pos_ratio by "
              "submitting all-positive (and all-negative). For F-beta invert "
              "F = (1+b^2)P / ((1+b^2)P + (N-P)). precision(all-pos) == pos_ratio.")
        feasible.append("confusion")
    else:
        print(f"[?] metric '{metric}': value probing recipe unknown; "
              f"if it is a per-sample mean, subset probing still applies.")

    # 4) structural / subset-cardinality probing ----------------------------
    mean_metric = metric in PER_SAMPLE_MEAN_METRICS or args.per_sample_mean == "yes"
    if mean_metric and fmt == "code" and meta:
        print("[OK] STRUCTURAL probing: recover per-group sample counts + membership")
        print("     (metric is a per-sample mean AND a group key is readable at "
              "inference). Resolution ~ 1/N per sample.")
        feasible.append("structural")
    elif mean_metric and not meta:
        print("[~] STRUCTURAL probing needs a test-side group key you can branch on "
              "at inference. Not available -> can only probe globally.")
    elif mean_metric and fmt == "csv":
        print("[~] STRUCTURAL probing usually needs a CODE comp (to read test "
              "metadata). In CSV comps you can still target subsets if the row "
              "order/ids map to known groups.")

    # 4c) ID / structure probing (EDA-level, broadly available) --------------
    print("[OK] ID/STRUCTURE probing: inspect test IDs for a generation rule "
          "(hash / sequential / modular) to split public/private or recover "
          "groups. Low ethical risk (EDA-level), no submission needed.")
    feasible.append("id")

    # 5) row-level probing (ethics flag) ------------------------------------
    if mean_metric:
        print("[GRAY] ROW-LEVEL probing (flip 1 row -> 1 bit of a label) is "
              "technically possible but is usually a DE FACTO RULE VIOLATION. "
              "Confirm with the user; default = do NOT.")

    # 6) quota gate ----------------------------------------------------------
    print()
    if quota is not None:
        print(f"[budget] {quota} submissions/day.")
        if quota <= 2:
            print("         Tight: spend probing carefully; value probing (1-2 subs) "
                  "is the only affordable mode. Structural probing costs ~1 sub/group.")
        else:
            print("         Enough for value probing + a few structural-probing groups.")
    if not feasible:
        print("\n=> No practical probing mode for this setup.")
    else:
        print(f"\n=> Feasible modes: {', '.join(feasible)}. "
              f"See SKILL.md for the matching procedure.")


# --------------------------------------------------------------------------- #
# gen
# --------------------------------------------------------------------------- #
def cmd_gen(args):
    sample = Path(args.sample)
    if not sample.exists():
        sys.exit(f"[gen] sample not found: {sample}")
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    with sample.open() as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = [r for r in reader]

    if args.col not in header:
        sys.exit(f"[gen] column '{args.col}' not in header {header}")
    col_idx = header.index(args.col)

    for v in args.values:
        out = outdir / f"const_{args.col}_{v}.csv"
        with out.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            for r in rows:
                r = list(r)
                r[col_idx] = v
                w.writerow(r)
        print(f"[gen] wrote {out}  ({len(rows)} rows, {args.col}={v})")
    print(f"[gen] done.")
    print(f"[gen] NOTE: in a Code Competition you cannot upload these CSVs directly. "
          f"Put the same constant/conditional logic INSIDE the inference notebook "
          f"(see SKILL.md). These local CSVs are for format-check / CSV competitions.")


# --------------------------------------------------------------------------- #
# invert
# --------------------------------------------------------------------------- #
def _parse_pairs(pairs):
    """'0.1=0.105' -> [(key, score)]. key may be a float (const) or 'classK'."""
    out = []
    for p in pairs:
        if "=" not in p:
            sys.exit(f"[invert] bad pair '{p}', expected key=score")
        k, s = p.split("=", 1)
        out.append((k.strip(), float(s)))
    return out


def invert_logloss(pairs):
    """Binary LogLoss. Constant p submission gives:
        L = -ln(1-p) + r*(ln(1-p) - ln p)   ->   r = (L + ln(1-p)) / (ln(1-p) - ln p)
    p=0.5 is useless (L=ln2 for any r); use p != 0.5.
    """
    results = []
    for k, L in pairs:
        p = float(k)
        if abs(p - 0.5) < 1e-9:
            print(f"[invert] p=0.5 carries no info, skipping")
            continue
        p = min(max(p, EPS), 1 - EPS)
        r = (L + math.log(1 - p)) / (math.log(1 - p) - math.log(p))
        results.append(r)
        print(f"  p={p:<6} L={L:<10} -> pos_ratio = {r:.6f}")
    if results:
        print(f"[invert] pos_ratio estimate = {sum(results)/len(results):.6f} "
              f"(mean of {len(results)} probes)")


def invert_rmse(pairs):
    """RMSE(c)^2 = Var(y) + (mean(y)-c)^2. Two constants solve mean & var.
        mean = [(c1+c2) - (R1^2 - R2^2)/(c1-c2)] / 2
    """
    if len(pairs) < 2:
        sys.exit("[invert] rmse needs >=2 constant probes (e.g. 0.0=.. 1.0=..)")
    (c1, r1), (c2, r2) = (float(pairs[0][0]), pairs[0][1]), (float(pairs[1][0]), pairs[1][1])
    R1, R2 = r1 ** 2, r2 ** 2
    mean = ((c1 + c2) - (R1 - R2) / (c1 - c2)) / 2
    var = R1 - (mean - c1) ** 2
    print(f"  c1={c1} RMSE={r1}   c2={c2} RMSE={r2}")
    print(f"[invert] mean(y) = {mean:.6f}   Var(y) = {var:.6f}   std(y) = "
          f"{math.sqrt(var) if var>=0 else float('nan'):.6f}")


def invert_mae(pairs):
    """MAE(c) = E|y-c|, minimized at the median. Report the lowest-MAE constant
    as the median proxy and hint at binary search."""
    best = min(pairs, key=lambda kv: kv[1])
    print("  MAE samples:", ", ".join(f"c={k}:{s}" for k, s in pairs))
    print(f"[invert] lowest MAE at c={best[0]} -> median(y) ~ {best[0]}. "
          f"Refine with binary search on c around this point.")


def invert_accuracy(pairs):
    """Constant class-k submission -> Accuracy == ratio of class k in test."""
    for k, s in pairs:
        print(f"  const={k}: ratio(class={k}) = {s:.6f}")
    print("[invert] each accuracy IS the class ratio directly.")


def invert_fbeta(args):
    """Confusion-matrix probing for F-beta / precision / recall (binary).
    Submit ALL-POSITIVE (predict 1 for every row): TP=P, FP=N-P, FN=0, so
        F_beta = (1+b^2)P / ((1+b^2)P + (N-P))   ->   P = F*N / (a - F*(a-1)),  a=1+b^2
    precision(all-positive) = P/N = pos_ratio directly.
    Pass the all-positive submission score via --pairs allpos=<score>.
    """
    if args.n is None:
        sys.exit("[invert] fbeta/f1/f2 needs --n (total test rows)")
    if not args.pairs:
        sys.exit("[invert] needs --pairs allpos=<score of the all-positive submission>")
    a = 1 + args.beta ** 2
    _, F = _parse_pairs(args.pairs)[0]
    denom = a - F * (a - 1)
    if abs(denom) < 1e-12:
        sys.exit("[invert] degenerate (check the F-beta value / beta)")
    P = F * args.n / denom
    print(f"  beta={args.beta}  N={args.n}  F_beta(all-positive)={F}")
    print(f"[invert] positive count P = {P:.2f}  -> pos_ratio = {P/args.n:.4f}")
    print(f"  (note: with the precision metric, precision(all-positive) is pos_ratio directly)")


def invert_subset_count(args):
    """Structural probing. For a per-sample-mean metric score = (1/N) sum m_i:
      - flip ALL N rows the same way   -> swing_full = S_full - S_base = d (per-sample delta)
      - flip ONLY the target subset G  -> swing_sub  = S_probe - S_base = (k/N)*d
      => k = N * swing_sub / swing_full
    swing_sub ~ 0  =>  the group is NOT in the test set (0 samples / membership=false).
    """
    N = args.n
    base, full, probe = args.base, args.full, args.probe
    swing_full = full - base
    swing_sub = probe - base
    if abs(swing_full) < 1e-12:
        sys.exit("[invert] full-swing is ~0; bad calibration (flip ALL rows for --full)")
    frac = swing_sub / swing_full
    k = N * frac
    print(f"  N={N}  base={base}  full(all-flip)={full}  probe(subset)={probe}")
    print(f"  per-sample delta d = swing_full = {swing_full:.6g}")
    print(f"  subset swing = {swing_sub:.6g}  -> fraction = {frac:.4f}")
    if abs(k) < 0.5:
        print(f"[invert] subset count ~ 0  => group is NOT in the test set")
    else:
        print(f"[invert] subset count = {k:.3f}  -> {round(k)} samples "
              f"({frac*100:.1f}% of test)")


INVERTERS = {
    "logloss": invert_logloss,
    "rmse": invert_rmse,
    "mae": invert_mae,
    "accuracy": invert_accuracy,
}


def cmd_invert(args):
    if args.metric == "subset_count":
        if None in (args.n, args.base, args.full, args.probe):
            sys.exit("[invert] subset_count needs --n --base --full --probe")
        return invert_subset_count(args)
    if args.metric in ("fbeta", "f1", "f2", "precision", "recall"):
        if args.metric == "f1":
            args.beta = 1.0
        elif args.metric == "f2":
            args.beta = 2.0
        elif args.metric == "precision":
            args.beta = 0.0  # precision(all-positive) = pos_ratio (a=1, denom=1)
        return invert_fbeta(args)
    fn = INVERTERS.get(args.metric)
    if fn is None:
        sys.exit(f"[invert] unsupported metric '{args.metric}'. choices: "
                 f"{list(INVERTERS) + ['subset_count', 'fbeta/f1/f2/precision']}")
    if not args.pairs:
        sys.exit(f"[invert] metric '{args.metric}' needs --pairs")
    fn(_parse_pairs(args.pairs))


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="LB probing helper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("diagnose", help="judge feasible probing from the setup")
    d.add_argument("--format", default="code",
                   help="csv | code | docker (default: code — most Kaggle comps "
                        "this workspace targets are Code Competitions)")
    d.add_argument("--metric", required=True,
                   help="logloss|rmse|mae|accuracy|auc|dice|fbeta|map|iou|other")
    d.add_argument("--group-key-visible", default="no",
                   help="yes if a group key (group_id, patient_id...) is readable "
                        "at inference (code comps)")
    d.add_argument("--per-sample-mean", default="auto",
                   help="yes/no: is the metric a plain mean over per-sample scores? "
                        "(auto-inferred for known metrics)")
    d.add_argument("--quota", type=int, default=None, help="submissions per day")
    d.set_defaults(func=cmd_diagnose)

    g = sub.add_parser("gen", help="generate constant-prediction submissions")
    g.add_argument("--sample", required=True, help="sample_submission.csv path")
    g.add_argument("--col", required=True, help="target column to fill")
    g.add_argument("--values", nargs="+", required=True, help="constant value(s)")
    g.add_argument("--outdir", default="probing/subs")
    g.set_defaults(func=cmd_gen)

    i = sub.add_parser("invert", help="invert observed LB scores to a statistic")
    i.add_argument("--metric", required=True,
                   help="logloss | rmse | mae | accuracy | subset_count | "
                        "fbeta | f1 | f2 | precision")
    i.add_argument("--pairs", nargs="+",
                   help="value probing: key=score pairs, e.g. 0.1=0.105 0.9=2.30; "
                        "confusion probing: allpos=<F-beta of all-positive submission>")
    i.add_argument("--beta", type=float, default=1.0,
                   help="confusion probing: beta for F-beta (f1=>1, f2=>2)")
    # structural (subset_count) probing args:
    i.add_argument("--n", type=int, help="subset_count: total test rows N")
    i.add_argument("--base", type=float, help="subset_count: baseline score")
    i.add_argument("--full", type=float,
                   help="subset_count: score with ALL rows flipped (calibration)")
    i.add_argument("--probe", type=float,
                   help="subset_count: score with ONLY the subset flipped")
    i.set_defaults(func=cmd_invert)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
