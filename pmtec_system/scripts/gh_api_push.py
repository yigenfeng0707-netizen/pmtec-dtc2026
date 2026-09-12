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
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if os.path.exists(TMP):
        os.remove(TMP)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[:2000])
    return json.loads(r.stdout) if r.stdout.strip() else None


def remote_exists(path):
    """路径是否存在于远端 main (避免对不存在路径发 DELETE -> 422 BadObjectState)"""
    from urllib.parse import quote
    cmd = ["gh", "api", f"repos/{REPO}/contents/{quote(path)}?ref=main"]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode == 0


# 0) 远端当前 head
remote = gh("git/refs/heads/main")["object"]["sha"]
log(f"remote head: {remote[:10]}")

# 1) 差异 (API 提交对象不在本地库, 用等价本地树 8ebb2e3 作 diff 基准:
#    492f1b6 的 tree 与本地 8ebb2e3 完全一致 —— 上一轮 API 推送即该差异)
LOCAL_BASE = "4ad51e2"
raw = subprocess.run(["git", "-C", ROOT, "diff", "--name-only", "-z",
                      f"{LOCAL_BASE}..HEAD"], capture_output=True,
                     text=True, encoding="utf-8", errors="replace").stdout
paths = [p for p in raw.split("\0") if p]
if not paths:
    log("无差异, 无需推送")
    sys.exit(0)
changes = [("A", p) for p in paths]
log(f"待推送: {len(changes)} 个文件 ({', '.join(p[:50] for p in paths)})")

# 2) blobs (优先 git 对象库读取 — 不依赖磁盘状态, 天然处理 Unicode 路径;
#    HEAD 中不存在的路径 = 删除条目, 以 sha:null 传播删除)
entries = []
for k, (st, path) in enumerate(changes):
    cat = subprocess.run(["git", "-C", ROOT, "cat-file", "blob", f"HEAD:{path}"],
                         capture_output=True)
    if cat.returncode != 0:
        if remote_exists(path):
            entries.append({"path": path, "mode": "100644",
                            "type": "blob", "sha": None})
            log(f"  [{k + 1}/{len(changes)}] {path} -> DELETE")
        else:
            log(f"  [{k + 1}/{len(changes)}] {path} -> skip DELETE (远端不存在)")
        continue
    raw_bytes = cat.stdout
    b64 = base64.b64encode(raw_bytes).decode()
    blob = gh("git/blobs", {"content": b64, "encoding": "base64"})
    entries.append({"path": path, "mode": "100644",
                    "type": "blob", "sha": blob["sha"]})
    log(f"  [{k + 1}/{len(changes)}] {path} ({len(raw_bytes) / 1e3:.0f} KB)"
        f" -> {blob['sha'][:10]}")

# 2b) 远端残留垃圾显式清理 (本地先加后删 -> diff 不含, 但远端存在)
REMOTE_JUNK = [
    "参考视频.mp4",
    "工业互联网研究院的视频.mp4",
    "_ref_readme.md",
    "pmtec_system/output/_ref_frames/ref_0.jpg",
    "pmtec_system/output/_ref_frames/ref_1.jpg",
    "pmtec_system/output/_ref_frames/ref_2.jpg",
]
for p in REMOTE_JUNK:
    if remote_exists(p):
        entries.append({"path": p, "mode": "100644", "type": "blob",
                        "sha": None})
        log(f"  [junk] {p} -> DELETE")
    else:
        log(f"  [junk] {p} -> 远端不存在, 跳过")

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
