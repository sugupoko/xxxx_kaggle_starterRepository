---
name: daily-report
description: Create today's daily_reports/YYYYMMDD.md by carrying over pending TODOs and recent experiment results from yesterday's report. Use at the start of a session.
argument-hint: "[YYYY-MM-DD to specify date, blank for today]"
---

# Daily Report Skill

## Steps

1. **Determine target date**:
   - Use YYYY-MM-DD from `$ARGUMENTS` if given
   - Otherwise use today's date (system date)

2. **Check existing file**:
   - If `daily_reports/<YYYYMMDD>.md` **already exists**, open it and report "Today's report already exists" — then stop
   - Past reports must **never be edited** (CLAUDE.md rule)

3. **Read yesterday's report**:
   - Get the latest file matching `daily_reports/[0-9]*.md` (restrict the glob so non-report .md files are never picked up by mistake)
   - Extract "Next Steps", pending TODOs, "Numerical Summary", "Strategy & Roadmap"

4. **Carry over recent experiment results** (parallel-load, leveraging 1M ctx):
   - Read `workspace/exp*/SESSION_NOTES.md` updated since yesterday
   - Latest row of `submit/SUBMISSIONS.md`
   - Best score history from `claudeSummary.md`

5. **Generate today's report** (per CLAUDE.md template):

```markdown
# Daily Report YYYY-MM-DD

## Competition Info
- **Competition**: <from KAGGLE_DIRECTION.md>
- **Deadline**: YYYY-MM-DD (N days remaining)
- **Metric**: <from KAGGLE_DIRECTION.md>
- **LB Status**: <carried over from yesterday>

## What was done today
<!-- Empty at session start. Append as you work. -->

## Numerical Summary
| Experiment | Data Size | CV | LB | Status |
|------------|-----------|-----|-----|--------|
<!-- Carry over only "in progress" / "recent" rows. Skip closed ones. -->

## Strategy & Roadmap
<!-- Carry over from yesterday. Rewrite if updated. -->

## Decisions & Insights
<!-- Important decisions / insights from today. Empty at start. -->

## Data Inventory
<!-- Carry over from yesterday -->

## Next Steps
<!-- Carry over pending TODOs from yesterday's "Next Steps" -->
- [ ] ...
```

6. **Report**:
   - Generated file path
   - Number of pending TODOs carried over
   - Recent experiment summary (CV/LB trend, 1-2 lines)

## Notes

- **Never overwrite** an existing daily report
- If "yesterday" was multiple days ago (weekend etc.), still carry over the latest report
- "What was done today" starts empty. Claude or human appends as work progresses
- Past reports are history. To correct, **create a corrected version on a new date** — never edit
