# PMTEC 数字孪生战场系统 - 阿里云 ECS 部署指南

## 快速开始

### 1. 创建 ECS 实例

| 配置项 | 推荐值 |
|---|---|
| 实例规格 | ecs.g7.xlarge (4C8G) 或 ecs.g7.large (2C4G) |
| 镜像 | Ubuntu 22.04 64位 |
| 系统盘 | 40GB ESSD |
| 公网 IP | 分配固定公网 IP |
| 安全组 | 放行 50051-50054, 9091, 3000, 16686, 22 |

### 2. SSH 登录后一键部署

```bash
# 从 GitHub 拉取部署脚本并执行
curl -sL https://raw.githubusercontent.com/yigenfeng0707-netizen/pmtec-dtc2026/main/pmtec_system/deploy/deploy.sh | sudo bash -s -- --repo-token YOUR_GITHUB_TOKEN
```

或手动上传后执行：

```bash
# 上传 deploy.sh 到 ECS
scp deploy.sh root@<ECS_IP>:/root/

# SSH 登录执行
ssh root@<ECS_IP>
sudo bash deploy.sh --repo-token YOUR_GITHUB_TOKEN
```

### 3. 验证部署

```bash
# 本地验证
bash healthcheck.sh

# 远程验证 (从开发机)
bash healthcheck.sh <ECS_IP>
```

## 服务端口

| 服务 | 端口 | 用途 |
|---|---|---|
| WarEngine | 50051 | 仿真引擎、ASDA 闭环、威胁查询 |
| BattleNetwork | 50052 | 航迹推送、实体状态、实时数据流 |
| ApplicationStore | 50053 | 应用管理、DQN 推理 |
| PlugAndPlay | 50054 | 组件注册、服务发现、健康检查 |
| Prometheus | 9091 | 指标采集 |
| Grafana | 3000 | 可视化仪表盘 (admin/admin) |
| Jaeger UI | 16686 | 分布式追踪 |
| Jaeger OTLP | 4317 | OTLP gRPC 上报 |

## 常用命令

```bash
cd /opt/pmtec/pmtec-dtc2026/pmtec_system

# 查看日志
docker compose logs -f war-engine
docker compose logs -f --tail=50

# 重启服务
docker compose restart

# 停止所有服务
docker compose down

# 重新启动
docker compose up -d --wait

# 查看容器状态
docker compose ps

# 进入容器调试
docker compose exec war-engine bash
```

## 开启实时数据

编辑 `docker-compose.yml`，将 war-engine 的环境变量改为：

```yaml
environment:
  - LIVE_DATA_USE_REAL_API=1
```

然后重启：

```bash
docker compose up -d --wait
```

## 安全组配置

ECS 安全组需放行以下端口：

| 端口范围 | 协议 | 用途 |
|---|---|---|
| 22 | TCP | SSH |
| 50051-50054 | TCP | gRPC 服务 |
| 9091 | TCP | Prometheus |
| 3000 | TCP | Grafana |
| 16686 | TCP | Jaeger UI |

> 生产环境建议仅放行 22 (SSH) + 50051-50054 (gRPC)，Prometheus/Grafana/Jaeger 通过 SSH 隧道访问。

## SSH 隧道访问 (推荐)

```bash
# 从本地机器建立隧道
ssh -L 3000:localhost:3000 -L 16686:localhost:16686 -L 9091:localhost:9091 root@<ECS_IP>

# 然后浏览器访问
# Grafana:   http://localhost:3000
# Jaeger:    http://localhost:16686
# Prometheus: http://localhost:9091
```

## 资源消耗参考

| 实例规格 | 容器数 | 内存占用 | 适用场景 |
|---|---|---|---|
| 2C4G | 8 | ~2.5GB | 服务部署 + DQN 推理 |
| 4C8G | 8 | ~3GB | Monte Carlo 仿真 (50ep) |
| 8C16G | 8 | ~4GB | 全功能演示 + 并发仿真 |

## 故障排查

```bash
# 容器未启动
docker compose ps -a
docker compose logs war-engine --tail=100

# 端口被占用
ss -tlnp | grep 5005

# 磁盘不足
df -h
docker system prune -a  # 清理无用镜像

# 模型文件缺失
ls -la data/models/*.zip data/models/*.pt
# 需要从开发环境上传:
# scp pmtec_dqn_p7_v2.zip root@<ECS_IP>:/opt/pmtec/pmtec-dtc2026/pmtec_system/data/models/

# proto 生成失败
cd /opt/pmtec/pmtec-dtc2026/pmtec_system
pip3 install grpcio-tools
python3 -m grpc_tools.protoc -I./proto --python_out=./proto/generated --grpc_python_out=./proto/generated proto/dtb_model.proto
```
