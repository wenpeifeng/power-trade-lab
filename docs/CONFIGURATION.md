# 配置与部署说明

本文面向下载源码后自行运行或部署 Power Trade Lab 的开发者。核心原则是：基础功能零第三方凭证运行，增强能力显式开启，每个部署使用自己的账号与密钥。

## 1. 三种运行模式

| 模式 | 适合场景 | 第三方凭证 |
|---|---|---|
| 本地基础模式 | 学习、刷题、考试、仿真和源码开发 | 不需要 |
| 本地增强模式 | 加入 AI、MinerU、天气和真实数据采集 | 按功能选填 |
| 生产模式 | 公网或团队部署 | 必须配置安全参数，增强功能仍按需 |

后端读取 `backend/.env`，前端读取 `frontend/.env`。这两个真实文件都被 `.gitignore` 排除；只能提交 `.env.example`。

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

不要在 Issue、截图、录屏、日志、聊天或提交说明中粘贴真实值。

## 2. 本地基础模式

不创建 `.env` 也可以运行：

```bash
./start.sh
```

开发环境会自动完成：

- 使用本地 SQLite 数据库 `backend/power_trade.db`
- 生成随机登录密钥到 `data/credentials/jwt-secret.key`
- 生成 AI Key 加密主密钥到 `data/credentials/llm-master.key`
- 绑定 `127.0.0.1`，不开放局域网或公网
- 保持 MinerU 与和风天气关闭

上述数据库、密钥和运行日志均在 Git 忽略范围内。

## 3. 基础参数

| 参数 | 本地默认 | 生产要求 | 说明 |
|---|---:|---:|---|
| `ENVIRONMENT` | `development` | 必填为 `production` | 决定安全校验和调试行为 |
| `DEBUG` | `true` | 建议 `false` | 是否显示调试信息 |
| `ALLOWED_HOSTS` | `[]` | 必填 | JSON 数组，填写真实后端域名，不允许 `*` |
| `CORS_ORIGINS` | 本地 Vite 地址 | 必填 | JSON 数组，只允许真实 HTTPS 前端 Origin |
| `DATABASE_URL` | 本地 SQLite | 正式多用户建议填写 | SQLAlchemy 数据库连接串；需自行安装对应驱动并验证迁移 |
| `JWT_SECRET_KEY` | 自动生成本地文件 | 必填 | 登录会话签名密钥，至少使用 32 字节随机值 |
| `JWT_ACCESS_TOKEN_HOURS` | `24` | 选填 | 会话有效小时数 |
| `AUTH_COOKIE_NAME` | `power_session` | 选填 | HttpOnly 会话 Cookie 名称 |
| `LLM_CONFIG_MASTER_KEY` | 自动生成本地文件 | 必填 | Fernet Key，用于加密不同用户的 AI Key |

生成随机 JWT 密钥：

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

生成 Fernet Key：

```bash
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

不要频繁更换 `LLM_CONFIG_MASTER_KEY`；更换后，数据库中原有用户 AI Key 将无法解密，除非先完成密钥迁移。

## 4. 管理员

每个部署独立管理账号，不存在作者提供的统一账号，也不存在默认 `admin/123456`。

```bash
backend/.venv/bin/python backend/scripts/create_admin.py
```

推荐策略：

- 个人本地部署：一个 Owner 管理员即可。
- 团队部署：每名管理员使用独立账号，便于撤销与审计；不要多人共享一个密码。
- 普通用户通过注册页面创建，默认角色不是管理员。
- 管理员负责数据接入、采集触发、质量审核和索引维护。

当前脚本允许再次运行以创建或提升其他管理员，这是灾备和团队协作能力，不是公共默认账号。

## 5. 用户 AI（可选，BYOK）

系统不接受仓库级或作者级大模型 API Key。每位登录用户在页面的 AI 设置中填写自己的供应商信息和 API Key；后端使用 `LLM_CONFIG_MASTER_KEY` 加密保存，只向页面返回脱敏状态。

不配置时：

- 基础学习、刷题、考试、知识库、仿真仍可使用。
- AI 解读、AI 生成题和教材 AI 加工不可用或使用非 AI 降级内容。

开源部署者应在隐私政策中说明：用户 Key 会被加密保存在部署者的数据库中，调用请求会发往用户选择的模型供应商。

## 6. MinerU 教材解析（可选）

```env
MINERU_ENABLED=true
MINERU_API_URL=http://127.0.0.1:18000
MINERU_BACKEND=hybrid-engine
MINERU_EFFORT=medium
MINERU_TIMEOUT_SEC=1800
```

| 参数 | 作用 |
|---|---|
| `MINERU_ENABLED` | 总开关，默认 `false` |
| `MINERU_API_URL` | 独立 MinerU HTTP 服务地址 |
| `MINERU_BACKEND` | MinerU 解析后端 |
| `MINERU_EFFORT` | 解析强度/质量档位 |
| `MINERU_TIMEOUT_SEC` | 大文件解析超时 |

建议让 MinerU 作为独立本地服务运行，业务项目只走 HTTP，不共享 Python 依赖。若连接私网 MinerU，还需把精确主机名加入 `OUTBOUND_PRIVATE_HOST_ALLOWLIST`；不要使用宽泛网段。

## 7. 和风天气（可选，默认关闭）

### 7.1 默认行为

```env
QWEATHER_ENABLED=false
```

默认不会：

- 创建天气定时任务
- 请求和风天气接口
- 消耗作者或下载者的调用额度
- 要求普通系统用户登录和风天气

和风天气是部署级连接器。只有系统部署者需要注册自己的和风开发者账号；普通学习用户不需要和风账号。

### 7.2 JWT 配置（推荐）

```env
QWEATHER_ENABLED=true
QWEATHER_API_HOST=YOUR_DEDICATED_API_HOST
QWEATHER_AUTH_TYPE=jwt
QWEATHER_PROJECT_ID=YOUR_PROJECT_ID
QWEATHER_CREDENTIAL_ID=YOUR_CREDENTIAL_ID
QWEATHER_PRIVATE_KEY_PATH=/absolute/local/path/qweather-ed25519-private.pem
QWEATHER_FORECAST_HOURS=24h
```

私钥建议保存在仓库的 `data/credentials/` 或操作系统密钥目录；该目录已被 Git 忽略。公钥上传和风控制台，私钥只保留在部署机器。

### 7.3 API Key 配置（兼容）

```env
QWEATHER_ENABLED=true
QWEATHER_API_HOST=YOUR_DEDICATED_API_HOST
QWEATHER_AUTH_TYPE=api_key
QWEATHER_API_KEY=YOUR_API_KEY
```

不要把 API Key 放进 URL、前端环境变量或浏览器代码。

### 7.4 城市与调用量

默认采集太原、济南、广州、杭州和呼和浩特，可用单行 JSON 覆盖：

```env
QWEATHER_LOCATIONS_JSON={"山西":{"city":"太原","location_id":"101100101"}}
```

当前调度为每小时每城市请求一次实时天气和一次逐小时预报。默认五城市约 7,200 次/月，手动同步和城市搜索会增加请求量。费用与许可必须以部署者自己的和风控制台和最新服务条款为准。

### 7.5 不暴露作者账号的保证

- `.env`、私钥和 `data/credentials/` 不进入源码包。
- 连接器状态接口不返回 API Host、项目 ID、凭据 ID、Key 或私钥路径。
- 原始响应和日志不记录认证请求头。
- 每个下载者必须使用自己的凭证；不配置就保持关闭。

## 8. 知识库检索（可选调优）

| 参数 | 默认 | 说明 |
|---|---|---|
| `KB_EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | 本地嵌入模型名称 |
| `KB_EMBEDDING_DIM` | `512` | 向量维度，必须和模型输出一致 |
| `KB_RERANKER_MODEL` | 空 | 可选重排模型；空表示不启用 |

模型不可用时，知识库仍可使用关键词/BM25 检索。部署前请单独检查模型权重许可和下载来源。

## 9. 文件与出站安全

| 参数 | 默认 | 说明 |
|---|---:|---|
| `ASSET_UPLOAD_MAX_MB` | `100` | 数据资产上传上限 |
| `OUTBOUND_FETCH_MAX_MB` | `50` | 服务端抓取最大响应体 |
| `OUTBOUND_PRIVATE_HOST_ALLOWLIST` | 空 | 允许访问的精确私网主机，默认禁止 SSRF 到内网 |
| `LOGIN_MAX_FAILURES` | `5` | 登录失败窗口内最大次数 |
| `REGISTER_MAX_ATTEMPTS` | `5` | 注册窗口内最大次数 |

公网部署不要把 `OUTBOUND_PRIVATE_HOST_ALLOWLIST` 设置成 `localhost`、整个内网域名或通配符。

## 10. 前端参数

`frontend/.env`：

| 参数 | 默认 | 说明 |
|---|---|---|
| `VITE_API_BASE_URL` | `/api` | 浏览器访问 API 的前缀 |
| `VITE_DEV_API_TARGET` | `http://127.0.0.1:8000` | Vite 开发代理目标 |

前端 `VITE_*` 会进入浏览器构建产物，绝不能放 API Key、密码或私钥。

## 11. 生产部署最低检查

1. 使用 HTTPS 反向代理，不直接把 Uvicorn 暴露公网。
2. 设置生产环境、强密钥、真实 Host 和严格 CORS。
3. 正式多用户环境使用 PostgreSQL、备份和最小权限数据库账号；当前依赖清单未内置 PostgreSQL 驱动，切换前需选择驱动并完成迁移测试。
4. 为上传目录、教材和数据库设置持久化与访问控制。
5. 把限流迁移到 Redis、网关或其他多实例共享存储。
6. 执行 `python3 scripts/open_source_check.py`。
7. 检查 `git status --ignored`，确认本地凭证和数据没有被强制加入。
8. 轮换任何曾进入聊天、截图、日志或 Git 历史的凭证。

更完整的安全边界见 [SECURITY.md](../SECURITY.md) 和 [开源发布检查清单](OPEN_SOURCE_RELEASE.md)。
