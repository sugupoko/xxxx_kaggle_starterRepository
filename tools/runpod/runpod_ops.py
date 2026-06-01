#!/usr/bin/env python
"""ローカルから RunPod を操作する（Python SDK 版）。Network Volume アタッチ対応。汎用・移植用。

★推奨は CLI パス: `runpodctl 2.3.0 pod create`（`--network-volume-id`/`--stop-after`自動停止/`--compliance`対応）。
  全仕様・GPU ID・操作シーケンスは README.md を見ること。本スクリプトは Python 完結したい時の代替。

鍵: RUNPOD_API_KEY は環境変数から読む（コード/repoに書かない）。先に `source .runpod.env`。
使い方:
  python runpod_ops.py up         # pod 起動（★課金開始）
  python runpod_ops.py list       # pod 一覧・状態
  python runpod_ops.py stop <id>  # 停止（課金停止。Volume/disk保持）
  python runpod_ops.py down <id>  # terminate（削除。Network Volumeは残る）
"""
import os, sys, json

# ===== 設定（プロジェクトに合わせて編集） =====
class CFG:
    name             = "train"
    gpu_type_id      = "NVIDIA A100 80GB PCIe"   # README の GPU ID 表から。`runpodctl gpu list` で確認
    cloud_type       = "SECURE"                   # SECURE=機密/Network Volume / COMMUNITY=安いが第三者ホスト
    # ★公式テンプレ必須（bare image だと常駐プロセス無しで即EXITED。GUIはテンプレ使用）
    template_id      = "runpod-torch-v280"        # runpodctl template list --type official
    image_name       = ""                          # template使用時は空でよい（templateが画像+起動を提供）
    network_volume_id= os.environ.get("RUNPOD_VOLUME_ID", "")
    volume_mount_path= "/workspace"
    container_disk_gb= 40
    ports            = "8888/http,22/tcp"         # Jupyter + SSH
    cost_ceiling     = None
    # ★pod に注入する env。鍵は「生値」でなく RunPod Secret 参照 {{ RUNPOD_SECRET_x }} を渡す
    #   = pod設定/ダッシュボード/API/履歴に生値が残らない（生値はRunPod側に暗号化保管）。
    #   ⚠️ API/SDK経由で {{ }} が解決されるかは初回pod起動で要検証。
    #      解決されない場合は use_runpod_secrets=False にして os.environ の生値を渡す（Web UI起動なら確実に解決）。
    use_runpod_secrets = True
    _secret_keys     = ["GH_TOKEN", "GIT_REPO", "KAGGLE_USERNAME", "KAGGLE_KEY", "HF_TOKEN"]  # RunPod Secretの名前
    if use_runpod_secrets:
        pod_env = {k: "{{ RUNPOD_SECRET_%s }}" % k for k in _secret_keys}
    else:
        pod_env = {k: os.environ.get(k, "") for k in _secret_keys}
    pod_env["HF_HOME"] = "/workspace/cache/hf"


def _client():
    import runpod
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        sys.exit("[FATAL] RUNPOD_API_KEY 未設定。先に `source .runpod.env`（鍵はチャットに貼らない）")
    runpod.api_key = key
    return runpod


def up():
    rp = _client()
    if not CFG.network_volume_id:
        print("[warn] network_volume_id 未設定。Volumeなしで起動（データは pod 停止で消える）。")
    env = {k: v for k, v in CFG.pod_env.items() if v}   # 空の鍵は渡さない
    kw = dict(
        name=CFG.name, gpu_type_id=CFG.gpu_type_id,
        cloud_type=CFG.cloud_type, container_disk_in_gb=CFG.container_disk_gb,
        ports=CFG.ports, volume_mount_path=CFG.volume_mount_path, env=env,
    )
    if CFG.template_id:   kw["template_id"] = CFG.template_id   # ★常駐+SSHはテンプレ任せ
    elif CFG.image_name:  kw["image_name"]  = CFG.image_name
    if CFG.network_volume_id:
        kw["network_volume_id"] = CFG.network_volume_id
    print(f"[create] {CFG.cloud_type} {CFG.gpu_type_id} vol={CFG.network_volume_id or 'NONE'} (★課金開始)")
    pod = rp.create_pod(**kw)
    print(json.dumps(pod, indent=2, ensure_ascii=False))
    print(f"\n→ 起動後: python {sys.argv[0]} list / runpodctl ssh info <id>")


def lst():
    rp = _client()
    pods = rp.get_pods()
    for p in pods:
        print(f"- {p.get('id')} | {p.get('name')} | {p.get('desiredStatus')} | "
              f"{(p.get('machine') or {}).get('gpuDisplayName','?')} | costPerHr={p.get('costPerHr')}")
    if not pods:
        print("(pod なし)")


def stop(pod_id):
    rp = _client(); print(rp.stop_pod(pod_id)); print(f"[stopped] {pod_id} (Volume/disk保持・課金停止)")


def down(pod_id):
    rp = _client(); print(rp.terminate_pod(pod_id)); print(f"[terminated] {pod_id} (削除。Network Volumeは残る)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "up":     up()
    elif cmd == "list": lst()
    elif cmd == "stop": stop(sys.argv[2])
    elif cmd == "down": down(sys.argv[2])
    else: sys.exit(f"unknown cmd: {cmd}  (up|list|stop <id>|down <id>)")
