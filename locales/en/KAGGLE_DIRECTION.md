# Introduction
This is a repository for data science competitions (supports Kaggle as well as grand-challenge.org / CodaBench / custom platforms — the filename `KAGGLE_DIRECTION.md` is historical).
Please review the rules together with CLAUDE.md.

Target competition:
Competition name:
URL:
Deadline / timeline:
Evaluation metric:


# Directory Structure

Only the places you touch most often are shown here (see "Repository Structure" in Readme.md for the latest complete structure).

```
./                                # Primary working directory
├── myMemo.md                     # Personal notes
├── claudeSummary.md              # Aggregated notes and insights from each experiment
├── datasets/                     # Competition data (not tracked by git)
├── tools/                        # Utility scripts
│   ├── kaggle_elapsed_time.py    # Submission status monitoring
│   └── kaggle_upload.sh          # Dataset upload/versioning script
├── survey/                       # Research and investigation folder
│   ├── competition/              # Competition overview (overview.md produced by /onboard)
│   ├── discussion/               # Regular monitoring of Kaggle discussions
│   └── papers/                   # Paper summaries
└── workspace/                    # Main development workspace
    ├── fold/                     # Persisted fold assignments (generate_folds.py + {version}/folds.csv)
    └── expXXX/                   # Experiment folders
```

# Experiment Method
Claude's experiment folders and human experiment folders are separated.
* Claude:
  * Create folders as exp(letter)(2-digit number)_(experiment name)
    workspace/expA00_baseline
  * Only change numbering for major experiment changes. Minor tweaks and parameter searches stay in the same folder.
* Human:
  * exp(3-digit number)_experiment_name

## Session Recording Rules

**Important**: Every experiment folder must have a `SESSION_NOTES.md`

### What SESSION_NOTES.md Should Include

1. **Session Info**
   - Date
   - Working folder
   - Goal

2. **Approaches Tried and Results**
   - Detailed description of each approach
   - File names used
   - Quantitative results (metrics, scores, etc.)
   - Issues and improvements

3. **File Structure**
   - List of created scripts
   - List of visualization outputs
   - List of data files

4. **Key Insights**
   - Important discoveries made during the session
   - Approaches to avoid
   - Techniques that worked

5. **Next Steps**
   - Tasks for next session
   - Ideas to explore
   - Prioritized

6. **Performance History**
   - Record of experiment names and performance changes
   - Overview of what was done and what happened

7. **Command History**
   - Major commands executed
   - For reproducibility

### Example
```
workspace/exp000_all_test/SESSION_NOTES.md
workspace/exp200_xxxxxxxx/SESSION_NOTES.md
```

### Purpose
- Resume work immediately after session interruption
- Never lose track of past attempts
- Documentation that others (or your future self) can understand

# Competition Workflow
- Always analyze the data first and proceed based on those findings
- Follow competition rules and improve performance according to the competition metric

# Training Code
1. Keep training logs. Things like learning curves. Structure it cleanly like this:
```
./exp000_all_test
├── SESSION_NOTES.md
├── run.sh                        # cd "$(dirname "$0")" first, then call train.py
├── train.py                      # placed directly in the experiment folder
├── config.yaml
├── src/                          # modules such as datamodule / model
└── results/
    └── {experiment_name}/
        └── foldN/                # ckpt, learning curves, logs, config copy all here
```
2. Training must be resumable from checkpoints. The PC may stop mid-training.
3. Use AMP for training.

# Survey Folder

## Discussion Folder
Keep scraping results organized in the folder for regular monitoring. Summarize what new information appeared in diffs separately.

### Discussion Collection Workflow

#### 1. Initial Setup
```bash
# Install Playwright
pip install playwright beautifulsoup4 lxml
playwright install chromium

# Create directories
mkdir -p survey/discussion
cd survey/discussion
```

#### 2. Get Discussion List

**Script**: `scrape_with_playwright.py`

```python
# Scrape discussion page using Playwright
# - Get HTML after JavaScript execution with headless browser
# - Extract discussion titles and URLs
# - Save to discussions_playwright.json
```

**Run**:
```bash
python scrape_with_playwright.py
```

#### 3. Get Detailed Info (Comment Count, etc.)

**Script**: `scrape_discussion_details.py`

```python
# Visit each discussion page
# - Get comment count
# - Get view count, vote count (when available)
# - Save to discussion_snapshot_YYYYMMDD_detailed.json
```

**Run**:
```bash
python scrape_discussion_details.py
```

#### 4. Snapshot Management

**File Structure**:
- `discussion_snapshot_YYYYMMDD.json` - Basic info snapshot
- `discussion_snapshot_YYYYMMDD_detailed.json` - Detailed info with comment counts
- `kaggle_discussions_organized.md` - Organized summary
- `discussion_activity_summary.md` - Activity analysis report
- `README.md` - Snapshot history and guide

#### 5. Diff Check (Next Run)

```bash
# Get new snapshot
python scrape_with_playwright.py
python scrape_discussion_details.py

# Check diffs (manual or scripted)
# - New topics
# - Increase in comment count
# - Changes in last updated timestamp
```

#### 6. Recommended Schedule

**Frequency**: 1-2 times per week
**Timing**: More frequent early in competition, weekly later on

**Checkpoints**:
- Check official announcements
- Important updates like data patches
- Discussions about evaluation metrics
- Shared effective solutions

### Notes

1. **Kaggle API Limitations**
   - Official Kaggle API has no discussion retrieval feature
   - Dynamic scraping with Playwright is required

2. **Scraping Etiquette**
   - 2-3 second wait between requests
   - Run in headless mode
   - Avoid excessive access

### Using WebFetch / WebSearch

Claude Code ships with **WebFetch / WebSearch built in**. For pages that can be fetched statically (official Overview / Rules / Data pages, etc.), use these first.
Fall back to the Playwright scraping above only for pages that require JavaScript rendering (e.g., the Kaggle discussion list).

## Papers Folder
Summarize paper contents.

### Research Workflow

1. **Search Related Papers**
   - Search past competitions and related research via WebSearch
   - Retrieve papers from arXiv, Google Scholar, etc.

2. **Create Paper Summaries**
   - Summarize in per-topic .md files under `survey/papers/`
   - Record methods, datasets, metrics, results

3. **Organize by Category**
   - Dataset papers
   - Method papers
   - Benchmark papers
   - Tools/Libraries

## Competition Folder (`survey/competition/`)
Summarize basic competition information in `survey/competition/` (the output location of `/onboard`).

### Information to Collect

1. **overview.md** - Competition overview
   - Background & purpose
   - Data format
   - Evaluation metric
   - Key challenges
   - Recommended approaches

2. **Data Sources**
   - Analysis of distributed data (train/test)
   - Understanding file format structure (CSV / Parquet / images, etc.)
   - Metadata review

---

# Design Intent: Why These Rules

This section provides **judgment guidelines**, not step-by-step procedures.
For procedures, refer to Skills and Readme.md.

## Phase Guidance (Early / Mid / Late)

**A time-axis guard to prevent "premature ensemble" and "premature TTA".**
Competitions have phases. **If you don't separate "what to do" from "what NOT to do" per phase, you'll waste resources by bringing late-stage optimization into early stages** (classic premature optimization).

Phase detection is **hybrid: time-based + milestone-based**:
- Time-based: compute progress % from the deadline in `KAGGLE_DIRECTION.md` and the first date in `daily_reports/`
- Milestone-based: check `SESSION_NOTES.md` / `submit/SUBMISSIONS.md` / `claudeSummary.md` for each phase's completion criteria
- **Warn if the two diverge**: "Entered late phase but baseline doesn't run yet" / "Trying ensemble in early phase"

### Early (~30% / Milestone: baseline complete + CV/LB correlation confirmed + 1 successful submission)

**Do**:
- Data understanding (EDA: distribution, missing, group structure, outliers)
- Fold design (identify grouping key → persist to `workspace/fold/{version}/folds.csv`)
- Accurate metric implementation (close the gap between competition spec and sklearn defaults)
- Build **one strong single model** (reference/ as base is fine)
- Working submission pipeline (CSV / prediction zip / Docker)
- Paper / similar competition / discussion research (`/survey-papers`)

**Forbidden**:
- Ensemble (**without absolute single-model score, you can't measure lift**)
- TTA (keep base inference baseline so you can measure effects later)
- Heavy augmentation (overfitting fix is for when overfitting actually happens)
- Complex post-processing (threshold optimization, morphology)
- Excessive hyperparameter tuning (try architecture before search)

**Completion criteria**:
- [ ] CV score is stable (fold variance within acceptable range)
- [ ] CV/LB correlation confirmed at least once
- [ ] Submission pipeline works (no submission errors)
- [ ] Metric implementation matches official spec

### Mid (30-70% / Milestone: 3+ independent single models, error patterns understood)

**Do**:
- **Increase model diversity**: encoder swap, architecture change, input modality change
- Error analysis (visually inspect ≥20 prediction vs ground truth pairs → classify error types)
- Consider added data / external data / pseudo-labeling
- **Quantitatively validate augmentation by CV**
- Improve preprocessing (normalization, sampling, class imbalance)
- Loss function tuning (focal, dice, custom)

**Forbidden**:
- **Serious ensemble work** (lift single CV first; mixing hides per-model contribution)
- Excessive hyperparameter search (don't burn time on lr/batch/optimizer grids)
- Late-stage post-processing tuning (makes evaluation unstable)

**Completion criteria**:
- [ ] 3-5 single models with independent directions (CV improving independently)
- [ ] Error patterns classified (you can identify which of preprocessing / postprocessing / model capacity / data shortage matters)
- [ ] Stable CV/LB correlation continues

### Late (70%- / Milestone: ensemble CV > best single CV, final 2 submission criteria clear)

**Do**:
- **Ensemble strategy**: weight optimization (CV-based), stacking, blending
- TTA (flip / multi-scale / probability averaging choice)
- Post-processing optimization (threshold, morphology, NMS)
- Final submission selection (best CV / best LB / conservative-stable balance)
- LB shake risk assessment (CV/LB correlation, fold variance, submission history dispersion)
- Full pre-submission validation (`/submit-check`)

**Forbidden**:
- **Starting a new architecture** (training won't finish / validation too shallow)
- Large preprocessing changes (don't break the pipeline established in mid)
- Large-scale hyperparameter tuning (diminishing returns)
- New external data (insufficient validation time)

**Completion criteria**:
- [ ] Ensemble CV exceeds best single CV
- [ ] Final 2 submission selection criteria are clear (reasoning written in SESSION_NOTES)
- [ ] LB shake scenarios evaluated (optimistic + pessimistic)
- [ ] `/submit-check` passes for every intended submission

### Phase Misalignment Warnings

When time and milestones diverge, the `competition-strategist` agent warns:

- **Progress delay**: "Entered mid phase but baseline still doesn't run" → prioritize early phase
- **Premature optimization**: "Trying ensemble in early phase" → lift single first
- **Late new-architecture attempt**: "3 days left, trying new architecture" → restrict to optimizing existing assets

## Intent of "Safe + Bold"

Looking back at top Kaggle solutions, it's rare to win with incremental improvement (safe) alone. Many gold medal solutions contain a "nobody would normally do that" leap.

- Safe approaches alone lead to local optima. Encoder changes, hyperparameter tuning, augmentation additions... these are necessary but alone will plateau
- Bold alone is gambling. You need a solid baseline to properly measure bold ideas
- **By always presenting both, you separate "what to do now" from "what's worth trying"**
- Bold ideas are expected to fail. If 1 out of 10 hits, that's a huge jump
- Typical bold ideas: cross-domain transfer (NLP→CV, audio→time series), problem reframing (segmentation→detection), non-obvious external data usage
- The more you think "that would never work," the more likely no other participants have tried it

## Intent of Fold Design

How you split folds determines CV reliability. **If CV isn't reliable, every experiment decision is flawed.**

- Random KFold assumes "data is completely i.i.d." In real Kaggle data, this assumption rarely holds
- Group leakage (same patient/image/session split across train/val) inflates CV unfairly. Discovering this only on LB is too late
- Time series leakage (predicting past with future info) is even worse. Requires explicit prevention with Purged KFold etc.
- **Time spent on initial fold design determines the value of all subsequent experiments**
- Large variance in fold scores likely means you're missing a group structure in the data
- Weak CV/LB correlation means fold design doesn't reflect the real test distribution

## Intent of Preprocessing

- Normalizing with train statistics only prevents leakage. Within folds, likewise don't use val fold info for train normalization
- Starting with weak augmentation verifies the model's raw learning ability first. Strong augmentation is a symptomatic fix for overfitting that can mask root causes (insufficient data/model capacity)
- **Always judge augmentation effects quantitatively by CV. Don't add something because it "seems useful"**

## Intent of Evaluation Metrics

- Accurately reproducing the competition metric is fundamental. Default parameters in sklearn etc. often don't match the competition (average specification, thresholds, weighting, etc.)
- When loss and metric differ (e.g., BCELoss for training, F1 for evaluation), the optimal solution may diverge. Be aware of this gap and consider threshold optimization or custom losses as needed
- **"CV improved" only holds if the metric implementation is correct**

## Intent of Submission & Ensemble

- Recording single model scores before ensembling helps understand each model's contribution. Ensembling is "combining the best models," not "mixing everything"
- Pre-submission checks seem obvious, but wasting time on submission errors from row count mismatches or column name typos is avoidable. Always check after modifying post-processing
