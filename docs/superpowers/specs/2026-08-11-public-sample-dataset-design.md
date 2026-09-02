# 公共样本数据集设计（脱敏发布）

- 日期：2026-08-11
- 状态：已与维护者确认方向，待写实现计划
- 关联：README「配置入口」「目录结构」、`docs/OPEN_SOURCE_RELEASE.md`、路线图「建立可公开再分发的脱敏演示数据集」

## 1. 背景与目标

Power Trade Lab 定位为**开源工具，下载者各自本地运行**。GitHub 仓库不是"读者上传内容的平台"，只发布源码 + 维护者精选的静态样本。当前下载者 clone 后得到空库，无法演示功能。

**目标**：随仓库发布一份**精选、脱敏**的样本数据集，让新部署 `--load` 后即有可演示内容，且**不泄露**任何个人数据、版权内容、受 ToS 约束的数据。

**非目标**：
- 不做"读者上传到公共库"（那是托管平台形态，不在本项目范围）。
- 不做运行时"开放公共"开关（部署内跨用户共享，单用户部署无意义，留待多用户教学部署时再做）。
- 不收录任何教材 PDF 及其派生内容（版权）。

## 2. 范围

### 2.1 收录（in）

| 内容 | 来源表 | 条件 |
|---|---|---|
| 政策原文 | `policies` | 来自公开政府/监管页，导出时强制带 `source`/`source_url`/`provider` 署名 |
| 公开数值行情/统计 | `public_data` | 来自公开统计/交易中心行情；**剔除** `provider=qweather` 的行；强制带 `provenance_level`/`source` |
| 自编题目 | `questions` | 仅维护者确认**本人原创**的题；`source_type` 标注为原创；排除"真题"与抓取题 |

### 2.2 排除（out，硬约束）

| 排除项 | 原因 | 落点 |
|---|---|---|
| 教材《现货市场101问》PDF | 版权（网上下载的出版书，非开放许可） | 不导出 `learning_books` 任何行 |
| 教材派生内容：章节、导读、原文依据、知识库 chunk | 同一版权的衍生 | 不导出 `learning_book_chapters` 全表，以及 `doc_chunks`/`knowledge_docs` 中可溯源至排除教材的行（按其实际溯源字段，如 `book_id`/`source_id`，字段名在实现时按 schema 确认） |
| 教材派生题目（303 题） | 同一版权衍生——由 GLM 从教材章节 `quiz_json` 生成 | 不导出 `questions` 中 `source_type='book'` 或 `source` 以 `book:` 开头的行（硬排除，即便误入 manifest） |
| 和风天气原始 JSON（1440 文件） | 和风 ToS 禁止再分发 | 不导出 `public_data` 中 `provider=qweather` 的行；`data/raw/public/qweather/` 不进仓库 |
| 整个 `power_trade.db` 库文件 | 含个人路径/账号哈希/做题记录/版权正文 | 永不整库发布，只导出经脱敏的子集到 `data/sample/` |
| 用户/账号/做题/考试数据 | 个人隐私，无发布价值 | 不导出 `users`/`user_profiles`/`user_llm_configs`/`answer_logs`/`wrong_answers`/`exam_sessions`/`ai_chat_history`/`trade_*` |
| 真题 | 受考试机构条款约束 | 不导出 `is_real_exam=true` 或 source 含"真题"的题 |
| 个人绝对路径 | 泄露本机身份 | 导出时全部相对化或置空 |

## 3. 机制

### 3.1 目录与产物

```
data/sample/                  # 不忽略，随仓库发布（需在 .gitignore 显式 !data/sample/）
├── manifest.yaml             # 维护者手写的"收录清单"
├── policies/*.json           # 导出产物
├── questions/*.json
├── market_data/*.json
└── README.md                 # 样本说明 + 各项来源/署名
backend/scripts/sample_data.py
   --export                   # 读 manifest + 库 → 导出脱敏 JSON 到 data/sample/
   --load                      # 下载者跑：把 data/sample/ 灌进空库
   --check                     # 校验 data/sample/ 不含被禁标记（qweather / /Users/ / 教材标题等）
```

### 3.2 manifest.yaml 结构（示例）

```yaml
# 维护者按 ID/范围精选收录；未列出的不导出
policies:
  ids: [12, 15, 23, 41]          # 来自 policies.id
questions:
  ids: [3, 7, 19, 88]           # 仅自编题
market_data:
  - data_type: carbon            # 来自 public_data.data_type
    date_range: ["2026-07-01", "2026-07-31"]
    exclude_providers: [qweather]
  - data_type: clearing
    date_range: ["2026-07-01", "2026-07-07"]
# 教材、和风、真题、用户数据均不在此列，脚本硬排除
```

### 3.3 导出流程（维护者偶尔做一次）

1. 编辑 `data/sample/manifest.yaml` 列出收录项。
2. 跑 `python backend/scripts/sample_data.py --export`，脚本按 manifest 读库、脱敏、写 `data/sample/`。
3. **人工逐个打开导出的 JSON 复核**（自动化脱敏是地板，不是天花板；电力数据/政策正文里藏的真实主体名靠正则去不干净）。
4. 跑 `python backend/scripts/sample_data.py --check` 做发布前校验。
5. `git add data/sample/ && git commit`。

### 3.4 灌入流程（下载者）

```bash
python backend/scripts/sample_data.py --load
# 幂等：重复运行行数不变（按 sha256/dedup_key 去重）
```

## 4. 脱敏规则（导出时自动）

1. **删除字段**：`user_id`（或置 0 占位）、`raw_path`/`markdown_path`（置空或相对化）、`hashed_password` 相关一切。
2. **路径清洗**：任何字段值中含 `/Users/`、`/home/`、本机绝对路径的，相对化或置空。
3. **来源强制**：`policies`/`public_data` 行若缺 `source`/`provider` 则**拒绝导出**并报错（宁可漏不可错）。
4. **硬排除**：`provider=qweather` 的行；`is_real_exam=true` 或 `source` 含"真题"的题；`source_type='book'` 或 `source` 以 `book:` 开头的教材派生题；`learning_books` 全表及其派生 chunk。
5. **provenance 标注**：所有 `public_data` 行保留 `provenance_level` 与 `disclosure_scope`，不篡改。

## 5. 安全原则与额外护栏（"务必要安全"的落地）

1. **白名单优先于黑名单**：`--export` 只导出 manifest 显式列出的项；manifest 未列的，**一律不导出**，不论它看起来多无害。manifest 是唯一入口，没有"默认全收"模式。
2. **只读连接**：`--export` 以只读方式打开本库，绝不写回本库；所有脱敏产物只落 `data/sample/`。本库（`power_trade.db`）在导出过程中零修改。
3. **硬排除优先于 manifest**：即便某条被误写进 manifest，只要命中排除类（`provider=qweather`、`is_real_exam=true` 或 source 含"真题"、`source_type='book'` 或 source 以 `book:` 开头的教材派生题、`learning_books` 及其派生 chunk），导出**仍跳过并告警**，不因 manifest 列了就放行。
4. **存疑即拒**：`--export` 与 `--check` 任一字段无法确认来源/署名、或疑似含 PII/个人路径时，**整次导出失败并退出非零**，不输出半成品。
5. **PII 扫描并入 `--check`**：`--check` 对 `data/sample/` 全量做正则扫描，命中邮箱、手机号、身份证号、`/Users/`、`/home/`、本机绝对路径、教材书名等任一标记 → 失败。
6. **人工复核为强制门槛**：导出后必须人工逐文件复核；`--check` 通过不等于可发布，只是可进入人工复核。README 与脚本输出均明示这一点。
7. **最小化优先**：宁可少收、不可错收。首版宁缺毋滥，无法确认授权的内容一律不收。

## 6. v1 首版样本目标规模

- 政策：约 10–15 条（从 66 条里挑代表性文件）。
- 数值数据：碳价/出清/煤价各 1 周（剔除和风），标注 `provenance=observed_public`。
- 题目：3–5 道维护者确认自编的题。
- 教材：0。
- 目标仓库增量：`data/sample/` < 1MB（纯 JSON，不含 PDF/图片）。

## 7. 测试

- **export 单测**：用 fixture 库（含一题"真题"、一行 `provider=qweather`、一本教材章节、一条含 `/Users/` 路径的政策）跑导出，断言产物中：无 qweather、无 book 派生 chunk、无真题、无 `/Users/`、无 user 表。
- **load 单测**：连续 `--load` 两次，断言行数不变（幂等）。
- **check 单测**：在被禁标记存在时返回非零退出码。
- **接入 `open_source_check.py`**：新增一条规则——若 `data/sample/` 内文件含 `qweather`、`/Users/`、教材书名等被禁标记，检查失败。

## 8. 文档更新

- README「配置入口」附近加「样本数据集」小节：说明 `data/sample/` 是维护者精选脱敏样本，下载者可选跑 `--load` 灌入。
- `docs/系统启动指南.md`：在"首次启动"后补一步"（可选）灌入样本数据：`python backend/scripts/sample_data.py --load`"。
- `data/sample/README.md`：每项来源、署名、provenance 说明。

## 9. 不在本期范围（后续）

- 应用内"加入公开样本"勾选 UI / 公共样本管理页：等维护者频繁可视化操作样本时再做，本期用 manifest 文件足够。
- 部署内跨用户共享（A）：多用户教学部署成形后再做。
- 社区中心库（C）：有社区贡献者规模再谈。
- 教材样本：仅在取得作者/出版社书面授权后才纳入，本期不安排。
