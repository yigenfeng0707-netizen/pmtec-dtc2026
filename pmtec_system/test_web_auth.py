#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web 展示层认证测试（rest_gateway × P7 security/auth 模块端到端）

Validates (全部离线，起真实 ThreadingHTTPServer，不依赖外网):
  1. PMTEC_WEB_USERS 解析：三角色条目 + 非法条目跳过 + 角色域校验
  2. 公开端点放行：/health（uptime 为真实运行秒数且 auth_enabled 标志正确）
  3. 门禁：未认证访问业务端点 401；伪造/过期凭据 401
  4. 登录：正确凭据 200 + Set-Cookie(HttpOnly) + JWT(Bearer 双通道)；错误凭据 401
  5. 会话校验：/auth/check Cookie/Bearer 双通道返回 user_id/role
  6. 角色矩阵：observer 只读；operator 可触发 AI 分析、不可启停仿真；
     commander 全量（仿真启停/实例注册）
  7. 登出：Cookie 清除后业务端点回到 401
  8. 未启用（未设 PMTEC_WEB_USERS）时行为与历史版本一致（业务端点无门禁）

Run: python -X utf8 test_web_auth.py
"""
import hashlib
import http.client
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

PASS = 0
FAIL = 0
RESULTS = []


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        RESULTS.append(f"  [PASS] {name}")
    else:
        FAIL += 1
        RESULTS.append(f"  [FAIL] {name}  {detail}")


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


TEST_USERS = ",".join(
    [
        f"fengyigen:{sha('Fyg236998@')}:commander",
        f"pingwei:{sha('Test123456@')}:operator",
        f"test:{sha('Test236998@')}:observer",
        "bad-entry-no-role",
        "shortdigest:abc123:observer",
        f"ghost:{sha('x')}:spectator",
    ]
)


def req(port, method, path, body=None, cookie=None, bearer=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    payload = json.dumps(body) if body is not None else None
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    set_cookie = resp.getheader("Set-Cookie") or ""
    conn.close()
    try:
        parsed = json.loads(data) if data else {}
    except json.JSONDecodeError:
        parsed = {"_raw": data[:200].decode("utf-8", "replace")}
    return resp.status, parsed, set_cookie


def start_gateway(env_users: str):
    os.environ["PMTEC_JWT_SECRET"] = "unit-test-secret"
    if env_users is None:
        os.environ.pop("PMTEC_WEB_USERS", None)
    else:
        os.environ["PMTEC_WEB_USERS"] = env_users
    from dt_platform.rest_gateway import RestGateway

    gw = RestGateway(port=0)  # 端口 0 = 系统分配，避免并发冲突
    gw.start()
    port = gw._server.server_address[1]
    return gw, port


def main():
    print("=" * 60)
    print("PMTEC Web 认证测试 (rest_gateway × security/auth)")
    print("=" * 60)

    from dt_platform.rest_gateway import parse_web_users

    # ---- 1. 用户库解析 ----
    print("[1] PMTEC_WEB_USERS 解析")
    users = parse_web_users(TEST_USERS)
    check("三账号入库", set(users) == {"fengyigen", "pingwei", "test"}, str(users.keys()))
    check("角色映射正确", users.get("pingwei", ("", ""))[1] == "operator"
          and users.get("fengyigen", ("", ""))[1] == "commander"
          and users.get("test", ("", ""))[1] == "observer")
    check("非法条目跳过", "bad-entry-no-role" not in users and "ghost" not in users)

    # ---- 2-7. 启用认证的网关 ----
    gw, port = start_gateway(TEST_USERS)
    try:
        check("auth_enabled=True", gw.auth_enabled is True)

        print("[2] 公开端点")
        st, body, _ = req(port, "GET", "/api/v1/health")
        check("health 200 且公开", st == 200, f"st={st}")
        check("auth_enabled 标志", body.get("auth_enabled") is True)
        check("uptime 为真实秒数", isinstance(body.get("uptime_s"), int) and 0 <= body["uptime_s"] <= 30,
              str(body.get("uptime_s")))

        print("[3] 门禁")
        st, body, _ = req(port, "GET", "/api/v1/state")
        check("未认证访问 state → 401", st == 401, f"st={st}")
        st, body, _ = req(port, "GET", "/api/v1/state", cookie="pmtec_token=forged.jwt.value")
        check("伪造令牌 → 401", st == 401, f"st={st}")

        print("[4] 登录")
        st, body, _ = req(port, "POST", "/api/v1/auth/login",
                          body={"username": "pingwei", "password": "wrong"})
        check("错误密码 → 401", st == 401, f"st={st}")
        st, body, setck = req(port, "POST", "/api/v1/auth/login",
                              body={"username": "pingwei", "password": "Test123456@"})
        check("评委登录 200", st == 200, f"st={st}")
        check("角色 operator", body.get("role") == "operator", str(body))
        check("Set-Cookie HttpOnly", "pmtec_token=" in setck and "HttpOnly" in setck, setck)
        judge_token = body.get("token", "")
        check("同时返回 JWT", len(judge_token) > 40, judge_token[:20])

        print("[5] 会话校验")
        cookie = setck.split(";")[0]
        st, body, _ = req(port, "GET", "/api/v1/auth/check", cookie=cookie)
        check("Cookie 通道 check 200", st == 200 and body.get("user_id") == "pingwei", f"st={st}")
        st, body, _ = req(port, "GET", "/api/v1/auth/check", bearer=judge_token)
        check("Bearer 通道 check 200", st == 200, f"st={st}")

        print("[6] 角色矩阵")
        st, _, _ = req(port, "GET", "/api/v1/state", cookie=cookie)
        check("operator 读 state 过门禁(503=引擎未挂)", st == 503, f"st={st}")
        st, body, _ = req(port, "POST", "/api/v1/analysis", body={}, cookie=cookie)
        check("operator 可触发 AI 分析(过门禁)", st == 503, f"st={st}")
        st, body, _ = req(port, "POST", "/api/v1/sim/start", body={}, cookie=cookie)
        check("operator 启停仿真 → 403", st == 403 and body.get("required_role") == "commander", f"st={st}")
        st, _, sc2 = req(port, "POST", "/api/v1/auth/login",
                         body={"username": "test", "password": "Test236998@"})
        obs_cookie = sc2.split(";")[0]
        st, _, _ = req(port, "POST", "/api/v1/analysis", body={}, cookie=obs_cookie)
        check("observer 触发分析 → 403", st == 403, f"st={st}")
        st, _, sc3 = req(port, "POST", "/api/v1/auth/login",
                         body={"username": "fengyigen", "password": "Fyg236998@"})
        admin_cookie = sc3.split(";")[0]
        st, _, _ = req(port, "POST", "/api/v1/sim/start", body={}, cookie=admin_cookie)
        check("commander 启停仿真过门禁(503)", st == 503, f"st={st}")

        print("[7] 登出")
        st, _, outck = req(port, "POST", "/api/v1/auth/logout", cookie=cookie)
        check("logout 200 + 清 Cookie", st == 200 and "Max-Age=0" in outck, outck)
        st, _, _ = req(port, "GET", "/api/v1/state", cookie="pmtec_token=")
        check("清后回 401", st == 401, f"st={st}")
    finally:
        gw.stop()

    # ---- 8. 未启用认证 = 历史行为 ----
    print("[8] 未启用认证（未设 PMTEC_WEB_USERS）")
    gw2, port2 = start_gateway(None)
    try:
        check("auth_enabled=False", gw2.auth_enabled is False)
        st, body, _ = req(port2, "GET", "/api/v1/state")
        check("业务端点无门禁(503)", st == 503, f"st={st}")
        st, body, _ = req(port2, "GET", "/api/v1/health")
        check("health auth_enabled=False", body.get("auth_enabled") is False)
    finally:
        gw2.stop()

    print("-" * 60)
    for line in RESULTS:
        print(line)
    print("-" * 60)
    print(f"PASS={PASS} FAIL={FAIL}")
    if FAIL:
        sys.exit(1)
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
