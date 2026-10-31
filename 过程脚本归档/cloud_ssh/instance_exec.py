# -*- coding: utf-8 -*-
"""PMTEC 训练实例 SSH 执行助手（P19，2026-10-28）。

用法:
  python instance_exec.py exec "command" [timeout_s]   执行命令
  python instance_exec.py put <local> <remote>         上传文件
  python instance_exec.py get <remote> <local>         下载文件
密码从环境变量 PMTEC_GPU_PW 读取（不落盘；控制台「登录信息」可随时重查）。
实例: ubuntu@36.103.199.248（RTX 4090 24GB x2, 按量计费；10-31 起 IP，旧 .153 已易主）
"""
import os
import sys
import time

import paramiko

HOST = "36.103.199.248"  # 2026-10-31 起：旧 IP .153 停机重开后未保留，已易主
USER = "ubuntu"


def connect():
    pw = os.environ.get("PMTEC_GPU_PW", "").strip()
    if not pw:
        sys.exit("请先 set PMTEC_GPU_PW=<密码>（控制台登录信息里查）")
    last = None
    for _ in range(3):
        try:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(HOST, 22, USER, pw, timeout=20,
                      banner_timeout=30, auth_timeout=30)
            return c
        except Exception as e:
            last = e
            time.sleep(5)
    raise last


def main():
    mode = sys.argv[1]
    c = connect()
    if mode == "exec":
        cmd, tmo = sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 120
        _, out, err = c.exec_command(cmd, timeout=tmo)
        print(out.read().decode("utf-8", "replace").strip())
        e = err.read().decode("utf-8", "replace").strip()
        if e:
            print("STDERR:", e[:400])
    else:
        sftp = c.open_sftp()
        if mode == "put":
            sftp.put(sys.argv[2], sys.argv[3])
            print("put ok:", sys.argv[3])
        elif mode == "get":
            sftp.get(sys.argv[2], sys.argv[3])
            print("get ok:", sys.argv[3])
        sftp.close()
    c.close()


if __name__ == "__main__":
    main()
