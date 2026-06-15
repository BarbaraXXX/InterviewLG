# InterviewLG

模拟技术面试系统，基于 LangGraph Agent + 面经偏好分析 + Web 前端。

## 项目结构

```
interviewLG/
├── interview-agent/        # 面试 Agent（LangGraph + FastAPI + React）
├── interview-vectordb/     # 面经偏好服务（Profile 聚合 + MCP Server + REST API）
└── data/                   # 运行时数据（不上传 git）
    ├── experiences/        # 面经原始文件
    └── profiles/           # 聚合后的 Profile
```

## 架构

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   浏览器     │────▶│  interview-agent │────▶│ interview-vectordb│
│  React SPA  │◀────│  FastAPI :8000   │◀────│  FastAPI :9000    │
│             │     │                  │     │  + MCP :9000/mcp  │
│             │     │  LangGraph Agent │     │  ProfileDB (JSON) │
│             │     │  JWT Auth        │     │  LLM 聚合(DeepSeek)│
└─────────────┘     └──────────────────┘     └──────────────────┘
```

**数据流**：
1. 前端选择领域/难度/JD/偏好 → Agent 创建会话
2. Agent 调用 vectordb 获取 Profile → 注入系统提示词
3. JD 经 LLM 结构化 → 注入系统提示词
4. 面试全程由 LangGraph Agent 驱动，SSE 流式输出

## 快速调试

### 前置条件

- Python 3.12+, uv, Node.js 22.13+
- DeepSeek API Key（或其他 OpenAI 兼容 API）

### 1. 配置 .env

```bash
# interview-agent/.env
cp interview-agent/.env.example interview-agent/.env
# 编辑 LLM_PROVIDERS 填入 API Key

# interview-vectordb/.env
cp interview-vectordb/.env.example interview-vectordb/.env
# 编辑 LLM_API_KEY 填入 API Key
```

### 2. 启动 vectordb（先启动）

```bash
cd interview-vectordb
uv sync
uv run interview-vectordb         # 启动 REST+MCP 服务 (端口 9000)
```

### 3. 导入面经 & 生成 Profile

```bash
cd interview-vectordb
uv run interview-vectordb import /path/to/experiences/   # 导入面经
uv run interview-vectordb regen                          # 生成 Profile
uv run interview-vectordb list                           # 查看 Profile
```

### 4. 启动 Agent

```bash
cd interview-agent
uv sync
cd web && npm install && npm run build && cd ..   # 构建前端
uv run interview-agent-server                     # 启动服务 (端口 8000)
```

### 5. 访问

浏览器打开 http://localhost:8000

### 6. 连接 Profile

在 `interview-agent/.env` 中设置：
```
VECTORDB_BASE_URL=http://localhost:9000
```

前端 SetupView 的"面试偏好"下拉框会自动加载已有 Profile。

## 生产部署

### 前置条件

- **服务器**：最低 1 核 2G，建议加 2G swap（`docker build` 内存不足会 OOM）
- **域名**：已备案，DNS 解析到服务器 IP
- **端口**：阿里云安全组放行 80（HTTP）和 443（HTTPS）
- **Docker**：服务器已安装 Docker + Docker Compose
- **Git**：代码托管在 GitHub，服务器配置好 SSH key

### 1. 首次部署

```bash
# 克隆仓库
git clone git@github.com:BarbaraXXX/InterviewLG.git
cd InterviewLG

# 配置环境变量
cp interview-agent/.env.example interview-agent/.env
vim interview-agent/.env
```

编辑 `interview-agent/.env`，填写以下**全部**配置项（缺一不可，`deploy.sh` 会强制校验）：

| 配置项 | 说明 | 示例 |
|---|---|---|
| `LLM_PROVIDERS` | LLM API 配置（JSON） | 填入 DeepSeek API Key |
| `AUTH_SECRET_KEY` | JWT 签名密钥 | `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` 生成 |
| `AUTH_INVITE_CODE` | 注册邀请码（逗号分隔多个） | `mycode1,mycode2` |
| `VECTORDB_ADMIN_TOKEN` | VectorDB 写接口管理令牌 | `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` 生成 |
| `SERVER_CORS_ORIGINS` | CORS 允许的来源 | `https://foolzheng.top` |
| `SSL_DOMAIN` | 你的域名 | `foolzheng.top` |
| `SSL_EMAIL` | Let's Encrypt 通知邮箱 | `admin@foolzheng.top` |
| `PYPI_INDEX_URL` | Docker 构建 Python 依赖源，国内服务器建议配置镜像 | `https://pypi.tuna.tsinghua.edu.cn/simple` |

然后一键部署：

```bash
cd interview-agent/deploy
bash deploy.sh
```

`deploy.sh` 做了这些事：
1. 校验必需配置项
2. 创建证书存储目录
3. 生成 nginx 配置文件（含域名替换）
4. 若首次运行：写临时 HTTP nginx → 启动服务 → certbot 申请 SSL 证书 → 切回 HTTPS nginx
5. 构建 Docker 镜像并启动全部服务（app、内网 vectordb、nginx、certbot）

部署完成后访问 `https://你的域名`，证书会自动续期（certbot 容器每 12 小时检查）。

### 2. 代码更新后部署

```bash
cd /home/foolzheng/InterviewLG
git pull origin main
cd interview-agent/deploy
bash deploy.sh
```

`deploy.sh` 检测到已有证书后会跳过申请步骤，并按低内存服务器友好的顺序单独构建 vectordb 和 app，再重启服务。**务必用 `bash deploy.sh`，不要手动 `docker compose build/up`**——手动操作不会执行 `envsubst` 域名替换，也更容易在 2G 内存机器上触发 OOM。

### 3. 服务管理

```bash
cd /home/foolzheng/InterviewLG/interview-agent/deploy

# 查看日志
docker compose logs -f app    # 后端
docker compose logs -f nginx  # 反向代理

# 重启单个服务
docker compose restart app

# 停止全部
docker compose down
```

### 4. 常见问题

**部署后无法访问 HTTPS**
→ 确认安全组放行了 80 和 443 端口。

**nginx 报错 `cannot load certificate //fullchain.pem`**
→ 说明 `.env` 变量未被 `envsubst` 替换，用 `bash deploy.sh` 重新部署即可。

**构建时服务器卡死或 SSH 断开**
→ 内存不足被 OOM killer。加 swap 后再构建：
```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**注册报错 `Permission denied: /app/data/interview.db`**
→ `data/` 目录权限问题。不要使用 `chmod 777`，改为让当前部署用户拥有数据目录：
```bash
sudo mkdir -p /home/foolzheng/InterviewLG/data
sudo chown -R "$USER:$USER" /home/foolzheng/InterviewLG/data
chmod 750 /home/foolzheng/InterviewLG/data
```

**证书已存在但 nginx 不加载**
→ 可能是 archive 目录为空导致符号链接断掉，重新签发：
```bash
docker compose run --rm certbot certbot certonly --force-renewal \
    --webroot --webroot-path /var/www/certbot \
    -d 你的域名 --email 你的邮箱 --agree-tos --no-eff-email
docker compose restart nginx
```

## CLI 模式（无前端）

```bash
cd interview-agent
uv run interview-agent    # 交互式 CLI 面试
```
