#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub 直连被代理阻断时的备用同步工具（走 api.github.com）。

用法：
    python tools\\push_github_api.py                 # 默认 debrnr/DeepinOfflineMaker
    python tools\\push_github_api.py <owner> <repo>  # 指定其他仓库

原理：用 Git Credential Manager 中已保存的 github.com 凭据，通过 REST API
把工作区里全部 git 跟踪文件（含二进制 .deb）做成一次提交推到 main。
空仓库会自动先建初始提交。凭据只在本进程内使用，不会打印或写入文件。
"""
import os
import sys
import json
import base64
import subprocess
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNER = "debrnr"
REPO = "DeepinOfflineMaker"
if len(sys.argv) >= 3:
    OWNER, REPO = sys.argv[1], sys.argv[2]


def get_token():
    p = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        text=True,
        capture_output=True,
        cwd=ROOT,
    )
    for ln in p.stdout.splitlines():
        if ln.startswith("password="):
            return ln.split("=", 1)[1]
    raise SystemExit("ERROR: 未找到 github.com 凭据，请先用 Git Credential Manager 登录一次")


TOKEN = get_token()
BASE = "/repos/%s/%s" % (OWNER, REPO)


def api(method, path, payload=None):
    url = "https://api.github.com" + path
    data = (
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if payload is not None
        else None
    )
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "DeepinOfflineMaker-push",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw[:300]}
        return e.code, body
    except Exception as e:
        return -1, {"error": repr(e)}


def head_sha(branch):
    st, body = api("GET", BASE + "/git/ref/heads/" + branch)
    if st == 200 and "object" in body:
        return body["object"]["sha"]
    return None


def ensure_initialized(branch):
    sha = head_sha(branch)
    if sha:
        print("[github] 仓库已初始化，父提交 %s" % sha, flush=True)
        return sha
    with open(os.path.join(ROOT, ".gitattributes"), "rb") as f:
        content = f.read()
    st, body = api(
        "PUT",
        BASE + "/contents/.gitattributes",
        {
            "message": "Initialize repository",
            "content": base64.b64encode(content).decode("ascii"),
            "branch": branch,
        },
    )
    print("[github] 初始提交: %s" % st, flush=True)
    if st not in (200, 201):
        print(str(body)[:300], flush=True)
        raise SystemExit(1)
    sha = head_sha(branch)
    if not sha:
        raise SystemExit("ERROR: 初始化后仍找不到 main 分支")
    return sha


def main():
    st, info = api("GET", BASE)
    if st != 200:
        print("[github] 读取仓库信息失败: %s %s" % (st, str(info)[:300]), flush=True)
        raise SystemExit(1)
    branch = info.get("default_branch") or "main"
    print("[github] 目标: %s/%s  分支: %s" % (OWNER, REPO, branch), flush=True)

    parent = ensure_initialized(branch)

    raw = subprocess.check_output(["git", "ls-files", "-s", "-z"], cwd=ROOT)
    entries = []
    for rec in raw.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        entries.append((meta.split()[0].decode(), path.decode("utf-8")))
    print("[github] 待上传文件: %d" % len(entries), flush=True)

    tree = []
    for i, (mode, path) in enumerate(entries, 1):
        with open(os.path.join(ROOT, path), "rb") as f:
            blob = f.read()
        st, body = api(
            "POST",
            BASE + "/git/blobs",
            {"content": base64.b64encode(blob).decode("ascii"), "encoding": "base64"},
        )
        if st != 201 or "sha" not in body:
            print("[github] 上传失败 %s -> %s %s" % (path, st, str(body)[:200]), flush=True)
            raise SystemExit(1)
        tree.append({"path": path, "mode": mode, "type": "blob", "sha": body["sha"]})
        if i % 6 == 0 or i == len(entries):
            print("[github]   进度 %d/%d" % (i, len(entries)), flush=True)

    st, tree_obj = api("POST", BASE + "/git/trees", {"tree": tree})
    if st != 201:
        print("[github] 建树失败: %s %s" % (st, str(tree_obj)[:300]), flush=True)
        raise SystemExit(1)
    print("[github] tree: %s" % tree_obj["sha"], flush=True)

    st, commit = api(
        "POST",
        BASE + "/git/commits",
        {
            "message": "Sync DeepinOfflineMaker (via api.github.com)",
            "tree": tree_obj["sha"],
            "parents": [parent],
        },
    )
    if st != 201:
        print("[github] 建提交失败: %s %s" % (st, str(commit)[:300]), flush=True)
        raise SystemExit(1)
    print("[github] commit: %s" % commit["sha"], flush=True)

    st, ref = api("PATCH", BASE + "/git/refs/heads/" + branch, {"sha": commit["sha"]})
    if st != 200:
        print("[github] 更新分支失败: %s %s" % (st, str(ref)[:300]), flush=True)
        raise SystemExit(1)
    print("[github] 完成 -> https://github.com/%s/%s" % (OWNER, REPO), flush=True)


if __name__ == "__main__":
    main()
