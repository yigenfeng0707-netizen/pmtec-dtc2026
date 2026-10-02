#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web 展示层账号条目生成器 —— 从明文口令生成 PMTEC_WEB_USERS 环境变量行。

密码只以 sha256 摘要形态进入 .env / 环境变量，明文不落盘、不入仓。

用法（在 pmtec_system/ 下，或任意位置指定 -r 指向仓库根）:
  python deploy/web_auth_helper.py 用户名 明文密码 角色      # 单条
  python deploy/web_auth_helper.py --stdin                    # 多条: 每行 "用户名 密码 角色"
  python deploy/web_auth_helper.py --secret                   # 附带生成 PMTEC_JWT_SECRET

角色: commander(管理员/指挥员) | operator(评委) | observer(普通用户/观察员)

输出示例:
  PMTEC_WEB_USERS=fengyigen:9f86d0...:commander,pingwei:ab53a2...:operator
"""

import argparse
import hashlib
import secrets
import sys

VALID_ROLES = ("commander", "operator", "observer")


def digest(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def entry(username: str, password: str, role: str) -> str:
    if role not in VALID_ROLES:
        raise SystemExit(f"[!] 非法角色 '{role}'，可选: {'/'.join(VALID_ROLES)}")
    if not username or ":" in username or "," in username:
        raise SystemExit("[!] 用户名不能为空且不得包含 ':' 或 ','")
    return f"{username}:{digest(password)}:{role}"


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 PMTEC_WEB_USERS 条目")
    ap.add_argument("args", nargs="*", help="用户名 密码 角色")
    ap.add_argument("--stdin", action="store_true", help="从 stdin 逐行读取多账号")
    ap.add_argument("--secret", action="store_true", help="同时生成 PMTEC_JWT_SECRET")
    a = ap.parse_args()

    lines = []
    if a.stdin:
        for raw in sys.stdin:
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            parts = raw.split()
            if len(parts) != 3:
                raise SystemExit(f"[!] 行格式应为 '用户名 密码 角色': {raw!r}")
            lines.append(entry(*parts))
    elif len(a.args) == 3:
        lines.append(entry(*a.args))
    else:
        ap.error("需要 '用户名 密码 角色' 三个参数，或 --stdin")

    print(f"PMTEC_WEB_USERS={','.join(lines)}")
    if a.secret:
        print(f"PMTEC_JWT_SECRET={secrets.token_urlsafe(48)}")
    print("# 写入 pmtec_system/.env（与 docker-compose.demo.yml 同目录）后重载:")
    print("#   docker compose -f docker-compose.demo.yml up -d")
    return 0


if __name__ == "__main__":
    sys.exit(main())
