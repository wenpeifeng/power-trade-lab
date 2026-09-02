<template>
  <div class="lesson-page" v-loading="loading">
    <template v-if="lesson">
      <div class="lesson-top">
        <button class="back" @click="$router.push('/learn/study')">← 返回学习路径</button>
        <span class="unit-no">UNIT {{ String(lesson.order).padStart(2, '0') }}</span>
        <h1>{{ lesson.title }}</h1>
        <p>{{ lesson.subtitle }}</p>
        <div class="lesson-meta">
          <span><Clock3 :size="14" /> {{ lesson.duration_min }}分钟</span>
          <span><Target :size="14" /> {{ lesson.objectives.length }}个目标</span>
          <span :class="['state', lesson.progress.status]">{{ statusLabel(lesson.progress.status) }}</span>
          <a v-if="lesson.progress.status === 'completed'" href="#check" class="review-shortcut">查看课后复盘 ↓</a>
        </div>
      </div>

      <div class="flow-rail">
        <a v-for="(item, index) in flow" :key="item.id" :href="`#${item.id}`">
          <i>{{ index + 1 }}</i><span>{{ item.label }}</span>
        </a>
      </div>

      <section id="learn" class="lesson-section">
        <div class="section-kicker">LEARN · 建立框架</div>
        <h2>学完这一课，你要能做到</h2>
        <div class="objective-grid">
          <div v-for="(objective, index) in lesson.objectives" :key="objective">
            <CheckCircle2 :size="18" /><span>{{ objective }}</span><b>0{{ index + 1 }}</b>
          </div>
        </div>
        <div v-for="concept in lesson.concepts" :key="concept.title" class="concept">
          <h3>{{ concept.title }}</h3>
          <p>{{ concept.body }}</p>
        </div>
      </section>

      <section id="observe" class="lesson-section observation">
        <div class="section-kicker">OBSERVE · 用数据验证</div>
        <h2>{{ lesson.observation.title }}</h2>
        <p class="lead">{{ lesson.observation.instruction }}</p>
        <div v-if="observations.length" class="data-strip">
          <a v-for="item in observations" :key="`${item.type}-${item.date}`" :href="item.source_url || '#'"
            :target="item.source_url ? '_blank' : null" rel="noopener">
            <span class="data-date">{{ item.date }}</span>
            <strong>{{ item.typeLabel }}</strong>
            <small>{{ item.source || '来源待核验' }} · {{ provenanceLabel(item.provenance_level) }}</small>
          </a>
        </div>
        <div v-else class="empty-data">当前没有匹配的结构化数据。本课不会用模拟值冒充真实观测，可先阅读下方官方资料。</div>
      </section>

      <section id="check" class="lesson-section">
        <div class="section-kicker">CHECK · 即时检查</div>
        <h2>确认你真正理解了</h2>
        <div v-for="(check, ci) in lesson.checks" :key="check.question" class="check-card">
          <h3>{{ ci + 1 }}. {{ check.question }}</h3>
          <label v-for="(option, oi) in check.options" :key="option" :class="{
            chosen: answers[ci] === oi,
            'answer-correct': checked && review?.items?.[ci]?.correct_answer_index === oi,
            'answer-wrong': checked && review?.items?.[ci]?.user_answer_index === oi && review?.items?.[ci]?.is_correct === false,
          }">
            <input v-model="answers[ci]" type="radio" :name="`check-${ci}`" :value="oi" />
            <span>{{ String.fromCharCode(65 + oi) }}</span>{{ option }}
          </label>
          <div v-if="checked && review?.items?.[ci]" :class="['answer-review', review.items[ci].is_correct === false ? 'wrong' : 'correct']">
            <strong v-if="review.items[ci].is_correct === true">回答正确</strong>
            <strong v-else-if="review.items[ci].is_correct === false">本题答错</strong>
            <strong v-else>历史答案记录</strong>
            <p>你的回答：{{ review.items[ci].user_answer_text }}</p>
            <p>正确答案：{{ String.fromCharCode(65 + review.items[ci].correct_answer_index) }}. {{ review.items[ci].correct_answer_text }}</p>
            <p class="explanation">{{ review.items[ci].explanation }}</p>
            <small v-if="review.items[ci].is_correct === false">{{ review.items[ci].review_action }}</small>
          </div>
        </div>
        <button class="secondary-action" @click="runCheck">{{ checked ? '再次提交检查' : '提交检查' }}</button>
        <span v-if="checked" class="score">得分 {{ checkScore }}</span>
        <div v-if="review" class="review-report">
          <div class="review-summary">
            <div><span>最近得分</span><strong>{{ review.score }}</strong></div>
            <div><span>正确</span><strong>{{ review.correct_count ?? '—' }}/{{ review.total }}</strong></div>
            <div><span>错题</span><strong>{{ review.wrong_count ?? '—' }}</strong></div>
            <div><span>累计尝试</span><strong>{{ attempts.length || lesson.progress.attempt_count || 0 }}</strong></div>
          </div>
          <p v-if="review.record_available === false" class="legacy-note">
            这节课完成于逐题记录功能上线前，无法恢复你当时的选择；正确答案和解析已补充展示。
          </p>
          <div v-if="review.weak_points?.length" class="weak-points">
            <b>建议回看</b><span v-for="point in review.weak_points" :key="point">{{ point }}</span>
          </div>
          <details v-if="attempts.length > 1" class="attempt-history">
            <summary>查看全部 {{ attempts.length }} 次回答记录</summary>
            <div v-for="(attempt, index) in [...attempts].reverse()" :key="attempt.submitted_at" class="attempt-row">
              <span>第 {{ attempts.length - index }} 次</span>
              <span>{{ formatCheckTime(attempt.submitted_at) }}</span>
              <strong>{{ attempt.score }}分</strong>
              <small>错 {{ attempt.wrong_count }} 题</small>
            </div>
          </details>
        </div>
      </section>

      <section id="deliver" class="lesson-section deliverable">
        <div class="section-kicker">DELIVER · 形成业务成果</div>
        <h2>{{ lesson.deliverable.title }}</h2>
        <p class="lead">{{ lesson.deliverable.prompt }}</p>
        <div class="example">参考结构：{{ lesson.deliverable.example }}</div>
        <textarea v-model="deliverable" rows="7" placeholder="在这里写下你的业务成果。系统会保存它，而不是学完即忘。"></textarea>
        <div class="deliver-actions">
          <button class="secondary-action" @click="saveProgress">保存草稿</button>
          <button class="primary-action" @click="completeLesson">完成本课并解锁下一课 →</button>
          <router-link v-if="lesson.simulation_scenario" :to="{ path: '/trade/lab', query: { scenario: lesson.simulation_scenario } }">
            进入配套交易仿真
          </router-link>
        </div>
      </section>

      <section id="source" class="lesson-section sources">
        <div class="section-kicker">SOURCE · 证据与延伸</div>
        <h2>本课关联的真实资料</h2>
        <a v-for="source in lesson.sources" :key="source.id" :href="source.source_url || '#'"
          :target="source.source_url ? '_blank' : null" rel="noopener">
          <div><strong>{{ source.title }}</strong><small>{{ source.publish_date || '日期待核验' }} · {{ source.source }}</small></div>
          <span>{{ source.source_url ? '查看原文 ↗' : '暂无原文' }}</span>
        </a>
        <div v-if="!lesson.sources.length" class="empty-data">知识资产中暂未找到已审核的匹配资料。</div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CheckCircle2, Clock3, Target } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { knowledgeApi, studyApi } from '../../api'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const lesson = ref(null)
const answers = reactive({})
const checked = ref(false)
const checkScore = ref(null)
const review = ref(null)
const attempts = ref([])
const deliverable = ref('')
const observations = ref([])
const flow = [
  { id: 'learn', label: '理解' }, { id: 'observe', label: '观察' },
  { id: 'check', label: '检查' }, { id: 'deliver', label: '产出' }, { id: 'source', label: '来源' },
]
const statusLabel = (s) => ({ not_started: '未开始', in_progress: '学习中', completed: '已完成' }[s] || s)
const formatCheckTime = (value) => value ? new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'
const provenanceLabel = (s) => ({
  observed_public: '公开观测', observed_authorized: '授权观测',
  reconstructed: '重构数据', synthetic: '模拟数据',
}[s] || '来源待核验')

async function loadObservations(types = []) {
  const results = await Promise.all(types.slice(0, 2).map(async (type) => {
    const res = await knowledgeApi.publicData({ data_type: type, limit: 2 })
    return (res.items || []).map(item => ({
      ...item,
      type,
      typeLabel: type.replaceAll('_', ' '),
    }))
  }))
  observations.value = results.flat().slice(0, 4)
}

async function loadLesson() {
  loading.value = true
  try {
    lesson.value = await studyApi.guidedDetail(route.params.code)
    if (!lesson.value.unlocked) {
      ElMessage.warning('请先完成前置课程')
      router.push('/learn/study')
      return
    }
    deliverable.value = lesson.value.progress.deliverable_text || ''
    review.value = lesson.value.review || null
    attempts.value = lesson.value.attempts || []
    if (review.value) {
      checked.value = true
      checkScore.value = review.value.score
      if (review.value.record_available && Array.isArray(review.value.answers)) {
        review.value.answers.forEach((answer, index) => { answers[index] = answer })
      }
    }
    await studyApi.updateGuidedProgress(route.params.code, { action: 'start' })
    await loadObservations(lesson.value.observation.data_types)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function runCheck() {
  const submittedAnswers = lesson.value.checks.map((_, index) => answers[index] ?? null)
  if (submittedAnswers.some(answer => answer === null)) {
    ElMessage.warning('请先完成全部即时检查题')
    return false
  }
  try {
    const res = await studyApi.updateGuidedProgress(route.params.code, {
      action: 'check', answers: submittedAnswers,
    })
    review.value = res.review
    checkScore.value = res.review.score
    checked.value = true
    attempts.value = [...attempts.value, res.review]
    ElMessage[checkScore.value >= 60 ? 'success' : 'warning'](`即时检查得分 ${checkScore.value}`)
    return true
  } catch (e) {
    ElMessage.error(e.message)
    return false
  }
}

async function saveProgress() {
  try {
    await studyApi.updateGuidedProgress(route.params.code, {
      action: 'save', deliverable_text: deliverable.value,
    })
    ElMessage.success('学习成果已保存')
  } catch (e) { ElMessage.error(e.message) }
}

async function completeLesson() {
  try {
    if (!review.value) {
      const passed = await runCheck()
      if (!passed) return
    }
    await studyApi.updateGuidedProgress(route.params.code, {
      action: 'complete', deliverable_text: deliverable.value,
    })
    ElMessage.success('本课已完成，回答记录和课后复盘已保存')
    router.push('/learn/study')
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(loadLesson)
</script>

<style scoped>
.lesson-page { max-width: 960px; margin: 0 auto; color: var(--text-primary); }
.lesson-top { position: relative; padding: 42px; border-radius: 20px; color: #fff; overflow: hidden; background: linear-gradient(135deg, #172554 0%, #2937a9 62%, #5965ef 100%); box-shadow: 0 22px 55px rgba(36, 50, 145, .22); }
.lesson-top::after { content: ""; position: absolute; width: 330px; height: 330px; right: -130px; top: -180px; border: 48px solid rgba(255,255,255,.08); border-radius: 50%; }
.back { border: 0; background: none; color: rgba(255,255,255,.72); cursor: pointer; padding: 0; }
.unit-no { display: block; margin-top: 36px; color: #b9c5ff; font-size: 12px; letter-spacing: .18em; font-weight: 800; }
.lesson-top h1 { font-size: 34px; margin: 8px 0; letter-spacing: -.02em; }
.lesson-top p { color: rgba(255,255,255,.78); margin: 0; }
.lesson-meta { display: flex; gap: 20px; margin-top: 28px; align-items: center; font-size: 13px; }
.lesson-meta > span { display: inline-flex; align-items: center; gap: 6px; }
.review-shortcut { color: #fff; font-size: 12px; text-decoration: none; border-bottom: 1px solid rgba(255,255,255,.45); }
.state { padding: 5px 10px; border-radius: 999px; background: rgba(255,255,255,.12); }
.state.completed { background: #17a673; }
.flow-rail { display: grid; grid-template-columns: repeat(5, 1fr); margin: 26px 10px 34px; position: relative; }
.flow-rail::before { content: ""; height: 2px; background: #dfe3f4; position: absolute; left: 10%; right: 10%; top: 15px; }
.flow-rail a { position: relative; z-index: 1; display: flex; flex-direction: column; align-items: center; color: var(--text-secondary); text-decoration: none; font-size: 12px; gap: 7px; }
.flow-rail i { width: 31px; height: 31px; border-radius: 50%; background: #fff; border: 2px solid #6b72ef; color: #5258d8; display: grid; place-items: center; font-style: normal; font-weight: 800; }
.lesson-section { margin: 18px 0; padding: 30px; background: var(--bg-card); border: 1px solid var(--border-light); border-radius: 16px; box-shadow: var(--shadow-card); scroll-margin-top: 80px; }
.section-kicker { color: #5a61df; letter-spacing: .12em; font-size: 11px; font-weight: 800; }
.lesson-section h2 { font-size: 22px; margin: 7px 0 20px; }
.objective-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 24px; }
.objective-grid > div { position: relative; min-height: 92px; padding: 17px; background: #f3f5ff; border-radius: 12px; display: flex; gap: 9px; line-height: 1.55; font-size: 13px; overflow: hidden; }
.objective-grid svg { color: #5965ef; flex: none; }
.objective-grid b { position: absolute; right: 8px; bottom: -10px; font-size: 38px; color: rgba(73,81,210,.08); }
.concept { padding: 4px 0 16px 18px; border-left: 3px solid #9fa5ff; }
.concept h3 { margin: 0 0 6px; font-size: 16px; }.concept p,.lead { margin: 0; line-height: 1.8; color: var(--text-secondary); font-size: 14px; }
.observation { background: linear-gradient(145deg, #f8f9ff, #eef2ff); }
.data-strip { display: grid; grid-template-columns: repeat(2,1fr); gap: 10px; margin-top: 20px; }
.data-strip a { display: flex; flex-direction: column; padding: 15px; background: #fff; border: 1px solid #dce1f3; border-radius: 10px; text-decoration: none; color: var(--text-primary); }
.data-date { color: #5965ef; font-size: 12px; }.data-strip small,.sources small { display: block; color: var(--text-tertiary); margin-top: 6px; }
.check-card { margin: 14px 0; padding: 18px; background: #f8f9fc; border-radius: 12px; }
.check-card h3 { font-size: 15px; margin: 0 0 12px; }
.check-card label { display: flex; align-items: center; gap: 9px; padding: 10px; cursor: pointer; border: 1px solid transparent; border-radius: 8px; }
.check-card label.chosen { background: #eef0ff; border-color: #aeb4ff; }.check-card label span { width: 24px; height: 24px; border-radius: 6px; background: #fff; display: grid; place-items: center; font-weight: 700; }
.check-card label.answer-correct { background:#e9f8f1; border-color:#5fbe99; }.check-card label.answer-wrong { background:#fff0f0; border-color:#dc8888; }
.correct { color: #16835d; }.wrong { color: #bd4b4b; }.score { margin-left: 12px; font-weight: 700; color: #5965ef; }
.answer-review { margin-top:12px; padding:14px 16px; border-radius:9px; background:#eaf8f2; color:#286b55; }.answer-review.wrong{background:#fff2f2;color:#9f4343}.answer-review p{margin:5px 0;font-size:13px}.answer-review .explanation{color:var(--text-secondary);line-height:1.65}.answer-review small{display:inline-block;margin-top:5px;padding:4px 8px;background:#fff;border-radius:5px}
.review-report{margin-top:20px;padding:20px;border-radius:12px;background:linear-gradient(145deg,#f4f5ff,#edf1ff);border:1px solid #d9ddf4}.review-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.review-summary>div{padding:13px;background:#fff;border-radius:9px}.review-summary span{display:block;color:var(--text-tertiary);font-size:11px}.review-summary strong{font-size:20px;color:#5159d4}.legacy-note{padding:11px;margin:14px 0 0;background:#fff8e7;color:#825e16;border-left:3px solid #d7a43c;font-size:13px}.weak-points{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-top:14px;font-size:12px}.weak-points span{padding:5px 8px;border-radius:5px;background:#fff;color:#9a4b4b}.attempt-history{margin-top:15px}.attempt-history summary{cursor:pointer;color:#535bdc;font-size:13px}.attempt-row{display:grid;grid-template-columns:80px 1fr 60px 60px;padding:9px 3px;border-bottom:1px solid #dce0f1;font-size:12px;color:var(--text-secondary)}.attempt-row strong{color:#535bdc}.attempt-row small{color:#a75c5c}
.example { padding: 12px 14px; margin: 16px 0; border-left: 3px solid #d29d35; background: #fff9ed; color: #72571e; font-size: 13px; }
textarea { width: 100%; resize: vertical; box-sizing: border-box; border: 1px solid #d8dceb; border-radius: 10px; padding: 14px; font: inherit; line-height: 1.7; }
.deliver-actions { display: flex; gap: 10px; align-items: center; margin-top: 14px; }.deliver-actions a { color: #5965ef; font-size: 13px; text-decoration: none; }
.primary-action,.secondary-action { border: 0; border-radius: 8px; padding: 10px 16px; cursor: pointer; font-weight: 650; }
.primary-action { background: #535bdc; color: white; }.secondary-action { background: #eef0ff; color: #4c54cf; }
.sources a { display: flex; justify-content: space-between; gap: 20px; align-items: center; padding: 14px 0; color: var(--text-primary); text-decoration: none; border-top: 1px solid var(--border-light); }.sources a > span { white-space: nowrap; color: #5965ef; font-size: 13px; }
.empty-data { margin-top: 14px; padding: 18px; text-align: center; color: var(--text-tertiary); background: rgba(255,255,255,.55); border: 1px dashed #cbd0e2; border-radius: 10px; }
@media(max-width:720px){.lesson-top{padding:28px}.lesson-top h1{font-size:26px}.objective-grid,.data-strip{grid-template-columns:1fr}.lesson-section{padding:22px}.deliver-actions{align-items:stretch;flex-direction:column}.review-summary{grid-template-columns:repeat(2,1fr)}}
</style>
