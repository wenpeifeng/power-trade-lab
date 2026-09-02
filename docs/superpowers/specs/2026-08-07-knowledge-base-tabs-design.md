# 电力知识库：Tab 切换 + 系统化教学内容设计

> 日期：2026-08-07
> 范围：知识库页（`/knowledge`）改造 + 修复「数据资产」按钮 + 撰写系统化电力知识

## 一、背景与问题

### 1.1 「数据资产」按钮失效
- 路由 `/asset`（`frontend/src/router/index.js:67`）带 `meta.requiresAdmin: true`，路由守卫（`index.js:118-120`）对非 admin 用户**静默重定向回首页**，按钮表现为"点了没反应"。
- 后端 `backend/app/knowledge/admin_router.py:35-39` 整个 `/asset` router 用 `dependencies=[Depends(require_admin)]` 闸住，连读接口（`/asset/stats`、`/asset/timeline`、`/asset/quality` 等）也 403，首页 Portal 调 `assetApi.stats()` 也被吞掉。
- 治理/审核功能确实应留 admin，但**浏览读功能**对学习型用户放开更合理。

### 1.2 电力知识库现状
- 数据源 100% 来自爬虫：`backend/crawlers/sources.yaml` 配置发改委、能源局、省政府、交易中心等源 → 抓取 → 清洗 → 入 `knowledge_docs` 表；也支持手动 cURL / 文件上传 / 飞书导入（`backend/app/knowledge/ingest.py`）。
- DB 现状：84 篇文档（64 已过审），类型为 regulation / national_policy / exchange_info / industry_news。约 80 个分类里仅 16 个有文档、43 篇未分类——大量分类为空。
- **缺少系统性教学知识**：中长期合同、双边交易、集中竞价、挂牌交易、现货等核心概念没有任何解释性内容，爬不到，必须人工撰写。

## 二、目标

1. 让「数据资产」按钮对所有登录用户可点入浏览（写/审核仍 admin）。
2. 知识库页加 Tab：`📚 知识库`（系统化教学）+ `📰 资讯·爬取`（现有爬取内容），两者完全分离。
3. 撰写一套**覆盖完整、循序渐进、通俗化**的电力市场知识体系（13 章），让**完全的小白**（不懂电力、不懂交易）也能从零建立认知。

## 二之一、写作原则（面向小白，硬性）

读者画像：**完全的初学者**——可能没碰过电力行业、没做过交易，连"千瓦时"和"出清"都没听过。所有内容必须满足：

1. **零术语起步**：每个概念第一次出现时，必须先用大白话解释，再用术语。术语本身要附"人话版"。
2. **一句话懂了（tldr）必须零 jargon**：用生活类比开头，例如
   - 中长期交易 = "批发"（像超市大批量进货，量大、价稳、提前订）
   - 现货市场 = "当日菜价"（今天用多少、当天现买现卖，价随供需波动）
   - 辅助服务 = "电网的急救队"（专门兜底、保持电网不垮）
   - 节点电价 = "不同地段的菜价不同"（堵车/缺电的地方更贵）
3. **生活类比优先**：每个概念尽量给一个生活类比（菜市场/批发零售/快递/急救队等），再回到电力本身。
4. **前置概念显式化**：每个概念标注 `prereq`（看这个之前应先懂什么），小白按链条爬就能循序渐进，不会半路卡住。
5. **对比表说人话**：对比维度用"谁定价格/什么时候交易/像什么"这类日常用语，不用"价格形成机制/时序特征"。
6. **对应仿真接地气**：`link2sim` 写"打开交易终端你会看到X"——把抽象概念落到用户能在本系统点开看到的东西。
7. **不假设前置知识**：不写"如所周知/众所周知"；不用缩写不展开（LMP 首次出现写"节点边际电价（LMP）= 这个地点这一刻的电价"）。
8. **每章开头一段白话导语**：3 句话告诉小白"这章在讲什么、为什么重要、和前面哪章有关"。

## 三、方案

### 3.1 修复「数据资产」按钮

**前端** `frontend/src/router/index.js:67`
- 删除 `/asset` 路由 meta 的 `requiresAdmin: true`。

**后端** `backend/app/knowledge/admin_router.py`
- 移除 router 构造里的 `dependencies=[Depends(require_admin)]`（第 38 行）。
- 读接口改为 `current_user=Depends(get_current_user)`（任何登录用户可读）：
  - `GET /asset/stats`
  - `GET /asset/timeline`
  - `GET /asset/quality`
  - `GET /asset/refs/{doc_id}`
  - `GET /asset/crawler/status`
  - `GET /asset/connectors/qweather/status`
  - `GET /asset/connectors/qweather/locations`
- 写/审核接口保留/补齐 `require_admin`（逐一核对，多数已有 `current_user=Depends(require_admin)`）：
  - `POST /asset/ingest/*`（curl / upload / manual / feishu / spreadsheet / api / rss / feishu-base）
  - `POST /asset/crawler/run`
  - `POST /asset/review`、`POST /asset/review/batch`
  - `POST /asset/track-ref`
  - `POST /asset/connectors/qweather/test`
- 实现时逐一比对每个端点签名，确保不漏放写权限、不误拒读权限。

### 3.2 知识库页 Tab 切换

**`frontend/src/views/knowledge/Layout.vue`**
- 顶部新增 Tab 切换：`📚 知识库` / `📰 资讯·爬取`。
- Tab 状态同步到 URL query `?tab=book|feed`，支持分享与刷新保持。
- Tab1 渲染新组件 `<KnowledgeBook/>`；Tab2 渲染现有 `<Browse/>`。

**`frontend/src/views/knowledge/Browse.vue`**
- 不动，保持现有爬取内容浏览逻辑。

### 3.3 系统化知识组件

**新建 `frontend/src/views/knowledge/KnowledgeBook.vue`** —— 教材式布局：
- 左栏：章节树（章→节→概念），支持搜索、高亮当前阅读、展开/折叠。
- 右栏：正文阅读区
  - 面包屑（章 / 节 / 概念）
  - 「一句话懂了」高亮卡
  - 定义段
  - 关键点列表
  - 对比/易混表（`<table>`）
  - 「对应仿真」联调卡（指向 `/trade` 终端里的市场）
  - 交叉引用 chips（点击跳转到关联概念）
  - 上一节 / 下一节
- 移动端折叠左栏为抽屉。

### 3.4 静态结构化内容

**新建 `frontend/src/knowledge/curriculum.js`** —— 导出 `CURRICULUM` 数组，结构：

```js
// 章
{
  code: '3',
  title: '中长期交易',
  intro: '3 句白话导语：这章讲什么、为什么重要、和前面哪章有关',
  sections: [
    // 节
    {
      code: '31',
      title: '中长期交易总览',
      concepts: [
        // 概念（精要结构，面向小白）
        {
          code: '311',
          title: '双边协商',
          prereq: ['1', '21'],            // 看这个之前应先懂哪几章/哪几个概念
          tldr: '一句话懂了，零术语，带生活类比',
          analogy: '像菜市场的批发买卖——买卖双方直接谈好量、价、送货时间',
          definition: '核心定义，先用大白话再用术语',
          keyPoints: ['要点1，说人话', '要点2'],
          compare: [                        // 可选，对比维度用日常用语
            { dim: '像什么', a: '双边协商=批发谈价', b: '集中竞价=拍卖' },
            { dim: '价格谁定', a: '买卖双方自己谈', b: '系统撮合出清' },
          ],
          link2sim: '打开交易终端 → mid_long_term 市场，你会看到…',
          related: ['312', '313'],          // 概念 code 交叉引用
        },
      ],
    },
  ],
}
```

**知识库顶部加「入门学习路线」**：在 `curriculum.js` 导出 `LEARNING_PATH`，是一组按推荐阅读顺序排列的概念 code，对小白做引导：
"完全不懂？按这个顺序看 → 1 总览 → 21 谁在交易 → 311 双边协商 → 312 集中竞价 → 313 挂牌 → 411 日前 → 412 实时 → …"。
`KnowledgeBook.vue` 首屏渲染一张"学习路线卡"，点击直达对应概念，降低小白"不知道从哪看起"的门槛。

**13 章骨架**（全骨架 + 精要释义，通俗化表述）：

1. **电力市场全景**
   - 计划→市场、9号文及配套文件、电力商品物理特性（实时平衡/难存储/网络约束）、市场体系层次、参与者总览、术语速查
2. **市场主体**
   - 发电企业（火/水/核/风/光/生物质）、电网（输配调三分离）、售电公司、电力用户、新型经营主体、运营机构（交易中心·调度·监管）
3. **中长期交易** ⭐
   - 总览（为何是压舱石）、双边协商、集中竞价、挂牌交易、年度/月度/月内/周周期、合同与发电权转让、价格形成、与现货衔接（曲线分解）
4. **现货市场**
   - 总览（为何要现货）、日前市场、实时·平衡市场、集中竞价出清、节点边际电价 LMP / 统一出清、发电报价、用户侧参与、与中长期衔接
5. **辅助服务**
   - 总览、一次调频、AGC二次调频、调峰、冷/热备用、黑启动、无功电压支撑、"两个细则"与市场化新机制
6. **绿色权益与碳**
   - 绿色电力交易、绿证 GEC、碳排放权交易、CCER、绿电与绿证关系
7. **容量与输电权**
   - 容量市场 / 容量补偿机制、输电权 FTR（国内试点现状）
8. **电价与结算**
   - 输配电价（准许收入+准许收益率）、上网电价（标杆→市场）、销售电价（目录→市场化）、容量电价与两部制、结算规则（中长期/现货/偏差结算）、交叉补贴与政府性基金及附加
9. **需求响应**
   - 需求响应 IL/DR、可中断负荷、聚合参与现货+辅助服务
10. **新兴主体与机制**
    - 独立·共享储能、虚拟电厂 VPP、负荷聚合商、隔墙售电·分布式交易、综合能源服务
11. **跨省跨区与区域市场**
    - 省间市场、区域市场、跨省跨区交易
12. **电力金融与风险管理**
    - 电力期货/期权、合同风险与对冲
13. **市场监管与信用**
    - 监管体系（能源局·发改委）、市场力监测、信用体系（履约保函·违约处理）

### 3.5 共用 markdown 工具

**新建 `frontend/src/utils/markdown.js`**
- 抽取 `frontend/src/views/learn/BookReader.vue` 中的 `parseMarkdown` + `inlineHtml`（含 `escapeHtml`），导出为共用函数。
- `BookReader.vue` 改为 `import { parseMarkdown, inlineHtml } from '@/utils/markdown'`，删除本地副本。
- `KnowledgeBook.vue` 同样引入，用于渲染 `definition` 等富文本字段。
- 零新依赖。

## 四、数据流

- 知识库 Tab1：纯前端，`curriculum.js` → `KnowledgeBook.vue` 直接渲染，无后端调用。
- 知识库 Tab2：现有 `categoryApi` / `knowledgeApi` → `knowledge_docs` 表，不变。
- 数据资产中心：前端 `assetApi.*` → 后端 `/asset/*` 读接口（登录即可）/ 写接口（admin）。

## 五、文件清单

新增：
- `frontend/src/knowledge/curriculum.js`
- `frontend/src/views/knowledge/KnowledgeBook.vue`
- `frontend/src/utils/markdown.js`

修改：
- `frontend/src/router/index.js`（去 `requiresAdmin`）
- `frontend/src/views/knowledge/Layout.vue`（加 Tab + 路由 query）
- `backend/app/knowledge/admin_router.py`（router 级 guard 拆分到端点级）
- `frontend/src/views/learn/BookReader.vue`（改用共用 markdown 工具，行为不变）

不动：
- `frontend/src/views/knowledge/Browse.vue`
- `frontend/src/views/admin/AssetCenter.vue`（前端本身不限权，后端是真边界）

## 六、测试与验收

- 数据资产：非 admin 账号点首页「数据资产」→ 能进入并加载统计/时间线（不再静默跳回）；ingest/review 等接口对非 admin 仍 403。
- 知识库 Tab：`/knowledge` 默认进 Tab1 知识库；切 Tab2 显示原爬取列表；刷新 `?tab=feed` 保持；移动端左栏抽屉化。
- 内容：13 章全部有 `intro`（白话导语），每节概念都有 `prereq + tldr + analogy + definition + keyPoints`；用户点名的中长期/双边/集中竞价/挂牌/现货在对应章节里完整释义且对零基础可读；`LEARNING_PATH` 学习路线卡在知识库首屏可见。
- 回归：`BookReader` 阅读页渲染与改造前一致（markdown 解析行为不变）。

## 七、不在本次范围

- 不动爬虫与 `knowledge_docs` 数据沉淀流程。
- 不补爬取内容的空分类（那是数据运营问题，另做）。
- 不接入题目网络（概念暂不与 `KnowledgePoint`/题目表打通；Tab1 与 Tab2 物理隔离）。
- 不做知识库全文搜索（13 章前端本地过滤即可；后续如需可再加）。
