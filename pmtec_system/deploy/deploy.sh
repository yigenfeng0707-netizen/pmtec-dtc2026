#!/bin/bash
# ============================================================
# PMTEC 数字孪生战场系统 - 阿里云 ECS 一键部署脚本
# DTC 2026 参赛专用
# 适用系统: Ubuntu 22.04 / 20.04 (ECS)
# 用法: sudo bash deploy.sh [--repo-token TOKEN] [--repo-url URL]
# ============================================================
set -euo pipefail

# ---- 颜色输出 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${BLUE}==== $1 ====${NC}"; }

# ---- 默认参数 ----
REPO_URL="https://github.com/yigenfeng0707-netizen/pmtec-dtc2026.git"
REPO_TOKEN=""
INSTALL_DIR="/opt/pmtec"
SERVICE_NAME="pmtec"

# ---- 解析命令行参数 ----
while [[ $# -gt 0 ]]; do
    case $1 in
        --repo-token) REPO_TOKEN="$2"; shift 2;;
        --repo-url)   REPO_URL="$2"; shift 2;;
        --install-dir) INSTALL_DIR="$2"; shift 2;;
        --help|-h)
            echo "用法: sudo bash deploy.sh [选项]"
            echo ""
            echo "选项:"
            echo "  --repo-token TOKEN   GitHub 私有仓库访问令牌"
            echo "  --repo-url URL       自定义仓库地址 (默认: $REPO_URL)"
            echo "  --install-dir PATH   安装目录 (默认: $INSTALL_DIR)"
            echo "  --help               显示帮助"
            exit 0
            ;;
        *) log_error "未知参数: $1"; exit 1;;
    esac
done

# ---- 前置检查 ----
log_step "1/7 环境检查"

if [[ $EUID -ne 0 ]]; then
    log_error "请以 root 或 sudo 运行此脚本"
    exit 1
fi
log_info "root 权限确认"

# 检查系统
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    log_info "操作系统: $PRETTY_NAME"
    if [[ "$ID" != "ubuntu" && "$ID" != "centos" && "$ID" != "alinux" ]]; then
        log_warn "仅验证过 Ubuntu/CentOS/Alibaba Cloud Linux, 当前: $ID"
    fi
else
    log_error "无法识别操作系统"
    exit 1
fi

# 检查内存
MEM_TOTAL=$(free -g | awk '/^Mem:/{print $2}')
log_info "总内存: ${MEM_TOTAL}GB"
if [[ $MEM_TOTAL -lt 3 ]]; then
    log_warn "内存 < 4GB, 建议 4C8G 以上; Monte Carlo 仿真需 8GB+"
fi

# 检查磁盘
DISK_FREE=$(df -BG "$INSTALL_DIR" 2>/dev/null | awk 'NR==2{print $4}' | tr -d 'G')
if [[ -z "$DISK_FREE" || "$DISK_FREE" -lt 10 ]]; then
    log_warn "可用磁盘 < 10GB, Docker 镜像 + 数据需 10GB+"
fi
log_info "磁盘可用: ${DISK_FREE:-?}GB"

# ---- 安装 Docker ----
log_step "2/7 安装 Docker"

if command -v docker &>/dev/null; then
    log_info "Docker 已安装: $(docker --version)"
else
    log_info "安装 Docker..."
    
    if [[ "$ID" == "ubuntu" || "$ID" == "debian" ]]; then
        apt-get update -qq
        apt-get install -y -qq ca-certificates curl gnupg lsb-release
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/$(. /etc/os-release; echo "$ID")/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        chmod a+r /etc/apt/keyrings/docker.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$(. /etc/os-release; echo "$ID") $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
        apt-get update -qq
        apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    elif [[ "$ID" == "centos" || "$ID" == "alinux" ]]; then
        yum install -y -q yum-utils
        yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
        yum install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    else
        log_error "不支持的系统: $ID, 请手动安装 Docker"
        exit 1
    fi
    
    systemctl enable docker
    systemctl start docker
    log_info "Docker 安装完成: $(docker --version)"
fi

# 检查 docker compose (v2)
if docker compose version &>/dev/null; then
    log_info "Docker Compose v2: $(docker compose version)"
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &>/dev/null; then
    log_info "Docker Compose v1: $(docker-compose --version)"
    COMPOSE_CMD="docker-compose"
else
    log_info "安装 Docker Compose 插件..."
    apt-get install -y -qq docker-compose-plugin 2>/dev/null || yum install -y -q docker-compose-plugin 2>/dev/null
    COMPOSE_CMD="docker compose"
fi

# ---- 拉取代码 ----
log_step "3/7 拉取项目代码"

mkdir -p "$INSTALL_DIR"

if [[ -d "$INSTALL_DIR/pmtec-dtc2026/.git" ]]; then
    log_info "代码已存在, 执行 git pull..."
    cd "$INSTALL_DIR/pmtec-dtc2026"
    git pull -q 2>/dev/null || log_warn "git pull 失败, 使用现有代码"
else
    if [[ -n "$REPO_TOKEN" ]]; then
        AUTH_URL=$(echo "$REPO_URL" | sed "s|https://|https://${REPO_TOKEN}@|")
        log_info "使用 token 从私有仓库拉取..."
        git clone -q "$AUTH_URL" "$INSTALL_DIR/pmtec-dtc2026"
    else
        log_info "尝试直接拉取 (公开仓库或已配置凭证)..."
        if ! git clone -q "$REPO_URL" "$INSTALL_DIR/pmtec-dtc2026" 2>/dev/null; then
            log_error "拉取失败。私有仓库请使用: --repo-token YOUR_GITHUB_TOKEN"
            exit 1
        fi
    fi
fi

PROJECT_DIR="$INSTALL_DIR/pmtec-dtc2026/pmtec_system"
if [[ ! -d "$PROJECT_DIR" ]]; then
    log_error "项目目录不存在: $PROJECT_DIR"
    exit 1
fi
log_info "项目目录: $PROJECT_DIR"
cd "$PROJECT_DIR"

# ---- 生成 Proto 桩代码 ----
log_step "4/7 生成 gRPC Proto 桩代码"

if [[ ! -f proto/generated/dtb_model_pb2.py ]]; then
    log_info "生成 proto stubs..."
    pip3 install -q grpcio-tools 2>/dev/null || true
    mkdir -p proto/generated
    python3 -m grpc_tools.protoc \
        -I./proto \
        --python_out=./proto/generated \
        --grpc_python_out=./proto/generated \
        proto/dtb_model.proto
    touch proto/generated/__init__.py
    log_info "Proto stubs 生成完成"
else
    log_info "Proto stubs 已存在, 跳过"
fi

# ---- 验证模型文件 ----
log_step "5/7 验证生产模型"

MODEL_DIR="$PROJECT_DIR/data/models"
REQUIRED_MODELS=(
    "pmtec_dqn_p7_v2.zip"
    "pmtec_dqn_p6.zip"
    "pmtec_dqn_p7.zip"
    "pmtec_iql_intercept.zip"
    "pmtec_iql_dispersal.zip"
    "pmtec_maddpg_intercept.pt"
    "pmtec_maddpg_dispersal.pt"
)

MISSING=0
for model in "${REQUIRED_MODELS[@]}"; do
    if [[ -f "$MODEL_DIR/$model" ]]; then
        log_info "  [OK] $model"
    else
        log_warn "  [缺失] $model"
        MISSING=$((MISSING + 1))
    fi
done

if [[ $MISSING -gt 0 ]]; then
    log_warn "$MISSING 个模型文件缺失, AI 推理功能将受限"
    log_warn "请从开发环境 scp 上传模型到 $MODEL_DIR/"
fi

# ---- 构建 Docker 镜像 ----
log_step "6/7 构建 Docker 镜像并启动服务"

log_info "构建镜像 pmtec-distributed:latest ..."
cd "$PROJECT_DIR"
docker build -t pmtec-distributed:latest -f Dockerfile . 2>&1 | tail -3
log_info "镜像构建完成"

log_info "启动服务栈 (生产配置: bind mount + 资源限制)..."
COMPOSE_FILES="-f docker-compose.yml"
if [[ -f deploy/docker-compose.prod.yml ]]; then
    COMPOSE_FILES="$COMPOSE_FILES -f deploy/docker-compose.prod.yml"
fi
$COMPOSE_CMD $COMPOSE_FILES up -d --wait 2>&1 | tail -10

log_info "所有服务已启动"

# ---- 健康检查 ----
log_step "7/7 健康检查"

sleep 5

PASS=0
FAIL=0

check_port() {
    local name=$1 port=$2
    if timeout 5 bash -c "echo > /dev/tcp/localhost/$port" 2>/dev/null; then
        log_info "  [PASS] $name (port $port)"
        PASS=$((PASS + 1))
    else
        log_error "  [FAIL] $name (port $port)"
        FAIL=$((FAIL + 1))
    fi
}

check_port "WarEngine"        50051
check_port "BattleNetwork"    50052
check_port "ApplicationStore" 50053
check_port "PlugAndPlay"      50054
check_port "Prometheus"       9091
check_port "Grafana"          3000
check_port "Jaeger-OTLP"      4317
check_port "Jaeger-UI"        16686

# 检查容器状态
echo ""
log_info "容器状态:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null | head -12

echo ""
log_info "健康检查: ${PASS} PASS / ${FAIL} FAIL"

if [[ $FAIL -eq 0 ]]; then
    echo ""
    log_info "============================================"
    log_info "  PMTEC 部署成功!"
    log_info "============================================"
    echo ""
    echo "  gRPC 服务:"
    echo "    WarEngine:        localhost:50051"
    echo "    BattleNetwork:    localhost:50052"
    echo "    ApplicationStore: localhost:50053"
    echo "    PlugAndPlay:      localhost:50054"
    echo ""
    echo "  可观测性:"
    echo "    Prometheus: http://<ECS_IP>:9091"
    echo "    Grafana:    http://<ECS_IP>:3000  (admin/admin)"
    echo "    Jaeger UI:  http://<ECS_IP>:16686"
    echo ""
    echo "  管理命令:"
    echo "    cd $PROJECT_DIR"
    echo "    $COMPOSE_CMD logs -f          # 查看日志"
    echo "    $COMPOSE_CMD restart          # 重启服务"
    echo "    $COMPOSE_CMD down             # 停止所有服务"
    echo "    $COMPOSE_CMD up -d            # 重新启动"
    echo ""
else
    log_error "$FAIL 个服务启动失败, 请检查: $COMPOSE_CMD logs"
    exit 1
fi
