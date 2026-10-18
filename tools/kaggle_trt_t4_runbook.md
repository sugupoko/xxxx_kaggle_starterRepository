# Kaggle T4 で TensorRT 変換テストを回す手順書（再発防止版）

学習済みモデル（ONNX 化可能なもの）を **Kaggle の T4 GPU 上で TensorRT FP16 に変換 → 等価性＆速度を検証** するための定型手順。
分類モデル（convnext + attention-pool）と検出モデル（YOLO）で確立した。

> なぜローカルでなく Kaggle T4 か: ① **engine はビルドした GPU アーキ専用**（本番が T4 なら T4 でビルドが要る）② ローカルの新しい GPU（例: sm_120）では T4 用 engine は作れない ③ `pip install tensorrt-cu12` はローカルだと重く失敗しがち。Kaggle T4 が一番手軽で本番と一致する。

---

## 0. 前提

- `kaggle` CLI が入った python と `kaggle.json` がある（`python -m kaggle config view` で `username` が出る。置き場が `HOME` の外なら `KAGGLE_CONFIG_DIR` を明示・`kaggle_code_competition_submission.md` §6.1）。**鍵の値は出力しない**。
- 構成は **dataset（コード + 入力データ）＋ kernel（実行ランチャ）** の 2 点セット。kernel が dataset を読んで実行する。
  ```
  submit/_kaggle_trt_<name>_dataset/   ← dataset（push対象）
    ├── trt_bench.py                   # 本体: モデル構築→ONNX→engine build→3者ベンチ→等価判定
    ├── sample_input.npy               # 代表入力（実データ由来。例: [S,3,H,W]）
    └── dataset-metadata.json          # {"id":"<user>/<name>-trt", ...}
  submit/_kaggle_trt_<name>_kernel/    ← kernel（push対象）
    ├── run.py                         # pip install → dataset の bench を exec するだけ
    ├── kernel-metadata.json           # ★machine_shape など（下の落とし穴参照）
    └── upload.sh                      # 全自動E2E（このディレクトリで bash upload.sh）
  ```

---

## 1. ★4大落とし穴（先に潰す）

| # | 症状 | 原因 | 対策 |
|---|---|---|---|
| 1 | GPU が **P100** になり `sm_60 not compatible`／TRT 非対応で詰む | kernel-metadata の GPU 指定フィールド名が**間違い** | フィールドは **`machine_shape`（snake_case）**。`machineShape`（camelCase）は**黙殺**されデフォルト割当になる。値 `"NvidiaTeslaT4"` |
| 2 | `ModuleNotFoundError: No module named 'onnxscript'` | 新しい torch（2.10 で確認）の `torch.onnx.export` が onnxscript を要求 | pip install に **`onnxscript`** を追加。export 呼び出しに **`dynamo=False`**（実証済みの TorchScript exporter ＝ TRT と相性の良いグラフ） |
| 3 | 実行は成功しているのに **ログ（ベンチ表）が取れない** | `kaggle kernels output` は working dir の生成物だけ落とし、stdout を落とさないことがある | **`kaggle.api.kernels_logs("<user>/<slug>")`** で stdout/stderr の JSON を確実に取得（upload.sh 内に実装する） |
| 4 | dataset 更新直後に kernel が**古い版**で走る | `datasets version` 直後は処理中 | push 前に `datasets status` が **`ready`** になるまで待つ（upload.sh に実装する） |

### kernel-metadata.json の正しい形（最小）
```json
{
  "id": "<user>/<name>-trt-run",
  "title": "<name>-trt-run",
  "code_file": "run.py",
  "language": "python",
  "kernel_type": "script",
  "is_private": true,
  "enable_gpu": true,
  "enable_internet": true,
  "dataset_sources": ["<user>/<name>-trt"],
  "machine_shape": "NvidiaTeslaT4"
}
```
> `id` の `<user>` は **実ユーザー名**（`kaggle.json` の `username`）。表示名やメールではない。
> title と `id` の slug は揃える（実 slug は title から決まる・`kaggle_code_competition_submission.md` §8.1）。
> これは**検証用 kernel**なので `enable_internet: true`（pip install のため）。Code Competition の提出 notebook では使えない。

### run.py（pip 行が肝）
```python
subprocess.run(f"{sys.executable} -m pip -q install timm onnxscript 'tensorrt-cu12==10.13.3.9'", shell=True, check=True)
```
> TRT は **10.13.3.9 に pin**（動作実証した版。11.x は `BuilderFlag.FP16` 周りが変わる）。
> `check=True` で pip 失敗をその場で落とす（失敗を流すと後段の import エラーで原因が見えにくくなる）。

### export 行（bench スクリプト内）
```python
torch.onnx.export(m, x, onnx_path, input_names=["input"], output_names=["logits"],
                  opset_version=17, dynamic_axes=None, dynamo=False)  # ★dynamo=False
```

---

## 2. 実行（全自動E2E・1コマンド）

```bash
cd submit/_kaggle_trt_<name>_kernel
PYTHON=<kaggle CLI を持つ python> bash upload.sh
```
`upload.sh` に以下を全部やらせる:
1. 認証確認（鍵は出さない）
2. dataset create/version
3. **dataset ready 待ち**（落とし穴4）
4. kernel push（= T4 で自動実行開始。push した時点で run が始まる）
5. **status ポーリング**（COMPLETE/ERROR まで）
6. **`kernels_logs` でログ取得**（落とし穴3）→ `out_t4.log`
7. **ゲート検証**: `Tesla T4` で走ったか＋等価判定が通ったか

> Claude が実アップロードまでやる場合は**ユーザーの明示許可が必要**（CLAUDE.md: アップロードは原則手動）。手動なら `upload.sh` の中身を順に叩く。

---

## 3. 合否ゲート（このスクリプトで採用判定）

ログのベンチ表で、TRT-FP16 行が全部満たせば採用:
1. **等価**: `max|Δ| < 2e-2`（PyTorch FP32 と比較）
2. **NaN 無**
3. **高速化**: `vsFP32 > 1`

参考実測（Tesla T4 / torch 2.10 / TRT 10.13.3.9、分類モデル・1 サンプル = 16 スライス）:

| backbone | TRT-FP16 ms/サンプル | vsFP32 | max\|Δ\| |
|---|---|---|---|
| convnext_small | 33.26 | **3.14x** | 2.4e-4 ✅ |
| convnext_nano | 15.06 | **3.04x** | 6.4e-5 ✅ |

> TRT-FP16 は PyTorch FP16 も上回る。分類は compute-bound 寄りで TRT が効く（YOLO 検出では 1.51x 程度だった）。

---

## 4. 結果が出たら

- ベンチ表（`out_t4.log` から抜粋）を **日報 `daily_reports/YYYYMMDD.md`** に貼る。
- 採用なら本番推論パイプラインに engine ビルド手順を組み込む（**T4 上でビルド**を必ず守る）。
- `out_t4.log` / `*.onnx` / `*.engine` は `.gitignore`（巨大・再生成可）。コミットは `*.py` / metadata / `upload.sh` / この手順書のみ。

## 5. 別モデルへ流用するとき

bench スクリプトの **モデル定義と入力ロード**だけ差し替える（残りは共通）。
- aggregation を変える（attention-pool → **bi-LSTM** など）場合、ONNX に `LSTM` op が乗る → T4 TRT で通るか**必ず再検証**（attention-pool は op-clean 確認済み、LSTM は要確認）。
- 入力解像度・スライス数・**バッチ**を変えたら、その形で engine を作り直して測る（engine は固定 shape）。
