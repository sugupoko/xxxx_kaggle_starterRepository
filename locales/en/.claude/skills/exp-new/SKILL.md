---
name: exp-new
description: Create a new experiment folder by copying reference/ as a template. Auto-generates SESSION_NOTES.md and run.sh. Claude experiments use expA00, A01, ...; human experiments use exp200, 201, ... in sequential numbering.
argument-hint: "<experiment_name> [--human for human-style exp200_xxx]"
---

# New Experiment Folder Skill

## Steps

1. **Parse arguments**:
   - Get experiment name from `$ARGUMENTS` (required)
   - Check for `--human` flag

2. **Determine folder name**:
   - Claude: start at `workspace/expA00_<name>`, advance to A01, A02, ..., B00, ... based on existing folders
   - Human: start at `workspace/exp200_<name>`, advance to 201, 202, ...
   - `ls workspace/` first to determine the next number

3. **Copy template**:
   ```bash
   cp -r reference/ workspace/<new-folder>/
   ```

4. **Generate SESSION_NOTES.md** (don't overwrite if it exists):

```markdown
# SESSION_NOTES — <folder name>

## Session Info
- Date: YYYY-MM-DD
- Working folder: workspace/<folder name>
- Goal: <inferred from name or asked from user>

## Base
- Base: reference/ (PyTorch Lightning + timm + smp)
- Parent exp (if any): ...

## Approaches Tried and Results
<!-- Append after each run -->

## File Structure
- train.py
- src/
- config.yaml
- run.sh

## Key Insights
<!-- Insights from training -->

## Next Steps
- [ ] ...

## Performance History
| Trial | Change | CV | LB | Notes |
|-------|--------|-----|-----|-------|

## Command History
<!-- Major commands run -->
```

5. **Generate run.sh** (with execute permission):

```bash
#!/bin/bash
# Train + inference in one script
# IMPORTANT: cd "$(dirname "$0")" must run before python.
#            Without it, results/ may be created at the repo root or elsewhere.
# Usage: bash run.sh data.fold=0 trainer.max_epochs=30
#        Arguments override config.yaml in OmegaConf dotlist format (there is no --config flag)
set -e

cd "$(dirname "$0")"

# Train (train.py lives directly in the experiment folder; pass arguments through)
python train.py "$@"

# Inference (as needed)
# python predict.py ckpt_path=results/<experiment_name>/fold0/last.ckpt
```

6. **Update `experiment.name` in config.yaml** to the new folder name

7. **Make the results/ output path relative to the experiment folder**:
   - Verify `train.py`'s output path is not cwd-dependent
   - If needed, rewrite to use the **absolute path resolved from the experiment folder**: `output_dir = Path(__file__).resolve().parent / 'results' / experiment_name / f'fold{fold}'` (one `parent` because train.py lives directly in the experiment folder)
   - Run a quick training trial to confirm output appears in `workspace/<new-folder>/results/...` before reporting to the user

8. **Report**:
   - Path of the created folder
   - Paths of SESSION_NOTES.md and run.sh
   - Next action (edit config.yaml → `bash workspace/<new-folder>/run.sh`)

## Notes

- **If a folder with the same name exists, do not overwrite.** Ask the user how to handle numbering
- Stop with a warning if reference/ is missing
- Don't include datasets or model files in the template (covered by `.gitignore`)
