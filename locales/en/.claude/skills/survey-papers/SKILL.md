---
name: survey-papers
description: Search for papers and similar competition solutions related to the competition, and summarize in survey/papers/. Use during the research phase or when exploring new approaches.
argument-hint: "[search keywords or leave blank to auto-search from competition name]"
context: fork
agent: Explore
---

# Paper & Solution Research Skill

## Steps

1. **Determine Search Query**:
   - Use `$ARGUMENTS` if provided
   - Otherwise extract related keywords from the competition name in `KAGGLE_DIRECTION.md`

2. **Research via WebSearch** (search the following in parallel):
   - Related papers on arXiv
   - Top solutions from similar past competitions across platforms (Kaggle / grand-challenge.org / MICCAI Challenges / CodaBench — not limited to Kaggle)
   - Related methods on Papers With Code
   - Related implementations on GitHub

3. **Summarize each paper/solution**:
   - Title, authors, URL
   - Method summary (3-5 lines)
   - Model/architecture used
   - Dataset & evaluation metrics
   - Key results
   - Applicability to this competition

4. **Return the full research output**:
   - This skill runs in `context: fork` (read-only Explore agent), so **do not save files inside the fork**
   - Return the **full research output**, organized by category (dataset papers, method papers, benchmark papers, tools/libraries), as the final response
   - The receiving main conversation appends and saves it to `survey/papers/maybe_related_research.md`

5. **Propose transfer ideas**:
   - List methods potentially applicable to this competition
   - Evaluate implementation difficulty and expected impact
