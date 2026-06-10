---
name: submit-check
description: Run pre-submission validation. Handles 4 formats — Kaggle CSV / Kaggle Code Competition / prediction-file zip / Docker container. Delegates to the submission-validator agent for mechanical checks. Use right before any submission.
argument-hint: "<path to submit/v00X_<source-exp>_xxx> [--platform kaggle|gc|codabench]"
---

# Pre-submission Validation Skill

## Steps

1. **Parse arguments**:
   - Get submission folder path from `$ARGUMENTS` (required, e.g., `submit/v001_baseline`)
   - Use `--platform` flag if given, otherwise infer from `KAGGLE_DIRECTION.md`

2. **Detect format**:
   - From folder contents:
     - `notebook.py` present → (A) Kaggle CSV
     - `kernel-metadata.json` + `dataset-metadata.json` present → (A') Kaggle Code Competition
     - `predict.py` + `run.sh` present → (B) Prediction-file zip
     - `Dockerfile` + `process.py` present → (C) Docker container

3. **Invoke submission-validator agent**:
   - Pass the detected format and submission folder path
   - Agent handles format-specific validation automatically
   - For (A'), have submission-validator run "1'. Kaggle Code Competition checks" (kernel-metadata / dataset-metadata / self-contained notebook validation)

4. **Aggregate results and report**:
   - Show Pass / Fail / Warning in that order
   - If any Fail, emphasize **do not submit**
   - List recommended fixes at the end

5. **Prep `submit/SUBMISSIONS.md` entry**:
   - Extract metadata (experiment folder, model source path, fold definition, training data, key params, preprocessing, CV) from agent output
   - If no entry exists yet, propose a row to append (**do not auto-commit**)

## Notes

- **Never upload externally.** Actual uploads are done by the user manually
- During validation, ensure model files / submission.csv / prediction zips are not removed from `.gitignore`
- For Docker validation, `bash test.sh` may take long — run with `run_in_background` if needed
