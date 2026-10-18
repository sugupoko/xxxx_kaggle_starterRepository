# Knowledge Wiki (Stock Layer)

This directory stores **distilled, reusable knowledge** — the "stock layer."
It is made of atomic pages (one topic per file), with `INDEX.md` as the retrieval index.
It applies the same proven pattern as `memory/` (Claude Code's cross-session notes) to **competition-specific knowledge**.

## Separate Flow from Stock

| Layer | Location | Nature | When to write |
|-------|----------|--------|---------------|
| **Flow** | `daily_reports/YYYYMMDD.md` | Time-ordered log. Append-only, never edited | Record what happened / numbers immediately |
| **Stock** | `knowledge/**.md` | Distilled knowledge. Atomic, deduplicated, current | Promote reusable insights from the flow |

**Principle: write to the daily report first → distill and promote into knowledge.**
The daily report is "what happened (history)"; knowledge is "what we currently know (reusable conclusions)."

## Directory

```
knowledge/
  INDEX.md          # Retrieval index (one line per page + hook). Look here before reading any page
  README.md         # This document
  _template.md      # Template for new pages
  technique/        # Methods that worked / didn't (with CV/LB deltas)
  data/             # Data characteristics, leakage, fold-design insights
  error/            # Error patterns and their fixes
  decision/         # Direction decisions and rationale (why chosen / dropped)
  ledgers/          # List-style ledgers for runs, data versions, experiment folders and the ★ index (not wiki pages; see AGENTS.md)
```

Add categories freely (e.g. `metric/`, `pipeline/`). When you do, add a section in INDEX.

## Page Conventions

- **Atomic**: one page = one topic. Split when it grows
- **Frontmatter required** (see `_template.md`): `id / title / category / status / tags / source / links / updated`
- **Keep the body distilled**: takeaway → evidence (numbers) → how to apply → caveats. No rambling
- **Cross-link**: connect related pages with `[[id]]`. Linking a not-yet-written id is fine (a marker to write later)
- **Keep provenance**: put the source in `source:` (daily-report date / exp folder / survey paper) so it stays traceable

## Lifecycle (status)

`idea` (hypothesis) → `testing` → `validated` / `rejected` / `stale` (premise changed)

Keep rejected insights too — **don't delete them, mark `rejected`** (so the same mistake isn't repeated).

## How to Retrieve (for the LLM)

1. Read `INDEX.md` only (not all pages)
2. Pick 2-3 relevant pages from their hooks
3. Load only those pages

This lets you recall knowledge without burning context even as it grows large.

## Accumulate / consolidate with `/wiki`

- `/wiki` … show INDEX and propose missing-knowledge gaps
- `/wiki add <topic>` … distill an insight into the right page (create or update) + update INDEX
- `/wiki find <query>` … search for relevant pages and load them
- `/wiki promote` … harvest un-promoted insights from the latest daily report and propose pages
- `/wiki consolidate` … merge duplicates/contradictions/staleness and regenerate INDEX (roughly weekly)
