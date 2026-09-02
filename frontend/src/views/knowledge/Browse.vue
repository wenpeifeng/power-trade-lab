<template>
  <div class="browse">
    <!-- 左栏：分类树 -->
    <aside class="cat-sidebar">
      <div class="sidebar-head">
        <span><FolderTree :size="14" /> 分类导航</span>
      </div>
      <el-input
        v-model="treeFilter" placeholder="搜索分类..." size="small" clearable
        class="tree-filter"
      />
      <el-tree
        ref="treeRef"
        :data="treeData" :props="treeProps"
        node-key="code"
        :filter-node-method="filterNode"
        :expand-on-click-node="false"
        :default-expand-all="false"
        :default-expanded-keys="['0','1','2','3']"
        @node-click="onCategoryClick"
        class="cat-tree"
      >
        <template #default="{ node, data }">
          <span class="tree-node">
            <FileText class="tn-icon" :size="14" />
            <span class="tn-label">{{ data.name }}</span>
            <span v-if="data.doc_count" class="tn-count">{{ data.doc_count }}</span>
          </span>
        </template>
      </el-tree>
    </aside>

    <!-- 主区 -->
    <main class="content-main">
      <section class="knowledge-radar">
        <div class="radar-copy">
          <span class="radar-kicker"><Sparkles :size="14" /> KNOWLEDGE SIGNAL</span>
          <h1>从可信原文中，<br><em>找到能回答业务的问题</em></h1>
          <p>政策、规则、市场公告与学习资料在同一套索引中关联。搜索结果保留来源、发布日期与原文路径。</p>
        </div>
        <div class="radar-visual" aria-hidden="true">
          <div class="radar-ring ring-one"></div>
          <div class="radar-ring ring-two"></div>
          <div class="radar-sweep"></div>
          <span class="radar-point point-a"></span>
          <span class="radar-point point-b"></span>
          <span class="radar-point point-c"></span>
          <div class="radar-core"><BookOpen :size="22" /><strong>{{ resultTotal }}</strong><small>当前索引</small></div>
          <span class="radar-label label-source"><FileText :size="13" /> 可信原文</span>
          <span class="radar-label label-ai"><Bot :size="13" /> AI关联</span>
        </div>
      </section>

      <!-- 顶部：搜索 + 模式切换 -->
      <div class="content-topbar">
        <el-input
          v-model="searchQuery" placeholder="搜索知识库（标题/正文/AI摘要）"
          class="search-input" clearable size="default"
          @keyup.enter="doSearch"
        />
        <el-button type="primary" class="search-btn" :loading="searching" @click="doSearch"><Search :size="14" /> 搜索</el-button>
        <div class="mode-tabs">
          <button class="mode-tab" :class="{active: searchMode==='keyword'}" @click="switchMode('keyword')">关键词</button>
          <button class="mode-tab" :class="{active: searchMode==='hybrid'}" @click="switchMode('hybrid')">混合检索</button>
          <button class="mode-tab" :class="{active: searchMode==='dense'}" @click="switchMode('dense')">{{ denseTabLabel }}</button>
          <button class="mode-tab" :class="{active: searchMode==='sparse'}" @click="switchMode('sparse')">BM25</button>
        </div>
      </div>
      <!-- 检索引擎诚实标注：语义模型在线时显示模型名，否则标明是词频匹配 -->
      <div class="engine-status" v-if="engineStatus">
        检索引擎：{{ engineStatus }}
      </div>

      <!-- 面包屑 -->
      <div class="breadcrumb" v-if="currentPath.length || kpFilter">
        <span class="bc-item" @click="goRoot">全部</span>
        <template v-for="p in currentPath" :key="p.code">
          <span class="bc-sep">/</span>
          <span class="bc-item" :class="{last: p===currentPath[currentPath.length-1] && !kpFilter}">{{ p.name }}</span>
        </template>
        <span class="bc-count">（{{ resultTotal }} 篇）</span>
        <span v-if="kpFilter" class="bc-facet bc-kp">知识点: {{ kpName }}
          <span class="bc-clear" @click="clearKp">✕</span>
        </span>
        <span v-if="activeFacet" class="bc-facet">× {{ activeFacet.facet }}: {{ activeFacet.value }}
          <span class="bc-clear" @click="clearFacet">✕</span>
        </span>
      </div>

      <!-- 多维标签筛选条 -->
      <div class="facet-bar" v-if="facetDimensions.length && !activeSearch">
        <div class="facet-group" :class="`facet-${fd.key}`" v-for="fd in facetDimensions" :key="fd.key">
          <span class="facet-label">{{ fd.label }}:</span>
          <span
            v-for="v in fd.values" :key="v"
            class="facet-tag"
            :class="{active: activeFacet && activeFacet.facet===fd.key && activeFacet.value===v}"
            @click="onFacetClick(fd.key, v)"
          >{{ v }}</span>
        </div>
      </div>

      <!-- 文档列表 -->
      <div class="doc-list" v-loading="loading">
        <div
          v-for="doc in docs" :key="doc.id"
          class="doc-card"
          @click="openDetail(doc)"
        >
          <div class="doc-card-head">
            <span class="doc-type-badge" :class="doc.doc_type">{{ typeLabel(doc.doc_type) }}</span>
            <span class="doc-title">{{ doc.title }}</span>
            <span v-if="doc.is_starred" class="doc-star"><Star :size="14" /></span>
          </div>
          <div class="doc-card-meta">
            <span v-if="doc.province" class="meta-item"><MapPin :size="12" /> {{ doc.province }}</span>
            <span v-if="doc.publish_date" class="meta-item"><Calendar :size="12" /> {{ doc.publish_date }}</span>
            <span v-if="doc.source" class="meta-item"><Newspaper :size="12" /> {{ doc.source }}</span>
            <span class="meta-item"><Eye :size="12" /> {{ doc.view_count || 0 }}</span>
          </div>
          <div class="doc-card-summary" v-if="doc.ai_summary"><span class="ai-tag">AI</span>{{ doc.ai_summary }}</div>
          <div class="doc-card-tags" v-if="doc.facet_tags">
            <span v-for="(vals, dim) in doc.facet_tags" :key="dim" v-if="vals && vals.length" class="ft-group">
              <span v-for="v in vals" :key="v" class="ft-tag" @click.stop="onFacetClick(dim, v)">{{ v }}</span>
            </span>
          </div>
        </div>
        <div v-if="!loading && !docs.length" class="empty-state">
          <Inbox class="empty-icon" :size="48" />
          <div>暂无文档</div>
          <small v-if="!activeSearch">从左侧选择分类，或点击「全部」浏览所有内容</small>
          <small v-else>没有匹配「{{ activeSearch }}」的文档，试试切换「混合检索」或「BM25」模式</small>
        </div>
      </div>

      <!-- 分页 -->
      <div class="pagination" v-if="resultTotal > 0">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="resultTotal"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="onPageChange"
          @size-change="onSizeChange"
        />
      </div>
    </main>

    <!-- 右侧详情抽屉 -->
    <el-drawer v-model="detailVisible" size="520px" direction="rtl" :with-header="false">
      <div class="detail-panel" v-if="detail" v-loading="detailLoading">
        <div class="detail-close" @click="detailVisible = false">✕</div>
        <div class="detail-type-badge" :class="detail.doc_type">{{ typeLabel(detail.doc_type) }}</div>
        <h2 class="detail-title">{{ detail.title }}</h2>
        <div class="detail-meta">
          <span v-if="detail.province"><MapPin :size="12" /> {{ detail.province }}</span>
          <span v-if="detail.publish_date"><Calendar :size="12" /> {{ detail.publish_date }}</span>
          <span v-if="detail.doc_number"><FileText :size="12" /> {{ detail.doc_number }}</span>
          <span v-if="detail.source"><Newspaper :size="12" /> {{ detail.source }}</span>
          <span><Eye :size="12" /> {{ detail.view_count || 0 }}次浏览</span>
        </div>

        <!-- 分类归属 -->
        <div class="detail-section" v-if="detail.category_code || detailPath">
          <div class="section-title"><FolderOpen :size="14" /> 分类归属</div>
          <div class="detail-path">
            <span v-for="(p, i) in detailPath" :key="p.code">
              <span v-if="i"> / </span>
              <span>{{ p.name }}</span>
            </span>
          </div>
        </div>

        <!-- AI摘要 -->
        <div class="detail-section" v-if="detail.ai_summary">
          <div class="section-title"><Bot :size="14" /> AI 摘要 <span class="ai-caveat">AI 生成 · 以原文为准</span></div>
          <div class="detail-summary">{{ detail.ai_summary }}</div>
        </div>

        <!-- 多维标签 -->
        <div class="detail-section" v-if="detail.facet_tags">
          <div class="section-title"><Tag :size="14" /> 多维标签</div>
          <div class="detail-tags">
            <template v-for="(vals, dim) in detail.facet_tags" :key="dim">
              <span v-if="vals && vals.length" class="dt-group">
                <small>{{ facetLabel(dim) }}:</small>
                <span v-for="v in vals" :key="v" class="dt-tag">{{ v }}</span>
              </span>
            </template>
          </div>
        </div>

        <!-- 正文 -->
        <div class="detail-section" v-if="detail.content">
          <div class="section-title"><BookOpen :size="14" /> 正文内容</div>
          <div class="detail-content">{{ detail.content }}</div>
        </div>

        <!-- 附件 -->
        <div class="detail-section" v-if="detail.attachments && detail.attachments.length">
          <div class="section-title"><Paperclip :size="14" /> 附件下载</div>
          <div class="detail-attachments">
            <a v-for="att in detail.attachments" :key="att.id"
               :href="downloadUrl(att.id)" target="_blank" class="att-link">
              <FileText class="att-icon" :size="16" />
              <span class="att-name">{{ att.filename }}</span>
              <span class="att-type">.{{ att.file_type }}</span>
            </a>
          </div>
        </div>

        <!-- 知识网络 -->
        <div class="detail-section" v-if="network && network.related_questions?.length">
          <div class="section-title"><Link :size="14" /> 知识网络</div>
          <div v-if="network.knowledge_point" class="kp-link">
            关联知识点：{{ network.knowledge_point.name }}
          </div>
          <div class="related-qs">
            <div class="rq-hint">相关题目（{{ network.related_questions.length }}题）：</div>
            <div v-for="q in network.related_questions" :key="q.id" class="rq-item"
                 @click="$router.push('/learn/quiz')">
              <span class="rq-type" :class="q.type">{{ qtypeLabel(q.type) }}</span>
              <span>{{ q.stem }}</span>
            </div>
          </div>
        </div>

        <!-- 底部操作 -->
        <div class="detail-actions">
          <el-button size="small" @click="toggleStar">
            <Star :size="14" /> {{ detail.is_starred ? '已收藏' : '收藏' }}
          </el-button>
          <a v-if="detail.source_url" :href="detail.source_url" target="_blank" class="src-link">
            <el-button size="small" plain><Link :size="14" /> 查看原文</el-button>
          </a>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { nextTick, ref, reactive, watch, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  FolderTree, FileText, Search, Star, MapPin, Calendar, Newspaper,
  Eye, Inbox, Bot, Tag, BookOpen, Paperclip, Link, FolderOpen, Sparkles,
} from 'lucide-vue-next'
import { categoryApi, knowledgeApi, learnApi } from '../../api'

const route = useRoute()
const router = useRouter()

const props = defineProps({ totalDocsHandler: Function })

// ---- 分类树 ----
const treeRef = ref()
const treeData = ref([])
const treeFilter = ref('')
const treeProps = { label: 'name', children: 'children' }

watch(treeFilter, (val) => treeRef.value?.filter(val || ' '))
const filterNode = (value, data) => {
  if (!value || value === ' ') return true
  return data.name.includes(value)
}

// ---- 文档列表 ----
const docs = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(20)
const resultTotal = ref(0)
const currentPath = ref([])
const activeFacet = ref(null) // {facet, value}
const selectedCode = ref(null)

// ---- 搜索 ----
const searchQuery = ref('')
const activeSearch = ref('') // 已提交的搜索词；筛选栏与结果视图以它为准，避免输入过程中筛选栏闪现消失
watch(searchQuery, (v) => {
  // 清空输入框（点 × 或删空）时退出搜索、恢复分类浏览与筛选栏
  if (!v && activeSearch.value) { activeSearch.value = ''; loadDocs() }
})
const searching = ref(false)
const searchMode = ref('keyword') // keyword | semantic

// ---- 检索引擎诚实化 ----
// 后端 /knowledge/search-status 报告当前活跃 embedder：
//   embedder ∈ {uninitialized, tfidf, sentence-transformer}
//   semantic_available：TF-IDF 降级时为 false，真实语义模型在线时为 true
// 未加载时 semantic_available 仅反映 sentence_transformers 是否可导入，
// 前端据此决定 dense 模式标签：语义可用→"语义"，否则→"词频(伪语义)"。
const searchStatus = ref(null)
const semanticAvailable = computed(() => !!searchStatus.value?.semantic_available)
const engineStatus = computed(() => {
  const s = searchStatus.value
  if (!s) return ''
  if (s.semantic_available) {
    const name = (s.model_name || '').split('/').pop() || s.model_name || '语义模型'
    return `语义模型：${name}`
  }
  return '词频匹配（TF-IDF）'
})
const denseTabLabel = computed(() => (semanticAvailable.value ? '语义' : '词频(伪语义)'))

// ---- 多维标签 ----
const facetDimensions = ref([])

// ---- 详情抽屉 ----
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref(null)
const detailPath = ref([])
const network = ref(null)

// ---- 知识点过滤（?kp=<code> URL 入参）----
// 后端 /knowledge/docs 与 /knowledge/search 均接受 knowledge_point_id（int）；
// ?kp= 传的是知识点 code（如 'spot'），需经 learnApi.knowledgeTree() 解析 code→id。
// /category/docs 与 /category/by-facet 不支持 knowledge_point_id，故点击分类/标签时清除此过滤。
const kpFilter = ref(null) // 解析后的 knowledge_point_id，null 表示未启用
const kpName = ref('')      // 用于 chip 展示的知识点名称
const kpCodeToId = ref({})
const kpCodeToName = ref({})
const kpMapLoading = ref(true)

async function loadKpMap() {
  try {
    const tree = await learnApi.knowledgeTree()
    const idMap = {}, nameMap = {}
    for (const p of tree || []) { idMap[p.code] = p.id; nameMap[p.code] = p.name }
    kpCodeToId.value = idMap
    kpCodeToName.value = nameMap
  } catch (e) { console.error('知识点树加载失败', e) }
  finally { kpMapLoading.value = false }
}

// 依据 route.query.kp 解析并设置 kpFilter；返回是否发生变化
async function applyKpFromQuery() {
  const prevId = kpFilter.value
  const code = route.query.kp
  if (!code) { kpFilter.value = null; kpName.value = '' }
  else {
    // 映射可能仍在加载中（onMounted 内已 await，此分支主要服务 watch）
    if (kpMapLoading.value) await loadKpMap()
    const id = kpCodeToId.value[code]
    if (id) { kpFilter.value = id; kpName.value = kpCodeToName.value[code] || String(code) }
    else { kpFilter.value = null; kpName.value = '' }
  }
  return kpFilter.value !== prevId
}

// 清除知识点过滤：重置状态并从 URL 移除 ?kp=（不触发 reload，由调用方决定）
function clearKpFilter() {
  kpFilter.value = null
  kpName.value = ''
  if (route.query.kp) {
    const q = { ...route.query }
    delete q.kp
    router.replace({ query: q })
  }
}

onMounted(async () => {
  await Promise.all([loadTree(), loadFacetDimensions(), loadKpMap(), loadSearchStatus()])
  await applyKpFromQuery()
  await loadDocs()
})

// 外部导航变更 ?kp=（如 KnowledgeBook 切换知识点、浏览器前进后退）时同步过滤并重载
watch(() => route.query.kp, async () => {
  const changed = await applyKpFromQuery()
  if (changed) {
    currentPage.value = 1
    selectedCode.value = null
    activeFacet.value = null
    activeSearch.value = ''
    searchQuery.value = ''
    loadDocs()
  }
})

async function loadTree() {
  try {
    const res = await categoryApi.tree()
    treeData.value = res.tree || []
  } catch (e) { console.error('分类树加载失败', e) }
}

// 加载检索引擎状态（用于诚实化标注，失败时静默，不阻塞浏览）
async function loadSearchStatus() {
  try {
    searchStatus.value = await knowledgeApi.searchStatus()
  } catch (e) { /* 状态查询失败不影响检索，按未标注处理 */ }
}

async function loadFacetDimensions() {
  try {
    const raw = await categoryApi.facetDimensions()
    // 后端返回 {key: {label, values}} dict，转成数组便于遍历
    facetDimensions.value = Object.entries(raw).map(([key, val]) => ({
      key, label: val.label || key, values: val.values || [],
    }))
  } catch (e) { /* ignore */ }
}

// ---- 加载文档列表 ----
async function loadDocs() {
  loading.value = true
  try {
    let res
    // 知识点过滤参数（仅 /knowledge/docs 与 /knowledge/search 后端支持）
    const kpParam = kpFilter.value ? { knowledge_point_id: kpFilter.value } : {}
    if (activeSearch.value && searchMode.value !== 'keyword') {
      // 混合/语义/BM25 检索（走 /knowledge/search，后端支持 knowledge_point_id）
      const mode = searchMode.value === 'hybrid' ? 'hybrid' : (searchMode.value === 'dense' ? 'dense' : 'sparse')
      res = await knowledgeApi.search(activeSearch.value, { top_k: 20, mode, ...kpParam })
      // 把 chunk 结果聚合成 doc 列表
      const seen = new Map()
      for (const r of (res.results || [])) {
        if (!seen.has(r.doc_id)) {
          seen.set(r.doc_id, {
            id: r.doc_id, title: r.title, doc_type: r.doc_type,
            province: r.province, source: r.source, publish_date: r.publish_date,
            ai_summary: r.chunk_text?.slice(0, 100),
            facet_tags: null, view_count: 0, is_starred: false,
            _score: r.score,
          })
        }
      }
      docs.value = [...seen.values()]
      resultTotal.value = docs.value.length
      currentPath.value = []
    } else if (activeSearch.value) {
      // 关键词搜索（走 /knowledge/docs?q=，后端支持 knowledge_point_id）
      res = await knowledgeApi.docs({ q: activeSearch.value, page: currentPage.value, page_size: pageSize.value, ...kpParam })
      docs.value = res.items || []
      resultTotal.value = res.total || 0
      currentPath.value = []
    } else if (activeFacet.value) {
      // 多维标签筛选（/category/by-facet 不支持 knowledge_point_id）
      res = await categoryApi.byFacet(activeFacet.value.facet, activeFacet.value.value, currentPage.value)
      docs.value = res.items || []
      resultTotal.value = res.total || 0
      currentPath.value = []
    } else if (selectedCode.value) {
      // 按分类浏览（/category/docs 不支持 knowledge_point_id）
      res = await categoryApi.docs(selectedCode.value, currentPage.value)
      docs.value = res.items || []
      resultTotal.value = res.total || 0
      currentPath.value = res.path || []
    } else {
      // 全部（/knowledge/docs，后端支持 knowledge_point_id）
      res = await knowledgeApi.docs({ page: currentPage.value, page_size: pageSize.value, ...kpParam })
      docs.value = res.items || []
      resultTotal.value = res.total || 0
      currentPath.value = []
    }
    props.totalDocsHandler?.(resultTotal.value)
  } catch (e) {
    ElMessage.error('加载失败: ' + e.message)
  }
  loading.value = false
}

// ---- 交互 ----
function onCategoryClick(data) {
  // 再次点击已选中的分类 → 取消选中，回到「全部」
  if (selectedCode.value === data.code) {
    selectedCode.value = null
    treeRef.value?.setCurrentKey(null)
    searchQuery.value = ''
    activeSearch.value = ''
    activeFacet.value = null
    currentPage.value = 1
    clearKpFilter()
    loadDocs()
    return
  }
  selectedCode.value = data.code
  searchQuery.value = ''
  activeSearch.value = ''
  activeFacet.value = null
  currentPage.value = 1
  // /category/docs 不支持 knowledge_point_id，点击分类即清除知识点过滤
  clearKpFilter()
  loadDocs()
}

function goRoot() {
  selectedCode.value = null
  searchQuery.value = ''
  activeSearch.value = ''
  activeFacet.value = null
  currentPage.value = 1
  clearKpFilter()
  loadDocs()
}

function doSearch() {
  const q = searchQuery.value.trim()
  if (!q) return
  activeSearch.value = q
  activeFacet.value = null
  selectedCode.value = null
  currentPage.value = 1
  searching.value = true
  // /knowledge/search 与 /knowledge/docs 均支持 knowledge_point_id，保留知识点过滤
  loadDocs().finally(() => { searching.value = false })
}

async function switchMode(mode) {
  if (searchMode.value === mode) return
  searchMode.value = mode
  await nextTick()
  if (searchQuery.value) doSearch()
}

async function onFacetClick(facet, value) {
  // 再次点击已选中的标签 → 取消筛选
  const same = activeFacet.value && activeFacet.value.facet === facet && activeFacet.value.value === value
  activeFacet.value = same ? null : { facet, value }
  searchQuery.value = ''
  activeSearch.value = ''
  selectedCode.value = null
  currentPage.value = 1
  // /category/by-facet 不支持 knowledge_point_id，点击标签即清除知识点过滤
  clearKpFilter()
  await nextTick()
  loadDocs()
}

function clearFacet() {
  activeFacet.value = null
  loadDocs()
}

// 清除知识点过滤 chip：重置状态、移除 ?kp=、回到全部浏览
function clearKp() {
  clearKpFilter()
  currentPage.value = 1
  loadDocs()
}

function onPageChange() {
  loadDocs()
}

function onSizeChange() {
  currentPage.value = 1
  loadDocs()
}

// ---- 详情 ----
async function openDetail(doc) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  network.value = null
  detailPath.value = []
  try {
    const [d, net] = await Promise.all([
      knowledgeApi.docDetail(doc.id),
      knowledgeApi.network(doc.id).catch(() => null),
    ])
    detail.value = d
    network.value = net
    // 如果文档有分类编码，取分类路径
    if (d.category_code) {
      try {
        const res = await categoryApi.docs(d.category_code)
        detailPath.value = res.path || []
      } catch (e) { /* ignore */ }
    }
  } catch (e) {
    ElMessage.error('加载详情失败: ' + e.message)
  }
  detailLoading.value = false
}

async function toggleStar() {
  try {
    const res = await knowledgeApi.toggleStar(detail.value.id)
    detail.value.is_starred = res.starred
    // 同步更新列表中的收藏状态
    const doc = docs.value.find((d) => d.id === detail.value.id)
    if (doc) doc.is_starred = res.starred
  } catch (e) { ElMessage.error('操作失败') }
}

function downloadUrl(attId) {
  return knowledgeApi.downloadUrl(attId)
}

// ---- 辅助 ----
const typeMap = {
  national_policy: '国家政策', regulation: '监管规则', exchange_info: '交易公告',
  industry_news: '行业资讯', exam_info: '考试信息',
}
const typeLabel = (t) => typeMap[t] || t

const facetLabelMap = {
  entity: '主体', product: '品种', timeframe: '时间', source_level: '来源层级', region: '地域',
}
const facetLabel = (k) => facetLabelMap[k] || k

const qtypeMap = { single: '单选', multiple: '多选', judge: '判断' }
const qtypeLabel = (t) => qtypeMap[t] || t
</script>

<style scoped>
.browse {
  display: grid;
  grid-template-columns: 260px 1fr;
  height: 100%;
  max-width: 1400px;
  margin: 0 auto;
}

/* 左栏分类树 */
.cat-sidebar {
  border-right: 1px solid #e4e4e7;
  padding: 16px;
  overflow-y: auto;
  height: 100%;
  background: #fafafa;
}
.sidebar-head {
  font-size: 12px; font-weight: 700; color: #71717a;
  padding: 0 4px 10px;
  display: flex; align-items: center; gap: 6px;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.tree-filter { margin-bottom: 12px; }
.tree-filter :deep(.el-input__wrapper) {
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 0 0 1px #e4e4e7;
  padding: 4px 12px;
}
.tree-filter :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px #d4d4d8;
}
.tree-filter :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 2px #6366f1;
}
.cat-tree { background: transparent; }
.tree-node {
  display: flex; align-items: center; gap: 6px; font-size: 13px;
}
.tn-icon { flex-shrink: 0; display: inline-flex; color: #a1a1aa; }
.tn-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #3f3f46; }
.tn-count {
  font-size: 10px; font-weight: 600; color: #a1a1aa;
  background: #f4f4f5; border-radius: 6px;
  padding: 1px 7px; min-width: 20px; text-align: center;
}
:deep(.el-tree-node__content) { height: 32px; border-radius: 8px; padding: 0 4px; transition: all 0.15s; }
:deep(.el-tree-node__content:hover) { background: #f4f4f5; }
:deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: #eef2ff;
}
:deep(.el-tree-node.is-current > .el-tree-node__content .tn-label) { color: #6366f1; font-weight: 600; }
:deep(.el-tree-node.is-current > .el-tree-node__content .tn-icon) { color: #6366f1; }
:deep(.el-tree-node.is-current > .el-tree-node__content .tn-count) { background: #e0e7ff; color: #6366f1; }

/* 主区 */
.content-main {
  padding: 16px 24px;
  overflow-y: auto;
  height: 100%;
}

/* 顶栏搜索 */
.content-topbar {
  display: flex; gap: 12px; align-items: center; margin-bottom: 12px;
}
.search-input { flex: 1; }
.search-btn { flex-shrink: 0; }
.mode-tabs { display: flex; gap: 4px; }
.mode-tab {
  padding: 6px 12px; font-size: 12px; cursor: pointer;
  border-radius: 4px; color: var(--text-secondary);
  border: 1px solid var(--border-light);
  font-family:inherit;background:transparent;
  transition: all 0.2s cubic-bezier(0.22, 0.61, 0.36, 1);
}
.mode-tab:hover { border-color: var(--accent); color: var(--accent); }
.mode-tab.active { background: var(--accent-soft); color: var(--accent); border-color: var(--accent); font-weight: 600; }

/* 检索引擎诚实标注：一行小字，不喧宾夺主 */
.engine-status {
  margin: 6px 2px 10px;
  font-size: 11px;
  color: var(--text-tertiary);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* 面包屑 */
.breadcrumb {
  font-size: 13px; color: var(--text-secondary); margin-bottom: 12px;
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px;
}
.bc-item { cursor: pointer; }
.bc-item:hover { color: var(--accent); }
.bc-item.last { color: var(--text-primary); font-weight: 600; cursor: default; }
.bc-sep { color: var(--text-tertiary); }
.bc-count { color: var(--text-tertiary); font-size: 12px; }
.bc-facet {
  margin-left: 8px; padding: 2px 8px; border-radius: 10px;
  background: var(--accent-soft); color: var(--accent); font-size: 12px;
}
.bc-kp { background: #e6f7f6; color: #0b9684; font-weight: 600; }
.bc-clear { cursor: pointer; margin-left: 4px; }

/* 多维标签条 */
.facet-bar {
  display: flex; flex-direction: column; gap: 7px; margin-bottom: 16px;
  padding: 11px; background: linear-gradient(145deg, #fbfcff, #f2f6ff); border-radius: 14px;
  border: 1px solid #dfe7f5;box-shadow:0 9px 24px rgba(44,67,119,.055);
}
.facet-group {
  --facet:#4168dc;--facet-soft:#edf2ff;
  min-height:40px;padding:6px 8px;display:flex;align-items:center;gap:7px;flex-wrap:wrap;
  border:1px solid transparent;border-radius:10px;background:rgba(255,255,255,.58);
}
.facet-group.facet-product{--facet:#0b9684;--facet-soft:#e9f8f4}
.facet-group.facet-timeframe{--facet:#d47d18;--facet-soft:#fff4e4}
.facet-group.facet-source_level{--facet:#8a45b0;--facet-soft:#f6edfb}
.facet-group.facet-region{--facet:#257abf;--facet-soft:#eaf5fd}
.facet-label {
  min-width:78px;padding:5px 8px;border-radius:8px;
  color:var(--facet);background:var(--facet-soft);font-size:11px;font-weight:800;
}
.facet-tag {
  font-size: 11px;font-weight:650;padding:5px 12px;border-radius:9px;
  border:1px solid #e0e5ef;cursor:pointer;background:#fff;
  color:#657086;transition:transform .16s,border-color .16s,color .16s,background .16s,box-shadow .16s;
}
.facet-tag:hover { border-color:var(--facet);color:var(--facet);transform:translateY(-1px);background:var(--facet-soft);box-shadow:0 4px 12px rgba(65,104,220,.1) }
.facet-tag.active { background:var(--facet);color:#fff;border-color:var(--facet);box-shadow:0 5px 13px color-mix(in srgb,var(--facet) 26%,transparent) }

/* 文档卡片 */
.doc-list { display: flex; flex-direction: column; gap: 10px; }
.doc-card {
  background: var(--bg-card); border-radius: 8px; padding: 14px 16px;
  border: 1px solid var(--border-light); cursor: pointer; position: relative; overflow: hidden;
  transition: transform 0.24s cubic-bezier(0.22, 0.61, 0.36, 1), box-shadow 0.24s ease, border-color 0.24s ease;
}
.doc-card::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: var(--accent); transform: scaleY(0); transform-origin: center;
  transition: transform 0.24s ease;
}
.doc-card:hover { border-color: var(--accent); box-shadow: 0 10px 26px rgba(99, 102, 241, 0.12); transform: translateY(-3px); }
.doc-card:hover::before { transform: scaleY(1); }
.doc-card-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.doc-type-badge {
  font-size: 11px; padding: 1px 7px; border-radius: 3px; color: #fff;
  white-space: nowrap;
}
.doc-type-badge.national_policy { background: #f56c6c; }
.doc-type-badge.regulation { background: #9c27b0; }
.doc-type-badge.exchange_info { background: #e6a23c; }
.doc-type-badge.industry_news { background: #409eff; }
.doc-type-badge.exam_info { background: #67c23a; }
.doc-title { flex: 1; font-size: 15px; font-weight: 600; color: var(--text-primary); }
.doc-title:hover { color: var(--accent); }
.doc-star { font-size: 14px; }
.doc-card-meta { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 6px; }
.meta-item { font-size: 12px; color: var(--text-tertiary); display: inline-flex; align-items: center; gap: 3px; }
.doc-card-summary {
  font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 6px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.doc-card-tags { display: flex; flex-wrap: wrap; gap: 4px; }
/* AI 生成内容标注：提醒以原文为准，不可当决策依据 */
.ai-tag { display: inline-block; font-size: 10px; font-weight: 700; color: #d97706; background: rgba(245, 158, 11, 0.14); padding: 0 5px; border-radius: 4px; margin-right: 6px; vertical-align: middle; }
.ai-caveat { font-size: 11px; font-weight: 400; color: #d97706; background: rgba(245, 158, 11, 0.12); padding: 1px 8px; border-radius: 8px; margin-left: 6px; }
.ft-group { display: contents; }
.ft-tag {
  font-size: 11px; padding: 1px 6px; border-radius: 3px;
  background: var(--bg-hover); color: var(--text-secondary); cursor: pointer;
}
.ft-tag:hover { background: var(--accent-soft); color: var(--accent); }

/* 空状态 */
.empty-state {
  text-align: center; padding: 60px 20px; color: var(--text-tertiary);
}
.empty-icon { margin-bottom: 12px; color: var(--text-tertiary); }

/* 分页 */
.pagination { display: flex; justify-content: center; margin-top: 20px; }

/* ============ 详情抽屉 ============ */
.detail-panel { padding: 20px 24px; position: relative; }
.detail-close {
  position: absolute; top: 16px; right: 16px; cursor: pointer;
  font-size: 18px; color: var(--text-tertiary);
}
.detail-type-badge {
  display: inline-block; font-size: 12px; padding: 2px 8px; border-radius: 3px; color: #fff;
  margin-bottom: 8px;
}
.detail-title { font-size: 18px; font-weight: 700; margin: 0 0 12px; line-height: 1.4; }
.detail-meta {
  display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: var(--text-tertiary);
  padding-bottom: 12px; border-bottom: 1px solid var(--border-light); margin-bottom: 16px;
}
.detail-meta span { display: inline-flex; align-items: center; gap: 3px; }
.detail-section { margin-bottom: 18px; }
.section-title {
  font-size: 13px; font-weight: 600; color: var(--accent);
  margin-bottom: 6px; display: inline-flex; align-items: center; gap: 4px;
}
.detail-path { font-size: 13px; color: var(--text-secondary); }
.detail-summary {
  font-size: 13px; line-height: 1.7; color: var(--text-primary);
  background: var(--accent-soft); padding: 10px 12px; border-radius: 6px;
}
.detail-tags { display: flex; flex-direction: column; gap: 6px; }
.dt-group { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.dt-group small { color: var(--text-tertiary); font-size: 11px; }
.dt-tag {
  font-size: 11px; padding: 1px 6px; border-radius: 3px;
  background: var(--bg-hover); color: var(--text-secondary);
}
.detail-content {
  font-size: 13px; line-height: 1.8; color: var(--text-primary);
  white-space: pre-wrap; word-break: break-word;
  max-height: 400px; overflow-y: auto;
}
.detail-attachments { display: flex; flex-direction: column; gap: 6px; }
.att-link {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px;
  background: var(--bg-hover); border-radius: 6px; text-decoration: none;
  color: var(--text-primary); font-size: 13px; transition: all 0.15s;
}
.att-link:hover { background: var(--accent-soft); }
.att-icon { flex-shrink: 0; }
.att-name { flex: 1; }
.att-type { color: var(--text-tertiary); font-size: 11px; }
.kp-link { font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }
.related-qs { display: flex; flex-direction: column; gap: 6px; }
.rq-hint { font-size: 12px; color: var(--text-tertiary); }
.rq-item {
  display: flex; align-items: center; gap: 6px; padding: 6px 8px;
  background: var(--bg-hover); border-radius: 4px; font-size: 13px; cursor: pointer;
}
.rq-item:hover { background: var(--accent-soft); }
.rq-type {
  font-size: 10px; padding: 1px 5px; border-radius: 2px; color: #fff; white-space: nowrap;
}
.rq-type.single { background: #409eff; }
.rq-type.multiple { background: #e6a23c; }
.rq-type.judge { background: #67c23a; }
.detail-actions {
  display: flex; gap: 8px; margin-top: 20px; padding-top: 16px;
  border-top: 1px solid var(--border-light);
}
.src-link { text-decoration: none; }

/* 知识索引系统：钴蓝检索语言 + 单一雷达动效，区别于学习中心课程卡片。 */
.browse {
  max-width: 1440px;
  background: rgba(255,255,255,.38);
}
.cat-sidebar {
  height:100%;
  padding:20px 17px;
  border-right-color:#dce5f3;
  background:
    linear-gradient(180deg,rgba(245,248,255,.96),rgba(250,252,255,.92));
}
.sidebar-head {
  color:#50617c;
  font-size:11px;
  letter-spacing:.1em;
}
.tree-filter :deep(.el-input__wrapper) {
  min-height:38px;
  border-radius:11px;
  box-shadow:0 0 0 1px #dce5f2,0 5px 14px rgba(54,80,137,.045);
}
.tree-filter :deep(.el-input__wrapper.is-focus){box-shadow:0 0 0 2px rgba(65,104,220,.3)}
:deep(.el-tree-node__content){height:36px;border-radius:9px}
:deep(.el-tree-node__content:hover){background:#edf2ff;transform:translateX(2px)}
:deep(.el-tree-node.is-current > .el-tree-node__content){background:linear-gradient(90deg,#e7edff,#f2f6ff)}
:deep(.el-tree-node.is-current > .el-tree-node__content .tn-label),
:deep(.el-tree-node.is-current > .el-tree-node__content .tn-icon){color:#4168dc}
:deep(.el-tree-node.is-current > .el-tree-node__content .tn-count){background:#dce6ff;color:#4168dc}
.content-main {
  height:100%;
  padding:22px 28px 38px;
}
.knowledge-radar {
  min-height:190px;
  margin-bottom:16px;
  padding:27px 31px;
  display:grid;
  grid-template-columns:1.06fr .94fr;
  align-items:center;
  gap:24px;
  position:relative;
  overflow:hidden;
  border:1px solid #d9e3f5;
  border-radius:19px;
  background:
    radial-gradient(circle at 82% 35%,rgba(20,166,176,.13),transparent 28%),
    radial-gradient(circle at 14% 0,rgba(65,104,220,.11),transparent 36%),
    linear-gradient(125deg,#fff,#f3f7ff 62%,#eef9fb);
  box-shadow:0 16px 40px rgba(47,75,140,.1);
}
.knowledge-radar::before{
  content:"";position:absolute;inset:0;
  background-image:linear-gradient(rgba(65,104,220,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(65,104,220,.045) 1px,transparent 1px);
  background-size:25px 25px;
  mask-image:linear-gradient(90deg,transparent,#000 42%);
}
.radar-copy,.radar-visual{position:relative;z-index:1}
.radar-kicker{display:inline-flex;align-items:center;gap:7px;color:#4168dc;font-size:9px;font-weight:850;letter-spacing:.16em}
.radar-copy h1{margin:9px 0 9px;color:#172847;font-size:28px;line-height:1.22;letter-spacing:-.04em}
.radar-copy h1 em{color:#4168dc;font-style:normal}
.radar-copy p{max-width:620px;color:#687891;font-size:12px;line-height:1.7}
.radar-visual{height:135px}
.radar-ring{position:absolute;left:56%;top:50%;border:1px solid rgba(65,104,220,.22);border-radius:50%;transform:translate(-50%,-50%)}
.ring-one{width:180px;height:105px}
.ring-two{width:270px;height:142px;border-style:dashed;animation:radarOrbit 16s linear infinite}
.radar-sweep{
  position:absolute;left:56%;top:50%;width:125px;height:1px;transform-origin:left center;
  background:linear-gradient(90deg,#4168dc,rgba(65,104,220,0));animation:radarSweep 5s linear infinite;
}
.radar-core{
  position:absolute;left:56%;top:50%;transform:translate(-50%,-50%);
  width:78px;height:78px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-direction:column;
  color:#fff;background:linear-gradient(145deg,#304fae,#5278e4 65%,#1aa5ad);
  box-shadow:0 0 0 10px rgba(65,104,220,.07),0 13px 28px rgba(49,78,172,.23);
}
.radar-core svg{position:absolute;opacity:.14;width:49px;height:49px}
.radar-core strong{font-size:21px;line-height:1}
.radar-core small{margin-top:5px;font-size:8px;color:rgba(255,255,255,.67)}
.radar-point{position:absolute;width:7px;height:7px;border-radius:50%;background:#20b8c5;box-shadow:0 0 10px #20b8c5;animation:radarPoint 2.4s ease-in-out infinite}
.point-a{left:19%;top:28%}.point-b{right:14%;top:63%;animation-delay:.8s}.point-c{left:30%;bottom:8%;animation-delay:1.6s}
.radar-label{
  position:absolute;padding:7px 10px;display:inline-flex;align-items:center;gap:6px;border:1px solid #dce5f3;
  border-radius:10px;color:#52647e;background:rgba(255,255,255,.9);box-shadow:0 7px 17px rgba(47,70,126,.08);
  font-size:10px;font-weight:700;
}
.label-source{left:1%;top:9%}.label-ai{right:0;bottom:8%}

.content-topbar {
  position:relative;
  z-index:10;
  padding:10px;
  border:1px solid #dfe7f4;
  border-radius:14px;
  background:rgba(255,255,255,.9);
  box-shadow:0 9px 24px rgba(46,70,128,.075);
  backdrop-filter:blur(13px);
}
.search-input :deep(.el-input__wrapper){min-height:40px;border-radius:10px;background:#f8faff;box-shadow:inset 0 0 0 1px #e1e7f3}
.search-input :deep(.el-input__wrapper.is-focus){box-shadow:inset 0 0 0 1px #4168dc,0 0 0 4px rgba(65,104,220,.08)}
.search-btn{min-height:40px;border-radius:10px}
.mode-tabs{padding:4px;border-radius:10px;background:#f1f4fa}
.mode-tab{min-height:34px;border:0;border-radius:8px;padding:7px 11px}
.mode-tab.active{border:0;color:#fff;background:#4168dc;box-shadow:0 6px 14px rgba(65,104,220,.25)}
.doc-list{gap:9px}
.doc-card{
  padding:16px 18px;border-radius:12px;border-color:#e1e7f2;
  box-shadow:0 5px 17px rgba(43,67,122,.035);
}
.doc-card::before{background:linear-gradient(180deg,#4168dc,#18aab1)}
.doc-card:hover{border-color:#bdcbed;box-shadow:0 13px 29px rgba(49,76,142,.12);transform:translateY(-2px) translateX(3px)}
.doc-title{font-size:14px;color:#21324e}

@keyframes radarSweep{to{transform:rotate(360deg)}}
@keyframes radarOrbit{to{transform:translate(-50%,-50%) rotate(360deg)}}
@keyframes radarPoint{0%,100%{opacity:.35;transform:scale(.72)}50%{opacity:1;transform:scale(1.28)}}
@media(max-width:900px){.knowledge-radar{grid-template-columns:1fr}.radar-visual{display:none}.browse{grid-template-columns:220px 1fr}.mode-tabs{display:none}}
@media(max-width:680px){.browse{display:block}.cat-sidebar{display:none}.content-main{height:100%;padding:14px}.knowledge-radar{min-height:0;padding:23px}.radar-copy h1{font-size:24px}.content-topbar{position:relative}}
@media(prefers-reduced-motion:reduce){.ring-two,.radar-sweep,.radar-point{animation:none}}
</style>
