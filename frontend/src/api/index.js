// API 封装层：统一 axios 实例 + 各模块接口
import axios from 'axios'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

const request = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  withCredentials: true,
})

// 从旧版本升级时立即删除可被 JavaScript 读取的长期 JWT。
localStorage.removeItem('token')

// 响应拦截：直接返回 data；401 跳登录
request.interceptors.response.use(
  (res) => res.data,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      // 避免在登录页循环跳转
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login'
      }
    }
    const msg = err.response?.data?.detail || err.message || '请求失败'
    return Promise.reject(new Error(msg))
  }
)

// ============ 用户认证 ============
export const authApi = {
  register: (data) => request.post('/auth/register', data),
  login: (data) => request.post('/auth/login', data),
  logout: () => request.post('/auth/logout'),
  me: () => request.get('/auth/me'),
  changePassword: (data) => request.post('/auth/change-password', data),
}

// 获取当前用户（从 localStorage）
export const currentUser = () => {
  try { return JSON.parse(localStorage.getItem('user')) } catch { return null }
}
export const isLoggedIn = () => !!currentUser()
export const logout = async () => {
  try { await authApi.logout() } catch {}
  finally {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    window.location.href = '/login'
  }
}

// ============ AI 助手 ============
export const aiApi = {
  chat: (question, history) => request.post('/ai/chat', { question, history }, { timeout: 120000 }),
  suggestions: () => request.get('/ai/suggestions'),
  history: () => request.get('/ai/history'),
  // LLM 配置
  llmStatus: () => request.get('/ai/llm/status'),
  configLLM: (data) => request.post('/ai/llm/config', data),
  deleteLLM: () => request.delete('/ai/llm/config'),
  testLLM: () => request.post('/ai/llm/test'),
  // RAG 评估
  evalTestset: () => request.get('/ai/eval/testset'),
  evalRun: (mode, topK) => request.get('/ai/eval/run', { params: { mode, top_k: topK }, timeout: 120000 }),
  evalCompare: (topK) => request.get('/ai/eval/compare', { params: { top_k: topK }, timeout: 300000 }),
}

// ============ 门户 ============
export const portalApi = {
  overview: () => request.get('/portal/overview'),
}

// ============ 学习刷题 ============
export const learnApi = {
  knowledgeTree: () => request.get('/learn/knowledge-tree'),
  quiz: (params) => request.post('/learn/quiz', params),
  answer: (data) => request.post('/learn/answer', data),
  questionDetail: (id) => request.get(`/learn/questions/${id}`),
  // 按知识点抽题自检（hide_answer：is_correct 全 false，answer/analysis 不返回）
  check: (kpId, count = 1) =>
    request.get('/learn/check', { params: { kp: kpId, count } }),
  wrongAnswers: (reviewed) =>
    request.get('/learn/wrong-answers', { params: reviewed === undefined ? {} : { reviewed } }),
  wrongAnswersPaged: (params) => request.get('/learn/wrong-answers-paged', { params }),
  // 到期待复习错题（间隔重复）。返回 {items, pagination}；correct 在 body，缺省 true 兼容旧前端
  wrongDue: (page = 1, pageSize = 10) =>
    request.get('/learn/wrong-answers/due', { params: { page, page_size: pageSize } }),
  markReviewed: (id, correct = true) =>
    request.post(`/learn/wrong-answers/${id}/reviewed`, { correct }),
  relatedDocs: (wrongId) => request.get(`/learn/wrong-answers/${wrongId}/related-docs`),
  recommend: () => request.get('/learn/recommend'),
}

// ============ 分层学习（L1/L2/L3 + 诊断 + 省份 + 偏好）============
export const studyApi = {
  profile: () => request.get('/study/profile'),
  updatePrefs: (prefs) => request.put('/study/preferences', prefs),
  setHomeProvince: (province) => request.post('/study/set-home-province', { province }),
  diagnosisPaper: () => request.get('/study/diagnosis/paper'),
  evaluate: (answers) => request.post('/study/diagnosis/evaluate', { answers }),
  dashboard: () => request.get('/study/dashboard'),
  guided: () => request.get('/study/guided'),
  today: () => request.get('/study/today'),
  guidedDetail: (code) => request.get(`/study/guided/${code}`),
  updateGuidedProgress: (code, data) => request.post(`/study/guided/${code}/progress`, data),
  provinces: () => request.get('/study/provinces'),
  provinceDetail: (name) => request.get(`/study/province/${name}`),
  // 主动学习：概念阅读状态上报 + 掌握度总览
  markReading: (code, status) => request.post(`/study/reading/${code}`, { status }),
  reading: () => request.get('/study/reading'),
  mastery: () => request.get('/study/mastery'),
}

// ============ 教材工坊（MinerU解析 + 章节学习）============
export const bookApi = {
  mineruStatus: () => request.get('/study/books/mineru-status'),
  list: () => request.get('/study/books'),
  upload: (formData) => request.post('/study/books', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  }),
  reprocess: (bookId) => request.post(`/study/books/${bookId}/reprocess`, null, {
    timeout: 30000,
  }),
  detail: (bookId) => request.get(`/study/books/${bookId}`),
  chapter: (bookId, chapterId) => request.get(`/study/books/${bookId}/chapters/${chapterId}`),
  updateProgress: (bookId, chapterId, data) =>
    request.post(`/study/books/${bookId}/chapters/${chapterId}/progress`, data),
  downloadMarkdown: (bookId) =>
    request.get(`/study/books/${bookId}/markdown`, { responseType: 'blob' }),
}

// ============ 考试刷题（双模式：学习/考试）============
export const examApi = {
  blueprint: (level) => request.get('/exam/blueprint', { params: { level } }),
  prediction: (level) => request.get('/exam/prediction', { params: { level } }),
  studyPaper: (params) => request.post('/exam/study-paper', params),
  startExam: (params) => request.post('/exam/start', params),
  submitExam: (data) => request.post('/exam/submit', data),
  history: () => request.get('/exam/history'),
  examResult: (id) => request.get(`/exam/result/${id}`),
  realExamYears: (level) => request.get('/exam/real-exam/years', { params: { level } }),
}

// ============ 政策公告 ============
export const policyApi = {
  list: (params) => request.get('/policy', { params }),
  detail: (id) => request.get(`/policy/${id}`),
  unreadCount: () => request.get('/policy/unread-count'),
  categories: () => request.get('/policy/categories'),
  provinces: () => request.get('/policy/provinces'),
  markRead: (id) => request.post(`/policy/${id}/read`),
  markAllRead: () => request.post('/policy/read-all'),
}

// ============ 交易模拟 ============
export const tradeApi = {
  markets: () => request.get('/trade/markets'),
  quote: (marketId, tradeDate, province) => request.get('/trade/quote', {
    params: {
      market_id: marketId,
      ...(tradeDate ? { trade_date: tradeDate } : {}),
      ...(province ? { province } : {}),
    },
  }),
  availableDates: (marketId, province) => request.get('/trade/available-dates', {
    params: { market_id: marketId, ...(province ? { province } : {}) },
  }),
  account: () => request.get('/trade/account'),
  submitOrder: (marketId, side, bidCurve) =>
    request.post('/trade/order', bidCurve, { params: { market_id: marketId, side } }),
  positions: () => request.get('/trade/positions'),
  orderbook: (marketId) => request.get('/trade/orderbook', { params: { market_id: marketId } }),
  review: (marketId) => request.get('/trade/review', { params: { market_id: marketId } }),
  simulationScenarios: () => request.get('/trade/sim/scenarios'),
  simulationSessions: () => request.get('/trade/sim/sessions'),
  createSimulation: (data) => request.post('/trade/sim/sessions', data),
  simulationDetail: (id) => request.get(`/trade/sim/sessions/${id}`),
  openSimulation: (id) => request.post(`/trade/sim/sessions/${id}/open`),
  saveSimulationBids: (id, bids) => request.put(`/trade/sim/sessions/${id}/bids`, { bids }),
  sealSimulation: (id) => request.post(`/trade/sim/sessions/${id}/seal`),
  clearSimulation: (id) => request.post(`/trade/sim/sessions/${id}/clear`),
  settleSimulation: (id) => request.post(`/trade/sim/sessions/${id}/settle`),
}

// ============ 知识库沉淀（文档检索+公共数据+知识网络）============
export const knowledgeApi = {
  docs: (params) => request.get('/knowledge/docs', { params }),
  docDetail: (id) => request.get(`/knowledge/docs/${id}`),
  toggleStar: (id) => request.post(`/knowledge/docs/${id}/star`),
  facets: () => request.get('/knowledge/facets'),
  publicData: (params) => request.get('/knowledge/public-data', { params }),
  network: (id) => request.get(`/knowledge/network/${id}`),
  sediment: (data) => request.post('/knowledge/sediment', data),
  // 检索（混合:向量语义+BM25关键词，供后续AI集成）
  search: (q, params) => request.get('/knowledge/search', { params: { q, ...(params || {}) } }),
  // 检索引擎状态（诚实化：前端据此标注 语义/词频）
  searchStatus: () => request.get('/knowledge/search-status'),
  // 按概念标题召回相关真实原文（进阶/专家溯源）
  byConcept: (title, kp, limit = 3) =>
    request.get('/knowledge/by-concept', { params: { title, kp, limit } }),
  // 附件下载
  downloadUrl: (attId) => `${API_BASE_URL}/knowledge/attachments/${attId}/download`,
}

// ============ 分类体系（分类树浏览+多维标签）============
export const categoryApi = {
  tree: () => request.get('/category/tree'),
  facetDimensions: () => request.get('/category/facet-dimensions'),
  docs: (code, page = 1) => request.get('/category/docs', { params: { code, page } }),
  byFacet: (facet, value, page = 1) => request.get('/category/by-facet', { params: { facet, value, page } }),
}

// ============ 数据资产中心（多源接入+时间线+统计+运维）============
export const assetApi = {
  // 基础5通道
  ingestCurl: (data) => request.post('/asset/ingest/curl', data),
  ingestManual: (data) => request.post('/asset/ingest/manual', data),
  ingestFeishu: (data) => request.post('/asset/ingest/feishu', data),
  uploadFile: (formData) => request.post('/asset/ingest/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  runCrawler: (crawlerType) => request.post('/asset/crawler/run', { crawler_type: crawlerType }),
  crawlerStatus: (crawlerType) => request.get('/asset/crawler/status', { params: { crawler_type: crawlerType } }),
  qweatherStatus: () => request.get('/asset/connectors/qweather/status'),
  qweatherTest: () => request.post('/asset/connectors/qweather/test'),
  qweatherLocations: (q, adm) => request.get('/asset/connectors/qweather/locations', {
    params: { q, ...(adm ? { adm } : {}) },
  }),
  // 扩展4通道
  uploadSpreadsheet: (formData) => request.post('/asset/ingest/spreadsheet', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000,
  }),
  ingestApi: (data) => request.post('/asset/ingest/api', data),
  ingestRss: (data) => request.post('/asset/ingest/rss', data),
  ingestFeishuBase: (data) => request.post('/asset/ingest/feishu-base', data),
  // 查询
  timeline: (params) => request.get('/asset/timeline', { params }),
  stats: () => request.get('/asset/stats'),
  // 运维
  quality: () => request.get('/asset/quality'),
  trackRef: (docId, refType, note) => request.post('/asset/track-ref', { doc_id: docId, ref_type: refType, note }),
  docRefs: (docId) => request.get(`/asset/refs/${docId}`),
  review: (docId, action) => request.post('/asset/review', { doc_id: docId, action }),
  batchReview: (action = 'approve') => request.post('/asset/review/batch', null, { params: { action } }),
  pendingReview: (page = 1) => request.get('/asset/review/pending', { params: { page } }),
  updateDoc: (data) => request.post('/asset/doc/update', data),
}

// ============ 管理后台（爬虫+AI生题）============
export const adminApi = {
  stats: () => request.get('/admin/stats'),
  crawlerSources: () => request.get('/admin/crawler/sources'),
  runCrawler: (source) => request.post(`/admin/crawler/run/${source}`),
  runAllCrawlers: () => request.post('/admin/crawler/run-all'),
  aiGenFromPolicy: (policyId, count) =>
    request.post('/admin/ai/generate-from-policy', { policy_id: policyId, count }),
  aiGenFromKnowledge: (code, count) =>
    request.post('/admin/ai/generate-from-knowledge', { knowledge_point_code: code, count }),
}

export default request
