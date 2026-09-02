<template>
  <div class="asset-page">
    <header class="asset-header">
      <span class="brand"><span><DatabaseZap :size="19" /></span> 数据资产中心</span>
      <span class="sub">真实来源 · 增量采集 · 质量治理 · 全链路追踪</span>
      <router-link to="/" class="back-home"><House :size="14" /> 返回门户</router-link>
    </header>

    <main class="asset-main" v-loading="loading">
      <section class="asset-command">
        <div class="command-copy">
          <span class="command-kicker"><Sparkles :size="14" /> DATA INTELLIGENCE FABRIC</span>
          <h1>让数据持续流入，<br><em>变成可用的业务资产</em></h1>
          <p>从官方站点、API、文件和人工录入接入，经过去重、日期核验、分类、质量审核与知识化沉淀，为学习和仿真提供同一份可信底座。</p>
          <div class="command-state">
            <span :class="{ live: runningCount }"></span>
            <strong>{{ runningCount ? `${runningCount} 条采集链路运行中` : '数据管道待命' }}</strong>
            <small>库内 {{ stats.total || 0 }} 项 · 待审核 {{ pendingList.length }} 项</small>
          </div>
        </div>
        <div class="data-fabric" aria-label="数据从接入到服务化的处理流程">
          <div class="fabric-line"></div>
          <span class="fabric-particle p1"></span><span class="fabric-particle p2"></span><span class="fabric-particle p3"></span>
          <div class="fabric-node source">
            <span><RadioTower :size="17" /></span><strong>多源接入</strong><small>官方站点 / API / 文件</small>
          </div>
          <div class="fabric-node parse">
            <span><ScanSearch :size="17" /></span><strong>解析去重</strong><small>日期 · 原文 · 唯一标识</small>
          </div>
          <div class="fabric-node quality-node">
            <span><ShieldCheck :size="17" /></span><strong>质量治理</strong><small>{{ pendingList.length }} 项等待人工核验</small>
          </div>
          <div class="fabric-node service">
            <span><BrainCircuit :size="17" /></span><strong>业务服务</strong><small>学习 / 检索 / 仿真</small>
          </div>
          <div class="fabric-core">
            <i></i>
            <strong><span :key="stats.total" v-count="stats.total || 0">0</span></strong>
            <small>可信资产</small>
          </div>
        </div>
      </section>

      <!-- ① 统计概览 -->
      <section class="stats-bar">
        <div class="stat-pill">
          <span class="num">{{ stats.total || 0 }}</span>
          <span class="lbl">数据资产总数</span>
        </div>
        <div class="stat-pill" v-for="s in stats.by_ingest || []" :key="s.key">
          <span class="num">{{ s.count }}</span>
          <span class="lbl">{{ ingestLabel(s.key) }}</span>
        </div>
      </section>

      <nav class="asset-section-nav" aria-label="数据资产工作区">
        <button :class="{ active: assetView === 'governance' }" @click="assetView = 'governance'">
          <ShieldCheck :size="16" /><span><strong>质量治理</strong><small>审核、补全与可信分层</small></span>
          <i v-if="pendingList.length">{{ pendingList.length }}</i>
        </button>
        <button :class="{ active: assetView === 'ingest' }" @click="assetView = 'ingest'">
          <Inbox :size="16" /><span><strong>数据接入</strong><small>API、文件与人工录入</small></span>
        </button>
        <button :class="{ active: assetView === 'collectors' }" @click="assetView = 'collectors'">
          <RadioTower :size="16" /><span><strong>采集任务</strong><small>增量爬虫与运行状态</small></span>
          <i v-if="runningCount" class="running-count">{{ runningCount }}</i>
        </button>
        <button :class="{ active: assetView === 'timeline' }" @click="assetView = 'timeline'">
          <Calendar :size="16" /><span><strong>资产时间线</strong><small>来源、日期与原文追踪</small></span>
        </button>
      </nav>

      <!-- ② 多源接入（标签页） -->
      <section v-show="assetView === 'ingest'" class="ingest-section">
        <div class="section-head">
          <h3><Inbox :size="18" /> 数据接入（多源归一）</h3>
          <span class="hint">无论哪种方式进来，都会自动：分类 → AI总结 → 向量化 → 沉淀到统一知识库</span>
        </div>

        <el-tabs v-model="activeIngest" class="ingest-tabs">
          <!-- cURL 抓取 -->
          <el-tab-pane name="curl">
            <template #label><span class="tab-label"><Link :size="14" /> cURL快速抓取</span></template>
            <div class="ingest-form">
              <el-input
                v-model="curlInput" type="textarea" :rows="4"
                placeholder="粘贴完整 curl 命令（浏览器F12 → Copy as cURL），系统自动解析URL、请求头、body"
              />
              <div class="form-row">
                <el-select v-model="curlType" placeholder="类型" style="width:190px">
                  <el-option label="行业资讯" value="industry_news" />
                  <el-option label="国家政策" value="national_policy" />
                  <el-option label="交易中心公告" value="exchange_info" />
                  <el-option label="监管规则" value="regulation" />
                  <el-option label="考试信息" value="exam_info" />
                </el-select>
                <el-select v-model="curlProvince" placeholder="省份(可选)" clearable style="width:150px">
                  <el-option v-for="p in provinces" :key="p" :label="p" :value="p" />
                </el-select>
                <el-button type="primary" :loading="ingestLoading" @click="doCurl">
                  <Zap :size="14" /> 抓取并沉淀
                </el-button>
              </div>
              <div v-if="curlResult" class="ingest-result" :class="{ dup: curlResult.dedup }">
                <span v-if="curlResult.dedup"><AlertTriangle :size="14" /> 已存在（去重）: {{ curlResult.title }}</span>
                <span v-else><CheckCircle2 :size="14" /> 沉淀成功: {{ curlResult.title }} <br>
                  <small v-if="curlResult.ai_summary">AI摘要: {{ curlResult.ai_summary.slice(0,80) }}...</small>
                </span>
              </div>
            </div>
          </el-tab-pane>

          <!-- 文件上传 -->
          <el-tab-pane name="upload">
            <template #label><span class="tab-label"><Paperclip :size="14" /> 上传文件</span></template>
            <div class="ingest-form">
              <el-upload
                drag :show-file-list="false" :before-upload="doUpload"
                accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.md"
              >
                <div class="upload-dragger">
                  <Folder class="upload-icon" :size="36" />
                  <div>拖拽文件到此处，或点击选择</div>
                  <small>支持 PDF / Word / Excel / TXT（PDF自动提取正文，其余存为附件）</small>
                </div>
              </el-upload>
              <div class="form-row">
                <el-select v-model="uploadType" placeholder="类型" style="width:190px">
                  <el-option label="行业资讯" value="industry_news" />
                  <el-option label="国家政策" value="national_policy" />
                  <el-option label="交易中心公告" value="exchange_info" />
                  <el-option label="监管规则" value="regulation" />
                  <el-option label="考试信息" value="exam_info" />
                </el-select>
                <el-select v-model="uploadProvince" placeholder="省份(可选)" clearable style="width:150px">
                  <el-option v-for="p in provinces" :key="p" :label="p" :value="p" />
                </el-select>
              </div>
              <div v-if="uploadResult" class="ingest-result">
                <CheckCircle2 :size="14" /> {{ uploadResult.title }} 已沉淀
              </div>
            </div>
          </el-tab-pane>

          <!-- 手动录入 -->
          <el-tab-pane name="manual">
            <template #label><span class="tab-label"><PenTool :size="14" /> 手动录入</span></template>
            <div class="ingest-form">
              <el-input v-model="manualTitle" placeholder="标题" style="margin-bottom:8px" />
              <el-input
                v-model="manualContent" type="textarea" :rows="6"
                placeholder="粘贴正文内容（系统会自动AI总结、分类、向量化）"
              />
              <div class="form-row">
                <el-select v-model="manualType" placeholder="类型" style="width:190px">
                  <el-option label="行业资讯" value="industry_news" />
                  <el-option label="国家政策" value="national_policy" />
                  <el-option label="交易中心公告" value="exchange_info" />
                  <el-option label="监管规则" value="regulation" />
                </el-select>
                <el-select v-model="manualProvince" placeholder="省份(可选)" clearable style="width:150px">
                  <el-option v-for="p in provinces" :key="p" :label="p" :value="p" />
                </el-select>
                <el-button type="primary" :loading="ingestLoading" @click="doManual">沉淀</el-button>
              </div>
              <div v-if="manualResult" class="ingest-result"><CheckCircle2 :size="14" /> {{ manualResult.title }} 已沉淀</div>
            </div>
          </el-tab-pane>

          <!-- 飞书导入 -->
          <el-tab-pane name="feishu">
            <template #label><span class="tab-label"><MessageSquare :size="14" /> 飞书知识库</span></template>
            <div class="ingest-form">
              <p class="form-tip">输入飞书知识库节点的 node_token（URL里 /wiki/ 后面那段），系统通过 lark-cli 拉取文档正文沉淀。</p>
              <el-input v-model="feishuToken" placeholder="飞书 wiki node_token，如：XxxxxxxYyZz" />
              <div class="form-row">
                <el-select v-model="feishuType" placeholder="类型" style="width:190px">
                  <el-option label="国家政策" value="national_policy" />
                  <el-option label="行业资讯" value="industry_news" />
                  <el-option label="交易中心公告" value="exchange_info" />
                </el-select>
                <el-select v-model="feishuProvince" placeholder="省份(可选)" clearable style="width:150px">
                  <el-option v-for="p in provinces" :key="p" :label="p" :value="p" />
                </el-select>
                <el-button type="primary" :loading="ingestLoading" @click="doFeishu"><Inbox :size="14" /> 拉取沉淀</el-button>
              </div>
              <div v-if="feishuResult" class="ingest-result"><CheckCircle2 :size="14" /> {{ feishuResult.title }} 已沉淀</div>
              <div v-if="feishuError" class="ingest-result" style="color:#e6402d">{{ feishuError }}</div>
            </div>
          </el-tab-pane>

          <!-- Excel/CSV 批量导入 -->
          <el-tab-pane name="spreadsheet">
            <template #label><span class="tab-label"><BarChart3 :size="14" /> Excel/CSV批量</span></template>
            <div class="ingest-form">
              <p class="form-tip">上传结构化表格，自动识别列名逐行入库。支持题库、政策清单、市场参数表。</p>
              <el-upload drag :show-file-list="false" :before-upload="doSpreadsheet" accept=".xlsx,.xls,.csv">
                <div class="upload-dragger">
                  <ClipboardList class="upload-icon" :size="36" />
                  <div>拖拽 Excel/CSV 到此处</div>
                  <small>列名中英文兼容：标题/title、题干/stem、答案/answer</small>
                </div>
              </el-upload>
              <div class="form-row">
                <el-radio-group v-model="ssTarget" size="small">
                  <el-radio-button label="doc"><FileText :size="13" /> 文档</el-radio-button>
                  <el-radio-button label="question"><PenLine :size="13" /> 题库</el-radio-button>
                  <el-radio-button label="policy"><ScrollText :size="13" /> 政策</el-radio-button>
                </el-radio-group>
              </div>
              <div v-if="ssResult" class="ingest-result">
                <CheckCircle2 :size="14" /> 导入完成: {{ ssResult.imported }}条，跳过{{ ssResult.skipped }}条
              </div>
            </div>
          </el-tab-pane>

          <!-- API 数据源直连 -->
          <el-tab-pane name="api">
            <template #label><span class="tab-label"><Plug :size="14" /> API数据源</span></template>
            <div class="ingest-form">
              <div class="connector-card" :class="{ ready: qweatherStatus?.configured }">
                <div class="connector-marker">
                  <CloudSun :size="24" />
                  <span>{{ qweatherStatus?.configured ? 'READY' : 'SETUP' }}</span>
                </div>
                <div class="connector-content">
                  <div class="connector-title-row">
                    <div>
                      <div class="connector-eyebrow">国内气象辅助数据</div>
                      <h4>和风天气 · QWeather</h4>
                    </div>
                    <el-tag
                      size="small"
                      :type="qweatherStatus?.configured ? 'success' : 'warning'"
                      effect="plain"
                    >{{ qweatherStatus?.configured ? '已配置' : '待配置' }}</el-tag>
                  </div>
                  <div class="connector-facts">
                    <span>认证 {{ qweatherAuthLabel }}</span>
                    <span>城市 {{ qweatherLocationCount }}</span>
                    <span>资产 {{ qweatherStatus?.records || 0 }} 条</span>
                    <span>质量 {{ qweatherQualityLabel }}</span>
                  </div>
                  <div class="connector-note">
                    <template v-if="qweatherStatus?.configured">
                      凭证仅保存在后端本地环境；最近同步
                      {{ formatConnectorTime(qweatherStatus.last_sync_at) }}
                    </template>
                    <template v-else>
                      连接器默认关闭。部署者需在后端使用自己的和风账号配置；凭证不会进入浏览器、数据库或日志。
                    </template>
                  </div>
                  <div class="connector-actions">
                    <el-button size="small" :loading="qweatherLoading" @click="loadQWeatherStatus">
                      <RefreshCw :size="13" /> 刷新状态
                    </el-button>
                    <el-button
                      size="small"
                      :disabled="!qweatherStatus?.configured"
                      :loading="qweatherTesting"
                      @click="testQWeather"
                    >
                      <Plug :size="13" /> 测试连接
                    </el-button>
                    <el-button
                      size="small"
                      type="primary"
                      :disabled="!qweatherStatus?.configured"
                      :loading="crawlerLoading.weather"
                      @click="runCrawler('weather')"
                    >
                      <CloudSun :size="13" /> 立即同步
                    </el-button>
                  </div>
                  <div v-if="qweatherTestResult" class="connector-test-result">
                    <CheckCircle2 :size="14" />
                    {{ qweatherTestResult.province }}{{ qweatherTestResult.city }}
                    {{ qweatherTestResult.weather || '天气数据正常' }}
                    {{ qweatherTestResult.temp_c ?? '--' }}℃ · {{ qweatherTestResult.obs_time || '' }}
                  </div>
                </div>
              </div>
              <div class="generic-api-divider"><span>通用 API 导入</span></div>
              <p class="form-tip">配置一个API端点，直接拉取结构化数据。数值型→交易数据表，文档型→知识库。</p>
              <el-input v-model="apiForm.name" placeholder="数据源名称（如：中电联煤价）" style="margin-bottom:8px" />
              <el-input v-model="apiForm.url" placeholder="API URL（https://api.example.com/data）" />
              <div class="form-row">
                <el-select v-model="apiForm.data_type" size="small" style="width:160px">
                  <el-option label="出清价" value="clearing" />
                  <el-option label="煤价" value="coal" />
                  <el-option label="碳价" value="carbon" />
                  <el-option label="负荷" value="load" />
                  <el-option label="文档型" value="industry_news" />
                </el-select>
                <el-select v-model="apiForm.method" size="small" style="width:100px">
                  <el-option label="GET" value="GET" />
                  <el-option label="POST" value="POST" />
                </el-select>
                <el-input v-model="apiForm.province" placeholder="省份(可选)" size="small" style="width:120px" />
              </div>
              <el-input v-model="apiForm.extractJson" type="textarea" :rows="2"
                placeholder='提取路径JSON（可选）：{"date":"data.date","price":"data.price"}' />
              <div class="form-row">
                <el-button type="primary" :loading="ingestLoading" @click="doApi"><Plug :size="14" /> 拉取入库</el-button>
              </div>
              <div v-if="apiResult" class="ingest-result">
                <CheckCircle2 :size="14" /> {{ apiResult.target === 'public_data' ? `数值数据: 新增${apiResult.new}条` : `文档: 导入${apiResult.imported}条` }}
              </div>
            </div>
          </el-tab-pane>

          <!-- RSS 订阅监听 -->
          <el-tab-pane name="rss">
            <template #label><span class="tab-label"><Radio :size="14" /> RSS订阅</span></template>
            <div class="ingest-form">
              <p class="form-tip">监听电力行业媒体RSS源，新文章自动入库去重。适合北极星电力、能源杂志等。</p>
              <el-input v-model="rssUrl" placeholder="RSS Feed URL（如 https://news.bjx.com.cn/rss.xml）" />
              <div class="form-row">
                <el-select v-model="rssType" size="small" style="width:160px">
                  <el-option label="行业资讯" value="industry_news" />
                  <el-option label="交易中心公告" value="exchange_info" />
                </el-select>
                <el-button type="primary" :loading="ingestLoading" @click="doRss"><Radio :size="14" /> 拉取最新</el-button>
              </div>
              <div v-if="rssResult" class="ingest-result">
                <CheckCircle2 :size="14" /> 新增{{ rssResult.imported }}篇，跳过(已存在){{ rssResult.skipped }}篇
              </div>
            </div>
          </el-tab-pane>

          <!-- 飞书 Base 表格 -->
          <el-tab-pane name="feishuBase">
            <template #label><span class="tab-label"><FolderTree :size="14" /> 飞书Base表</span></template>
            <div class="ingest-form">
              <p class="form-tip">同步飞书多维表格(Base)。题库表→题库，文档表→知识库。</p>
              <el-input v-model="fbForm.app_token" placeholder="Base app_token" style="margin-bottom:8px" />
              <el-input v-model="fbForm.table_id" placeholder="table_id" />
              <div class="form-row">
                <el-radio-group v-model="fbForm.target" size="small">
                  <el-radio-button label="question"><PenLine :size="13" /> 题库表</el-radio-button>
                  <el-radio-button label="doc"><FileText :size="13" /> 文档表</el-radio-button>
                </el-radio-group>
                <el-button type="primary" :loading="ingestLoading" @click="doFeishuBase"><FolderTree :size="14" /> 同步</el-button>
              </div>
              <div v-if="fbResult" class="ingest-result">
                <CheckCircle2 :size="14" /> 同步{{ fbResult.imported }}条，跳过{{ fbResult.skipped }}条
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </section>

      <!-- ③ 爬虫触发（分类型） -->
      <section v-show="assetView === 'collectors'" class="crawler-section">
        <div class="section-head">
          <div class="ch-left">
            <h3><Bug :size="18" /> 爬虫触发（分类型）</h3>
            <el-tooltip v-if="runningCount > 0" :content="'运行中：' + runningNames" placement="top">
              <span class="crawler-running"><RefreshCw :size="14" class="spin" /> {{ progressLabel }}</span>
            </el-tooltip>
          </div>
          <span class="hint">手动触发后，数据自动沉淀到知识库 + PublicData 表</span>
        </div>
        <div class="crawler-grid">
          <div v-for="c in crawlerTypes" :key="c.key" class="crawler-card" :class="{ running: crawlerLoading[c.key] }">
            <div class="cc-main">
              <component :is="c.icon" class="cc-icon" :size="24" />
              <div class="cc-body">
                <div class="cc-name">{{ c.name }}</div>
                <div class="cc-desc">{{ c.desc }}</div>
              </div>
            </div>
            <el-button
              size="small" type="primary" plain
              :loading="crawlerLoading[c.key]"
              @click="runCrawler(c.key)"
            >{{ crawlerLoading[c.key] ? '运行中' : '立即运行' }}</el-button>
          </div>
        </div>
        <div v-if="crawlerLog.length" class="crawler-log">
          <div v-for="(log, i) in crawlerLog" :key="i" class="log-line" :class="{ err: log.errors }">
            {{ log.source }}: 新增{{ log.new || log.policies_new || 0 }}
            更新{{ log.updated || 0 }} 重复{{ log.dup || log.policies_dup || 0 }}
            <span v-if="log.error_msg">（{{ log.error_msg }}）</span>
          </div>
          <div v-if="lastCrawlSummary" class="crawler-result-route">
            <div>
              <strong>{{ lastCrawlSummary.name }}已归档</strong>
              <span>新增 {{ lastCrawlSummary.new }} 条、更新 {{ lastCrawlSummary.updated }} 条；文档和行情数据统一进入资产时间线。</span>
            </div>
            <el-button type="primary" @click="openLatestAssets"><Calendar :size="14" /> 查看新增资产</el-button>
          </div>
        </div>
      </section>

      <!-- ④ 运维：数据质量 + 审核 -->
      <section v-show="assetView === 'governance'" class="ops-section">
        <div class="section-head">
          <h3><ShieldCheck :size="18" /> 数据运维（质量看板 + 审核队列 + 流向追踪）</h3>
          <el-button size="small" :loading="refreshing" @click="refreshOps"><RefreshCw :size="13" /> 刷新</el-button>
        </div>

        <!-- 质量看板 -->
        <div class="quality-grid" v-if="quality">
          <div class="q-card q-high">
            <div class="q-num">{{ quality.quality?.high || 0 }}</div>
            <div class="q-lbl">高质量(≥80)</div>
          </div>
          <div class="q-card q-mid">
            <div class="q-num">{{ quality.quality?.mid || 0 }}</div>
            <div class="q-lbl">中等(50-79)</div>
          </div>
          <div class="q-card q-low">
            <div class="q-num">{{ quality.quality?.low || 0 }}</div>
            <div class="q-lbl">低质量(&lt;50)</div>
          </div>
          <div class="q-card q-warn" v-if="quality.outdated">
            <div class="q-num">{{ quality.outdated }}</div>
            <div class="q-lbl"><AlertTriangle :size="12" /> 可能过期</div>
          </div>
          <div class="q-card q-pending" v-if="quality.pending_review">
            <div class="q-num">{{ quality.pending_review }}</div>
            <div class="q-lbl"><Clock :size="12" /> 待审核</div>
          </div>
        </div>

        <!-- 低质量文档列表 -->
        <div v-if="quality?.low_quality_samples?.length" class="low-quality-list">
          <div class="lq-title">
            <span class="queue-icon"><TrendingDown :size="17" /></span>
            <span class="queue-copy"><strong>质量修复队列</strong><small>已入库资产缺少关键字段，点击条目补充并重新评分</small></span>
            <span class="queue-count">{{ quality.low_quality_samples.length }} 项待修复</span>
          </div>
          <div v-for="doc in lowQualityPaged" :key="doc.id" class="lq-item" @click="openSupplement(doc)">
            <span class="lq-score">{{ doc.score }}分</span>
            <span class="lq-name">{{ doc.title }}</span>
            <span class="lq-missing">缺: {{ doc.missing.join('、') }}</span>
          </div>
          <el-pagination
            v-if="quality.low_quality_samples.length > opsPageSize"
            v-model:current-page="qualityPage"
            class="ops-pagination"
            background layout="prev, pager, next"
            :page-size="opsPageSize"
            :total="quality.low_quality_samples.length"
          />
        </div>

        <!-- 待审核队列 -->
        <div v-if="pendingList.length" class="review-list">
          <div class="rv-title">
            <span class="review-heading">
              <span class="queue-icon"><ShieldCheck :size="17" /></span>
              <span class="queue-copy"><strong>外部数据准入审核</strong><small>爬虫与外部来源需核验日期、标题和官方原文后进入正式资产</small></span>
              <span class="queue-count">{{ pendingList.length }} 条待审核</span>
            </span>
            <el-button size="small" type="primary" :loading="batchReviewing" @click="doBatchReview">全部通过</el-button>
          </div>
          <div v-for="item in pendingPaged" :key="item.id" class="rv-item">
            <span class="rv-type" :class="item.doc_type">{{ typeLabel(item.doc_type) }}</span>
            <a
              v-if="item.source_url"
              :href="item.source_url"
              target="_blank"
              rel="noopener"
              class="rv-title-text rv-title-link"
              title="打开官方原文核验"
            >{{ item.title }}</a>
            <span v-else class="rv-title-text">{{ item.title }}</span>
            <span class="rv-date">{{ item.publish_date || '日期待核验' }}</span>
            <span class="rv-source">[{{ ingestLabel(item.ingest_type) }}]</span>
            <a
              v-if="item.source_url"
              :href="item.source_url"
              target="_blank"
              rel="noopener"
              class="rv-original"
              title="在新窗口打开官方原文"
            ><Link :size="12" /> 核验原文</a>
            <el-button size="small" type="success" plain @click="reviewDoc(item.id, 'approve')">通过</el-button>
            <el-button size="small" type="danger" plain @click="reviewDoc(item.id, 'reject')">驳回</el-button>
          </div>
          <el-pagination
            v-if="pendingList.length > opsPageSize"
            v-model:current-page="pendingPage"
            class="ops-pagination"
            background layout="prev, pager, next"
            :page-size="opsPageSize"
            :total="pendingList.length"
          />
        </div>
      </section>

      <!-- ⑤ 数据资产时间线 -->
      <section v-show="assetView === 'timeline'" class="timeline-section">
        <div class="section-head">
          <div>
            <h3><Calendar :size="18" /> 数据资产时间线 <em>{{ timelineTotal }} 项</em></h3>
            <p class="timeline-note">文档按官方发布日期、行情按数据所属日期倒排；采集时间单独展示，不冒充业务日期。</p>
          </div>
          <div class="tl-filters">
            <el-select v-model="tlType" placeholder="全部资产类型" size="small" clearable style="width:190px" @change="loadTimeline">
              <el-option-group label="文档资产">
                <el-option label="国家政策" value="national_policy" />
                <el-option label="交易中心公告" value="exchange_info" />
                <el-option label="行业资讯" value="industry_news" />
                <el-option label="监管规则" value="regulation" />
              </el-option-group>
              <el-option-group label="结构化时序数据">
                <el-option label="出清价格曲线" value="data:clearing" />
                <el-option label="负荷曲线" value="data:load" />
                <el-option label="气象实况" value="data:weather_observation" />
                <el-option label="逐小时天气预报" value="data:weather_forecast_hourly" />
                <el-option label="动力煤价格" value="data:coal" />
                <el-option label="全国碳市场价格" value="data:carbon" />
                <el-option label="官方能源统计" value="data:national_power_statistics" />
              </el-option-group>
            </el-select>
            <el-select v-model="tlProvince" placeholder="省份" size="small" clearable style="width:120px" @change="loadTimeline">
              <el-option v-for="p in provinces" :key="p" :label="p" :value="p" />
            </el-select>
          </div>
        </div>
        <div class="timeline-list">
          <div v-for="g in timeline" :key="g.date" class="tl-group">
            <div class="tl-date">{{ g.date }}</div>
            <div class="tl-items">
              <div v-for="item in g.items" :key="`${item.asset_kind}-${item.id}`" class="tl-item" :class="`kind-${item.asset_kind}`">
                <span class="tl-type" :class="item.doc_type">{{ typeLabel(item.doc_type) }}</span>
                <span class="tl-ingest">[{{ ingestLabel(item.ingest_type) }}]</span>
                <span v-if="item.province" class="tl-prov">{{ item.province }}</span>
                <span class="tl-title">{{ item.title }}</span>
                <span v-if="item.record_count > 1" class="tl-count">{{ item.record_count }} 条记录</span>
                <span v-if="item.provenance_level" class="tl-provenance" :class="item.provenance_level">{{ provenanceLabel(item.provenance_level) }}</span>
                <a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noopener" class="tl-src" @click.stop><Link :size="11" /> 查看原文</a>
                <small v-if="item.ai_summary" class="tl-summary"><span class="ai-tag">AI</span>{{ item.ai_summary.slice(0, 60) }}…</small>
                <small v-else-if="item.asset_kind === 'structured_data'" class="tl-summary tl-lineage">
                  来源：{{ item.source || '待补充' }}
                  <span v-if="item.fetched_at"> · 采集于 {{ formatConnectorTime(item.fetched_at) }}</span>
                </small>
              </div>
            </div>
          </div>
          <div v-if="!timeline.length" class="empty">暂无数据，请通过上方任一方式接入或触发爬虫</div>
        </div>
      </section>

      <!-- 缺字段补充弹窗 -->
      <el-dialog v-model="supplementVisible" title="补充文档字段" width="560px" class="brand-dialog">
        <div v-if="supplementDoc">
          <p style="font-size:15px;font-weight:600;color:#18181b;margin:0 0 4px">{{ supplementDoc.title }}</p>
          <p style="font-size:12px;color:#909399;margin:0 0 14px">补充以下缺失字段，保存后系统会重新评估质量分</p>
          <el-form label-position="top">
            <el-form-item v-for="f in supplementFields" :key="f.key" :label="f.label">
              <el-input v-if="f.type==='textarea'" v-model="supplementForm[f.key]" type="textarea" :rows="4" :placeholder="'请输入' + f.label" />
              <el-select v-else-if="f.type==='province'" v-model="supplementForm[f.key]" placeholder="选择省份" style="width:100%">
                <el-option v-for="p in provinces" :key="p" :label="p" :value="p" />
              </el-select>
              <el-date-picker v-else-if="f.type==='date'" v-model="supplementForm[f.key]" type="date" value-format="YYYY-MM-DD" placeholder="选择发布日期" style="width:100%" />
              <el-input v-else v-model="supplementForm[f.key]" :placeholder="'请输入' + f.label" />
            </el-form-item>
          </el-form>
        </div>
        <template #footer>
          <el-button @click="supplementVisible=false">取消</el-button>
          <el-button type="primary" :loading="supplementSaving" @click="saveSupplement">保存补充</el-button>
        </template>
      </el-dialog>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Database, Inbox, Link, Paperclip, PenTool, Bird, BarChart3, Plug,
  Radio, Bug, Calendar, ShieldCheck, RefreshCw, FileText, Folder,
  ClipboardList, ScrollText, PenLine, TrendingUp, TrendingDown, Zap,
  Activity, Coins, Star, AlertTriangle, Clock, CheckCircle2, FolderTree,
  CloudSun, DatabaseZap, House, Sparkles, RadioTower, ScanSearch, BrainCircuit,
} from 'lucide-vue-next'
import { assetApi } from '../../api'

const route = useRoute()
const loading = ref(false)
const stats = ref({})
const validAssetViews = ['governance', 'ingest', 'collectors', 'timeline']
const assetView = ref(validAssetViews.includes(route.query.view) ? route.query.view : 'governance')
watch(() => route.query.view, (view) => {
  if (validAssetViews.includes(view)) assetView.value = view
})
const provinces = ['山西', '山东', '广东', '浙江', '蒙西', '上海', '江苏', '福建', '四川', '云南', '广西']

// ---- 接入表单状态 ----
const activeIngest = ref('curl')
const ingestLoading = ref(false)

const curlInput = ref('')
const curlType = ref('industry_news')
const curlProvince = ref('')
const curlResult = ref(null)

const uploadType = ref('industry_news')
const uploadProvince = ref('')
const uploadResult = ref(null)

const manualTitle = ref('')
const manualContent = ref('')
const manualType = ref('industry_news')
const manualProvince = ref('')
const manualResult = ref(null)

const feishuToken = ref('')
const feishuType = ref('national_policy')
const feishuProvince = ref('')
const feishuResult = ref(null)
const feishuError = ref('')

// ---- 扩展通道状态 ----
const ssTarget = ref('doc')
const ssResult = ref(null)
const apiForm = reactive({ name: '', url: '', data_type: 'coal', method: 'GET', province: '', extractJson: '' })
const apiResult = ref(null)
const qweatherStatus = ref(null)
const qweatherLoading = ref(false)
const qweatherTesting = ref(false)
const qweatherTestResult = ref(null)
const rssUrl = ref('')
const rssType = ref('industry_news')
const rssResult = ref(null)
const fbForm = reactive({ app_token: '', table_id: '', target: 'question' })
const fbResult = ref(null)

// ---- 运维 ----
const quality = ref(null)
const pendingList = ref([])
const opsPageSize = 6
const qualityPage = ref(1)
const pendingPage = ref(1)
const lowQualityPaged = computed(() => {
  const items = quality.value?.low_quality_samples || []
  const start = (qualityPage.value - 1) * opsPageSize
  return items.slice(start, start + opsPageSize)
})
const pendingPaged = computed(() => {
  const start = (pendingPage.value - 1) * opsPageSize
  return pendingList.value.slice(start, start + opsPageSize)
})

// ---- 爬虫 ----
const crawlerTypes = [
  { key: 'policy', name: '政策法规', icon: ScrollText, desc: '发改委/能源局/监管局/国家标准' },
  { key: 'exam', name: '考题真题', icon: PenLine, desc: '知乎/B站电力交易考试内容' },
  { key: 'official_stats', name: '国家官方能源统计', icon: Database, desc: '能源局+统计局真实月度数据' },
  { key: 'trade_data', name: '市场数据资产', icon: Zap, desc: '南方现货+绿证+碳市场+官方统计' },
  { key: 'clearing', name: '重构出清曲线', icon: TrendingUp, desc: '公开区间参数重构(非实时)' },
  { key: 'load', name: '重构负荷曲线', icon: Activity, desc: '省级负荷特性重构(非实测)' },
  { key: 'weather', name: '国内气象', icon: CloudSun, desc: '和风实况+逐小时预报(5省)' },
  { key: 'commodity', name: '燃料与碳价', icon: Coins, desc: '全国碳市场真实日行情+重构煤价' },
  { key: 'all', name: '全部爬虫', icon: Star, desc: '一次性运行所有数据源' },
]
const crawlerLoading = reactive({})
const crawlerLog = ref([])
const lastCrawlSummary = ref(null)

// ---- 时间线 ----
const timeline = ref([])
const timelineTotal = ref(0)
const tlType = ref('')
const tlProvince = ref('')

const crawlerProgress = reactive({})
const runningCount = computed(() => Object.values(crawlerLoading).filter(Boolean).length)
const runningNames = computed(() => crawlerTypes.filter(c => crawlerLoading[c.key]).map(c => c.name).join('、'))
const progressLabel = computed(() => {
  const running = crawlerTypes.filter(c => crawlerLoading[c.key])
  if (running.length === 1) {
    const p = crawlerProgress[running[0].key]
    return p && p.total ? `${running[0].name} 运行中 ${p.done}/${p.total}` : `${running[0].name} 运行中`
  }
  return `${running.length} 个运行中`
})
const qweatherLocationCount = computed(
  () => Object.keys(qweatherStatus.value?.locations || {}).length,
)
const qweatherAuthLabel = computed(() => {
  const auth = qweatherStatus.value?.auth_type
  if (auth === 'jwt') return 'JWT'
  if (auth === 'api_key') return 'API KEY'
  return '未配置'
})
const qweatherQualityLabel = computed(() => ({
  valid: '正常',
  suspect: '需复核',
  invalid: '异常',
  unknown: '待同步',
}[qweatherStatus.value?.last_quality_status] || '待同步'))

// 刷新后从后端恢复运行状态（crawlerLoading 是前端本地态，刷新会丢；后端 _crawler_state 记着）
async function restoreCrawlerStatus() {
  try {
    const all = await assetApi.crawlerStatus()
    for (const [key, st] of Object.entries(all || {})) {
      if (st && st.running) { crawlerLoading[key] = true; pollCrawler(key) }
    }
  } catch (e) { /* ignore */ }
}

onMounted(() => {
  loadStats()
  loadTimeline()
  loadQuality()
  // 待审核队列仅管理员可读，非 admin 跳过以避免 403 控制台噪声
  try {
    if (JSON.parse(localStorage.getItem('user') || '{}').role === 'admin') loadPending()
  } catch (e) { /* ignore */ }
  loadQWeatherStatus()
  restoreCrawlerStatus()
})

async function loadStats() {
  try { stats.value = await assetApi.stats() } catch (e) { /* ignore */ }
}

async function loadTimeline() {
  loading.value = true
  try {
    const params = {}
    if (tlType.value) params.doc_type = tlType.value
    if (tlProvince.value) params.province = tlProvince.value
    const res = await assetApi.timeline(params)
    timeline.value = res.timeline || []
    timelineTotal.value = res.total || 0
  } catch (e) { /* ignore */ }
  loading.value = false
}

// ---- 接入操作 ----
async function doCurl() {
  if (!curlInput.value.includes('http')) {
    ElMessage.warning('请粘贴有效的 curl 命令')
    return
  }
  ingestLoading.value = true
  curlResult.value = null
  try {
    curlResult.value = await assetApi.ingestCurl({
      curl: curlInput.value, doc_type: curlType.value,
      province: curlProvince.value || null,
    })
    ElMessage.success('抓取沉淀成功')
    loadStats(); loadTimeline()
  } catch (e) {
    ElMessage.error('抓取失败: ' + e.message)
  }
  ingestLoading.value = false
}

async function doUpload(file) {
  ingestLoading.value = true
  uploadResult.value = null
  try {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('doc_type', uploadType.value)
    if (uploadProvince.value) fd.append('province', uploadProvince.value)
    uploadResult.value = await assetApi.uploadFile(fd)
    ElMessage.success('上传沉淀成功')
    loadStats(); loadTimeline()
  } catch (e) {
    ElMessage.error('上传失败: ' + e.message)
  }
  ingestLoading.value = false
  return false  // 阻止 el-upload 默认上传
}

async function doManual() {
  if (!manualTitle.value || !manualContent.value) {
    ElMessage.warning('标题和内容不能为空')
    return
  }
  ingestLoading.value = true
  manualResult.value = null
  try {
    manualResult.value = await assetApi.ingestManual({
      title: manualTitle.value, content: manualContent.value,
      doc_type: manualType.value, province: manualProvince.value || null,
    })
    ElMessage.success('录入沉淀成功')
    manualTitle.value = ''; manualContent.value = ''
    loadStats(); loadTimeline()
  } catch (e) {
    ElMessage.error('录入失败: ' + e.message)
  }
  ingestLoading.value = false
}

async function doFeishu() {
  if (!feishuToken.value) {
    ElMessage.warning('请输入飞书 wiki node_token')
    return
  }
  ingestLoading.value = true
  feishuResult.value = null
  feishuError.value = ''
  try {
    feishuResult.value = await assetApi.ingestFeishu({
      wiki_token: feishuToken.value, doc_type: feishuType.value,
      province: feishuProvince.value || null,
    })
    ElMessage.success('飞书文档沉淀成功')
    loadStats(); loadTimeline()
  } catch (e) {
    feishuError.value = e.message
    ElMessage.error('飞书导入失败: ' + e.message)
  }
  ingestLoading.value = false
}

// ---- 扩展通道 ----
async function doSpreadsheet(file) {
  ingestLoading.value = true
  ssResult.value = null
  try {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('target', ssTarget.value)
    ssResult.value = await assetApi.uploadSpreadsheet(fd)
    ElMessage.success(`导入${ssResult.value.imported}条`)
    loadStats(); loadTimeline(); loadQuality()
  } catch (e) {
    ElMessage.error('导入失败: ' + e.message)
  }
  ingestLoading.value = false
  return false
}

async function doApi() {
  if (!apiForm.url) { ElMessage.warning('请输入API URL'); return }
  ingestLoading.value = true
  apiResult.value = null
  try {
    const payload = { name: apiForm.name || 'API数据源', url: apiForm.url,
      method: apiForm.method, data_type: apiForm.data_type, province: apiForm.province || null }
    if (apiForm.extractJson) {
      try { payload.extract = JSON.parse(apiForm.extractJson) } catch (e) { /* 忽略 */ }
    }
    apiResult.value = await assetApi.ingestApi(payload)
    ElMessage.success('API拉取成功')
    loadStats(); loadTimeline()
  } catch (e) {
    ElMessage.error('API拉取失败: ' + e.message)
  }
  ingestLoading.value = false
}

async function loadQWeatherStatus() {
  qweatherLoading.value = true
  try {
    qweatherStatus.value = await assetApi.qweatherStatus()
  } catch (e) {
    qweatherStatus.value = null
  } finally {
    qweatherLoading.value = false
  }
}

async function testQWeather() {
  qweatherTesting.value = true
  qweatherTestResult.value = null
  try {
    qweatherTestResult.value = await assetApi.qweatherTest()
    ElMessage.success('和风天气连接正常')
  } catch (e) {
    ElMessage.error('连接测试失败: ' + (e.message || e))
  } finally {
    qweatherTesting.value = false
  }
}

async function doRss() {
  if (!rssUrl.value) { ElMessage.warning('请输入RSS URL'); return }
  ingestLoading.value = true
  rssResult.value = null
  try {
    rssResult.value = await assetApi.ingestRss({ feed_url: rssUrl.value, doc_type: rssType.value })
    ElMessage.success(`新增${rssResult.value.imported}篇`)
    loadStats(); loadTimeline()
  } catch (e) {
    ElMessage.error('RSS拉取失败: ' + e.message)
  }
  ingestLoading.value = false
}

async function doFeishuBase() {
  if (!fbForm.app_token || !fbForm.table_id) {
    ElMessage.warning('请输入 app_token 和 table_id'); return
  }
  ingestLoading.value = true
  fbResult.value = null
  try {
    fbResult.value = await assetApi.ingestFeishuBase({ ...fbForm })
    ElMessage.success(`同步${fbResult.value.imported}条`)
    loadStats(); loadTimeline()
  } catch (e) {
    ElMessage.error('Base同步失败: ' + e.message)
  }
  ingestLoading.value = false
}

// ---- 运维 ----
async function loadQuality() {
  try { quality.value = await assetApi.quality() } catch (e) { /* ignore */ }
}

// 数据运维「刷新」：真实全量刷新 + loading + 成功反馈（此前只调 loadQuality 且无反馈，像假象）
const refreshing = ref(false)
async function refreshOps() {
  refreshing.value = true
  try {
    await Promise.all([loadQuality(), loadPending(), loadStats(), loadTimeline()])
    ElMessage.success('数据运维已刷新')
  } catch (e) {
    ElMessage.error('刷新失败: ' + (e.message || e))
  } finally {
    refreshing.value = false
  }
}

async function loadPending() {
  try {
    const res = await assetApi.pendingReview()
    pendingList.value = res.items || []
    const maxPage = Math.max(1, Math.ceil(pendingList.value.length / opsPageSize))
    pendingPage.value = Math.min(pendingPage.value, maxPage)
  } catch (e) { /* ignore */ }
}

async function reviewDoc(id, action) {
  try {
    await assetApi.review(id, action)
    ElMessage.success(action === 'approve' ? '已通过' : '已驳回')
    loadPending(); loadQuality()
  } catch (e) {
    ElMessage.error('操作失败: ' + e.message)
  }
}

const batchReviewing = ref(false)
async function doBatchReview() {
  batchReviewing.value = true
  try {
    const r = await assetApi.batchReview('approve')
    ElMessage.success(`已通过 ${r.count} 条，进入可信层`)
    loadPending(); loadQuality(); loadTimeline()
  } catch (e) {
    ElMessage.error('批量审核失败: ' + (e.message || e))
  } finally {
    batchReviewing.value = false
  }
}

// ---- 缺字段补充 ----
const supplementVisible = ref(false)
const supplementDoc = ref(null)
const supplementSaving = ref(false)
const supplementForm = reactive({ content: '', ai_summary: '', category_code: '', province: '', publish_date: '' })
const MISSING_MAP = {
  '正文': { key: 'content', label: '正文', type: 'textarea' },
  '摘要': { key: 'ai_summary', label: 'AI 摘要', type: 'textarea' },
  '分类': { key: 'category_code', label: '分类编码', type: 'input' },
  '省份': { key: 'province', label: '省份', type: 'province' },
  '日期': { key: 'publish_date', label: '发布日期', type: 'date' },
}
const supplementFields = computed(() => (supplementDoc.value?.missing || []).map(m => MISSING_MAP[m]).filter(Boolean))
function openSupplement(doc) {
  supplementDoc.value = doc
  Object.assign(supplementForm, { content: '', ai_summary: '', category_code: '', province: '', publish_date: '' })
  supplementVisible.value = true
}
async function saveSupplement() {
  const filled = supplementFields.value.filter(f => supplementForm[f.key])
  if (!filled.length) { ElMessage.warning('请至少补充一个字段'); return }
  supplementSaving.value = true
  try {
    const payload = { doc_id: supplementDoc.value.id }
    for (const f of filled) payload[f.key] = supplementForm[f.key]
    await assetApi.updateDoc(payload)
    ElMessage.success('已补充，质量将重新评估')
    supplementVisible.value = false
    loadQuality()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  } finally {
    supplementSaving.value = false
  }
}

// ---- 爬虫触发 ----
async function runCrawler(key) {
  if (crawlerLoading[key]) return
  crawlerLoading[key] = true
  try {
    // 异步触发：后端后台跑，立即返回；前端轮询状态，不再阻塞/超时
    await assetApi.runCrawler(key)
    ElMessage.info(`${crawlerTypes.find(c => c.key === key)?.name} 已在后台运行…`)
    pollCrawler(key)
  } catch (e) {
    ElMessage.error('触发失败: ' + (e.message || e))
    crawlerLoading[key] = false
  }
}

function pollCrawler(key) {
  const timer = setInterval(async () => {
    try {
      const st = await assetApi.crawlerStatus(key)
      crawlerProgress[key] = st && st.progress ? st.progress : null
      if (st && !st.running) {
        clearInterval(timer)
        crawlerLoading[key] = false
        if (st.results) {
          crawlerLog.value = [...st.results, ...crawlerLog.value].slice(0, 10)
          const totalNew = st.results.reduce((a, r) => a + (r.new || r.policies_new || 0), 0)
          const totalUpdated = st.results.reduce((a, r) => a + (r.updated || 0), 0)
          const name = crawlerTypes.find(c => c.key === key)?.name
          lastCrawlSummary.value = { name, new: totalNew, updated: totalUpdated }
          if (totalNew > 0 || totalUpdated > 0) {
            ElMessage.success(`${name} 完成：新增 ${totalNew} 条，更新 ${totalUpdated} 条`)
          } else {
            ElMessage.info(`${name} 完成：无新增（这些源暂无新发布，库里已是最新）`)
          }
        }
        loadStats(); loadTimeline(); loadPending()
        if (key === 'weather' || key === 'all') loadQWeatherStatus()
      }
    } catch (e) {
      clearInterval(timer); crawlerLoading[key] = false
    }
  }, 2000)
}

async function openLatestAssets() {
  tlType.value = ''
  tlProvince.value = ''
  assetView.value = 'timeline'
  await loadTimeline()
  requestAnimationFrame(() => {
    document.querySelector('.timeline-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

// ---- 辅助 ----
function ingestLabel(k) {
  return { feishu: '飞书', crawler: '爬虫', structured: '结构化', upload: '上传', curl: 'cURL', manual: '手动' }[k] || k
}
function typeLabel(t) {
  return {
    national_policy: '国家政策', exchange_info: '交易公告', industry_news: '行业资讯',
    regulation: '监管规则', exam_info: '考试信息',
    clearing: '出清曲线', load: '负荷曲线', coal: '煤价', carbon: '碳价',
    weather_observation: '气象实况', weather_forecast_hourly: '天气预报',
    southern_spot_weekly: '南方现货', green_certificate_weekly: '绿证交易',
    national_market_transaction: '市场交易', national_market_transaction_ytd: '累计交易',
    national_power_consumption: '用电量', national_power_statistics: '电力统计',
    national_green_certificate: '绿证统计', national_new_energy_projects: '新能源项目',
    nbs_energy_production: '能源生产',
  }[t] || t
}
function provenanceLabel(value) {
  return {
    observed_public: '公开实测', observed_authorized: '授权实测',
    reconstructed: '公开数据重构', synthetic: '教学合成',
  }[value] || value
}
function formatConnectorTime(value) {
  if (!value) return '尚未同步'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.asset-page {
  min-height: 100vh;
  background: var(--bg-page, #f5f7fa);
  color: var(--text-main, #303133);
}
.asset-header {
  display: flex; align-items: center; gap: 16px;
  padding: 0 max(24px, calc((100vw - 1200px) / 2)); height:64px;
  background: rgba(255,255,255,.88);
  border-bottom: 1px solid var(--border-light, #ebeef5);
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);backdrop-filter:blur(16px);
  position:sticky;top:0;z-index:50;
}
.brand { font-size: 18px; font-weight: 800; display: inline-flex; align-items: center; gap: 9px;letter-spacing:-.02em }
.brand>span{width:34px;height:34px;display:grid;place-items:center;border-radius:11px;color:#fff;background:linear-gradient(145deg,#5964df,#3f4bc2);box-shadow:0 7px 17px rgba(72,83,197,.2)}
.sub { color: var(--text-sub, #909399); font-size: 13px; }
.back-home { margin-left: auto; min-height:34px;padding:0 11px;display:inline-flex;align-items:center;gap:6px;color:#4c57c8;text-decoration:none;font-size:12px;font-weight:720;border:1px solid #dfe3f1;border-radius:10px;background:#f8f9ff;box-shadow:0 5px 13px rgba(55,65,135,.06) }
.back-home:hover{color:#fff;background:#505bd1;border-color:#505bd1}

.asset-main { max-width: 1200px; margin: 0 auto; padding: 28px 20px 60px; }
.asset-command{min-height:330px;margin-bottom:18px;padding:43px 48px;display:grid;grid-template-columns:1.03fr .97fr;align-items:center;gap:38px;border:1px solid #1d3550;border-radius:20px;background:radial-gradient(circle at 82% 28%,rgba(30,191,205,.12),transparent 30%),linear-gradient(125deg,#081321,#0d1b2d 58%,#0b2130);box-shadow:0 24px 58px rgba(9,22,42,.2);position:relative;overflow:hidden}.asset-command::before{content:"";position:absolute;inset:0;background-image:linear-gradient(rgba(83,202,218,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(83,202,218,.045) 1px,transparent 1px);background-size:28px 28px;mask-image:linear-gradient(90deg,transparent,#000 37%,#000)}.asset-command::after{content:"";position:absolute;left:-20%;right:-20%;top:-2px;height:2px;background:linear-gradient(90deg,transparent,#4bd1df,transparent);animation:telemetryScan 5s ease-in-out infinite}.command-copy,.data-fabric{position:relative;z-index:1}.command-kicker{display:inline-flex;align-items:center;gap:7px;color:#55d3df;font-size:10px;letter-spacing:.15em;font-weight:850}.command-copy h1{margin:12px 0 15px;font-size:38px;line-height:1.18;letter-spacing:-.045em;color:#eef6ff}.command-copy h1 em{color:#62dce7;font-style:normal}.command-copy>p{max-width:580px;color:#8291a5;font-size:13px;line-height:1.8}.command-state{margin-top:23px;width:fit-content;padding:9px 12px;display:grid;grid-template-columns:auto auto;gap:2px 8px;align-items:center;border:1px solid #243c52;border-radius:8px;background:rgba(4,13,24,.45)}.command-state>span{grid-row:1/3;width:8px;height:8px;border-radius:50%;background:#718095}.command-state>span.live{background:#39d2a7;box-shadow:0 0 0 0 rgba(39,197,155,.4);animation:statePulse 2s infinite}.command-state strong{font-size:10px;color:#d8e5f2}.command-state small{font-size:9px;color:#718095}
.data-fabric{height:245px}.fabric-core{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:104px;height:104px;border-radius:22px;clip-path:polygon(23% 0,77% 0,100% 23%,100% 77%,77% 100%,23% 100%,0 77%,0 23%);z-index:5;display:flex;align-items:center;justify-content:center;flex-direction:column;color:#fff;background:linear-gradient(145deg,#15415a,#167286);box-shadow:0 0 34px rgba(66,211,224,.23)}.fabric-core i{width:42px;height:2px;margin-bottom:8px;background:linear-gradient(90deg,transparent,#8cf4fa,transparent);box-shadow:0 0 9px #6fe0ef;animation:fabricWave 2s ease-in-out infinite}.fabric-core strong{font-size:23px}.fabric-core small{font-size:9px;color:rgba(255,255,255,.65);margin-top:4px}.fabric-line{position:absolute;left:8%;right:8%;top:50%;height:1px;background:linear-gradient(90deg,transparent,#2e7385,#4ccbd7,#2e7385,transparent)}.fabric-line::after{content:"";position:absolute;left:50%;top:-82px;width:1px;height:164px;background:linear-gradient(transparent,#2e7385,transparent)}.fabric-node{position:absolute;z-index:4;width:134px;padding:10px;border:1px solid #244157;border-radius:8px;background:rgba(9,25,40,.88);box-shadow:0 9px 22px rgba(0,0,0,.13);display:grid;grid-template-columns:31px 1fr;gap:1px 8px;align-items:center}.fabric-node>span{grid-row:1/3;width:31px;height:31px;border-radius:7px;display:grid;place-items:center;color:#61dce7;background:#153448}.fabric-node strong{font-size:10px;color:#dbeaf5}.fabric-node small{font-size:8px;color:#6f8294;white-space:nowrap}.fabric-node.source{left:0;top:13px}.fabric-node.parse{right:0;top:13px}.fabric-node.quality-node{left:0;bottom:9px}.fabric-node.service{right:0;bottom:9px}.fabric-particle{position:absolute;z-index:6;width:6px;height:6px;top:calc(50% - 3px);border-radius:1px;background:#62d6e7;box-shadow:0 0 12px #3fc5d9;animation:dataFlow 3.4s linear infinite}.fabric-particle.p2{animation-delay:1.13s}.fabric-particle.p3{animation-delay:2.26s}

/* 统计 */
.stats-bar {
  display: grid;grid-template-columns:repeat(5,1fr); gap: 10px; margin-bottom: 20px;
}
.stat-pill {
  border-radius: 14px; padding: 17px 19px; min-width: 0; border: 1px solid #e5e8f2;
  display: flex; flex-direction: column; align-items: flex-start;
  position: relative; overflow: hidden;
  background: linear-gradient(145deg, #fff, #f5f6ff);
  box-shadow: 0 8px 20px rgba(55, 65, 135, 0.06);
  transition: transform 0.22s cubic-bezier(0.22, 0.61, 0.36, 1), box-shadow 0.22s ease;
}
.stat-pill:nth-child(2) { background: linear-gradient(145deg,#fff,#f6f0ff) }
.stat-pill:nth-child(3) { background: linear-gradient(145deg,#fff,#edfafd) }
.stat-pill:nth-child(4) { background: linear-gradient(145deg,#fff,#fff7e9) }
.stat-pill:nth-child(5) { background: linear-gradient(145deg,#fff,#edf9f4) }
.stat-pill::after {
  content: ''; position: absolute; top: -40%; right: -20%; width: 90px; height: 90px;
  border-radius: 50%; background: rgba(99, 102, 241, 0.06);
}
.stat-pill:hover { transform: translateY(-4px); box-shadow: 0 15px 30px rgba(74,84,173,.13);border-color:#cdd2f5 }
.stat-pill .num { font-size: 25px; font-weight: 800; color: #333d72; position: relative; }
.stat-pill .lbl { font-size: 11px; color: #8a91a3; margin-top: 3px; position: relative; }
@keyframes fabricWave{0%,100%{transform:scaleX(.5);opacity:.4}50%{transform:scaleX(1.25);opacity:1}}@keyframes dataFlow{from{left:9%;opacity:0}15%{opacity:1}85%{opacity:1}to{left:90%;opacity:0}}@keyframes statePulse{70%{box-shadow:0 0 0 8px rgba(39,197,155,0)}}@media(max-width:900px){.asset-command{grid-template-columns:1fr}.data-fabric{max-width:520px;width:100%;margin:auto}.stats-bar{grid-template-columns:repeat(2,1fr)}}@media(max-width:620px){.asset-header{padding:0 14px}.asset-header .sub{display:none}.asset-command{padding:30px 22px}.command-copy h1{font-size:31px}.data-fabric{display:none}.stats-bar{grid-template-columns:1fr 1fr}}@media(prefers-reduced-motion:reduce){.fabric-core i,.fabric-particle,.command-state>span.live{animation:none}}
@keyframes telemetryScan{0%,100%{transform:translateY(0);opacity:.35}50%{transform:translateY(332px);opacity:.85}}
.asset-section-nav{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:0 0 16px;padding:7px;border:1px solid #dce7ea;border-radius:15px;background:rgba(255,255,255,.82);box-shadow:0 8px 24px rgba(36,84,100,.045)}.asset-section-nav button{min-height:58px;padding:8px 11px;display:flex;align-items:center;gap:9px;border:0;border-radius:10px;background:transparent;color:#7f9099;text-align:left;cursor:pointer;position:relative;transition:color .2s,background .2s,box-shadow .2s,transform .2s}.asset-section-nav button:hover{color:#287c8e;background:#f1f8f9;transform:translateY(-1px)}.asset-section-nav button.active{color:#286f7e;background:linear-gradient(145deg,#fff,#eaf5f7);box-shadow:inset 0 0 0 1px #c5e0e5,0 5px 13px rgba(42,112,127,.08)}.asset-section-nav button>span{display:flex;flex-direction:column;flex:1}.asset-section-nav strong{font-size:11px}.asset-section-nav small{margin-top:2px;font-size:8px;color:#9da3b1}.asset-section-nav button.active small{color:#75939b}.asset-section-nav button>svg{box-sizing:content-box;padding:6px;border-radius:8px;color:#748791;background:#f2f6f7}.asset-section-nav button.active>svg{color:#fff;background:#348fa0;box-shadow:0 5px 12px rgba(52,143,160,.2)}.asset-section-nav i{min-width:18px;height:18px;padding:0 4px;display:grid;place-items:center;border-radius:9px;font:700 9px/1 ui-monospace;color:#fff;background:#e36f65}.asset-section-nav i.running-count{background:#24a987;animation:statePulse 2s infinite}.ops-pagination{display:flex;justify-content:flex-end;margin:10px 0 18px}
@media(max-width:760px){.asset-section-nav{grid-template-columns:1fr 1fr}.asset-section-nav small{display:none}}

/* 数据系统色彩校准：与学习中心共享品牌冷色，但使用青灰数据语义。 */
.brand>span{background:linear-gradient(145deg,#3b8da0,#287488);box-shadow:0 7px 17px rgba(42,119,137,.18)}
.back-home{color:#327f91;border-color:#d3e2e7;background:#f6fbfc}.back-home:hover{color:#fff;background:#358b9d;border-color:#358b9d}
.asset-command{
  border-color:#cfdee7;
  background:
    radial-gradient(circle at 82% 24%,rgba(53,166,183,.1),transparent 31%),
    linear-gradient(125deg,#fbfdfe,#eff7fa 58%,#eaf4f7);
  box-shadow:0 22px 52px rgba(36,75,96,.1);
}
.asset-command::before{
  background-image:
    linear-gradient(rgba(33,118,140,.055) 1px,transparent 1px),
    linear-gradient(90deg,rgba(33,118,140,.055) 1px,transparent 1px);
}
.asset-command::after{background:linear-gradient(90deg,transparent,#42aabd,transparent)}
.command-kicker{color:#238ca1}.command-copy h1{color:#19334b}.command-copy h1 em{color:#258da2}
.command-copy>p{color:#637788}.command-state{border-color:#d5e2e8;background:rgba(255,255,255,.72)}
.command-state strong{color:#385267}.command-state small{color:#8797a3}
.fabric-core{background:linear-gradient(145deg,#2c7184,#3193a6);box-shadow:0 0 0 11px rgba(48,145,163,.07),0 16px 31px rgba(31,102,118,.18)}
.fabric-line{background:linear-gradient(90deg,transparent,#8fbac5,#42aabd,#8fbac5,transparent)}
.fabric-line::after{background:linear-gradient(transparent,#9bc4cd,transparent)}
.fabric-node{border-color:#cfdee5;background:rgba(255,255,255,.86);box-shadow:0 9px 22px rgba(33,82,103,.08)}
.fabric-node>span{color:#278da2;background:#e3f2f5}.fabric-node strong{color:#385166}.fabric-node small{color:#8796a2}
.fabric-particle{background:#3cb4c5;box-shadow:0 0 10px #68cbd5}
.stat-pill,.stat-pill:nth-child(2),.stat-pill:nth-child(3),.stat-pill:nth-child(4),.stat-pill:nth-child(5){
  border-color:#dfe9ed;background:linear-gradient(145deg,#fff,#f4f9fa);box-shadow:0 8px 20px rgba(43,106,126,.055)
}
.stat-pill::before{content:"";position:absolute;left:0;top:14px;bottom:14px;width:3px;border-radius:0 2px 2px 0;background:#409caf}
.stat-pill::after{background:rgba(43,145,163,.05)}
.stat-pill:hover{border-color:#bcd7df;box-shadow:0 15px 30px rgba(43,106,126,.12)}
.stat-pill .num{color:#294d62}
.asset-section-nav button:hover{color:#287c8e;background:#f1f8f9}
.asset-section-nav button.active{
  color:#286f7e;
  background:linear-gradient(145deg,#fff,#eaf5f7);
  box-shadow:inset 0 0 0 1px #c5e0e5,0 5px 13px rgba(42,112,127,.08);
}
.asset-section-nav button.active small{color:#75939b}
.asset-section-nav button.active>svg{color:#fff;background:#348fa0}
.asset-section-nav i{background:#e36f65}

/* 审核/补全列表：整行反馈，链接保持应用内视觉而非浏览器默认样式。 */
.low-quality-list,.review-list{padding:14px;border:1px solid #e6ecef;border-radius:12px;background:#fbfcfd}
.review-list{margin-top:12px}.lq-item,.rv-item{position:relative;overflow:hidden;border:1px solid transparent}
.lq-item::before,.rv-item::before{content:"";position:absolute;left:0;top:8px;bottom:8px;width:3px;border-radius:0 3px 3px 0;background:#3a94a5;transform:scaleY(0);transition:transform .2s}
.lq-item:hover,.rv-item:hover{border-color:#d1e4e9;background:#f2f8fa;transform:translateX(4px);box-shadow:0 7px 16px rgba(41,102,120,.075)}
.lq-item:hover::before,.rv-item:hover::before{transform:scaleY(1)}
.rv-title-link,.rv-title-link:visited,.rv-title-link:hover,.rv-title-link:active{text-decoration:none!important}
.rv-title-link:hover{color:#257e91}
.rv-original{transition:transform .2s,background .2s,color .2s}
.rv-item:hover .rv-original{transform:translateX(2px);color:#247d8f;background:#e3f2f5}
.ops-pagination :deep(.el-pager li.is-active){background:#348b9d!important}

/* 区块通用 */
.ingest-section, .crawler-section, .timeline-section {
  background: var(--bg-card, #fff); border:1px solid var(--border-light); border-radius: 16px; padding: 22px;
  margin-bottom: 20px; box-shadow: var(--shadow-card);
}
.section-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px;
}
.section-head h3 {
  margin: 0; font-size: 16px; font-weight: 700; color: #1f2937;
  display: inline-flex; align-items: center; gap: 10px; letter-spacing: -0.2px;
}
.section-head h3 :deep(svg) {
  color: var(--accent); background: var(--accent-soft);
  padding: 6px; border-radius: 9px; box-sizing: content-box; flex-shrink: 0;
}
.tab-label { display: inline-flex; align-items: center; gap: 4px; }
.hint { font-size: 12px; color: var(--text-sub, #909399); }

/* 接入表单 */
.ingest-form { padding: 8px 0; }
.form-row { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
.form-tip { color: var(--text-sub, #909399); font-size: 13px; margin: 0 0 10px; }
.ingest-result {
  margin-top: 10px; padding: 8px 12px; border-radius: 6px;
  background: #f0f9eb; color: #67c23a; font-size: 13px;
}
.ingest-result.dup { background: #fdf6ec; color: #e6a23c; }
.upload-dragger { padding: 24px; color: var(--text-sub, #909399); text-align: center; }
.upload-icon { margin: 0 auto; }

/* 国内气象连接器：像数据采集站状态铭牌，强调可追溯性与安全边界 */
.connector-card {
  display: grid; grid-template-columns: 82px 1fr; gap: 18px;
  padding: 18px; margin-bottom: 16px;
  border: 1px solid #e4e7ed; border-radius: 12px;
  background: linear-gradient(135deg, #f8fafc 0%, #f3f7fb 100%);
}
.connector-card.ready {
  border-color: #b9decf;
  background: linear-gradient(135deg, #f7fcfa 0%, #edf8f4 100%);
}
.connector-marker {
  min-height: 82px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px;
  border-radius: 10px; color: #52606d; background: #e8eef5;
  font: 700 10px/1 ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: 1.2px;
}
.connector-card.ready .connector-marker { color: #0f766e; background: #d8f0e8; }
.connector-content { min-width: 0; }
.connector-title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.connector-eyebrow {
  margin-bottom: 3px; color: #64748b; font-size: 11px; font-weight: 650; letter-spacing: 0.08em;
}
.connector-title-row h4 { margin: 0; color: #1f2937; font-size: 17px; }
.connector-facts { display: flex; flex-wrap: wrap; gap: 8px 18px; margin-top: 10px; color: #334155; font-size: 12px; }
.connector-facts span { position: relative; }
.connector-facts span:not(:last-child)::after {
  content: ''; position: absolute; top: 5px; right: -10px; width: 3px; height: 3px; border-radius: 50%; background: #94a3b8;
}
.connector-note { margin-top: 8px; color: #64748b; font-size: 12px; line-height: 1.6; }
.connector-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.connector-test-result {
  display: flex; align-items: center; gap: 6px; margin-top: 10px; padding: 8px 10px;
  border-radius: 7px; color: #0f766e; background: rgba(16, 185, 129, 0.1); font-size: 12px;
}
.generic-api-divider {
  display: flex; align-items: center; gap: 10px; margin: 18px 0 12px; color: #94a3b8; font-size: 11px;
  letter-spacing: 0.08em;
}
.generic-api-divider::before, .generic-api-divider::after { content: ''; flex: 1; height: 1px; background: #e5e7eb; }

@media (max-width: 680px) {
  .connector-card { grid-template-columns: 1fr; }
  .connector-marker { min-height: 56px; flex-direction: row; }
}

/* 爬虫卡片 */
.ch-left { display: flex; align-items: center; gap: 12px; }
.crawler-running {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 12px; font-weight: 600; color: var(--accent);
  background: var(--accent-soft); padding: 3px 12px; border-radius: 20px;
}
.spin { animation: spin 1s linear infinite; transform-origin: center; }
@keyframes spin { to { transform: rotate(360deg); } }
.crawler-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px;
}
.crawler-card {
  border: 1px solid var(--border-light); border-radius: 12px;
  padding: 14px 16px; display: flex; align-items: center; justify-content: space-between;
  background: #fff; position: relative; overflow: hidden;
  transition: transform 0.22s cubic-bezier(0.22, 0.61, 0.36, 1), box-shadow 0.22s ease, border-color 0.22s ease;
}
.crawler-card::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: linear-gradient(180deg, #348fa0, #65b4c0);
  transform: scaleY(0); transform-origin: center; transition: transform 0.22s ease;
}
.crawler-card:hover { transform: translateY(-3px); border-color: #bcdce2; box-shadow: 0 10px 24px rgba(42, 121, 139, 0.11); }
.crawler-card:hover::before { transform: scaleY(1); }
/* 运行中：数据青脉冲 + 左色条常亮 */
.crawler-card.running { border-color: var(--accent); animation: crawlerRun 1.6s ease-out infinite; }
.crawler-card.running::before { transform: scaleY(1); }
.crawler-card.running .cc-icon { color: var(--accent); transform: scale(1.1); }
@keyframes crawlerRun {
  0% { box-shadow: 0 0 0 0 rgba(52, 143, 160, 0.3); }
  70% { box-shadow: 0 0 0 8px rgba(52, 143, 160, 0); }
  100% { box-shadow: 0 0 0 0 rgba(52, 143, 160, 0); }
}
.cc-main { display: flex; align-items: center; gap: 10px; }
.cc-icon { flex-shrink: 0; color: var(--accent); transition: transform 0.22s cubic-bezier(0.34, 1.56, 0.64, 1); }
.crawler-card:hover .cc-icon { transform: scale(1.14); }
.cc-name { font-weight: 600; font-size: 14px; }
.cc-desc { font-size: 12px; color: var(--text-sub, #909399); }
.crawler-log {
  margin-top: 12px; padding: 10px; background: var(--bg-page, #f5f7fa);
  border-radius: 6px; font-size: 12px; font-family: monospace;
}
.log-line { padding: 2px 0; color: #606266; }
.log-line.err { color: #f56c6c; }
.crawler-result-route {
  margin-top: 10px; padding: 12px 14px; border-radius: 10px;
  border: 1px solid #badde5; background: linear-gradient(100deg, #f4fbfc, #eef8ff);
  display: flex; align-items: center; justify-content: space-between; gap: 18px;
  font-family: inherit;
}
.crawler-result-route div { display: flex; flex-direction: column; gap: 3px; }
.crawler-result-route strong { color: #174f5d; font-size: 14px; }
.crawler-result-route span { color: #66818a; font-size: 12px; }

/* 时间线 */
.tl-filters { display: flex; gap: 8px; }
.timeline-section .section-head > div:first-child { min-width: 0; }
.timeline-section .section-head h3 em {
  margin-left: 6px; padding: 2px 7px; border-radius: 999px; background: #e7f5f8;
  color: #25879a; font-size: 11px; font-style: normal; vertical-align: 2px;
}
.timeline-note { margin: 5px 0 0; color: #7a9098; font-size: 12px; }
.timeline-list { max-height: 560px; overflow-y: auto; position: relative; padding: 4px 4px 4px 6px; }
.tl-group { position: relative; margin-bottom: 22px; padding-left: 24px; }
.tl-group::before {
  content: ''; position: absolute; left: 5px; top: 20px; bottom: -22px; width: 2px;
  background: linear-gradient(180deg, #cfe3e7, rgba(207, 227, 231, 0));
}
.tl-group:last-child::before { display: none; }
.tl-date {
  position: relative; font-size: 13px; font-weight: 700; color: #287f91;
  margin-bottom: 10px; letter-spacing: 0.2px;
}
.tl-date::before {
  content: ''; position: absolute; left: -24px; top: 2px; width: 10px; height: 10px;
  border-radius: 50%; background: #348fa0; box-shadow: 0 0 0 3px #dceef1;
}
.tl-item {
  padding: 10px 12px; font-size: 13px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  background: #fff; border: 1px solid #eef0f5; border-radius: 10px; margin-bottom: 8px;
  transition: transform 0.2s cubic-bezier(0.22, 0.61, 0.36, 1), box-shadow 0.2s ease, border-color 0.2s ease;
}
.tl-item:hover {
  border-color: #bfdce2; box-shadow: 0 6px 18px rgba(52, 143, 160, 0.1); transform: translateX(4px);
}
.tl-item.kind-structured_data {
  border-left: 3px solid #26a7bb;
  background: linear-gradient(90deg, rgba(231, 247, 250, 0.72), #fff 18%);
}
.tl-type {
  padding: 1px 6px; border-radius: 3px; font-size: 11px; color: #fff;
  background: #909399;
}
.tl-type.national_policy { background: #f56c6c; }
.tl-type.exchange_info { background: #e6a23c; }
.tl-type.industry_news { background: #409eff; }
.tl-type.regulation { background: #9c27b0; }
.tl-type.clearing { background: #4f63d9; }
.tl-type.load { background: #8b5cf6; }
.tl-type.weather_observation { background: #0ea5a4; }
.tl-type.weather_forecast_hourly { background: #1697d5; }
.tl-type.coal { background: #b7791f; }
.tl-type.carbon { background: #239365; }
.tl-type.southern_spot_weekly { background: #d65a86; }
.tl-type.green_certificate_weekly,
.tl-type.national_green_certificate { background: #42a66f; }
.tl-type.national_market_transaction,
.tl-type.national_market_transaction_ytd,
.tl-type.national_power_consumption,
.tl-type.national_power_statistics,
.tl-type.national_new_energy_projects,
.tl-type.nbs_energy_production { background: #2f7da3; }
.tl-ingest { color: var(--text-sub, #909399); font-size: 11px; }
.tl-prov {
  padding: 0 4px; border: 1px solid var(--border-light, #ebeef5);
  border-radius: 3px; font-size: 11px;
}
.tl-title { flex: 1; }
.tl-count {
  padding: 2px 7px; border-radius: 999px; background: #edf7f9; color: #287f91;
  font-size: 11px; white-space: nowrap;
}
.tl-provenance {
  padding: 2px 7px; border-radius: 999px; border: 1px solid #d7e0e5;
  color: #667780; background: #f7f9fa; font-size: 11px; white-space: nowrap;
}
.tl-provenance.observed_public,
.tl-provenance.observed_authorized { border-color: #a7dfca; color: #177a59; background: #ecfaf4; }
.tl-provenance.reconstructed { border-color: #efcf9b; color: #9a6415; background: #fff8e9; }
.tl-provenance.synthetic { border-color: #d5c8f5; color: #7351b4; background: #f7f2ff; }
.tl-summary { color: var(--text-sub, #909399); width: 100%; }
.tl-lineage { padding-left: 1px; color: #738993; }
.tl-src {
  display: inline-flex; align-items: center; gap: 3px;
  font-size: 12px; color: var(--accent); text-decoration: none;
  white-space: nowrap; padding: 2px 8px; border-radius: 6px;
  background: var(--accent-soft); transition: all 0.18s ease;
}
.tl-src:hover { background: #d8edf0; transform: translateY(-1px); }
.ai-tag { display: inline-block; font-size: 10px; font-weight: 700; color: #d97706; background: rgba(245, 158, 11, 0.14); padding: 0 5px; border-radius: 4px; margin-right: 5px; }
.empty { text-align: center; color: var(--text-sub, #909399); padding: 40px; }

@media (max-width: 760px) {
  .crawler-result-route, .timeline-section .section-head { align-items: stretch; flex-direction: column; }
  .tl-filters { width: 100%; }
  .tl-filters :deep(.el-select) { flex: 1; width: auto !important; }
}

/* 运维面板 */
.ops-section {
  background: var(--bg-card, #fff); border:1px solid var(--border-light); border-radius: 16px; padding: 22px;
  margin-bottom: 20px; box-shadow: var(--shadow-card);
}
.quality-grid { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.q-card {
  flex: 1; min-width: 110px; padding: 16px; border-radius: 8px; text-align: center;
  transition: transform 0.22s cubic-bezier(0.22, 0.61, 0.36, 1), box-shadow 0.22s ease;
}
.q-card:hover { transform: translateY(-3px); box-shadow: 0 10px 24px rgba(0, 0, 0, 0.07); }
.q-card .q-num { font-size: 28px; font-weight: 700; }
.q-card .q-lbl { font-size: 12px; margin-top: 4px; display: inline-flex; align-items: center; gap: 3px; justify-content: center; }
.q-high { background: #f0f9eb; color: #67c23a; }
.q-mid { background: #fdf6ec; color: #e6a23c; }
.q-low { background: #fef0f0; color: #f56c6c; }
.q-warn { background: #fef0f0; color: #f56c6c; }
.q-pending { background: #f4f4f5; color: #909399; }

.low-quality-list { margin-bottom: 16px; }
.lq-title, .rv-title { font-size: 13px; font-weight: 600; margin-bottom: 8px; color: var(--text-sub, #909399); display: inline-flex; align-items: center; gap: 4px; }
.rv-title { display: flex; justify-content: space-between; align-items: center; width: 100%; }
.rv-title > span { display: inline-flex; align-items: center; gap: 4px; }
.lq-item, .rv-item {
  display: flex; align-items: center; gap: 8px; padding: 9px 12px;
  background: var(--bg-page, #f5f7fa); border-radius: 8px; margin-bottom: 5px; font-size: 13px;
  transition: transform 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
}
.lq-item { cursor: pointer; }
.lq-item:hover { background: #eef7f9; transform: translateX(4px); box-shadow: 0 4px 14px rgba(52, 143, 160, 0.1); }
.rv-item:hover { background: #eef7f9; }
.lq-score { font-weight: 600; color: #f56c6c; min-width: 50px; }
.lq-name { flex: 1; }
.lq-missing { color: var(--text-sub, #909399); font-size: 12px; }
.rv-type {
  font-size: 11px; padding: 1px 6px; border-radius: 3px; color: #fff; background: #909399;
}
.rv-title-text { flex: 1; font-size: 13px; }
.rv-title-link {
  color: var(--text-main, #303133); text-decoration: none;
  min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rv-title-link:hover { color: #287f91; text-decoration: none; }
.rv-date { color: #606266; font-size: 11px; white-space: nowrap; font-variant-numeric: tabular-nums; }
.rv-source { color: var(--text-sub, #909399); font-size: 11px; }
.rv-original {
  display: inline-flex; align-items: center; gap: 3px; white-space: nowrap;
  color: #287f91; text-decoration: none; font-size: 12px; font-weight: 600;
  padding: 5px 8px; border-radius: 6px; background: #e7f4f6;
}
.rv-original:hover { background: #d9edf1; }

/* 资产指标是只读遥测带，不使用可点击卡片反馈。 */
.stats-bar {
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0;
  min-height: 86px;
  padding: 0 13px;
  border: 1px solid #dce8eb;
  border-radius: 16px;
  background: rgba(255,255,255,.82);
  box-shadow: 0 9px 25px rgba(39,95,111,.055);
  overflow: hidden;
}
.stat-pill,
.stat-pill:nth-child(2),
.stat-pill:nth-child(3),
.stat-pill:nth-child(4),
.stat-pill:nth-child(5) {
  min-width: 0;
  min-height: 86px;
  padding: 16px 21px;
  justify-content: center;
  border: 0;
  border-right: 1px solid #e7eef0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  cursor: default;
  overflow: visible;
  transition: none;
}
.stat-pill:last-child { border-right: 0; }
.stat-pill::before {
  left: 21px;
  right: calc(100% - 58px);
  top: auto;
  bottom: 11px;
  width: auto;
  height: 2px;
  border-radius: 2px;
  background: #55a4b3;
}
.stat-pill::after { display: none; }
.stat-pill:hover {
  transform: none;
  border-color: #e7eef0;
  box-shadow: none;
}
.stat-pill .num { color: #294d62; font-size: 25px; }
.stat-pill .lbl { color: #85959e; }

/* 工作区是唯一的可点击导航层。 */
.asset-section-nav { margin-top: 14px; }
.asset-section-nav button { cursor: pointer; }

/* 质量等级共享青灰表面，仅用细状态线与数字颜色表达语义。 */
.quality-grid { gap: 10px; }
.q-card {
  --quality-tone: #5f8c98;
  position: relative;
  min-height: 104px;
  padding: 19px 14px 15px;
  border: 1px solid #dfe9eb;
  border-radius: 12px;
  color: #657983;
  background: linear-gradient(180deg,#fbfdfd,#f5f9fa);
  box-shadow: inset 0 3px 0 var(--quality-tone);
  cursor: default;
  overflow: hidden;
  transition: none;
}
.q-card::after {
  content: "";
  position: absolute;
  width: 72px;
  height: 72px;
  right: -36px;
  bottom: -42px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--quality-tone) 8%, transparent);
}
.q-card:hover { transform: none; box-shadow: inset 0 3px 0 var(--quality-tone); }
.q-card .q-num { color: var(--quality-tone); font-size: 27px; }
.q-card .q-lbl { color: #7e8f97; }
.q-high { --quality-tone: #3b947c; }
.q-mid { --quality-tone: #a48345; }
.q-low { --quality-tone: #b46868; }
.q-warn { --quality-tone: #b46b60; }
.q-pending { --quality-tone: #718892; }
@media(max-width:900px){
  .stats-bar{grid-template-columns:repeat(2,1fr)}
  .stat-pill:nth-child(2n){border-right:0}
}
@media(max-width:620px){
  .stats-bar{grid-template-columns:1fr 1fr}
  .stat-pill{padding-inline:15px}
  .stat-pill::before{left:15px;right:calc(100% - 47px)}
}

/* 2026 数据中枢视觉：高明度电气蓝，不再使用灰蒙青灰后台感。 */
.asset-page {
  background:
    radial-gradient(circle at 8% 5%, rgba(31, 132, 220, .11), transparent 28rem),
    radial-gradient(circle at 94% 22%, rgba(15, 190, 199, .08), transparent 25rem),
    linear-gradient(180deg, #f7fbff 0, #f1f8ff 520px, #f6faff 100%);
}
.asset-header {
  height: 68px;
  border-bottom-color: rgba(183, 211, 235, .72);
  box-shadow: 0 7px 24px rgba(31, 91, 145, .07);
}
.brand>span {
  background: linear-gradient(145deg, #2387dc, #1266bd 58%, #08a6b5);
  box-shadow: 0 8px 20px rgba(25, 118, 210, .25);
}
.back-home {
  margin-left:auto;
  color:#fff;
  border-color:#1976d2;
  background:#1976d2;
  box-shadow:0 7px 17px rgba(25,118,210,.2);
}
.back-home:hover { background:#125fae;border-color:#125fae;transform:translateY(-1px) }
.asset-command {
  border-color: #c5def1;
  background:
    radial-gradient(circle at 78% 26%, rgba(14, 178, 193, .18), transparent 33%),
    radial-gradient(circle at 12% 10%, rgba(38, 135, 221, .12), transparent 35%),
    linear-gradient(126deg, #ffffff, #edf7ff 57%, #e4f7fb);
  box-shadow: 0 24px 58px rgba(32, 103, 164, .13);
}
.asset-command::before {
  background-image:
    linear-gradient(rgba(25,118,210,.065) 1px,transparent 1px),
    linear-gradient(90deg,rgba(25,118,210,.065) 1px,transparent 1px);
}
.asset-command::after { background: linear-gradient(90deg,transparent,#239de0,#14c5c7,transparent); }
.command-kicker { color: #1678c8; }
.command-copy h1 { color: #112f4d; }
.command-copy h1 em { color: #147aca; }
.command-copy>p { color: #56728a; }
.command-state { border-color: #cfe3f2; background: rgba(255,255,255,.88); }
.command-state strong { color: #254b6e; }
.fabric-core {
  background: linear-gradient(145deg,#147bd0,#1472c5 56%,#0aa9b2);
  box-shadow: 0 0 0 12px rgba(32,135,215,.08),0 18px 38px rgba(27,105,174,.23);
}
.fabric-node { border-color: #c8dfee; background: rgba(255,255,255,.94); }
.fabric-node>span { color: #147acb; background: #e8f4ff; }
.fabric-line { background: linear-gradient(90deg,transparent,#8fc4e7,#1e8ed8,#16bbc3,#8fc4e7,transparent); }
.fabric-particle { background:#19b8c6;box-shadow:0 0 12px #30cbd4; }

.stats-bar {
  border-color: #cee2f2;
  background: rgba(255,255,255,.94);
  box-shadow: 0 12px 32px rgba(35,104,162,.09);
}
.stat-pill { border-right-color:#e1edf6; }
.stat-pill::before { background: linear-gradient(90deg,#1976d2,#18b8c0); }
.stat-pill .num { color:#173f67; font-size:28px; }
.stat-pill .lbl { color:#667f96; font-size:12px; font-weight:650; }

.asset-section-nav {
  gap: 10px;
  padding: 9px;
  border-color: #cfE2f1;
  background: rgba(255,255,255,.94);
  box-shadow: 0 12px 32px rgba(35,104,162,.08);
}
.asset-section-nav button {
  min-height: 76px;
  padding: 12px 14px;
  border: 1px solid transparent;
}
.asset-section-nav button:hover {
  color:#166eb8;
  border-color:#d9e9f6;
  background:#f2f8ff;
  transform:translateY(-2px);
  box-shadow:0 8px 20px rgba(36,104,164,.08);
}
.asset-section-nav button.active {
  color:#135f9f;
  border-color:#bcd9ee;
  background:linear-gradient(145deg,#fff,#e9f5ff);
  box-shadow:0 8px 22px rgba(31,112,180,.12);
}
.asset-section-nav strong { font-size:14px; letter-spacing:-.01em; }
.asset-section-nav small { margin-top:4px; font-size:11px; line-height:1.35; color:#8296a9; }
.asset-section-nav button>svg {
  width:20px;
  height:20px;
  padding:9px;
  color:#44718f;
  background:#edf5fb;
}
.asset-section-nav button.active>svg {
  color:#fff;
  background:linear-gradient(145deg,#2388dc,#1570c4);
  box-shadow:0 7px 16px rgba(25,118,210,.24);
}

.ops-section,.ingest-section,.crawler-section,.timeline-section {
  border-color:#d9e8f3;
  box-shadow:0 12px 34px rgba(37,94,143,.075);
}
.section-head h3 { color:#173652; font-size:18px; }
.quality-grid { gap:12px; }
.q-card {
  min-height:110px;
  border-color:#dce9f3;
  background:linear-gradient(180deg,#fff,#f7fbff);
  box-shadow:inset 0 3px 0 var(--quality-tone),0 7px 19px rgba(35,95,145,.055);
}
.q-card:hover { box-shadow:inset 0 3px 0 var(--quality-tone),0 7px 19px rgba(35,95,145,.055); }
.q-card .q-lbl { color:#647b91; font-size:12px; font-weight:650; }
.q-high { --quality-tone:#1689c7; }
.q-mid { --quality-tone:#4d7ed2; }
.q-low { --quality-tone:#796fc4; }
.q-warn { --quality-tone:#d07948; }
.q-pending { --quality-tone:#5a7894; }

/* 队列标题承担分类职责：修复（暖金）与准入（数据蓝）明确分区。 */
.low-quality-list,.review-list{
  padding:0 14px 14px;
  overflow:hidden;
  border-color:#dce8f2;
  background:#fff;
}
.lq-title,.rv-title{
  min-height:70px;
  margin:0 -14px 12px;
  padding:12px 16px;
  display:flex;
  align-items:center;
  gap:11px;
}
.lq-title{
  color:#765122;
  border-bottom:1px solid #f0dec2;
  background:linear-gradient(90deg,#fff8ec,#fffcf7 68%,#fff);
}
.rv-title{
  color:#215a91;
  border-bottom:1px solid #d8e8f6;
  background:linear-gradient(90deg,#edf7ff,#f7fbff 68%,#fff);
}
.review-heading{display:flex;align-items:center;gap:11px;flex:1;min-width:0}
.queue-icon{
  width:38px;height:38px;display:grid;place-items:center;flex:none;border-radius:11px;
  color:#b77822;background:#fff0d6;box-shadow:inset 0 0 0 1px #f1d7ad;
}
.rv-title .queue-icon{color:#1976d2;background:#dfefff;box-shadow:inset 0 0 0 1px #c8e1f7}
.queue-copy{display:flex;flex-direction:column;gap:4px;min-width:0}
.queue-copy strong{font-size:14px;letter-spacing:-.01em}
.queue-copy small{color:#8c7d69;font-size:10px;font-weight:500}
.rv-title .queue-copy small{color:#7189a0}
.queue-count{
  margin-left:auto;padding:4px 9px;border-radius:12px;white-space:nowrap;
  color:#9a641c;background:rgba(255,255,255,.75);font-size:10px;font-weight:750;
}
.rv-title .queue-count{color:#176eb8;background:#fff}
.rv-title>.el-button{margin-left:10px}

/* 清理旧青灰硬编码，关键操作统一为数据资产电气蓝。 */
.rv-original{color:#176fbe;background:#e8f4ff}
.rv-original:hover,.rv-item:hover .rv-original{color:#fff;background:#1976d2}
.rv-title-link:hover{color:#176fbe}
.ops-pagination :deep(.el-pager li.is-active){background:#1976d2!important}
.ops-pagination :deep(.el-pager li:hover){color:#1976d2}
.tl-src{color:#176fbe;background:#e8f4ff}
.tl-src:hover{color:#fff;background:#1976d2}
.lq-item::before,.rv-item::before{background:#1976d2}
.lq-item:hover,.rv-item:hover{
  border-color:#d1e4f3;
  background:#f2f8ff;
  box-shadow:0 7px 16px rgba(31,101,163,.08);
}

@media(prefers-reduced-motion:reduce){
  .asset-section-nav button{transition:none}
}
</style>
