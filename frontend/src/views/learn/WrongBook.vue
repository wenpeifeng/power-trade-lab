<template>
  <div class="wrong-book" v-loading="loading">
    <section class="review-hero">
      <div>
        <span class="hero-kicker"><RotateCcw :size="14" /> REVIEW LOOP</span>
        <h1>错题不是清单，是下一轮学习计划</h1>
        <p>系统已按最近错误、知识模块与掌握状态整理。先看错因，再回到解析与关联知识。</p>
      </div>
      <div class="mastery-ring" :style="{ '--rate': `${stats.mastery_rate * 3.6}deg` }">
        <div><strong><span v-count="stats.mastery_rate">0</span>%</strong><small>错题掌握率</small></div>
      </div>
    </section>

    <section class="review-stats">
      <button :class="{ active: status === 'all' }" @click="setStatus('all')">
        <span class="stat-icon total"><LibraryBig :size="18" /></span>
        <div><strong v-count="stats.total">0</strong><small>累计错题</small></div>
      </button>
      <button :class="{ active: status === 'pending' }" @click="setStatus('pending')">
        <span class="stat-icon pending"><AlarmClock :size="18" /></span>
        <div><strong v-count="stats.pending">0</strong><small>待复习</small></div>
      </button>
      <button :class="{ active: status === 'mastered' }" @click="setStatus('mastered')">
        <span class="stat-icon mastered"><BadgeCheck :size="18" /></span>
        <div><strong v-count="stats.mastered">0</strong><small>已掌握</small></div>
      </button>
      <div class="review-advice">
        <Sparkles :size="17" />
        <span><strong>今日建议</strong><small>{{ adviceText }}</small></span>
      </div>
    </section>

    <section class="review-workspace">
      <div class="workspace-head">
        <div>
          <div class="tab-row">
            <button class="tab" :class="{ active: mode === 'all' }" @click="setMode('all')">全部错题</button>
            <button class="tab" :class="{ active: mode === 'due' }" @click="setMode('due')">
              今日复习<span v-if="dueCount" class="tab-badge">{{ dueCount }}</span>
            </button>
          </div>
          <span class="section-kicker">REVIEW QUEUE</span>
          <h2>{{ statusTitle }}</h2>
        </div>
        <div class="filters">
          <el-input
            v-model="keyword"
            clearable
            placeholder="搜索题干或解析"
            :prefix-icon="Search"
            @keyup.enter="applyKeyword"
            @clear="applyKeyword"
          />
          <el-select v-model="questionType" placeholder="全部题型" clearable>
            <el-option value="single" label="单选题" />
            <el-option value="multiple" label="多选题" />
            <el-option value="judge" label="判断题" />
          </el-select>
          <el-select v-model="knowledgePointId" placeholder="全部知识模块" clearable>
            <el-option
              v-for="kp in kpOptions"
              :key="kp.id"
              :value="kp.id"
              :label="kp.count ? `${kp.name} · ${kp.count}` : kp.name"
            />
          </el-select>
        </div>
      </div>

      <div v-if="!list.length" class="empty">
        <span class="empty-icon"><PartyPopper :size="34" /></span>
        <h3>{{ mode === 'due' ? '今日没有到期复习的错题' : (status === 'pending' ? '当前没有待复习错题' : '没有符合筛选条件的错题') }}</h3>
        <p>{{ mode === 'due' ? '到期或新错的题会自动进入这里，保持节奏即可。' : (status === 'pending' ? '做题后，新的错题会自动进入这里。' : '可以调整题型、模块或搜索关键词。') }}</p>
        <el-button v-if="mode === 'due' || status === 'pending'" type="primary" plain @click="$router.push('/learn/quiz')">去做一组题</el-button>
      </div>

      <div v-else class="wrong-list">
        <article
          v-for="(w, idx) in list"
          :key="w.id"
          class="wrong-card"
          :class="{ expanded: expandedId === w.id, mastered: w.reviewed }"
        >
          <button class="question-summary" @click="toggleExpand(w.id)">
            <span class="queue-index">{{ String((pagination.page - 1) * pagination.page_size + idx + 1).padStart(2, '0') }}</span>
            <span class="question-main">
              <span class="question-meta">
                <i :class="`type-${w.question?.type}`">{{ typeLabel(w.question?.type) }}</i>
                <i v-if="w.knowledge_point" class="knowledge-tag">{{ w.knowledge_point.name }}</i>
                <i class="reason-tag">{{ w.error_reason }}</i>
                <i v-if="w.reviewed" class="mastered-tag">已掌握</i>
              </span>
              <strong>{{ w.question?.stem }}</strong>
              <small>{{ fmtDate(w.created_at) }} · 难度 {{ w.question?.difficulty || '-' }}</small>
            </span>
            <span class="answer-compare">
              <small>你的答案</small><strong>{{ w.user_answer || '未作答' }}</strong>
              <ArrowDown :size="16" />
            </span>
          </button>

          <transition name="review-expand">
            <div v-if="expandedId === w.id" class="question-detail">
              <div v-if="w.question?.options?.length" class="w-options">
                <div v-for="opt in w.question.options" :key="opt.key" class="w-opt" :class="optClass(w, opt.key)">
                  <span class="opt-key">{{ opt.key }}</span>
                  <span class="opt-text">{{ opt.text }}</span>
                  <span v-if="isAnswer(w, opt.key)" class="opt-tag correct"><Check :size="13" /> 正确答案</span>
                  <span v-else-if="isMyWrong(w, opt.key)" class="opt-tag wrong"><X :size="13" /> 你的选择</span>
                </div>
              </div>
              <div class="answer-strip">
                <span><small>你的答案</small><strong class="wrong">{{ w.user_answer || '未作答' }}</strong></span>
                <ArrowRight :size="17" />
                <span><small>正确答案</small><strong class="right">{{ w.question?.answer }}</strong></span>
                <span><small>错因归类</small><strong>{{ w.error_reason }}</strong></span>
              </div>
              <div class="analysis-box">
                <span class="analysis-icon"><Lightbulb :size="18" /></span>
                <div><strong>答案解析</strong><p>{{ w.question?.analysis || '这道题暂未补充解析。' }}</p></div>
              </div>
              <div v-if="relatedById[w.id]" class="related-box">
                <strong>关联知识库</strong>
                <a v-for="doc in relatedById[w.id]" :key="doc.doc_id" @click.stop="$router.push('/knowledge')">
                  <BookMarked :size="14" /><span>{{ doc.title }}</span><em>相关度 {{ Math.round((doc.score || 0) * 100) }}%</em>
                </a>
                <p v-if="!relatedById[w.id].length">知识库暂未检索到直接关联内容。</p>
              </div>
              <div v-if="kpCodeOf(w)" class="kp-link-box">
                <router-link :to="`/knowledge?tab=book&kp=${kpCodeOf(w)}`" class="kp-link" @click.stop>
                  <BookMarked :size="14" /><span>学相关概念</span><em>{{ w.knowledge_point?.name }}</em>
                </router-link>
              </div>
              <div v-if="reviewState[w.id]?.active" class="review-panel">
                <strong class="review-title"><RotateCcw :size="15" /> 复习这题</strong>
                <p class="review-stem">{{ w.question?.stem }}</p>
                <div v-if="w.question?.options?.length" class="review-options">
                  <label
                    v-for="opt in w.question.options"
                    :key="opt.key"
                    class="review-opt"
                    :class="reviewOptClass(w, opt.key)"
                  >
                    <input
                      :type="reviewPickType(w)"
                      :name="`review-${w.id}`"
                      :value="opt.key"
                      :checked="isReviewPicked(w, opt.key)"
                      :disabled="reviewState[w.id]?.submitted"
                      @change="toggleReviewPick(w, opt.key, $event)"
                    />
                    <span class="opt-key">{{ opt.key }}</span>
                    <span class="opt-text">{{ opt.text }}</span>
                    <span v-if="reviewState[w.id]?.submitted && isAnswer(w, opt.key)" class="opt-tag correct"><Check :size="13" /> 正确</span>
                    <span v-else-if="reviewState[w.id]?.submitted && isReviewPicked(w, opt.key) && !isAnswer(w, opt.key)" class="opt-tag wrong"><X :size="13" /> 你的选择</span>
                  </label>
                </div>
                <div v-if="reviewState[w.id]?.submitted" class="review-result" :class="reviewState[w.id]?.correct ? 'ok' : 'again'">
                  <template v-if="reviewState[w.id]?.correct">
                    <BadgeCheck :size="16" /> 已掌握 · {{ reviewState[w.id]?.interval }} 天后复习
                  </template>
                  <template v-else>
                    <AlarmClock :size="16" /> 再记一遍，明天复习
                  </template>
                </div>
                <div class="review-actions">
                  <el-button
                    v-if="!reviewState[w.id]?.submitted"
                    type="primary"
                    size="small"
                    :disabled="!reviewState[w.id]?.picked?.length"
                    :loading="reviewState[w.id]?.loading"
                    @click="submitReview(w)"
                  >提交复习</el-button>
                  <el-button v-if="!reviewState[w.id]?.submitted" size="small" @click="closeReview(w.id)">取消</el-button>
                  <el-button v-else size="small" @click="resetReview(w.id)">再来一次</el-button>
                </div>
              </div>
              <div class="detail-actions">
                <el-button :loading="relatedLoading === w.id" @click="loadRelated(w)">
                  <BookMarked :size="15" /> {{ relatedById[w.id] ? '刷新关联知识' : '查找关联知识' }}
                </el-button>
                <el-button v-if="!w.reviewed || mode === 'due'" @click="openReview(w.id)">
                  <RotateCcw :size="15" /> 复习
                </el-button>
                <el-button v-if="!w.reviewed" type="success" @click="markMasteredDirect(w.id)">
                  <BadgeCheck :size="15" /> 直接标记已掌握
                </el-button>
              </div>
            </div>
          </transition>
        </article>
      </div>

      <div v-if="pagination.total > pagination.page_size" class="pagination-wrap">
        <span>共 {{ pagination.total }} 道，当前第 {{ pagination.page }} / {{ pagination.pages }} 页</span>
        <el-pagination
          v-model:current-page="pagination.page"
          :page-size="pagination.page_size"
          :total="pagination.total"
          layout="prev, pager, next"
          background
        />
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { learnApi } from '../../api'
import {
  RotateCcw, LibraryBig, AlarmClock, BadgeCheck, Sparkles, Search,
  PartyPopper, ArrowDown, Check, X, ArrowRight, Lightbulb, BookMarked,
} from 'lucide-vue-next'

const loading = ref(false)
const relatedLoading = ref(null)
const list = ref([])
const status = ref('pending')
const mode = ref('all') // 'all' | 'due'
const dueCount = ref(0)
const questionType = ref('')
const knowledgePointId = ref(null)
const keyword = ref('')
const appliedKeyword = ref('')
const expandedId = ref(null)
const relatedById = ref({})
const stats = ref({ total: 0, pending: 0, mastered: 0, mastery_rate: 0 })
const knowledgePoints = ref([])
const kpTree = ref([])
const reviewState = ref({})
const pagination = ref({ page: 1, page_size: 8, total: 0, pages: 1 })

const kpCodeById = computed(() => {
  const m = {}
  for (const k of kpTree.value) m[k.id] = k.code
  return m
})
const kpOptions = computed(() => {
  // due 模式 due 端点不返回 knowledge_points，从 knowledgeTree 兜底
  if (mode.value === 'due' || !knowledgePoints.value.length) {
    return kpTree.value.map((k) => ({ id: k.id, name: k.name, code: k.code, count: 0 }))
  }
  return knowledgePoints.value
})

const statusTitle = computed(() => ({
  pending: '优先复习队列',
  mastered: '已经掌握的题',
  all: '全部错题记录',
}[status.value]))
const adviceText = computed(() => stats.value.pending
  ? `先复盘 ${Math.min(stats.value.pending, 5)} 道，约需 ${Math.min(stats.value.pending, 5) * 3} 分钟`
  : '待复习队列已清空，保持练习节奏')

const reviewedValue = computed(() => {
  if (status.value === 'pending') return false
  if (status.value === 'mastered') return true
  return undefined
})
const typeLabel = (t) => ({ single: '单选', multiple: '多选', judge: '判断' }[t] || '题目')
const isAnswer = (w, key) => (w.question?.answer || '').toUpperCase().includes(String(key).toUpperCase())
const isMyWrong = (w, key) => {
  const ua = (w.user_answer || '').toUpperCase()
  return ua.includes(String(key).toUpperCase()) && !isAnswer(w, key)
}
const optClass = (w, key) => ({ 'is-correct': isAnswer(w, key), 'is-wrong': isMyWrong(w, key) })
const fmtDate = (value) => value ? new Date(value).toLocaleDateString('zh-CN') : '日期未知'

const load = async () => {
  loading.value = true
  try {
    if (mode.value === 'due') {
      const data = await learnApi.wrongDue(pagination.value.page, pagination.value.page_size)
      let items = data.items || []
      // due 端点不支持服务端筛选，按当前页客户端筛选（最简方案）
      items = filterClientSide(items)
      list.value = items
      pagination.value = { ...pagination.value, ...data.pagination }
      // due 端点不返回 stats/knowledge_points；stats 保持上次值，kp 下拉由 kpTree 兜底
      dueCount.value = data.pagination?.total || 0
      if (expandedId.value && !list.value.some((item) => item.id === expandedId.value)) expandedId.value = null
    } else {
      const data = await learnApi.wrongAnswersPaged({
        page: pagination.value.page,
        page_size: pagination.value.page_size,
        reviewed: reviewedValue.value,
        question_type: questionType.value || undefined,
        knowledge_point_id: knowledgePointId.value || undefined,
        keyword: appliedKeyword.value || undefined,
      })
      list.value = data.items
      stats.value = data.stats
      knowledgePoints.value = data.knowledge_points
      pagination.value = { ...pagination.value, ...data.pagination }
      if (expandedId.value && !list.value.some((item) => item.id === expandedId.value)) expandedId.value = null
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}
const filterClientSide = (items) => {
  let out = items
  const kw = appliedKeyword.value.trim().toLowerCase()
  if (kw) {
    out = out.filter((w) =>
      (w.question?.stem || '').toLowerCase().includes(kw) ||
      (w.question?.analysis || '').toLowerCase().includes(kw))
  }
  if (questionType.value) {
    out = out.filter((w) => w.question?.type === questionType.value)
  }
  if (knowledgePointId.value) {
    out = out.filter((w) => w.knowledge_point?.id === knowledgePointId.value)
  }
  return out
}
const loadDueCount = async () => {
  try {
    const data = await learnApi.wrongDue(1, 1)
    dueCount.value = data.pagination?.total || 0
  } catch {
    dueCount.value = 0
  }
}
const loadKpTree = async () => {
  try {
    kpTree.value = await learnApi.knowledgeTree()
  } catch {
    kpTree.value = []
  }
}
const setMode = (value) => {
  if (mode.value === value) return
  mode.value = value
  pagination.value.page = 1
  load()
}
const setStatus = (value) => {
  if (mode.value === 'due') mode.value = 'all'
  status.value = value
}
const applyKeyword = () => {
  appliedKeyword.value = keyword.value.trim()
  pagination.value.page = 1
  load()
}
const toggleExpand = (id) => {
  expandedId.value = expandedId.value === id ? null : id
}
const kpCodeOf = (w) => kpCodeById.value[w.knowledge_point?.id]
const reviewPickType = (w) => (w.question?.type === 'multiple' ? 'checkbox' : 'radio')
const isReviewPicked = (w, key) => (reviewState.value[w.id]?.picked || []).includes(key)
const toggleReviewPick = (w, key, ev) => {
  const st = reviewState.value[w.id] || {}
  let picked = [...(st.picked || [])]
  if (w.question?.type === 'multiple') {
    if (ev.target.checked) picked.push(key)
    else picked = picked.filter((k) => k !== key)
  } else {
    picked = [key]
  }
  reviewState.value = { ...reviewState.value, [w.id]: { ...st, picked } }
}
const reviewOptClass = (w, key) => {
  const st = reviewState.value[w.id]
  if (!st?.submitted) return ''
  if (isAnswer(w, key)) return 'is-correct'
  if (isReviewPicked(w, key) && !isAnswer(w, key)) return 'is-wrong'
  return ''
}
const openReview = (id) => {
  reviewState.value = { ...reviewState.value, [id]: { active: true, picked: [], submitted: false, correct: null, interval: null, loading: false } }
}
const closeReview = (id) => {
  const next = { ...reviewState.value }
  delete next[id]
  reviewState.value = next
}
const resetReview = (id) => {
  reviewState.value = { ...reviewState.value, [id]: { active: true, picked: [], submitted: false, correct: null, interval: null, loading: false } }
}
const submitReview = async (w) => {
  const st = reviewState.value[w.id]
  if (!st || !st.picked?.length) return
  const ans = (w.question?.answer || '').toUpperCase().split('').sort().join('')
  const picked = [...st.picked].map((k) => String(k).toUpperCase()).sort().join('')
  const correct = picked === ans
  reviewState.value = { ...reviewState.value, [w.id]: { ...st, loading: true } }
  try {
    const data = await learnApi.markReviewed(w.id, correct)
    reviewState.value = {
      ...reviewState.value,
      [w.id]: { ...st, submitted: true, correct, interval: data.review_interval, nextAt: data.next_review_at, loading: false },
    }
    ElMessage[correct ? 'success' : 'warning'](correct ? '答对了，间隔已延长' : '答错了，明天再来')
    await Promise.all([load(), loadDueCount()])
  } catch (e) {
    reviewState.value = { ...reviewState.value, [w.id]: { ...st, loading: false } }
    ElMessage.error(e.message)
  }
}
const markMasteredDirect = async (id) => {
  try {
    await learnApi.markReviewed(id, true)
    ElMessage.success('已进入“已掌握”，后续仍可随时复盘')
    await Promise.all([load(), loadDueCount()])
  } catch (e) {
    ElMessage.error(e.message)
  }
}
const loadRelated = async (wrong) => {
  relatedLoading.value = wrong.id
  try {
    const data = await learnApi.relatedDocs(wrong.id)
    relatedById.value = { ...relatedById.value, [wrong.id]: data.related_docs || [] }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    relatedLoading.value = null
  }
}

watch([status, questionType, knowledgePointId], () => {
  pagination.value.page = 1
  load()
})
watch(() => pagination.value.page, load)
onMounted(() => {
  loadKpTree()
  loadDueCount()
  load()
})
</script>

<style scoped>
.wrong-book{color:var(--text-primary)}.review-hero{min-height:220px;padding:38px 44px;display:flex;align-items:center;justify-content:space-between;gap:30px;color:#302b3d;border:1px solid #ead8de;border-radius:24px;background:radial-gradient(circle at 88% 24%,rgba(184,115,104,.12),transparent 29%),linear-gradient(120deg,#fff,#fbf6f7 57%,#f6eaed);box-shadow:0 18px 42px rgba(105,61,78,.09);position:relative;overflow:hidden}.review-hero::before{content:"";position:absolute;width:380px;height:380px;border:1px solid rgba(153,83,96,.08);border-radius:50%;right:-110px;top:-180px;box-shadow:0 0 0 42px rgba(153,83,96,.025),0 0 0 86px rgba(153,83,96,.018);animation:reviewOrbit 4.8s ease-in-out infinite alternate}.review-hero::after{content:"";position:absolute;inset:-35% -18%;pointer-events:none;background:linear-gradient(105deg,transparent 42%,rgba(179,104,102,.065) 49%,transparent 56%);transform:translateX(-55%);animation:reviewScan 4.2s ease-in-out infinite}.review-hero>div{position:relative;z-index:1}.hero-kicker,.section-kicker{display:inline-flex;align-items:center;gap:7px;font-size:10px;letter-spacing:.15em;font-weight:850;color:#9a5360}.review-hero h1{margin:11px 0 9px;font-size:29px;letter-spacing:-.035em}.review-hero p{font-size:13px;color:#77707e;max-width:690px}.mastery-ring{width:130px;height:130px;border-radius:50%;flex:none;background:conic-gradient(#bd7168 var(--rate),#eadde0 0);display:grid;place-items:center;box-shadow:0 9px 24px rgba(112,65,82,.1);position:relative;animation:masteryFloat 2.25s ease-in-out infinite}.mastery-ring::before{content:"";position:absolute;width:102px;height:102px;border-radius:50%;background:#fff}.mastery-ring div{z-index:1;display:flex;align-items:center;flex-direction:column}.mastery-ring strong{font-size:25px;color:#75445e}.mastery-ring small{font-size:10px;color:#927883;margin-top:5px}
.review-stats{display:grid;grid-template-columns:repeat(3,1fr) minmax(270px,1.35fr);gap:10px;margin:16px 0 34px}.review-stats>button,.review-advice{min-height:82px;padding:14px 16px;border:1px solid #e6e8f0;border-radius:15px;background:#fff;display:flex;align-items:center;gap:12px;text-align:left;color:var(--text-primary);box-shadow:0 7px 20px rgba(31,41,90,.045)}.review-stats>button{cursor:pointer;transition:.22s}.review-stats>button:hover,.review-stats>button.active{border-color:#aab1f3;box-shadow:0 10px 25px rgba(79,88,185,.1);transform:translateY(-2px)}.stat-icon{width:38px;height:38px;display:grid;place-items:center;border-radius:12px;color:#5d66da;background:#eef0ff}.stat-icon.pending{color:#e7764b;background:#fff0e9}.stat-icon.mastered{color:#0b9c78;background:#e8f9f4}.review-stats button div{display:flex;flex-direction:column}.review-stats button strong{font-size:22px}.review-stats button small{font-size:10px;color:#9399aa}.review-advice{border-color:#dceef0;background:linear-gradient(135deg,#f0fbf9,#fff)}.review-advice>svg{color:#14a584}.review-advice span{display:flex;flex-direction:column}.review-advice strong{font-size:13px}.review-advice small{font-size:11px;color:#7f8999;margin-top:4px}
.review-workspace{padding:24px;border:1px solid #e6e8ef;border-radius:20px;background:rgba(255,255,255,.82);box-shadow:0 13px 35px rgba(31,41,90,.055)}.workspace-head{display:flex;justify-content:space-between;align-items:end;gap:24px;margin-bottom:20px}.workspace-head h2{font-size:21px;margin:5px 0 0}.section-kicker{color:#9a5360}.filters{display:flex;gap:8px}.filters :deep(.el-input){width:210px}.filters :deep(.el-select){width:148px}.filters :deep(.el-select:last-child){width:190px}.filters :deep(.el-input__wrapper),.filters :deep(.el-select__wrapper){border-radius:10px;box-shadow:0 0 0 1px #e0e3ec inset}
.wrong-list{display:flex;flex-direction:column;gap:9px}.wrong-card{border:1px solid #e8eaf1;border-radius:15px;background:#fff;overflow:hidden;transition:border-color .22s,box-shadow .22s}.wrong-card:hover,.wrong-card.expanded{border-color:#bdc2ef;box-shadow:0 10px 24px rgba(57,66,137,.08)}.wrong-card.mastered{background:#fcfffe}.question-summary{width:100%;min-height:112px;padding:17px 18px;border:0;background:transparent;color:inherit;text-align:left;display:grid;grid-template-columns:42px 1fr 110px;gap:14px;align-items:center;cursor:pointer}.queue-index{font:750 11px/1 ui-monospace;color:#b0b5c3}.question-main{min-width:0;display:flex;flex-direction:column}.question-meta{display:flex;gap:6px;margin-bottom:7px}.question-meta i{font-style:normal;font-size:9px;font-weight:700;padding:2px 7px;border-radius:8px}.type-single{color:#5260d5;background:#eef0ff}.type-multiple{color:#079270;background:#eaf9f4}.type-judge{color:#d67b19;background:#fff4e5}.knowledge-tag{color:#657084;background:#f1f3f6}.reason-tag{color:#d45c56;background:#fff0ef}.mastered-tag{color:#058561;background:#e8f8f2}.question-main>strong{font-size:14px;line-height:1.55;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.question-main>small{margin-top:7px;color:#a0a5b3;font-size:10px}.answer-compare{justify-self:end;display:grid;grid-template-columns:1fr auto;align-items:center;gap:2px 9px;text-align:right}.answer-compare small{grid-column:1;color:#a0a5b3;font-size:9px}.answer-compare strong{grid-column:1;color:#e06459;font-size:15px}.answer-compare svg{grid-column:2;grid-row:1/3;color:#9ca3af;transition:transform .25s}.expanded .answer-compare svg{transform:rotate(180deg)}
.question-detail{padding:0 20px 20px 74px;border-top:1px solid #f0f1f5}.w-options{padding-top:17px;display:grid;grid-template-columns:1fr 1fr;gap:7px}.w-opt{display:flex;align-items:center;gap:9px;padding:9px 11px;border:1px solid #e8eaf0;border-radius:10px;font-size:12px}.w-opt.is-correct{border-color:#9bdac8;background:#f0fbf7}.w-opt.is-wrong{border-color:#efb2ae;background:#fff5f4}.opt-key{width:23px;height:23px;display:grid;place-items:center;border-radius:7px;background:#f1f3f6;font-weight:750}.is-correct .opt-key{background:#17a37f;color:#fff}.is-wrong .opt-key{background:#e46a61;color:#fff}.opt-text{flex:1}.opt-tag{display:inline-flex;align-items:center;gap:3px;font-size:9px;font-weight:700}.opt-tag.correct{color:#0b9271}.opt-tag.wrong{color:#da5d55}.answer-strip{margin:12px 0;display:flex;align-items:center;gap:16px;padding:13px 16px;background:#f7f8fb;border-radius:12px}.answer-strip span{display:flex;flex-direction:column;gap:2px;min-width:90px}.answer-strip small{font-size:9px;color:#9ca3af}.answer-strip strong{font-size:13px}.answer-strip strong.wrong{color:#dc5c53}.answer-strip strong.right{color:#078c6b}.answer-strip>svg{color:#b0b5c2}.analysis-box{display:flex;gap:11px;padding:15px;border:1px solid #e4e9f3;border-radius:12px;background:#fbfcff}.analysis-icon{width:32px;height:32px;border-radius:10px;display:grid;place-items:center;flex:none;color:#5260d4;background:#edf0ff}.analysis-box strong{font-size:12px}.analysis-box p{font-size:12px;line-height:1.7;color:#697286;margin-top:4px}.related-box{margin-top:10px;padding:14px;border:1px dashed #ccd2ea;border-radius:12px}.related-box>strong{display:block;font-size:12px;margin-bottom:8px}.related-box a{display:flex;align-items:center;gap:7px;padding:6px 0;color:#4e59c9;font-size:11px;cursor:pointer}.related-box a span{flex:1}.related-box a em{font-style:normal;color:#9ca3af}.related-box p{font-size:11px;color:#9298a8}.detail-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:13px}.detail-actions :deep(.el-button span){display:inline-flex;align-items:center;gap:6px}.pagination-wrap{display:flex;align-items:center;justify-content:space-between;margin-top:20px;padding-top:16px;border-top:1px solid #eef0f4}.pagination-wrap>span{font-size:11px;color:#9298a8}.empty{text-align:center;padding:65px 20px}.empty-icon{width:64px;height:64px;border-radius:20px;display:grid;place-items:center;margin:0 auto 14px;color:#16a17d;background:#eaf9f4}.empty h3{font-size:16px;margin-bottom:6px}.empty p{font-size:12px;color:#9298aa;margin-bottom:16px}
.tab-row{display:flex;gap:6px;margin-bottom:10px}.tab{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border:1px solid #e6e8f0;border-radius:20px;background:#fff;color:#657084;font-size:12px;font-weight:600;cursor:pointer;transition:.2s}.tab:hover{border-color:#aab1f3}.tab.active{border-color:#5260d5;background:#eef0ff;color:#5260d5}.tab-badge{display:inline-grid;place-items:center;min-width:18px;height:18px;padding:0 5px;border-radius:9px;background:#e7764b;color:#fff;font-size:10px;font-weight:700}
.kp-link-box{margin-top:10px}.kp-link{display:inline-flex;align-items:center;gap:7px;padding:7px 12px;border:1px solid #c7e4ec;border-radius:10px;background:linear-gradient(135deg,#f0fbf9,#fff);color:#0b8a78;font-size:12px;font-weight:600;cursor:pointer;text-decoration:none}.kp-link svg{color:#14a584}.kp-link em{font-style:normal;color:#9ca3af;font-weight:400;margin-left:2px}.kp-link:hover{border-color:#14a584}
.review-panel{margin-top:12px;padding:14px 15px;border:1px solid #e3d9ef;border-radius:12px;background:linear-gradient(135deg,#fcfaff,#fff)}.review-title{display:flex;align-items:center;gap:7px;font-size:12px;color:#7a4d9a}.review-stem{margin:8px 0 10px;font-size:13px;line-height:1.6;color:#3a3548}.review-options{display:grid;grid-template-columns:1fr 1fr;gap:7px}.review-opt{display:flex;align-items:center;gap:9px;padding:9px 11px;border:1px solid #e8eaf0;border-radius:10px;font-size:12px;cursor:pointer;transition:.18s}.review-opt:hover{border-color:#bdc2ef}.review-opt.is-correct{border-color:#9bdac8;background:#f0fbf7}.review-opt.is-wrong{border-color:#efb2ae;background:#fff5f4}.review-opt input{margin:0}.review-opt .opt-key{width:23px;height:23px;display:grid;place-items:center;border-radius:7px;background:#f1f3f6;font-weight:750}.review-opt.is-correct .opt-key{background:#17a37f;color:#fff}.review-opt.is-wrong .opt-key{background:#e46a61;color:#fff}.review-opt .opt-text{flex:1}.review-result{display:flex;align-items:center;gap:7px;margin-top:11px;padding:9px 12px;border-radius:9px;font-size:12px;font-weight:600}.review-result.ok{background:#e8f9f4;color:#058561}.review-result.again{background:#fff0ef;color:#d45c56}.review-actions{display:flex;gap:8px;margin-top:11px}
@media(max-width:640px){.review-options{grid-template-columns:1fr}}
.review-expand-enter-active,.review-expand-leave-active{transition:opacity .25s ease,transform .25s ease}.review-expand-enter-from,.review-expand-leave-to{opacity:0;transform:translateY(-8px)}
@keyframes reviewScan{0%,35%{transform:translateX(-58%)}72%,100%{transform:translateX(58%)}}@keyframes reviewOrbit{from{transform:translate3d(0,0,0) scale(1)}to{transform:translate3d(-16px,10px,0) scale(1.035)}}@keyframes masteryFloat{0%,100%{transform:translateY(0);box-shadow:0 9px 24px rgba(112,65,82,.1)}50%{transform:translateY(-6px);box-shadow:0 16px 31px rgba(112,65,82,.15)}}
@media(max-width:900px){.review-stats{grid-template-columns:repeat(3,1fr)}.review-advice{grid-column:span 3}.workspace-head{align-items:flex-start;flex-direction:column}.filters{width:100%;flex-wrap:wrap}.filters :deep(.el-input){flex:1;min-width:220px}.question-summary{grid-template-columns:32px 1fr}.answer-compare{display:none}.question-detail{padding-left:64px}.w-options{grid-template-columns:1fr}}
@media(max-width:640px){.review-hero{padding:28px 22px}.review-hero h1{font-size:24px}.mastery-ring{display:none}.review-stats{grid-template-columns:1fr 1fr}.review-advice{grid-column:span 2}.review-stats>button:last-of-type{grid-column:span 2}.review-workspace{padding:14px}.filters>*{width:100%!important}.question-summary{padding:15px 12px}.question-detail{padding:0 12px 14px}.queue-index{display:none}.question-summary{grid-template-columns:1fr}.answer-strip{flex-wrap:wrap}.pagination-wrap{align-items:flex-start;gap:12px;flex-direction:column}}
@media(prefers-reduced-motion:reduce){.review-hero::before,.review-hero::after,.mastery-ring{animation:none}.review-stats>button,.wrong-card,.answer-compare svg{transition:none}}
</style>
