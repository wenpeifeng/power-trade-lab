<template>
  <div class="exam-paper" v-loading="loading">
    <div v-if="!session" class="loading-text">正在组卷...</div>

    <template v-else>
      <!-- 考试顶栏 -->
      <div class="exam-topbar">
        <div class="topbar-left">
          <span class="exam-mode">{{ modeLabel(session.mode) }}</span>
          <span class="q-progress">第 {{ current + 1 }} / {{ questions.length }} 题</span>
        </div>
        <div class="topbar-right">
          <span class="timer" :class="{ warning: timeLeft < 300 }"><Timer :size="18" /> {{ formatTime(timeLeft) }}</span>
          <el-button type="danger" plain size="small" @click="confirmSubmit">交卷</el-button>
        </div>
      </div>
      <el-progress :percentage="progressPct" :stroke-width="3" color="#2f6bff" :show-text="false" />

      <!-- 题目 -->
      <div class="question-card">
        <div class="q-meta">
          <el-tag size="small" :type="typeTag(currentQ.type)">{{ typeLabel(currentQ.type) }}</el-tag>
          <el-tag v-if="currentQ.is_real_exam" size="small" type="danger">真题</el-tag>
          <el-tag v-if="currentQ.prediction_tags" size="small" type="warning">{{ currentQ.prediction_tags.join('/') }}</el-tag>
          <span class="q-points">{{ typeScore(currentQ.type) }}分</span>
        </div>
        <div class="q-stem">{{ currentQ.stem }}</div>
        <div class="q-options">
          <div
            v-for="opt in currentQ.options"
            :key="opt.key"
            class="q-option"
            :class="{ selected: isSelected(opt.key) }"
            @click="selectOption(opt.key)"
          >
            <span class="opt-key">{{ opt.key }}</span>
            <span class="opt-text">{{ opt.text }}</span>
          </div>
        </div>
      </div>

      <!-- 导航 -->
      <div class="exam-nav">
        <el-button @click="prev" :disabled="current === 0">‹ 上一题</el-button>
        <span class="answered-count">已答 {{ answeredCount }} / {{ questions.length }}</span>
        <el-button type="primary" @click="next">
          {{ current < questions.length - 1 ? '下一题 ›' : '完成答题' }}
        </el-button>
      </div>

      <!-- 答题卡 -->
      <div class="answer-card">
        <div class="ac-title">答题卡（点击跳转）</div>
        <div class="ac-grid">
          <span
            v-for="(q, i) in questions"
            :key="q.id"
            class="ac-cell"
            :class="{ answered: answersMap[q.id], current: i === current }"
            @click="current = i"
          >{{ i + 1 }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { Timer } from 'lucide-vue-next'
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { examApi } from '../../api'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const session = ref(null)
const questions = ref([])
const current = ref(0)
const userAnswers = reactive({}) // {question_id: answer}
const timeLeft = ref(90 * 60)
let timer = null

const currentQ = computed(() => questions.value[current.value] || {})
const progressPct = computed(() =>
  questions.value.length ? Math.round(((current.value + 1) / questions.value.length) * 100) : 0
)
const answeredCount = computed(() =>
  questions.value.filter((q) => userAnswers[q.id]).length
)
const answersMap = computed(() => {
  const m = {}
  questions.value.forEach((q) => { m[q.id] = !!userAnswers[q.id] })
  return m
})

const modeLabel = (m) => ({ predict: '智能押题', exam: '全真模考', real: '历年真题' }[m] || m)
const typeLabel = (t) => ({ single: '单选', multiple: '多选', judge: '判断' }[t] || t)
const typeTag = (t) => ({ single: 'primary', multiple: 'success', judge: 'warning' }[t] || '')
const typeScore = (t) => ({ single: 0.5, multiple: 1.0, judge: 0.5 }[t] || 0.5)
const formatTime = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

const isSelected = (key) => {
  const ans = userAnswers[currentQ.value.id]
  if (!ans) return false
  return currentQ.value.type === 'multiple' ? ans.includes(key) : ans === key
}

const selectOption = (key) => {
  const q = currentQ.value
  if (q.type === 'multiple') {
    let arr = (userAnswers[q.id] || '').split('').filter(Boolean)
    const idx = arr.indexOf(key)
    if (idx >= 0) arr.splice(idx, 1)
    else arr.push(key)
    userAnswers[q.id] = arr.sort().join('')
  } else {
    userAnswers[q.id] = key
  }
}

const prev = () => { if (current.value > 0) current.value-- }
const next = () => {
  if (current.value < questions.value.length - 1) current.value++
  else confirmSubmit()
}

const confirmSubmit = async () => {
  const unanswered = questions.value.length - answeredCount.value
  const msg = unanswered > 0
    ? `还有 ${unanswered} 题未作答，确定交卷吗？`
    : '确定交卷吗？将自动判分。'
  try {
    await ElMessageBox.confirm(msg, '交卷确认', { type: unanswered > 0 ? 'warning' : 'info' })
    await submit()
  } catch { /* 取消 */ }
}

const submit = async () => {
  if (timer) clearInterval(timer)
  loading.value = true
  try {
    const answers = questions.value
      .filter((q) => userAnswers[q.id])
      .map((q) => ({ question_id: q.id, user_answer: userAnswers[q.id] }))
    const res = await examApi.submitExam({ session_id: session.value.session_id, answers })
    // 缓存结果给结果页展示
    sessionStorage.setItem('last_exam_result', JSON.stringify(res))
    router.replace({ name: 'exam-result', params: { id: session.value.session_id } })
  } catch (e) {
    ElMessage.error('交卷失败：' + e.message)
    loading.value = false
  }
}

const start = async () => {
  loading.value = true
  try {
    const mode = route.query.mode || 'exam'
    const level = route.query.level || 'four'
    const count = Number(route.query.count) || 50
    const focusWeak = route.query.focus_weak === '1'
    const res = await examApi.startExam({ mode, level, count, focus_weak: focusWeak })
    session.value = res
    questions.value = res.questions
    // 倒计时
    timeLeft.value = (res.duration_min || 90) * 60
    timer = setInterval(() => {
      timeLeft.value--
      if (timeLeft.value <= 0) {
        ElMessage.warning('考试时间到，自动交卷')
        submit()
      }
    }, 1000)
  } catch (e) {
    ElMessage.error(e.message)
    router.back()
  } finally {
    loading.value = false
  }
}

onMounted(start)
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.exam-paper { max-width: 800px; }
.loading-text { text-align: center; padding: 80px; color: var(--text-secondary); }
.exam-topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.topbar-left, .topbar-right { display: flex; align-items: center; gap: 12px; }
.exam-mode { font-size: 14px; font-weight: 600; color: var(--accent); }
.q-progress { font-size: 14px; color: var(--text-secondary); }
.timer { font-size: 18px; font-weight: 700; color: var(--text-primary); font-feature-settings: 'tnum'; display: inline-flex; align-items: center; gap: 4px; }
.timer.warning { color: var(--accent-red); animation: blink 1s infinite; }
@keyframes blink { 50% { opacity: 0.6; } }

.question-card { background: var(--bg-card); border-radius: var(--radius); padding: 28px; box-shadow: var(--shadow-card); margin: 20px 0; }
.q-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
.q-points { margin-left: auto; font-size: 13px; color: var(--accent); font-weight: 600; }
.q-stem { font-size: 16px; line-height: 1.8; color: var(--text-primary); margin-bottom: 24px; }
.q-options { display: flex; flex-direction: column; gap: 10px; }
.q-option { display: flex; align-items: center; gap: 12px; padding: 14px 16px; border: 2px solid var(--border-color); border-radius: var(--radius-sm); cursor: pointer; transition: all 0.15s; }
.q-option:hover { border-color: var(--accent); background: var(--bg-hover); }
.q-option.selected { border-color: var(--accent); background: var(--accent-soft); }
.opt-key { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: var(--bg-hover); color: var(--text-secondary); font-weight: 600; font-size: 14px; flex-shrink: 0; }
.q-option.selected .opt-key { background: var(--accent); color: #fff; }
.opt-text { font-size: 14px; color: var(--text-primary); }

.exam-nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.answered-count { font-size: 13px; color: var(--text-secondary); }

.answer-card { background: var(--bg-card); border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow-card); }
.ac-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--text-secondary); }
.ac-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(36px, 1fr)); gap: 8px; }
.ac-cell { height: 36px; display: flex; align-items: center; justify-content: center; border-radius: 6px; cursor: pointer; background: var(--bg-hover); color: var(--text-secondary); font-size: 13px; border: 2px solid transparent; }
.ac-cell:hover { border-color: var(--accent); }
.ac-cell.answered { background: var(--accent-soft); color: var(--accent); }
.ac-cell.current { background: var(--accent); color: #fff; }
</style>
