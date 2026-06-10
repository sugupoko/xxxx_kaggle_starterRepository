---
name: strategy
description: Run cross-experiment competition strategy synthesis. Invokes the competition-strategist agent which loads daily_reports/* + all SESSION_NOTES.md / claudeSummary.md / submit/SUBMISSIONS.md / KAGGLE_DIRECTION.md in parallel and proposes next moves. Use weekly or at inflection points.
argument-hint: "[additional focus or blank for default synthesis]"
---

# Strategy Synthesis Skill

## Steps

1. **Check target files exist**:
   - Check `KAGGLE_DIRECTION.md` / `claudeSummary.md` / `daily_reports/` / `submit/SUBMISSIONS.md` / `workspace/`
   - If any missing, mark "Not found" and pass through to agent

2. **Invoke competition-strategist agent**:
   - subagent_type: `competition-strategist`
   - In the prompt, specify:
     - Competition name and deadline (from KAGGLE_DIRECTION.md)
     - **Phase detection must be the first thing** (time-based + milestone-based; warn on misalignment)
     - **All subsequent proposals are restricted to that phase's "do" list** (see KAGGLE_DIRECTION.md "Phase Guidance")
     - `$ARGUMENTS` as additional focus if given (e.g., "focus on ensemble strategy", "emphasize LB shake risk")
     - Output target: append to the "Strategy & Roadmap" section of today's daily report `daily_reports/YYYYMMDD.md`

3. **Append agent output to today's daily report**:
   - Append to the "Strategy & Roadmap" section of today's daily report `daily_reports/YYYYMMDD.md` (**never create a separate `strategy_*.md` file** — records are consolidated in the daily report)
   - If today's daily report doesn't exist yet, create it via the `/daily-report` steps first, then append
   - Summarize key proposals (**phase detection**, safe+bold, unexplored, risks) for the user
   - **Surface misalignment warnings first** (e.g., "Entered mid phase but no working baseline")

4. **Propose next actions**:
   - Pick 1-2 of the proposed next moves to recommend for tomorrow
   - Suggest `/exp-new` for new experiment folders or `/survey-papers` for further research as needed

## When to Use

- **Weekly**: as a regular checkpoint
- **CV plateaus**: to break out of local optima
- **After LB shake**: to step back and identify the cause
- **New data drop**: to re-evaluate strategy
- **1 week before deadline**: to optimize remaining resource allocation

## Notes

- Agent output is fact-based. **Inferences are marked "Inference:"**
- "Best X" claims must always cite source (experiment folder, daily report date)
- Don't blindly execute agent suggestions — treat them as input for user judgment
