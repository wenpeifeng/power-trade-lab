# 开源发布检查清单

## 每次提交前

1. 运行 `python3 scripts/open_source_check.py`。
2. 运行后端测试：`cd backend && ./.venv/bin/python -m unittest discover -s tests -p 'test_*.py'`。
3. 运行后端漏洞审计：`cd backend && uvx pip-audit --path .venv/lib/python3.12/site-packages`。
4. 运行前端构建和审计：`cd frontend && npm run build && npm audit --omit=dev --registry=https://registry.npmjs.org`。
5. 确认 `git status --ignored` 中 `.env`、数据库、教材、附件、原始抓取数据、日志和 `.zcode` 均未进入暂存区。

## 首次公开前

- 选择并添加明确的开源许可证；这是维护者的法律选择，工具不自动代选。
- 当前目录尚未初始化 Git 时，先运行开源检查，再执行 `git init` 和首次暂存。
- 初始化 Git 后，对完整提交历史运行 Gitleaks 或 GitHub Secret Scanning。
- 轮换任何曾进入终端输出、聊天、截图、旧提交或共享文件的真实 Key。
- 在 GitHub 启用 Secret scanning、Push protection、Dependabot 和 Private vulnerability reporting。
- 用全新的空数据库验证首次启动，不要把个人开发库当作种子库发布。
- 管理员必须通过 `backend/scripts/create_admin.py` 交互创建，禁止在种子数据或文档中提供固定密码。
- 确认 `QWEATHER_ENABLED=false`，且状态接口不返回和风专属 Host 或账号标识。
- 使用全新的演示账号检查 `docs/showcase/`；截图和录屏不得出现作者姓名、本机路径、书签栏、教材、API Host 或余额。
- 检查前后端依赖许可证；GPL/AGPL、模型权重、字体、图标和数据集需要单独确认兼容性。

## 数据发布前

- 对每个数据源记录来源 URL、发布日期、抓取时间、许可证/使用条款和内容哈希。
- 区分“代码开源”“个人本地数据”“允许再分发的数据集”；三者不要混成同一发布物。
- 用户上传教材默认仅归上传者使用，不自动转为公共数据资产。
- 对书籍、题库、图片、PDF 和交易中心附件进行版权与个人信息审查。

## 生产部署前

- 设置 `ENVIRONMENT=production`。
- 配置强随机 `JWT_SECRET_KEY`、Fernet `LLM_CONFIG_MASTER_KEY`、实际 `ALLOWED_HOSTS` 与 HTTPS CORS Origin。
- 通过 HTTPS 反向代理运行，不直接把 Uvicorn 开放到公网。
- 将 SQLite 换为有备份、最小权限账号和传输加密的 PostgreSQL（多用户正式环境）。
- 将登录/AI 限流迁移到 Redis 或 API 网关，并接入脱敏后的集中日志与告警。
