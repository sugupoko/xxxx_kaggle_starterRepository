#!/usr/bin/env python3
"""fold 割り当て生成スクリプト（全実験で共有する folds.csv を作る）.

KFold / StratifiedKFold / GroupKFold / StratifiedGroupKFold を引数で選び、
`workspace/fold/{version}/folds.csv` に出力する。
設計意図・バージョニング規約は同階層の README.md と CLAUDE.md「Fold設計（最重要）」を参照。

使い方:
    # ランダム KFold（最後の手段。まずデータの性質を確認すること）
    python generate_folds.py --input ../../datasets/train.csv \\
        --version v1_random_kfold5 --strategy kfold --id-col image_id

    # クラス不均衡 → StratifiedKFold
    python generate_folds.py --input ../../datasets/train.csv \\
        --version v1_stratified_label --strategy stratified \\
        --id-col image_id --target-col label

    # グループ構造あり → GroupKFold
    python generate_folds.py --input ../../datasets/train.csv \\
        --version v1_group_patient --strategy group \\
        --id-col image_id --group-col patient_id

    # グループ + 不均衡 → StratifiedGroupKFold
    python generate_folds.py --input ../../datasets/train.csv \\
        --version v1_sgkf_patient_label --strategy stratified_group \\
        --id-col image_id --target-col label --group-col patient_id
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sklearn.model_selection import (
    GroupKFold,
    KFold,
    StratifiedGroupKFold,
    StratifiedKFold,
)

log = logging.getLogger(__name__)

# strategy 名 → (splitter クラス, target 必須か, group 必須か)
STRATEGIES = {
    "kfold": (KFold, False, False),
    "stratified": (StratifiedKFold, True, False),
    "group": (GroupKFold, False, True),
    "stratified_group": (StratifiedGroupKFold, True, True),
}

# 出力先はスクリプト基準で組む（cwd 依存禁止。CLAUDE.md「学習コードの鉄則」と同じ流儀）
FOLD_ROOT = Path(__file__).resolve().parent


def setup_logging(out_dir: Path) -> None:
    """コンソール（INFO）とファイル（DEBUG）の両方に出力する。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = out_dir / f"generate_folds_{datetime.now():%Y%m%d_%H%M%S}.log"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(fh)
    root_logger.addHandler(ch)

    log.info(f"Log file: {log_file}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="fold 割り当てを生成して workspace/fold/{version}/folds.csv に保存する")
    parser.add_argument("--input", required=True, help="入力 CSV のパス（train メタデータ）")
    parser.add_argument("--version", required=True, help="バージョン名（例: v1_group_patient）。出力先ディレクトリ名になる")
    parser.add_argument("--strategy", required=True, choices=sorted(STRATEGIES), help="fold の切り方")
    parser.add_argument("--id-col", required=True, help="サンプルを一意に識別するキー列名（例: image_id）")
    parser.add_argument("--target-col", default=None, help="stratify に使う列名（stratified / stratified_group で必須）")
    parser.add_argument("--group-col", default=None, help="グループ列名（group / stratified_group で必須）")
    parser.add_argument("--n-splits", type=int, default=5, help="fold 数（デフォルト: 5）")
    parser.add_argument("--seed", type=int, default=42, help="乱数シード（デフォルト: 42）")
    return parser.parse_args()


def make_splitter(strategy: str, n_splits: int, seed: int):
    cls, _, _ = STRATEGIES[strategy]
    if strategy == "group":
        # GroupKFold は shuffle / random_state 非対応（決定的な切り方になる）
        log.info("GroupKFold は shuffle 非対応のため seed は使われない")
        return cls(n_splits=n_splits)
    return cls(n_splits=n_splits, shuffle=True, random_state=seed)


def validate_args(args: argparse.Namespace, df: pd.DataFrame) -> None:
    """列の存在と strategy の必須引数をチェックする。"""
    _, need_target, need_group = STRATEGIES[args.strategy]
    if need_target and args.target_col is None:
        raise SystemExit(f"--strategy {args.strategy} には --target-col が必須")
    if need_group and args.group_col is None:
        raise SystemExit(f"--strategy {args.strategy} には --group-col が必須")

    for col in filter(None, [args.id_col, args.target_col, args.group_col]):
        if col not in df.columns:
            raise SystemExit(f"列 '{col}' が入力 CSV に存在しない。列一覧: {list(df.columns)}")

    if df[args.id_col].duplicated().any():
        raise SystemExit(f"キー列 '{args.id_col}' に重複がある。一意な列を指定すること")


def log_fold_distribution(df: pd.DataFrame, args: argparse.Namespace) -> None:
    """各 fold の件数・ターゲット分布・グループ非重複を記録する（SESSION_NOTES 転記用）。"""
    log.info(f"fold ごとの件数:\n{df['fold'].value_counts().sort_index().to_string()}")
    if args.target_col:
        dist = df.groupby("fold")[args.target_col].value_counts(normalize=True).unstack(fill_value=0)
        log.info(f"fold ごとの '{args.target_col}' 分布:\n{dist.round(4).to_string()}")
    if args.group_col:
        # 同一グループが複数 fold に跨っていないか（リーク検査）
        n_leaky = (df.groupby(args.group_col)["fold"].nunique() > 1).sum()
        if n_leaky > 0:
            raise SystemExit(f"グループ '{args.group_col}' が複数 fold に跨っている: {n_leaky} 件（リーク）")
        log.info(f"グループ '{args.group_col}' の fold 間リークなし（{df[args.group_col].nunique()} グループ）")


def main() -> None:
    args = parse_args()

    out_dir = FOLD_ROOT / args.version
    out_csv = out_dir / "folds.csv"
    # 既存バージョンは上書き禁止（過去実験の再現性のため。切り直すなら新バージョンを作る）
    if out_csv.exists():
        raise SystemExit(f"{out_csv} は既に存在する。上書きせず新しい --version を指定すること")

    setup_logging(out_dir)
    log.info(f"Args: {vars(args)}")

    df = pd.read_csv(args.input)
    log.info(f"入力: {args.input} ({len(df)} 行)")
    validate_args(args, df)

    y = df[args.target_col] if args.target_col else None
    groups = df[args.group_col] if args.group_col else None
    splitter = make_splitter(args.strategy, args.n_splits, args.seed)

    df["fold"] = -1
    for fold, (_, val_idx) in enumerate(splitter.split(df, y, groups)):
        df.loc[df.index[val_idx], "fold"] = fold
    assert (df["fold"] >= 0).all(), "fold 未割り当ての行がある"

    log_fold_distribution(df, args)

    # キー列 + stratify/group 列 + fold のみ保存（学習側は id で join する）
    keep_cols = [args.id_col] + [c for c in [args.target_col, args.group_col] if c] + ["fold"]
    df[keep_cols].to_csv(out_csv, index=False)
    log.info(f"保存: {out_csv}")
    log.info(f"config.yaml には cv.folds_csv: workspace/fold/{args.version}/folds.csv を指定する")


if __name__ == "__main__":
    main()
