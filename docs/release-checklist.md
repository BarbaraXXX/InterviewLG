# 发布检查清单

本文档用于每次将 `develop` 合并到 `main` 并部署到服务器前检查，目标是避免遗漏版本记录、数据文件、部署资源和安全项。

## 1. 代码分支

- 确认当前开发都在 `develop`。
- 确认没有未解释的本地改动：

```bash
git status --short --branch
```

- 合并前查看与 `main` 的差异：

```bash
git log --oneline main..develop
git diff --stat main...develop
```

## 2. 本地检查

默认检查：

```bash
bash scripts/check.sh
```

如果本次做了格式化基线或大范围样式调整，再执行：

```bash
CHECK_FORMAT=1 bash scripts/check.sh
```

前端单独检查：

```bash
cd interview-agent/web
npm run lint
npm run build
```

后端单独检查：

```bash
cd interview-agent
uv run ruff check src tests
uv run pytest
```

## 3. 版本信息

- 如果是正式版本，更新：
  - `interview-agent/pyproject.toml`
  - `interview-agent/web/package.json`
  - `interview-vectordb/pyproject.toml`，如 vectordb 有接口或数据结构变更
  - 前端版本展示文件
  - 前端版本更新记录
- 更新 `docs/git-version-history.md`。
- 创建或移动 git tag，例如：

```bash
git tag v1.x.x
```

## 4. 数据库与数据文件

- 确认是否需要上传新的 sqlite：
  - 题库数据库
  - RAG question cards 数据库
  - 其他 vectordb 成品数据
- 服务器运行数据目录通常在：

```text
/home/foolzheng/InterviewLG/data
```

- 不要覆盖用户账号、面试历史、简历等生产数据。
- 如果需要迁移数据库结构，确认迁移函数幂等，并且能在已有生产数据上重复执行。

## 5. 安全检查

- `.env`、API key、邀请码、JWT secret 不进入 git。
- 生产环境必须设置 `AUTH_SECRET_KEY`。
- vectordb 不暴露公网，优先只允许容器内或本机访问。
- nginx 不绕过 `/api/*` 的鉴权逻辑。
- 日志不打印完整简历、完整对话、API key、Cookie、Authorization header。
- Cookie 配置符合生产环境：
  - `HttpOnly`
  - `Secure`
  - 合理的 `SameSite`

## 6. 服务器资源检查

服务器当前资源较小，部署前注意：

- 不要在服务器上做非必要的大规模数据生成。
- 尽量上传 sqlite 成品，不在服务器上批量跑 embedding。
- 使用 `bash deploy.sh`，不要直接手动 `docker compose build`。
- 如果构建慢，优先确认 pip/uv 源和 Docker 缓存，而不是提高并发。
- 部署前可检查磁盘：

```bash
df -h
docker system df
```

## 7. 部署命令

服务器上：

```bash
cd /home/foolzheng/InterviewLG
git pull origin main
cd interview-agent/deploy
bash deploy.sh
```

## 8. 部署后验证

- 首页可访问。
- 登录、退出、重新登录正常。
- 面试配置流程可进入。
- Agent 能正常回复。
- RAG 查询或题库查询能在日志中看到正常调用。
- 历史记录能查看。
- 简历选择与注入不报错。
- 手撕题面板可打开、暂存、提交、收起。
- 检查容器状态：

```bash
docker compose ps
docker compose logs --tail=100 app
docker compose logs --tail=100 vectordb
docker compose logs --tail=100 nginx
```

## 9. 回滚准备

- 保留上一个可用 git tag。
- 不删除生产数据目录。
- 数据库结构变更前先备份：

```bash
cp -a /home/foolzheng/InterviewLG/data /home/foolzheng/InterviewLG/data.backup.$(date +%Y%m%d%H%M%S)
```
