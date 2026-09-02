<template>
  <div class="kb-list" v-loading="loading">
    <!-- 数据资产统计看板 -->
    <section class="asset-stats" v-if="stats">
      <div class="stats-head">
        <h3><ChartBar :size="18" /> 数据资产总览</h3>
        <span class="total-badge">共 {{ stats.total }} 篇</span>
      </div>
      <div class="stats-row">
        <div class="stat-mini" v-for="i in stats.by_ingest" :key="i.key">
          <component :is="ingestIconComp(i.key)" class="mini-icon" :size="16" />
          <span class="mini-label">{{ ingestLabel(i.key) }}</span>
          <span class="mini-num">{{ i.count }}</span>
        </div>
        <div class="stat-mini" v-for="t in stats.by_type" :key="t.key">
          <span class="mini-label">{{ typeLabel(t.key) }}</span>
          <span class="mini-num">{{ t.count }}</span>
        </div>
      </div>
    </section>

    <!-- 多源接入面板 -->
    <section class="ingest-panel">
      <div class="ingest-tabs">
        <span class="ingest-tab" :class="{active: ingestMode==='curl'}" @click="ingestMode='curl'"><Link :size="14" /> cURL抓取</span>
        <span class="ingest-tab" :class="{active: ingestMode==='upload'}" @click="ingestMode='upload'"><Paperclip :size="14" /> 上传文件</span>
        <span class="ingest-tab" :class="{active: ingestMode==='manual'}" @click="ingestMode='manual'"><PenTool :size="14" /> 手动录入</span>
        <span class="ingest-tab" :class="{active: ingestMode==='crawler'}" @click="ingestMode='crawler'"><Bug :size="14" /> 触发爬虫</span>
      </div>

      <!-- cURL抓取 -->
      <div v-if="ingestMode==='curl'" class="ingest-form">
        <el-input v-model="curlForm.curl" type="textarea" :rows="3"
          placeholder="粘贴curl命令，如：curl https://www.ndrc.gov.cn/xxgk/zcfb/tz/..." />
        <div class="form-row">
          <el-select v-model="curlForm.doc_type" size="small" style="width:140px">
            <el-option v-for="(label,key) in typeOptions" :key="key" :label="label" :value="key" />
          </el-select>
          <el-input v-model="curlForm.province" size="small" placeholder="省份(可选)" style="width:120px" />
          <el-button type="primary" size="small" :loading="ingesting" @click="doCurl">抓取并沉淀</el-button>
        </div>
      </div>

      <!-- 上传文件 -->
      <div v-if="ingestMode==='upload'" class="ingest-form">
        <el-upload
          :http-request="doUpload" :show-file-list="false"
          accept=".pdf,.doc,.docx,.xlsx,.txt"
          drag
        >
          <div class="upload-area">
            <Paperclip class="upload-icon" :size="32" />
            <p>点击或拖拽文件上传（PDF/Word/Excel）</p>
          </div>
        </el-upload>
      </div>

      <!-- 手动录入 -->
      <div v-if="ingestMode==='manual'" class="ingest-form">
        <el-input v-model="manualForm.title" placeholder="标题" size="small" style="margin-bottom:8px" />
        <el-input v-model="manualForm.content" type="textarea" :rows="4" placeholder="正文内容..." />
        <div class="form-row">
          <el-select v-model="manualForm.doc_type" size="small" style="width:140px">
            <el-option v-for="(label,key) in typeOptions" :key="key" :label="label" :value="key" />
          </el-select>
          <el-input v-model="manualForm.province" size="small" placeholder="省份" style="width:120px" />
          <el-button type="primary" size="small" :loading="ingesting" @click="doManual">录入并AI总结</el-button>
        </div>
      </div>

      <!-- 触发爬虫 -->
      <div v-if="ingestMode==='crawler'" class="ingest-form">
        <p class="crawler-hint">手动触发不同类型的爬虫，立即采集最新数据</p>
        <div class="crawler-btns">
          <el-button @click="runCrawler('policy')" :loading="crawlerLoading==='policy'"><ScrollText :size="14" /> 政策法规</el-button>
          <el-button @click="runCrawler('exam')" :loading="crawlerLoading==='exam'"><PenLine :size="14" /> 考题真题</el-button>
          <el-button @click="runCrawler('trade_data')" :loading="crawlerLoading==='trade_data'"><TrendingUp :size="14" /> 交易数据</el-button>
          <el-button @click="runCrawler('news')" :loading="crawlerLoading==='news'"><Newspaper :size="14" /> 行业新闻</el-button>
          <el-button type="primary" @click="runCrawler('all')" :loading="crawlerLoading==='all'">全部采集</el-button>
        </div>
      </div>
    </section>

    <!-- 搜索栏 -->
    <div class="search-bar">
      <el-input v-model="searchQ" placeholder="全文搜索数据资产..." size="large" clearable
        @keyup.enter="doSearch" @clear="doSearch">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button type="primary" size="large" @click="doSearch">搜索</el-button>
    </div>

    <!-- 筛选 -->
    <div class="filter-panel">
      <div class="filter-row">
        <span class="filter-label">类型</span>
        <span class="filter-tag" :class="{active:!filter.docType}" @click="setFilter('docType','')">全部</span>
        <span v-for="t in facets.doc_types" :key="t.key" class="filter-tag"
          :class="{active:filter.docType===t.key}" @click="setFilter('docType',t.key)">
          {{ typeLabel(t.key) }} ({{ t.count }})
        </span>
      </div>
      <div class="filter-row" v-if="facets.provinces?.length">
        <span class="filter-label">省份</span>
        <span class="filter-tag" :class="{active:!filter.province}" @click="setFilter('province','')">全部</span>
        <span v-for="p in facets.provinces" :key="p.key" class="filter-tag"
          :class="{active:filter.province===p.key}" @click="setFilter('province',p.key)">
          {{ p.key }} ({{ p.count }})
        </span>
      </div>
    </div>

    <!-- 文档列表 -->
    <div class="doc-list">
      <div v-for="doc in docs" :key="doc.id" class="doc-card" @click="openDoc(doc)">
        <div class="doc-header">
          <span class="doc-type-tag" :class="doc.doc_type">{{ typeLabel(doc.doc_type) }}</span>
          <span v-if="doc.province" class="doc-prov"><MapPin :size="12" /> {{ doc.province }}</span>
          <span class="doc-ingest"><component :is="ingestIconComp(doc.ingest_type)" :size="12" /> {{ ingestLabel(doc.ingest_type) }}</span>
          <span v-if="doc.is_starred" class="doc-star"><Star :size="14" /></span>
          <span class="doc-date">{{ doc.publish_date }}</span>
        </div>
        <div class="doc-title">{{ doc.title }}</div>
        <div class="doc-summary" v-if="doc.ai_summary"><Bot :size="13" /> {{ doc.ai_summary }}</div>
        <div class="doc-tags" v-if="doc.tags?.length">
          <span v-for="t in doc.tags" :key="t" class="doc-tag">{{ t }}</span>
        </div>
        <div class="doc-source">{{ doc.source }}</div>
      </div>
      <div v-if="!docs.length && !loading" class="empty">暂无数据，使用上方面板接入数据</div>
    </div>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" size="520px" :title="current?.title" direction="rtl">
      <div v-if="current" class="doc-detail">
        <div class="detail-meta">
          <el-tag size="small">{{ typeLabel(current.doc_type) }}</el-tag>
          <span>{{ current.publish_date }}</span>
          <span v-if="current.province">{{ current.province }}</span>
        </div>
        <div v-if="current.ai_summary" class="detail-section"><h4><Bot :size="15" /> AI 摘要</h4><p>{{ current.ai_summary }}</p></div>
        <div class="detail-section"><h4><FileText :size="15" /> 正文</h4><p>{{ current.content }}</p></div>
        <div v-if="current.ai_keywords?.length" class="detail-section">
          <h4><Tag :size="15" /> 关键词</h4><div><span v-for="k in current.ai_keywords" :key="k" class="kw">{{ k }}</span></div>
        </div>
        <div class="detail-actions">
          <el-button size="small" @click="toggleStar"><Star :size="14" /> {{ current.is_starred ? '取消收藏' : '收藏' }}</el-button>
          <a v-if="current.source_url" :href="current.source_url" target="_blank">
            <el-button size="small" type="primary" plain>原文 ↗</el-button>
          </a>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import {
  ChartBar, Link, Paperclip, PenTool, PenLine, Bug, Star, MapPin, Bot,
  FileText, ScrollText, TrendingUp, Newspaper, Inbox, Tag, BookOpen,
} from 'lucide-vue-next'
import { knowledgeApi, assetApi } from '../../api'

const loading = ref(false)
const ingesting = ref(false)
const crawlerLoading = ref('')
const docs = ref([])
const facets = ref({})
const stats = ref(null)
const searchQ = ref('')
const filter = reactive({ docType: '', province: '' })
const detailVisible = ref(false)
const current = ref(null)
const ingestMode = ref('curl')

const typeOptions = {
  national_policy: '国家政策', regulation: '监管规则', exchange_info: '交易中心',
  industry_news: '行业资讯', exam_info: '考试信息',
}
const typeLabel = (t) => typeOptions[t] || t
// 映射 ingest_type → lucide 组件，供模板用 <component :is> 渲染
const ingestIconComp = (k) => ({
  feishu: BookOpen, crawler: Bug, upload: Paperclip, curl: Link, manual: PenTool,
}[k] || FileText)
const ingestLabel = (k) => ({ feishu: '飞书', crawler: '爬虫', upload: '上传', curl: 'cURL', manual: '录入' }[k] || k)

const curlForm = reactive({ curl: '', doc_type: 'national_policy', province: '' })
const manualForm = reactive({ title: '', content: '', doc_type: 'industry_news', province: '' })

const loadAll = async () => {
  loading.value = true
  try {
    const [s, f] = await Promise.all([assetApi.stats(), knowledgeApi.facets()])
    stats.value = s
    facets.value = f
    await loadDocs()
  } catch (e) { ElMessage.error(e.message) }
  finally { loading.value = false }
}

const loadDocs = async () => {
  const params = {}
  if (searchQ.value) params.q = searchQ.value
  if (filter.docType) params.doc_type = filter.docType
  if (filter.province) params.province = filter.province
  const data = await knowledgeApi.docs(params)
  docs.value = data.items
}

const doSearch = () => loadDocs()
const setFilter = (k, v) => { filter[k] = v; loadDocs() }

// cURL抓取
const doCurl = async () => {
  if (!curlForm.curl) { ElMessage.warning('请粘贴curl命令'); return }
  ingesting.value = true
  try {
    const res = await assetApi.ingestCurl({
      curl: curlForm.curl, doc_type: curlForm.doc_type,
      province: curlForm.province || null,
    })
    ElMessage.success(`抓取成功：${res.title?.slice(0, 20)}...`)
    curlForm.curl = ''
    loadAll()
  } catch (e) { ElMessage.error(e.message) }
  finally { ingesting.value = false }
}

// 上传
const doUpload = async (option) => {
  const formData = new FormData()
  formData.append('file', option.file)
  formData.append('doc_type', 'industry_news')
  ingesting.value = true
  try {
    await assetApi.uploadFile(formData)
    ElMessage.success('上传成功')
    loadAll()
  } catch (e) { ElMessage.error(e.message) }
  finally { ingesting.value = false }
}

// 手动录入
const doManual = async () => {
  if (!manualForm.title || !manualForm.content) { ElMessage.warning('请填写标题和内容'); return }
  ingesting.value = true
  try {
    await assetApi.ingestManual({
      title: manualForm.title, content: manualForm.content,
      doc_type: manualForm.doc_type, province: manualForm.province || null,
    })
    ElMessage.success('录入成功，AI已自动总结')
    manualForm.title = ''; manualForm.content = ''
    loadAll()
  } catch (e) { ElMessage.error(e.message) }
  finally { ingesting.value = false }
}

// 爬虫
const runCrawler = async (type) => {
  crawlerLoading.value = type
  try {
    await assetApi.runCrawler(type)
    ElMessage.success(`${type} 爬虫执行完成`)
    loadAll()
  } catch (e) { ElMessage.error(e.message) }
  finally { crawlerLoading.value = '' }
}

// 详情
const openDoc = async (doc) => {
  try {
    current.value = await knowledgeApi.docDetail(doc.id)
    detailVisible.value = true
  } catch (e) { ElMessage.error(e.message) }
}
const toggleStar = async () => {
  try {
    const res = await knowledgeApi.toggleStar(current.value.id)
    current.value.is_starred = res.starred
    loadDocs()
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(loadAll)
</script>

<style scoped>
.asset-stats { background: var(--bg-card); border-radius: var(--radius); padding: 18px 20px; box-shadow: var(--shadow-card); margin-bottom: 16px; }
.stats-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.stats-head h3 { font-size: 16px; display: inline-flex; align-items: center; gap: 6px; }
.total-badge { font-size: 13px; padding: 2px 10px; border-radius: 10px; background: var(--accent-soft); color: var(--accent); }
.stats-row { display: flex; gap: 16px; flex-wrap: wrap; }
.stat-mini { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.mini-icon { flex-shrink: 0; }
.mini-label { color: var(--text-secondary); }
.mini-num { font-weight: 700; color: var(--accent); }

.ingest-panel { background: var(--bg-card); border-radius: var(--radius); padding: 16px 20px; box-shadow: var(--shadow-card); margin-bottom: 16px; }
.ingest-tabs { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
.ingest-tab { font-size: 13px; padding: 6px 14px; border-radius: 16px; background: var(--bg-hover); color: var(--text-secondary); cursor: pointer; transition: all 0.15s; display: inline-flex; align-items: center; gap: 4px; }
.ingest-tab:hover { color: var(--accent); }
.ingest-tab.active { background: var(--accent); color: #fff; }
.ingest-form { }
.form-row { display: flex; gap: 8px; align-items: center; margin-top: 10px; }
.upload-area { text-align: center; padding: 20px; }
.upload-icon { margin: 0 auto; }
.upload-area p { font-size: 13px; color: var(--text-secondary); margin-top: 8px; }
.crawler-hint { font-size: 13px; color: var(--text-secondary); margin-bottom: 12px; }
.crawler-btns { display: flex; gap: 10px; flex-wrap: wrap; }

.search-bar { display: flex; gap: 12px; margin-bottom: 16px; }
.filter-panel { background: var(--bg-card); border-radius: var(--radius); padding: 14px 20px; box-shadow: var(--shadow-card); margin-bottom: 16px; }
.filter-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 4px 0; }
.filter-label { font-size: 12px; color: var(--text-secondary); min-width: 36px; }
.filter-tag { font-size: 12px; padding: 3px 10px; border-radius: 12px; background: var(--bg-hover); color: var(--text-secondary); cursor: pointer; }
.filter-tag:hover { color: var(--accent); }
.filter-tag.active { background: var(--accent); color: #fff; }

.doc-list { display: flex; flex-direction: column; gap: 10px; }
.doc-card { background: var(--bg-card); border-radius: var(--radius); padding: 16px 18px; box-shadow: var(--shadow-card); cursor: pointer; transition: all 0.15s; border-left: 4px solid var(--border-color); }
.doc-card:hover { border-left-color: var(--accent); transform: translateX(4px); }
.doc-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 12px; flex-wrap: wrap; }
.doc-type-tag { padding: 2px 8px; border-radius: 8px; font-size: 11px; }
.doc-type-tag.national_policy { background: #fff0f5; color: #e74c8b; }
.doc-type-tag.regulation { background: #fff5e6; color: #ff9500; }
.doc-type-tag.exchange_info { background: #e8f0ff; color: #2f6bff; }
.doc-type-tag.industry_news { background: #e6fff5; color: #00a870; }
.doc-prov { color: var(--text-secondary); display: inline-flex; align-items: center; gap: 2px; }
.doc-ingest { color: var(--text-tertiary); font-size: 11px; display: inline-flex; align-items: center; gap: 2px; }
.doc-star { color: var(--accent-orange); }
.doc-date { margin-left: auto; color: var(--text-tertiary); }
.doc-title { font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.doc-summary { font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 6px; display: flex; align-items: flex-start; gap: 4px; }
.doc-tags { display: flex; gap: 6px; margin-bottom: 4px; }
.doc-tag { font-size: 11px; padding: 1px 6px; border-radius: 6px; background: var(--bg-hover); color: var(--text-tertiary); }
.doc-source { font-size: 12px; color: var(--text-tertiary); }
.empty { text-align: center; padding: 60px; color: var(--text-tertiary); }

.doc-detail { padding: 0 8px; }
.detail-meta { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; font-size: 13px; color: var(--text-secondary); }
.detail-section { margin-bottom: 20px; }
.detail-section h4 { font-size: 14px; color: var(--accent); margin-bottom: 8px; display: inline-flex; align-items: center; gap: 5px; }
.detail-section p { font-size: 13px; line-height: 1.8; color: var(--text-primary); }
.kw { display: inline-block; font-size: 12px; padding: 2px 8px; border-radius: 6px; background: var(--bg-hover); color: var(--text-secondary); margin: 0 4px 4px 0; }
.detail-actions { display: flex; gap: 12px; padding-top: 16px; border-top: 1px solid var(--border-light); }
</style>
