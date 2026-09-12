"""经 GitHub REST API 推送差异 (blob->tree->commit->ref), 可重复调用"""
import base64
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
REPO = "yigenfeng0707-netizen/pmtec-dtc2026"
ROOT = r"d:\APPs\数字孪生挑战赛"
TMP = os.path.join(ROOT, f"_ghapi_tmp_{os.getpid()}.json")
LOG = os.path.join(ROOT, "_ghapi_push.log")


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def gh(endpoint, payload=None, method=None):
    cmd = ["gh", "api", f"repos/{REPO}/{endpoint}"]
    if payload is not None:
        with open(TMP, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        cmd += ["--input", TMP]
    if method:
        cmd += ["-X", method]
    r = subprocess.run(cmd, capture_output=True)
    if os.path.exists(TMP):
        os.remove(TMP)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", errors="replace")[:500])
    out = r.stdout.decode("utf-8", errors="replace")
    return json.loads(out) if out.strip() else None


# 0) 远端当前 head
remote = gh("git/refs/heads/main")["object"]["sha"]
log(f"remote head: {remote[:10]}")

# 1) 差异 (API 提交对象不在本地库, 用等价本地树 8ebb2e3 作 diff 基准:
#    492f1b6 的 tree 与本地 8ebb2e3 完全一致 —— 上一轮 API 推送即该差异)
LOCAL_BASE = "8ebb2e3"
raw = subprocess.run(["git", "-C", ROOT, "diff", "--name-only", "-z",
                      f"{LOCAL_BASE}..HEAD"], capture_output=True).stdout
paths = [p for p in raw.decode("utf-8", errors="replace").split("\0") if p]
if not paths:
    log("无差异, 无需推送")
    sys.exit(0)
changes = [("A", p) for p in paths]
log(f"待推送: {len(changes)} 个文件 ({', '.join(p[:50] for p in paths)})")

# 2) blobs
entries = []
for k, (st, path) in enumerate(changes):
    fp = os.path.join(ROOT, path.replace("/", os.sep))
    with open(fp, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    blob = gh("git/blobs", {"content": b64, "encoding": "base64"})
    entries.append({"path": path, "mode": "100644",
                    "type": "blob", "sha": blob["sha"]})
    log(f"  [{k + 1}/{len(changes)}] {path} ({os.path.getsize(fp) / 1e3:.0f} KB)"
        f" -> {blob['sha'][:10]}")

# 3) tree
tree_sha = gh(f"commits/{remote}")["commit"]["tree"]["sha"]
new_tree = gh("git/trees", {"base_tree": tree_sha, "tree": entries})
log(f"tree: {new_tree['sha'][:10]}")

# 4) commit + 5) ref
msg = (
    "ci: GitHub Actions 工作流部署至仓库根目录\n"
    "\n"
    "- ci-cd.yml 从 pmtec_system/ 提升至根目录 (GitHub 仅识别根级 .github/workflows),\n"
    "  6 阶段流水线 (lint->test->build->security->push->deploy) 首次实际运行\n"
    "- 新增 workflow_dispatch 手动触发; SARIF 上传 continue-on-error 容错\n"
    "- (经 GitHub REST API 通道推送: git 协议 443 故障期间)"
)
commit = gh("git/commits", {"message": msg, "tree": new_tree["sha"],
                            "parents": [remote]})
gh("git/refs/heads/main", {"sha": commit["sha"], "force": False},
   method="PATCH")
log(f"commit: {commit['sha'][:10]} -> refs/heads/main  PUSHED")
