# Competition Workspace

このリポジトリはデータ分析コンペ用の実験管理テンプレートです。
Kaggle だけでなく、grand-challenge.org / CodaBench / 独自プラットフォームなど **Kaggle 以外のコンペにも対応** する想定で運用します。
**判断に迷ったら `KAGGLE_DIRECTION.md` の設計意図を確認すること。**（ファイル名は歴史的経緯で Kaggle のままですが、中身は汎用の設計原則として読む）

## Opus (1M context) を使う前提のメタルール

このテンプレートは **Claude Opus (1M context)** で運用することを前提にしている。1M コンテキストを活かすため、以下を**遠慮せず**やってよい:

- **横断分析**: `daily_reports/*.md` + 全 `workspace/exp*/SESSION_NOTES.md` + `claudeSummary.md` + `submit/SUBMISSIONS.md` を**並列に一括ロード**してから判断する。逐次 read で context を温存しようとしない
- **コードレビュー**: `src/` 全体 + `config.yaml` + fold 生成スクリプト + `KAGGLE_DIRECTION.md` を**同時に並列ロード**してから整合性を判断する（学習→推論→提出のリーク経路を通しで追う）
- **戦略判断**: 「点」ではなく「線」で見る。`competition-strategist` agent / `/strategy` skill が横断 synthesis に最適化されている
- **背景実行**: 学習ジョブ・スクレイピング・長い検証は `run_in_background` または `/loop` / `/schedule` で回す
- **外部GPU**: ローカルGPUで足りない学習は RunPod (`tools/runpod/`) で回す（接続・鍵運用・コスト管理を実機検証済み。鍵は `.runpod.env` ＝ gitignore で扱い、生値を出さない）
- **Plan mode**: 大きな方針変更（新しい exp 番号への移行、提出形式の変更など）の前に Plan mode で構造化する

並列 read が許容されるのは**コンペ関連の自分のファイル**まで。`reference/` の他人のコード・大量の `datasets/*` の中身を全部ロードする必要はない。

## コンペ開始時の把握フェーズ（学習コードを書く前に必ず実施）

新しいコンペに取り組むときは、いきなり学習コードに入らず、まず以下を **`survey/competition/` 配下に整理**してから実装に着手する:

1. **プラットフォーム特定**: Kaggle か / grand-challenge.org か / CodaBench か / 独自サイトか
2. **タスク定義**: 入出力、クラス数、評価単位（画像単位/ピクセル単位/患者単位 など）
3. **データの所在**: ダウンロード元 URL、サイズ、フォーマット、ライセンス、配置先のローカルパス
4. **評価指標**: 正確な定義（per-class/macro/micro、背景クラスの扱い、など実装上の曖昧さを潰す）
5. **提出形式**: CSV か / 予測ファイル（画像・JSON）の zip か / Docker コンテナか
6. **タイムライン**: Validation phase / Test phase / 最終締切、提出回数制限
7. **ルール**: チーム人数、外部データ可否、事前学習モデル可否、商用ライセンス

この 7 項目を埋めないまま実装を始めない。

**Simulation コンペ（エージェントを提出して対戦させる型。Lux AI / ConnectX / Halite など）の場合は、上記に加えて以下も確認する**（固定 train/test が無いぶん、環境とI/F契約の把握が要）:
- **エンジン / 環境**: `kaggle_environments` か独自エンジンか、ゲーム名（connectx / lux_ai_s3 など）、`make(...)` で再現できるか
- **観測空間・行動空間**: `observation` に何が入るか、`configuration` の中身、合法手の集合と非合法手のペナルティ
- **エピソード / ターン構造**: 1エピソードのターン数、同時手番か交互手番か、プレイヤー数
- **レーティング方式**: TrueSkill / ELO 的なスコア付け、マッチング方式、1日あたりのマッチ数
- **エージェント提出I/F**: `def agent(observation, configuration)` の戻り値（行動）形式、1手あたりのタイムアウト、メモリ制限、エージェントファイルサイズ上限

## フェーズ別ガード（いきなりアンサンブルしない）

**コンペには段階がある。各フェーズの "やる/やらない" を分けないと、終盤の最適化を序盤に持ち込んでリソースを溶かす。**

| フェーズ | 進捗 | やる | **絶対にやらない** |
|---------|------|------|------------------|
| 序盤 | ~30% | EDA / fold 設計 / **1つの strong baseline** / 動く submission pipeline / 調査 | アンサンブル, TTA, heavy aug, 複雑な post-processing, ハイパラ tuning |
| 中盤 | 30-70% | 多様性のある **3-5 single models** / エラー分析 / データ追加 / aug 効果検証 | **アンサンブル本格化**, 過度な hyperparam search |
| 終盤 | 70%- | **アンサンブル** / TTA / post-processing / 最終 submission 選定 / LB shake 評価 | 新アーキ着手, 大きな前処理変更, 新規外部データ |

判定は**時間ベース + マイルストーンベースのハイブリッド**。`competition-strategist` agent (`/strategy` で起動) が自動で判定し、乖離があれば警告する（「中盤入っているのに baseline 1個だけ」など）。

**Simulation コンペ版のフェーズ別ガード**（CV/アンサンブルの代わりに「対戦・相手プール・方策」で読み替える）:

| フェーズ | 進捗 | やる | **絶対にやらない** |
|---------|------|------|------------------|
| 序盤 | ~30% | 動く提出パイプライン（1エピソード完走するエージェント）/ **ヒューリスティック baseline** / 環境とI/Fの把握 / ローカル評価ハーネス + 相手プール初版 | 序盤から RL を大回し, 探索の重い実装, 相手1種だけへの過学習 |
| 中盤 | 30-70% | 探索（minimax/MCTS）・RL（self-play/PPO）強化 / **相手プールの多様化** / リプレイでの負け分析 | 相手1種だけで評価を回す, 評価ハーネス無しの体感チューニング |
| 終盤 | 70%- | **方策アンサンブル**（相手別カウンター・状況別の使い分け）/ メタ変化への追従 / LB shake 評価 / 最終エージェント選定 | 新規アルゴリズム着手, 大きな観測/行動設計変更 |

simulation には固定 CV が無いので、各フェーズの「進捗判定」は **相手プールに対する勝率の推移 + 提出レートの推移**で代理する。

**新規セッション開始時の確認手順**: アクション提案前に必ず以下を確認:
1. 今のフェーズはどこか（残り日数 + マイルストーン達成状況）
2. 提案するアクションは現フェーズの "やる" に含まれるか
3. 含まれないなら、フェーズ違反である旨を明示してからユーザーに判断を委ねる

詳細・各フェーズの完了条件は `KAGGLE_DIRECTION.md` の「フェーズ別の指針」を参照。

## アイデア提案の原則（堅実＋爆発）

**アプローチやアイデアを提案するときは、必ず「堅実案」と「爆発案」の両方を出すこと。**

- **堅実案**: 既知の手法、定石、段階的改善。確実にスコアが上がる見込みがあるもの
- **爆発案**: 常識外れ、異分野からの転用、誰もやらなそうなアプローチ。失敗リスクは高いが当たれば大きいもの

例:
```
堅実: encoder を efficientnet_b0 → b4 に変更（+0.5%程度の改善見込み）
爆発: セグメンテーションを捨てて物体検出で解く / 全く別のモダリティの事前学習済みモデルを転用
```

局所解に陥らないために、爆発案は「それは普通やらないだろう」くらいがちょうどいい。

## 基本ルール

- 実験は `workspace/` 以下で行う
- Claude用: `expA00_baseline` (アルファベット+数字2桁)、人間用: `exp200_name` (数字3桁)
- 各実験フォルダには必ず `SESSION_NOTES.md` を作成する
- 大きく方針が変わる時だけ新しいexp番号にする。微調整は同じフォルダ内で
- 結果・知見・戦略はすべて日報 `daily_reports/YYYYMMDD.md` に集約する（個別planファイルは作らない）

## 学習コードの鉄則

- **AMP (Mixed Precision) は常にON** (`precision: 16-mixed`)
- **チェックポイント再開は必須** (`save_last=True` + `ckpt_path`)
- **シード固定** (`pl.seed_everything(seed, workers=True)`)
- ハイパーパラメータはすべてconfigで管理（ハードコーディング禁止）
- **ログはPythonの `logging` モジュールで出力する**（`print`禁止）
  - コンソール（INFO）とファイル（DEBUG）の両方に出力する
  - ログファイルは `results/{experiment_name}/foldN/` にタイムスタンプ付きで保存する
  - フォーマット: `%(asctime)s | %(levelname)s | %(message)s`
- **全出力は `workspace/expXXX_xxx/results/{experiment_name}/foldN/` に集約する**
  - **必ず実験フォルダ直下の `results/` に出力する**。リポジトリルートや `workspace/results/` などに作らない
  - `train.py` の冒頭で `output_dir = Path(__file__).resolve().parent / 'results' / experiment_name / f'fold{fold}'` のように**実験フォルダ基準で絶対パスを組む**こと（`train.py` は実験フォルダ直下に置くため parent 1段）。`Path('results/...')` のような相対パスは cwd 依存で事故るので禁止
  - config.yaml の `output_dir` も実験フォルダからの相対 / 絶対パスで明示する
  - `run.sh` 内では `cd "$(dirname "$0")"` してから `python train.py "$@"` を呼ぶ（これも cwd 依存事故防止）。引数は OmegaConf dotlist 形式（例: `data.fold=0`）で config.yaml を上書きする。`--config` フラグは存在しない
  - 出力例: `workspace/expA00_baseline/results/expA00_baseline/fold0/best_model.ckpt`
  - best_model, checkpoint, log, training_log.json, **config.yaml** を全て同一ディレクトリに保存する
  - **config.yamlは学習開始時に自動コピーされる**（再現性のため）
  - `experiment.name` をconfigに定義し、パラメータ変更時は名前を変える
  - 同名の実験ディレクトリが存在する場合は `_001`, `_002` とナンバリングして上書きしない
- 実行は `run.sh` 経由で行う（各実験フォルダに `run.sh` を作成し、学習・推論はすべてこのスクリプト経由）
- **日報 `daily_reports/YYYYMMDD.md` がすべての記録の中心**
  - 1日1ファイル。戦略・ロードマップ・知見・実験結果をすべてここに書く
  - **知見が出たら都度追記する**（学習完了、エラー発見、スコア変化など、待たずに即記録）
  - 実験結果（CVスコア等）は数値で明記する
  - 過去分は編集せず履歴として保持
  - **セッション開始時に最新の日報を読んで状況を把握する**
  - テンプレート:
    ```markdown
    # 日報 YYYY-MM-DD

    ## コンペ情報
    - **コンペ**: コンペ名
    - **締切**: YYYY-MM-DD（残りN日）
    - **評価指標**:
    - **LB状況**:

    ## 今日やったこと
    ### 1. ...

    ## 数値まとめ
    | 実験 | データ量 | CV | LB | 状態 |
    |------|---------|-----|-----|------|

    ## 戦略・ロードマップ

    ## 判断・知見
    <!-- 今日得られた重要な判断や知見 -->

    ## データ在庫
    <!-- 利用可能なデータソースの整理 -->

    ## 次にやること
    - [ ] TODO
    ```

## ナレッジ蓄積（フロー → ストック）

**作業が増えると知見が膨大になる。時系列ログ（フロー）と蒸留知識（ストック）を分けて貯める。**

| 層 | 置き場 | 性質 |
|----|--------|------|
| **フロー** | `daily_reports/YYYYMMDD.md` | 時系列ログ。追記専用・編集しない。「何が起きたか」 |
| **ストック** | `knowledge/**.md` | 蒸留知識。原子ページ + `INDEX.md` 目次。「今わかっている事」 |

- `knowledge/` は **リポジトリ内の明示的な .md ファイル**（commit して共有する見える資産）。`memory/`（Claude Code のセッション横断メモ）とは別物
- **原則: まず daily_report に書く → 蒸留して `knowledge/` へ昇格**。フローを飛ばして直接ストックに書かない（出典が消えるため）
- ページは **1トピック1ファイル**（`technique/` `data/` `error/` `decision/`）。frontmatter + 短い蒸留本文。作法は `knowledge/README.md`、雛形は `knowledge/_template.md`
- **検索は `INDEX.md` を見てから該当ページだけロード**。全ページ走査しない（context を食わないため）
- 蓄積・検索・整理は `/wiki`（`add` / `find` / `promote` / `consolidate`）。SessionStart で `INDEX.md` が自動注入される
- 棄却された知見も `status: rejected` で残す（同じ轍を踏まないため）

## Fold設計（最重要）

**安易にランダムKFoldにしない。データの性質を先に確認する。**

- 時系列 → TimeSeriesSplit
- グループ構造あり → GroupKFold
- クラス不均衡 → StratifiedKFold
- グループ+不均衡 → StratifiedGroupKFold
- fold設計の理由と各foldの分布はSESSION_NOTES.mdに記録する
- CV/LBの相関を確認し、相関が弱ければfold設計を見直す

**fold割り当ての永続化（`workspace/fold/`）:**
- fold割り当ては `workspace/fold/{version}/folds.csv` に保存し、全実験で共有する
- `workspace/fold/generate_folds.py` で生成。バージョン管理付き
- 前処理やデータを変更した場合は新バージョンを作る。古いバージョンは削除しない
- config.yamlの `data.folds_csv` で使用バージョンを指定する
- 設計意図・切り方の詳細は `workspace/fold/README.md` に記載

**Simulation コンペには fold が無い:**
- 固定の train/test も CV も存在しない。代わりに「**対戦相手プール（版管理）+ ローカル評価ハーネス**」を設計する
- 固定の相手プールに対する**勝率を代理 CV** とする（同じ相手集合・同じシードで測り、版を上げたら旧版も残す）
- 相手プールは弱い順（random / 単純ヒューリスティック / 過去の自分のエージェント / 強い公開エージェント）で多様化し、過学習を防ぐ
- 詳細は `reference_sim/README.md` / `reference_sim/opponents/README.md` を参照

## 提出パイプライン（`submit/`）

提出用コードとモデルは `submit/` 以下で管理する。提出形式はプラットフォームによって異なるため、以下のいずれかに沿って構成する。

### 共通ルール（プラットフォーム非依存）

- **命名**: `v00X_<元実験フォルダ名>` または `v00X_<元実験フォルダ名>_<追加識別子>` の連番形式
  - 例: `submit/v001_expA02_super_clone` / `submit/v002_expA03_anchor_calib_ens5fold`
  - **元実験フォルダ名を必ず含める**。後で「これどの exp の weight だっけ？」を防ぐため
  - アンサンブル時は代表 exp 名 + `_ens` のように区別（例: `v005_expA04_ens3model`）
  - 追加識別子は推論パラメータの違いなど（例: `_tta8`, `_thresh07`）
- **自己完結**: 提出用スクリプトは前処理・後処理を内部に持ち、`workspace/` の学習コードに依存しない
- **環境判別**: 実行環境（Kaggle / grand-challenge / ローカル）を自動判別してパスを切り替える
- **推論パラメータ**: ファイル冒頭の定数で管理（ハードコーディング散在を避ける）
- **出典記録**: スクリプト冒頭の docstring に `Source: workspace/expXXX/.../best_model/` とコピー元パス・CV スコアを明記する
- **モデル取り扱い**: `workspace/` から `best_model/` をコピー。`model/` は git 管理外（`.gitignore`）。サイズが大きいため
- **ローカルテスト必須**: 提出物（CSV / 予測ファイル / Docker イメージ）をローカルで生成まで確認してから提出する
- **提出物の検証**: プラットフォームの要件（ファイル数・命名規則・値の範囲・欠損）を提出前に必ずチェック
- **アップロードは手動**: Kaggle Dataset / grand-challenge Submission ページ / その他への実アップロードはユーザーが手動で行う（Claude は実行しない）
- **提出履歴**: `submit/SUBMISSIONS.md` に全提出を記録する。実験フォルダ、モデル元パス、fold 定義、学習データ、学習/推論パラメータ、前処理、CV/LB スコアを必ず記載

### Kaggle の場合

Kaggle には **CSV Competition** と **Code Competition** の 2 タイプがある。提出フローが全く違うので最初に判別する:

| 種別 | 判別方法 | 提出方法 |
|---|---|---|
| **CSV Competition** | Rules に "Submit CSV directly" 等 / `kaggle competitions submit` が成功 | `submission.csv` を直接 upload。CLI 一発 |
| **Code Competition** | Rules に "Submissions are made from Kaggle Notebooks" / `kaggle competitions submit` が "Code Competition" エラー | Kaggle 上で Notebook 実行 → "Submit to Competition"。**最後の Submit は手動** |

#### (a) CSV Competition

```
submit/v001_baseline/
├── notebook.py          # ローカルで実行する推論スクリプト
└── model/               # 学習済みモデル一式
```

- エントリポイントは `notebook.py`
- 出力は `submission.csv`。**行数・カラム名・欠損・値の範囲**を必ず検証してから提出
- git には `notebook.py` のみコミット

#### (b) Code Competition

```
submit/v001_baseline/
├── inference_notebook.py     # jupytext で .ipynb と同期する Python ソース（commit）
├── inference_notebook.ipynb  # .py から生成（commit しない）
├── kernel-metadata.json      # Notebook の Kaggle メタ（commit）
├── dataset-metadata.json     # Dataset の Kaggle メタ（commit）
├── upload.sh                 # Dataset 作成 + Notebook push を1コマンド化（commit）
└── kaggle_dataset/           # Dataset アップロード対象（.gitignore）
    ├── models/
    └── (学習済みモデル一式)
```

- **詳細フロー・テンプレート・ハマりどころは `tools/kaggle_code_competition_submission.md` を参照**
- 流れ: `upload.sh` で Dataset upload + Notebook push → Kaggle UI で Save & Run All → "Submit to Competition"（手動）
- 必須: `enable_internet: false`（pip install 不可）、`kernel_sources` 使わず self-contained に
- 検証: notebook 末尾で `assert len(sub) == EXPECTED_ROWS` 等の形式 assert
- 提出時の CV スコアは `kernel-metadata.json` / `dataset-metadata.json` の title に埋め込む（どの weight か一目で分かるように）

### Kaggle 以外の場合（grand-challenge.org / CodaBench / 独自サイト など）

提出形式は主に次の 2 タイプ。コンペ仕様に合わせて選ぶ。

**(A) 予測ファイル提出型**（画像・マスク・JSON を zip してアップロード）

```
submit/v001_baseline/
├── predict.py           # 入力ファイル群を読んで予測を出力するスクリプト
├── run.sh               # predict.py → 出力検証 → zip 化を一発で行う
├── requirements.txt     # 再現性のため固定
├── model/               # 学習済みモデル一式（.gitignore）
└── output/              # 生成された提出物（.gitignore）
```

- 入出力ディレクトリは `predict.py` 冒頭の定数で指定（`INPUT_DIR` / `OUTPUT_DIR`）
- 出力は **ファイル名・サイズ・dtype・値域** まで厳密に公式仕様へ一致させる
- 提出前に「入力ファイル数 == 出力ファイル数」「stem 名の一致」を assert

**(B) Docker コンテナ提出型**（algorithm container として提出）

```
submit/v001_baseline/
├── Dockerfile
├── process.py           # grand-challenge の algorithm interface を実装
├── requirements.txt
├── test/                # ローカル検証用のサンプル入出力
│   ├── input/
│   └── expected_output/
├── build.sh             # docker build
├── test.sh              # ローカルでコンテナを回して出力を検証
├── export.sh            # docker save → tar.gz（提出物）
└── model/               # .gitignore
```

- プラットフォーム側の I/O 契約（入力パス / 出力パス / ファイル形式）を最優先で守る
- ビルド後に必ず `test.sh` でローカル回帰テスト。本番と同じ入出力パスで動くことを確認
- イメージサイズ・GPU 要件・推論時間制限を事前に把握し、必要ならモデル軽量化や ONNX 化を検討
- gitには `Dockerfile` / `process.py` / スクリプト類のみコミット（`model/` と `test/` の大容量データは除外）

### Simulation コンペの場合（エージェント提出型）

**(D) Simulation エージェント提出型**（`def agent(observation, configuration)` を実装した1ファイルを提出し、サーバ上で他者エージェントと対戦させる）

```
submit/v001_expA00_heuristic/
├── agent.py             # 提出するエージェント本体（self-contained な単一ファイル）
├── run_local.sh         # ローカルで1エピソード完走 + 相手プールに対する勝率確認
├── requirements.txt     # ローカル評価用（提出環境のプリインストール library に合わせる）
└── model/               # 方策の weight 等（.gitignore。使う場合のみ）
```

- エントリポイントは `agent.py` の `def agent(observation, configuration)`。**self-contained**（`workspace/` や外部モジュールに依存せず1ファイルで完結。weight を使う場合も読み込みパスを環境判別で解決）
- **ローカルで1エピソード完走を確認**してから提出する（`kaggle_environments` の `make(...)` / `env.run([agent, "random"])` を `reference_sim/evaluate.py` 経由で回す）
- **タイムアウト・メモリ・不正手で落ちないか検証**する。1手あたりの応答時間を計測し制限内に収める / 合法手のみ返す / エージェント関数内で stdout に余計な print をしない（採点ログを汚す）
- 命名規則は既存踏襲（`v00X_<元実験フォルダ名>[_追加識別子]`）。git には `agent.py` / スクリプト類のみコミット（`model/` は除外）

## エラーハンドリングの原則（握りつぶさない）

**なぜこの原則があるか**: 安易な `try/except` は「動いているように見えて実は壊れている」状態を作る。例外を握りつぶしてもエラーは**消えない — 見えなくなるだけ**で、間違った結果（NaN・空配列・古いデータ・デフォルト値）が静かに下流へ流れ、CV/LB が壊れた原因の特定を何時間も遅らせる。だから**原則 fail-fast（例外はそのまま落として早く気づく）**。

- **禁止**: `except:` / `except Exception: pass` / 例外を握りつぶしてデフォルト値・None・空を返す。これは「直す」のではなく「隠す」
- `try/except` を使ってよいのは次を**すべて**満たすときだけ:
  1. **回復可能**な失敗である（リトライ可能な一時エラー、任意機能の欠如など）
  2. **具体的な例外型**だけを捕まえる（例: `except requests.Timeout`）。広い `except Exception` は避ける
  3. 握りつぶさず **`logging` で記録**し、リトライ上限つきで再試行するか・明示的にフォールバックする
- データ・shape・前処理・指標・提出形式の不整合は**捕まえずに落とす**（`assert` で早期に止めるほうが安全）。「とりあえず except で囲んで動かす」は最悪手で、バグを本番まで運ぶ
- OK例: 学習監視ループの一時的なネットワーク失敗 →「具体型 + ログ + リトライ上限」で扱う（`tools/kaggle_elapsed_time.py`）。NG例: `KeyError` / `shape` 不一致を握りつぶす → バグを隠す

## エラー分析の原則（スコアの前に出力を見ろ）

**スコアを上げようとする前に、まず出力を観察して「何が悪いか」を特定する。**

- 実験後は必ず prediction vs ground truth を目視確認する（最低20件）
- エラーの種類を分類し、パターンを把握する（分類はタスク依存。事前にリスト化せず、出力から帰納的に発見する）
- エラーの種類に応じた対策を打つ（前処理・後処理・推論戦略・学習データ・モデル変更）
- スコアという数字だけ見てパラメータを変える盲目的な探索をしない

順序: 出力を読む → 何が悪いか特定 → 原因に対処する → スコアで検証

## 前処理・評価

- 正規化はtrainデータの統計量で計算する（testの情報を使わない）
- コンペの評価指標を正確に再現する（既存実装のパラメータも確認）
- Augmentationはまず弱めで、過学習が確認されてから強める
- single modelのCV/LBを記録してからアンサンブルする
- 提出前の検証はプラットフォームに応じて行う:
  - Kaggle (CSV): 行数・カラム名・欠損値・値の範囲
  - 予測ファイル (画像/JSON): ファイル数・命名規則・dtype・値域・サイズ
  - Docker: ローカル回帰テスト、入出力パス、GPU/時間制限

## リファレンスコード

- `reference/` に2.5Dセグメンテーションのテンプレートコード（PyTorch Lightning + timm + smp）がある
- 新しい実験のベースとして活用すること
- 詳細は `reference/README.md` を参照
- `reference_sim/` に **simulation コンペ用の参照**（エージェント I/F + 対戦評価ハーネス、ConnectX 実例）がある。エージェント提出型のコンペではこちらをベースにする。詳細は `reference_sim/README.md`

## 自動化（Hooks）

`.claude/settings.json` に以下が設定されている。`/hooks` で確認・編集可能:

- **SessionStart**: 最新の日報（`daily_reports/[0-9]*.md` の最新）と `knowledge/INDEX.md`（ナレッジ目次）を context に自動注入する。セッション開始時に状況把握とストック知識の所在把握をスキップしないため
- **SessionEnd**: セッション終了時に今日の日報があれば `<!-- session ended: ... -->` マーカーを追記する。日次の作業ログを残すため（応答完了のたびに発火する Stop ではなく SessionEnd を使う）

## 利用可能なSkills

- `/onboard [URL]` - コンペ開始時の7項目チェックリストを対話的に埋め、`survey/competition/overview.md` に保存。**新しいコンペに入ったら最初にこれ**（simulation コンペの追加項目にも対応）
- `/exp-new <name> [--human]` - `reference/` から雛形コピーで新しい実験フォルダを作成し、`SESSION_NOTES.md` と `run.sh` を生成
- `/daily-report` - 今日の `daily_reports/YYYYMMDD.md` を前日から引き継いで作成（セッション開始時）
- `/submit-check <path>` - 提出物の事前検証（Kaggle CSV / 予測ファイル zip / Docker / Simulation エージェント）。提出直前に必ず使う
- `/strategy [追加観点]` - 横断 synthesis を実行。`competition-strategist` agent が全 daily_report + SESSION_NOTES + claudeSummary を一括ロードして次の一手を出す。週1回や CV 頭打ち時
- `/survey-papers [キーワード]` - 論文・解法調査（`context: fork` でメインコンテキストを汚さない）
- `/wiki [add|find|promote|consolidate]` - コンペ知識を `knowledge/` ストック層（原子ページ + INDEX）に蓄積・検索・整理。daily_report のフローから蒸留して昇格。知見が出たとき・週次整理・過去知見を引きたいとき

## Custom Agents

状況に応じて自動的にサブエージェントに委譲される。並列実行も可能。

| Agent | Model | 用途 |
|-------|-------|------|
| **competition-strategist** | opus | 横断 synthesis（全 daily_report + SESSION_NOTES + claudeSummary + SUBMISSIONS を一括分析）。1M ctx を最大活用 |
| **code-reviewer** | opus | ML/DLコード品質レビュー。リーク・指標バグ・チェックポイント破綻など、複数ファイル横断でしか見えない問題を検出 |
| **submission-validator** | sonnet | 提出物の事前検証（CSV / 予測ファイル zip / Docker / Simulation エージェント）。提出ミスを潰す |
| **kaggle-researcher** | sonnet | 論文・類似コンペ解法・ディスカッション調査。Kaggle / grand-challenge.org / CodaBench など他プラットフォームも対応 |
| **data-analyst** | sonnet | EDA・可視化・特徴量分析。データの全体像把握 |

**モデル選定の基本方針**:
- **opus**: 「深く読まないと気付けない」系（リーク検出・横断 synthesis）。1M ctx の活用が前提
- **sonnet**: 「広く浅く回す」系（調査・EDA・形式チェック）。手数で回せる手続き的な仕事
