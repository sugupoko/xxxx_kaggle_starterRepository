---
name: probing
description: Run leaderboard probing (LB probing). First diagnose which kinds of probing the problem setup allows, then choose between "value probing" (constant submissions to back out public-test distribution — pos_ratio / mean / class ratios) and "structural probing" (back out per-group structure such as per-group sample counts and membership for group_id / patient_id etc.). **Defaults to Kaggle Code Competition** (submission = notebook run). Check the submission quota and rules before using.
argument-hint: "[start with metric logloss|rmse|mae|accuracy / leave empty to infer from KAGGLE_DIRECTION.md]"
---

# Leaderboard Probing Skill

A public LB score is an "aggregate statistic of the test set", so carefully designed submissions let you back out hidden test information from the returned score. This skill **(1) diagnoses which probing is possible from the problem setup** and **(2) runs it safely in the appropriate mode**.

For detailed principles, per-metric formulas, past cases and decision tables see `survey/papers/lb_probing.md` (if it doesn't exist, create it first with `/survey-papers leaderboard probing` or the kaggle-researcher agent).

> **Premise: defaults to Kaggle Code Competition.**
> In a Code Competition you **cannot upload a CSV directly; submissions are notebook runs**.
> Write the probing logic (constant / conditional predictions) **inside the inference notebook**. Building a CSV locally and uploading it is only for CSV Competitions.
> For the submission flow (Dataset upload → Notebook push → Save & Run All → Submit) see `tools/kaggle_code_competition_submission.md`.

## The 4 probing modes

| Mode | Information obtained | Preconditions |
|--------|-----------|---------|
| **A. Value probing** | Whole-test statistics (pos_ratio / mean / Var / class ratios) | A public LB exists. The metric responds to constant submissions (AUC does not) |
| **B. Structural probing** | Per-group sample counts and membership (e.g. count per group_id, present/absent in test) | **Code competition** where the test-side group key is visible at inference + the metric is a **per-sample mean** (moves in 1/N steps) |
| **C. Confusion-matrix probing** | Number of positives P / pos_ratio (from TP/FP/FN) | The metric is **F1 / F2 / Fβ / precision / recall** (computed from a global confusion matrix) |
| **D. ID/structure probing** | Public/private split, group structure (no submission needed) | Test **IDs follow a generation rule** (hash / sequential / modular). An extension of EDA; low ethical risk |

Because test metadata is readable at inference in a Code Competition, **A–D can be combined** (B in particular only works in code competitions). Sources: `survey/papers/lb_probing.md` §12 (C = bilzard's method / D = Ringa_hyj's method).

## Procedure

### Step 1. Feasibility diagnosis (precondition check — never skip)

Before implementing anything, always determine "what is possible in the first place". **Unless told otherwise, treat it as a Code Competition.**

1. **Submission format**: check `survey/competition/overview.md` (default: Code Competition)
   - **Code Competition (default)** → value probing **+ structural probing** possible. Submissions are notebook runs
   - CSV Competition → value probing is practical (build a constant CSV locally and upload directly)
   - Docker / no public LB → feedback is slow, probing **not recommended**
2. **Metric**: check the evaluation metric
   - LogLoss / RMSE / MAE / Accuracy → recoverable with value probing (mode A)
   - F1 / F2 / Fβ / precision / recall → recover the number of positives P with confusion-matrix probing (mode C)
   - Per-sample means (Dice / mAP / IoU / accuracy etc.) → structural probing (mode B) works well
   - **AUC → does not respond to constant submissions, probing is practically impossible**
3. **Group-key visibility**: can the inference notebook read test-side keys such as group_id / patient_id and branch on them (mode B)
   - Also check the test **ID scheme** (hash, sequential) → mode D (ID/structure probing) works without submitting
4. **Submission quota**: check the daily quota. Probing consumes quota, so make the trade-off against model submissions explicit
5. **Rules**: make sure probing is not prohibited by the competition rules. Learning the distribution via constant submissions is usually allowed. **Row-level probing to obtain all labels can be a de facto violation.** If it's gray, **ask the user to decide**

The diagnosis can be delegated to the helper (`--format` defaults to code):
```bash
python .claude/skills/probing/scripts/probe.py diagnose --metric dice --group-key-visible yes --quota 5
# → prints feasible modes (value / structural), costs and caveats
```

### Step 2. Choose a mode

Pick A / B based on the diagnosis. If both are possible, choose by goal (want the overall distribution → A; want the test composition → B).

---

### Mode A: Value probing (whole-test statistics)

**2A-1. Metric and number of submissions needed**:

| Metric | Constant to submit | Recoverable information | Submissions needed |
|------|------------|--------------|-----------|
| LogLoss (binary) | e.g. p=0.1 (**p≠0.5**) | pos_ratio | 1 |
| LogLoss (multi-class) | each class on all rows | per-class ratio | number of classes |
| RMSE | two points c=0.0, 1.0 | mean(y), Var(y) | 2 |
| MAE | search for the minimizing constant | median(y) | binary search O(log n) |
| Accuracy | all rows = class k | ratio of class k | number of classes |
| AUC | — | hard to recover directly | not recommended |

**2A-2. Build the submission**:

- **Code Competition (default)** — inside the inference notebook, ignore the input and output a constant for every row:
  ```python
  # replace the prediction part of inference_notebook.py for probing
  sub = pd.read_csv(SAMPLE_SUB)
  sub[TARGET] = 0.1            # constant (for LogLoss, p != 0.5)
  sub.to_csv("submission.csv", index=False)
  assert len(sub) == EXPECTED_ROWS
  ```
  Then push → Save & Run All → Submit following `tools/kaggle_code_competition_submission.md`.

- For a CSV Competition — generate constant CSVs locally and upload directly:
  ```bash
  python .claude/skills/probing/scripts/probe.py gen \
    --sample <sample_submission.csv> --col <target column> \
    --values 0.1 0.9 --outdir probing/subs
  ```
  Outputs go to `probing/subs/` (gitignored — they are submissions themselves, don't commit). The `const_*` file names distinguish them from model submissions.

**2A-3. Invert**:
```bash
python .claude/skills/probing/scripts/probe.py invert --metric logloss --pairs 0.1=<score>
# for rmse: --metric rmse --pairs 0.0=<score> 1.0=<score>
```

---

### Mode B: Structural probing (per-group counts and membership)

**Principle**: when the metric is `score = (1/N) Σ m_i` (a per-sample mean), changing the predictions for only some samples moves the score in proportion to the number of samples. With N=110, one sample ≈ a 0.9% quantization step, so **integer counts can be read off**. Requires that test-side metadata is visible in a Code Competition.

**2B-1. Write predictions conditioned on the group key in the inference notebook**:
```python
# inference_notebook.py — measure the count per group_id
sub = pd.read_csv(SAMPLE_SUB)
mask = (meta["group_key"] == TARGET_GROUP)   # branch on metadata visible at inference
sub.loc[mask,  TARGET] = FLIPPED              # change only this subset
sub.loc[~mask, TARGET] = BASELINE
sub.to_csv("submission.csv", index=False)
```
- First submit two notebooks: **all rows BASELINE** (base score) and **all rows FLIPPED** (full score = calibration)
- Then submit, per group, a notebook with **only TARGET_GROUP FLIPPED**

**2B-2. Back out counts and membership**:
```bash
python .claude/skills/probing/scripts/probe.py invert --metric subset_count \
  --n 110 --base <base score> --full <all-flip score> --probe <subset-flip score>
# → subset count = k (fraction %); swing≈0 means "not present in test"
```
- `k = N × (probe - base) / (full - base)`. `full - base` is the per-sample delta d
- A subset swing of ≈0 → that group is **not in test (0 samples)**
- Check that the per-group counts sum to N (e.g. with N=110, group A 78 + group B 32 = 110 means it closes)

---

### Mode C: Confusion-matrix probing (F1 / F2 / Fβ / precision / recall)

**Principle** (source: bilzard §12-A): F-scores are computed from a global confusion matrix (TP/FP/FN), so a single constant submission can't be inverted directly — but **submitting all rows as positive** fixes `TP=P, FP=N-P, FN=0`, making the F-score a function of the number of positives P alone:
```
F_beta(all=1) = (1+β²)·P / ((1+β²)·P + (N-P))   →   P = F·N / (a - F·(a-1)),  a = 1+β²
precision(all=1) = P/N = pos_ratio              (one shot for precision)
```

**C-1. Build an all-rows-positive submission** (in a Code Comp, `sub[TARGET]=1` inside the inference notebook)

**C-2. Back out the number of positives P**:
```bash
python .claude/skills/probing/scripts/probe.py invert --metric f1 --n <total rows> --pairs allpos=<F1 score>
# for f2 use --metric f2; for general Fβ use --metric fbeta --beta <β>
```
- Combined with an all-rows-negative submission you can separate per-subgroup precision/recall and fully reconstruct the confusion matrix (the key is designing multiple independent operations)

---

### Mode D: ID/structure probing (no submission needed, EDA level)

**Principle** (source: Ringa_hyj §12-B/C, Instant Gratification): reverse-engineering the test **ID generation rule** (MD5 hash, sequential, modular) can identify the public/private split or group structure without a single submission. Ethical risk is low (an extension of ordinary EDA).

**D-1. Inspect test IDs/metadata**: are the IDs sequential, hashed, or split modulo some variable (e.g. 512 groups from `wheezy-copper-turtle-magic` 0–511)?

**D-2. Test a hypothesis about the generation rule**: e.g. if you suspect "ID = md5(str(i)+'test')", check whether the rule reproduces it:
```python
import hashlib
cand = [hashlib.md5(f"{i}test".encode()).hexdigest() for i in range(EXPECTED)]
# compare against the set of test IDs
```

**D-3. Use it**: knowing the public/private boundary helps avoid overfitting the public LB; knowing the group structure lets you switch to within-group modeling. The biggest advantage is that **it consumes no submission quota**.

---

### Step 3. Submissions are manual by the user (all modes)

- Claude **does not perform** Code Competition submissions (Save & Run All → "Submit to Competition") or CSV uploads. Ask: "Please submit this notebook / CSV and tell me the public LB score you get"
- Present a **mapping table** so that which constant / which group produced which score isn't mixed up
- In a Code Competition each submission costs notebook run time. Watch not only the number of submissions but also the **run-time limit**

### Step 4. Record and use (all modes)

- Append the results to `survey/competition/probing_log.md` (create it if missing). Template:
  ```markdown
  ## probing YYYY-MM-DD — <mode> / <metric>
  - A value: const=<value> → LB=<score> → pos_ratio/mean=<value>
  - B structure: group=<key> → count=<k> / membership=<present/absent> / total N=<>
  - C confusion matrix: all=1 → F=<score> → positives P=<value> / pos_ratio=<value>
  - D-ID: rule=<hash/sequential/modular> → public/private split or group structure=<...>
  - Interpretation: difference from the train distribution, impact on CV design, public LB noise assessment
  ```
- **Propose how to use it** (solid + explosive):
  - Solid: use the recovered distribution/composition as the basis for post-calibration / **weight CV to match the test composition** / identify public LB noise (small groups) to avoid overreacting / explain CV–LB gaps
  - Explosive: after checking the rules, add the recovered labels as pseudo labels for training (more accurate than usual)

## Caveats

- **Row-level probing (flipping one row at a time to obtain every label) can be a de facto rule violation.** Always confirm with the user before doing it, and stop if it's gray
- A LogLoss submission with p=0.5 carries zero information (same score for any pos_ratio). **Use p≠0.5**
- Structural probing requires that **the metric is a per-sample mean** and **the group key is visible at inference**. It doesn't work for AUC or rank-based metrics
- In a Code Competition submissions are notebook runs, so write constant / conditional predictions **inside the notebook** (don't upload a local CSV). Mind the run-time limit and `enable_internet: false`
- The submission quota is finite. Declare in advance how many slots probing will use, and don't crowd out model validation
- If the recovered distribution/composition differs a lot from train, record the fold-design / validation-strategy review in the daily report
