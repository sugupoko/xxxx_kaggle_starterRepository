# RunPod 接続・運用ノウハウ（汎用・移植用）

外部GPU（RunPod）で学習を回すための**接続・操作・鍵運用・コスト管理**を1か所に集約。
このフォルダ（`tools/runpod/`）ごと別リポジトリにコピーすれば移植完了。実機（runpodctl 2.3.0）で検証済の内容。
**価格・在庫は変動するので使用直前に `runpodctl gpu list` / 公式pricingで確認。**

## 前提（このガイドが想定していること）
本書は **「接続〜運用」から** 始まる。以下は**済んでいる前提**で扱う（手順は本書の対象外。最新は公式を参照）:
- **RunPodアカウント作成済み**（runpod.io でサインアップ）
- **支払い方法の登録 / クレジット投入済み**（RunPodはプリペイド。**残高ゼロだと pod を起動できない**。自動チャージ推奨）

上記が未了の人はまず公式でアカウント登録とクレジット投入を済ませてから §1 へ。

## このフォルダの中身
| ファイル | 役割 |
|---|---|
| `README.md` | 本書（接続ノウハウ全部） |
| `runpod_ops.py` | ローカルから pod 操作（Python SDK版。up/list/stop/down、Network Volume対応） |
| `smoke_test.sh` | 疎通テスト（最安GPUで起動→RUNNING待ち→接続情報→teardown） |
| `startup.sh` | pod内で実行する起動スクリプト（鍵注入・private clone・自動停止）。鍵の値は持たない |
| `.runpod.env.example` | ローカルの鍵ファイル雛形。コピーして `.runpod.env` を作り値を入れる（**gitignore必須**） |

---

## 0. 全体像（3行）
1. ローカルに `runpodctl` + Python SDK を入れ、`RUNPOD_API_KEY` だけ `.runpod.env` に置く
2. pod に渡す鍵（GitHub PAT / HF / Kaggle）は **RunPod Secrets** に登録し、pod env では **参照 `{{ RUNPOD_SECRET_x }}`** で注入（生値を出さない）
3. `runpodctl pod create --template-id ... --stop-after ...` で起動 → ブラウザ Web Terminal で作業 → `pod stop/delete`

---

## ★推奨ワークフロー（Kaggle×RunPod。次コンペで検証予定）

**原則: Kaggle = 唯一の真実（DC非依存・durable）／ Network Volume = 使い捨て高速scratch（DCに縛られる）／ container disk = 揮発。**
Volumeが消えても・DCが変わっても、Kaggleから再構築できる状態を常に保つ。

```
[前処理] 生データ小 → ローカルで前処理 / 生データ大 → pod上で前処理（上り帯域がボトルネックになるため）
   ↓ Kaggle private dataset に up（= 真実・版管理。fold一貫性のため version を記録）
[学習] pod上で kaggle datasets download → 学習 → ckpt は Volume(高速scratch)
   ↓ 重要ckpt / 良モデルは その都度 Kaggle(/HF) にも push（DC非依存の保険）
[提出] 良モデルを dataset 化 → 推論notebookにattach（Kaggle Code Competition）
```

### ストレージ3層の役割
| 層 | 役割 | 揮発性 |
|---|---|---|
| **Kaggle dataset** | cold durable（入力データ / 出力モデルの真実の置き場） | 永続・無料 |
| **Network Volume** | warm scratch（学習中ckpt・中間生成物） | 永続だが残高ゼロで消える→真実はKaggle側 |
| container disk | ephemeral（pod削除で消える） | 揮発 |

### Volume 要否・サイズ・個数の判断
- **小〜中容量 / 起動少**: Volume不要 or ckptのみの最小Volume。データはKaggleから毎回DL
- **巨大データ × 頻繁起動**: ⚠️ DL中もGPU課金が走る → データも一度Volumeに置いて再DLを省く（Volumeは大きくなる）。判断式 `毎回DL時間×GPU単価×起動回数` vs `データ分のVolume月額`
- **個数**: 数でなく「**実際に使うDCごとに1個**」（Volumeはpodと同一DC固定）。1個の中をフォルダ分けで複数実験を回せる
- **On-Demand単発のみ**なら Volume すら省ける（ckpt→container disk→良いものだけ最後にKaggle up）。Volumeが効くのは spot / 頻繁stop-resume / 多pod並列read

### ★運用で刺さる落とし穴（と対策）
1. **ローカル→Kaggleの上り帯域**が最大のボトルネック → 巨大データは pod上で前処理。ローカル前処理は数GB級まで
2. **GPU在庫の偏在でVolumeのDCにGPUが無い事故** → Volumeは使い捨て前提（真実はKaggle）。DCにこだわらない
3. **ckptがVolumeだけだと別DCで再開不可** → 重要ckptは定期的に Kaggle/HF にも push（DC非依存の保険）
4. **残高ゼロでVolume消失＝復元不可** → 自動チャージON ＋ 上記3で被害ゼロ
5. **「良かったらup」を後回しにすると消える＋提出に必須** → 学習完了→即 `kaggle datasets version` で push→それからpod削除、を1手順に固定

> **追加すべき要点は実質1つ**: 「ckptと良モデルは Volume だけでなく Kaggle(/HF) にも逃がす」。これで在庫偏在・DCロック・Volume消失の全部に耐える。

---

## 1. ローカル環境構築（1回）

```bash
# runpodctl（sudo不要・ユーザー領域へ）
mkdir -p ~/.local/bin
TAG=$(curl -s https://api.github.com/repos/runpod/runpodctl/releases/latest | grep -oP '"tag_name":\s*"\K[^"]+')
curl -sL -o ~/.local/bin/runpodctl "https://github.com/runpod/runpodctl/releases/download/${TAG}/runpodctl-linux-amd64"
chmod +x ~/.local/bin/runpodctl
runpodctl version          # 2.3.0+ を確認

# Python SDK（runpod_ops.py 用。CLIだけなら不要）
pip install --user runpod
```

---

## 2. 認証（鍵はローカル `.runpod.env` のみ）

```bash
cp tools/runpod/.runpod.env.example .runpod.env   # リポジトリ直下に置く
# .runpod.env を編集して RUNPOD_API_KEY を貼る（runpod.io/console/user/settings → API Keys → Create, Read/Write）
source .runpod.env
runpodctl me               # 残高・spend が出れば認証OK（課金なし）
```

- **`.runpod.env` は必ず gitignore**（`*.env` / `.runpod.env`）。`git check-ignore .runpod.env` で確認
- `RUNPOD_API_KEY` だけはローカル必須（runpodctlを動かす鍵＝Secret化できない）。`~/.runpod/config.toml`(=`runpodctl doctor`) でも可だが、`.runpod.env` に一元化すると runpod_ops.py / smoke_test.sh と共有できて楽
- ⚠️ **鍵の値をチャット/ログ/コミットに出さない**。存在確認は真偽＋長さ＋先頭数文字のみ（`[ -n "$RUNPOD_API_KEY" ] && echo "set (${#RUNPOD_API_KEY}文字)"`）。`echo $VAR` / `${VAR:-...}` / 鍵ファイルの `cat` は使わない

---

## 3. runpodctl 2.3.0 コマンド体系（新）

> ⚠️ ネット上の古い記事の `runpodctl create pods` / `get pod` / `stop pod` は **deprecated**。下記の新体系を使う。

```
runpodctl pod         create|list|get|start|stop|restart|delete|update
runpodctl gpu list    利用可能GPU種別と空き（要API key）
runpodctl network-volume create|list|get|delete|update   (alias: nv)
runpodctl datacenter list                                (alias: dc)  ← Volumeとpodは同一DC必須
runpodctl me          残高・spend  (alias: user/account)
runpodctl ssh         add-key|info|list-keys|remove-key
runpodctl send <file> / receive <code>   croc経由のファイル転送（SSH鍵不要）
runpodctl billing     課金履歴
```

### `pod create` 主要フラグ（実機確認）
| フラグ | 用途 |
|---|---|
| `--gpu-id` | GPU種別ID（下表）。`runpodctl gpu list` の `gpuId` 列 |
| `--cloud-type` | `SECURE`(既定) / `COMMUNITY` |
| `--network-volume-id` | 永続Volumeアタッチ |
| `--volume-mount-path` | マウント先（既定 `/workspace`） |
| `--image` | Dockerイメージ（templateなしなら必須） |
| `--template-id` | テンプレ起動。`runpodctl template search <kw>` で探す |
| `--env` | 環境変数（**JSON文字列**）。Secret参照を渡せる（§5） |
| `--ports` | 公開ポート `'8888/http,22/tcp'` |
| `--container-disk-in-gb` | コンテナディスク（既定20） |
| `--stop-after` | **自動停止 datetime（課金漏れ最終防衛）** 例 `2026-06-01T09:00:00Z` |
| `--terminate-after` | 自動削除 datetime |
| `--compliance` | ホストを規約で絞る `HIPAA,SOC_2_TYPE_2`（医療/機密データ時） |
| `--data-center-ids` | DC指定（Volumeと一致必須） |

### GPU ID（`--gpu-id` にそのまま渡す verbatim）
| GPU | gpuId |
|---|---|
| A100 80GB PCIe | `NVIDIA A100 80GB PCIe` |
| A100 80GB SXM | `NVIDIA A100-SXM4-80GB` |
| RTX 4090 | `NVIDIA GeForce RTX 4090` |
| L40S | `NVIDIA L40S` |
| RTX A6000 | `NVIDIA RTX A6000` |
| RTX A5000 | `NVIDIA RTX A5000` |
| H100 80GB | `NVIDIA H100 80GB HBM3` |

※ `gpu list` に**価格は出ない**（公式pricing or コンソールで確認）。`stockStatus`(High/Low)と`available`は出る。

### `network-volume create`
| フラグ | 必須 | 備考 |
|---|---|---|
| `--name` | ✅ | |
| `--size` | ✅ | GB（1–4000） |
| `--data-center-id` | ✅ | `runpodctl datacenter list` で確認。**podと同一DC必須** |

---

## 4. pod ライフサイクル & 接続

```bash
source .runpod.env
runpodctl me                                  # 残高（課金前確認）
runpodctl datacenter list                     # Volume置くDC決定
runpodctl gpu list                            # 目的GPUの空き・ID確認
# ★--template-id 必須（bare --image だと即EXITED）／--stop-after は切り忘れ保険
#   ※継続行 `\` の後ろにコメントを書くと行継続が壊れて --stop-after 等が落ちるので書かない
runpodctl pod create --name train \
  --gpu-id "NVIDIA A100 80GB PCIe" --cloud-type SECURE \
  --network-volume-id <VOL_ID> --volume-mount-path /workspace \
  --template-id runpod-torch-v280 \
  --container-disk-in-gb 40 \
  --stop-after $(date -u -d '+8 hours' +%Y-%m-%dT%H:%M:%SZ)
runpodctl pod list                            # ID・状態（RUNNINGになるまで数十秒）
runpodctl ssh info <POD_ID>                   # ssh接続情報
# ... 作業 ...
runpodctl pod stop <POD_ID>                   # 課金停止（Volume/disk保持）
runpodctl pod delete <POD_ID>                 # 完全削除（Network Volumeは残る）
runpodctl me                                  # spend確認
```

### pod 内での作業（接続方法）— SSH必須ではない
| 方法 | 鍵 | 備考 |
|---|---|---|
| **Web Terminal**（RunPodコンソール） | 不要 | ブラウザで即シェル。最も手軽 |
| **JupyterLab**（`--ports '8888/http'`） | 不要 | ブラウザ。ノート作業向き |
| **SSH** | 要（`runpodctl ssh add-key` で公開鍵登録） | `ssh root@<ip> -p <port>`。CI/rsync向き |

### ファイル転送（SSH鍵不要）
`runpodctl send <file>` → コードフレーズ表示 → 受信側 `runpodctl receive <code>`（croc, P2P）。
小〜中サイズの受け渡しに。大容量データは pod 上で直接DL（HF/Kaggle/S3）して Network Volume へ。

---

## 5. 鍵運用（2層モデル）— 生値を露出させない

pod に鍵を渡す方法は2通り。**機密度の高い鍵は RunPod Secrets を使う**のがベスト。

| | A: RunPod Secrets 参照 | B: `.runpod.env` 生値 → `--env` |
|---|---|---|
| ローカルディスク | ✅ 残さなくていい | 🟡 平文で残る（gitignore済の自PC） |
| pod設定/ダッシュボード/API/履歴 | ✅ 参照のみ（生値出ない） | 🔴 生値が出うる |
| RunPod側保管 | ✅ 暗号化・**再表示不可** | 🟡 pod envとして保持 |
| 稼働中pod内 `echo $X` | 🔴 読める | 🔴 読める（**両方共通**） |

**手順（A方式）:**
1. コンソール → Secrets → Create。`Name=GH_TOKEN` / `Value=<生トークン>`（`{{ }}`は書かない・クォート無し）
2. pod env で参照: `GH_TOKEN={{ RUNPOD_SECRET_GH_TOKEN }}`（`--env` JSON か Web UI の Environment Variables）
3. ローカル `.runpod.env` からは生トークンを消し、**`RUNPOD_API_KEY` だけ残す**

- `runpod_ops.py` の `CFG.use_runpod_secrets` は**既定 False（生値を渡す）**。True にするとこの参照を自動生成するが、下記の通り SDK では解決されないため Web UI 起動以外では使えない（True のまま `up` すると警告が出る）
- ✅ **実機確認（2026-06-01）: CLI/SDK の `--env` では `{{ RUNPOD_SECRET_x }}` は解決されない**。→ Web UI から起動（UIは確実に解決）するか、`use_runpod_secrets=False`（既定）で生値を渡すか、**鍵は scp で起動後に注入**する（§9.5 の確定手順）
- pod内では結局 env として読めるので、**最後の砦は最小スコープ＋短期失効トークン**（例: GitHub PAT は Fine-grained / 対象repoのみ / Contents:Read-only / 期限付き）

---

## 6. pod上で private repo を clone（HTTPS + PAT。SSH鍵不要）

使い捨て pod には **HTTPS + Fine-grained PAT** が定石（SSH Deploy Key より配布管理が楽）。

1. GitHub → Settings → Developer settings → **Fine-grained tokens** → 対象repoのみ / **Contents: Read-only** / 期限付き
2. RunPod Secret に `GH_TOKEN`（値=`github_pat_...`）、`GIT_REPO`（値=`github.com/<user>/<repo>.git`）を登録
3. pod env で参照注入 → `startup.sh` が自動 clone:
   ```bash
   # ★トークンは URL に埋め込まない（ps/エラー出力に露出＋除去後の再起動 pull が壊れる）
   #   credential helper なら argv にトークンが出ず、再起動時の pull もそのまま通る
   git config --global credential.helper '!f() { echo "username=x-access-token"; echo "password=${GH_TOKEN}"; }; f'
   git clone "https://${GIT_REPO}" "$CODE_DIR"
   ```
- ローカルで事前検証（課金なし）: `git ls-remote "https://x:${GH_TOKEN}@${GIT_REPO}" HEAD`（使い捨てコマンドなので URL 埋め込みでも可）

---

## 7. Network Volume（永続ストレージ）

- **$0.07/GB/月**（〜1TB）。データセット/ckpt を常駐させ pod 再作成のたびにアタッチ
- ⚠️ **Secure Cloud 専用**（Community では使えない）
- ⚠️ **Volume と pod は同一 DC 必須**（リージョン固定）→ `datacenter list`→Volume作成DC→同DCのGPU空きを `gpu list`、の順
- 複数 pod から**読み取り共有可**（同時書き込みは破損リスクで不可）
- ⚠️ **残高不足が続くと Volume 削除＝復元不可** → 自動チャージ設定必須
- 縮小不可（増やすのみ）。最初から余裕を持って作成

---

## 8. コスト管理（課金漏れを物理的に防ぐ）

- 課金は **per-second**（Network Volume のみ時間/月単位）
- **二重の自動停止**: `--stop-after <datetime>`（pod側） + `startup.sh` の `trap '... pod stop' EXIT`（学習終了/中断時）
- `runpodctl me` の `spendLimit` でアカウント上限、コンソールで自動チャージ閾値を設定
- spot的に使うなら ckpt 30分ごと + Network Volume 保存（中断時 SIGTERM 5秒 → ckpt再開で復帰）

---

## 9. ハマりどころ（実地で踏んだ）
- **★bare `--image` は即EXITED**: 常駐プロセスが無いと pod が起動直後に終了する。**必ず `--template-id`（公式 `runpod-torch-v280` 等）を使う**。GUI起動はテンプレ既定なので動く＝CLIで `--image` 直指定したのが敗因だった（5090はGUIで取れたのに CLI で「消えた」ように見えたのはこれ）
- **`pod list` は EXITED を表示しない**（RUNNINGのみ）。終了/失敗の確認は `pod get <id>`。listが空でも EXITED pod が居る場合があるので `me` の spend と併せて見る
- **deprecated コマンド**: `create pods`/`get pod`/`stop pod` は旧。新は `pod create`/`pod list`/`pod stop`
- **`gpu list` に価格なし**: 価格は公式pricing/コンソール。在庫は `stockStatus`
- **Volume は同一DC固定**: 別DCのGPUにアタッチ不可
- **`{{ RUNPOD_SECRET_x }}` はCLI/SDKでは解決されない（実機確認済 2026-06-01）**: Web UI 起動か、scpで起動後注入（§9.5）か、生値
- **残高ゼロで Volume 削除**: 自動チャージ必須
- **WSL から GitHub/pod への SSH**: `~/.ssh` が 9p drvfs(metadata無)だと chmod が効かず 777 → OpenSSH が拒否。**push/接続は Windows 側 or runpodctl(HTTPS) or Web Terminal で回避**。直すなら `/etc/wsl.conf` に `[automount]\noptions=metadata` → `wsl --shutdown`
- **`gpu list` 結果は時々変動**: 同じ呼び出しでも在庫により出る種別が変わる

---

## 9.5 ★実証済みレシピ：Kaggle dataset → RunPod でモデル学習（2026-06-01 実機検証）

H100で end-to-end 成功（local subset→Kaggle upload→pod download→学習→best ckpt をscpで回収）。
**学習フレームワーク非依存**の、実走で踏んだ罠と確定手順:

**ローカル（upload）**
```bash
# データを zip 1本にして dataset-metadata.json と共に置く → 既定で private
python3 -m kaggle datasets create -p <stg_dir> --dir-mode skip
# ★Kaggleはupした.zipを自動展開する → datasetには中身(データ/設定ファイル)が直接入る
```
**pod（download→train）**
```bash
pip install -q --break-system-packages kaggle <学習ライブラリ>   # ★PEP668: runpod-torch templateは--break-system-packages必須
python -m kaggle datasets download -d <user>/<slug> -p .         # 鍵は scp で /root/.kaggle/kaggle.json に入れておく
unzip -o -q <slug>.zip -d data                                   # ★1段だけ（Kaggleが既に展開済なので二重zipにならない）
# ★学習設定ファイルのデータルートは絶対パスに（相対はCWD基準で誤解決）。例（YAML設定の場合）:
sed -i 's#^path:.*#path: /workspace/data#' data/<config>
<学習コマンド> ... data=/workspace/data/<config> ... project=/workspace/runs name=run   # 同名既存だと自動採番される例あり
# 成果物: /workspace/runs/.../best.* → scp でローカル/Kaggle/HFに退避
```
**4つの確定罠（フレームワーク非依存）**:
1. `pip` は **`--break-system-packages`** 必須（PEP668。runpod-torch template）
2. Kaggleは**upした.zipを自動展開** → DL後の展開は**1段だけ**（二重zipにしない）
3. **学習設定のデータルートは絶対パス**（相対 `.` はCWD基準で誤解決して not found になる）
4. **CLI/SDK `--env` は `{{ RUNPOD_SECRET_x }}` を解決しない** → 鍵は **scp で起動後注入**（`scp -i <key> -P <port> ~/.kaggle/kaggle.json root@<ip>:/root/.kaggle/`）

---

## 10. クイックスタート（疎通テスト）
```bash
source .runpod.env
bash tools/runpod/smoke_test.sh                 # 最安GPUで起動→RUNNING→接続情報（★数円）
# ブラウザ Web Terminal で nvidia-smi 確認 → 終わったら:
bash tools/runpod/smoke_test.sh teardown <POD_ID>
```
