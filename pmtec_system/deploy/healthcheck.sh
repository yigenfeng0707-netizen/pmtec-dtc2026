#!/bin/bash
# ============================================================
# PMTEC 健康检查脚本 - 部署后验证
# 用法: bash healthcheck.sh [ECS_IP]
# 不带参数则检查 localhost
# ============================================================
set -uo pipefail

HOST="${1:-localhost}"
PASS=0
FAIL=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_port() {
    local name=$1 port=$2
    if timeout 5 bash -c "echo > /dev/tcp/$HOST/$port" 2>/dev/null; then
        echo -e "${GREEN}  [PASS]${NC} $name (port $port)"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}  [FAIL]${NC} $name (port $port)"
        FAIL=$((FAIL + 1))
    fi
}

check_http() {
    local name=$1 port=$2 path=$3
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://$HOST:$port$path" 2>/dev/null || echo "000")
    if [[ "$code" == "200" || "$code" == "302" || "$code" == "401" ]]; then
        echo -e "${GREEN}  [PASS]${NC} $name (HTTP $code)"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}  [FAIL]${NC} $name (HTTP $code)"
        FAIL=$((FAIL + 1))
    fi
}

echo "============================"
echo " PMTEC 健康检查 -> $HOST"
echo "============================"

echo ""
echo "-- gRPC 服务 --"
check_port "WarEngine (50051)"        50051
check_port "BattleNetwork (50052)"     50052
check_port "ApplicationStore (50053)"   50053
check_port "PlugAndPlay (50054)"       50054

echo ""
echo "-- 可观测性 --"
check_http "Prometheus" 9091 /
check_http "Grafana"    3000 /
check_http "Jaeger UI"  16686 /
check_port "Jaeger OTLP (4317)" 4317

echo ""
echo "-- Docker 容器状态 --"
if command -v docker &>/dev/null; then
    docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null
    echo ""
    RUNNING=$(docker ps -q 2>/dev/null | wc -l)
    STOPPED=$(docker ps -aq --filter status=exited 2>/dev/null | wc -l)
    echo -e "  运行中: ${GREEN}$RUNNING${NC}  已停止: ${RED}$STOPPED${NC}"
else
    echo -e "  ${YELLOW}[SKIP]${NC} Docker 未安装或无权限"
fi

echo ""
echo "============================"
echo -e " 结果: ${GREEN}${PASS} PASS${NC} / ${RED}${FAIL} FAIL${NC}"
echo "============================"

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
