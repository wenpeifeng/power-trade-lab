<template>
  <div class="quiz-page" v-loading="loading">
    <!-- 设置面板：未开始时显示 -->
    <div v-if="!started" class="setup-panel">
      <div class="setup-heading">
        <span class="setup-kicker">ADAPTIVE PRACTICE</span>
        <h2>生成你的练习组合</h2>
        <p>按题量、题型、难度与知识模块组合；作答反馈会自动回流到错题复盘。</p>
      </div>
      <div class="setup-form">
        <div class="form-row">
          <label>题量</label>
          <el-radio-group v-model="config.count">
            <el-radio-button :value="10">10题</el-radio-button>
            <el-radio-button :value="20">20题</el-radio-button>
            <el-radio-button :value="50">50题</el-radio-button>
          </el-radio-group>
        </div>
        <div class="form-row">
          <label>题型</label>
          <el-radio-group v-model="config.type">
            <el-radio-button value="">全部</el-radio-button>
            <el-radio-button value="single">单选</el-radio-button>
            <el-radio-button value="multiple">多选</el-radio-button>
            <el-radio-button value="judge">判断</el-radio-button>
          </el-radio-group>
        </div>
        <div class="form-row">
          <label>难度</label>
          <el-radio-group v-model="config.difficulty">
            <el-radio-button :value="null">全部</el-radio-button>
            <el-radio-button :value="1">简单</el-radio-button>
            <el-radio-button :value="2">中等</el-radio-button>
            <el-radio-button :value="3">困难</el-radio-button>
          </el-radio-group>
        </div>
        <div class="form-row">
          <label>知识点</label>
          <el-select v-model="config.knowledge_point_id" placeholder="全部知识点" clearable style="width: 240px">
            <el-option v-for="kp in knowledgeTree" :key="kp.id" :label="kp.name" :value="kp.id" />
          </el-select>
        </div>
        <el-button type="primary" size="large" @click="startQuiz" :loading="loading">
          开始答题
        </el-button>
      </div>
    </div>

    <!-- 答题区 -->
    <div v-else-if="!finished" class="quiz-main">
      <!-- 进度条 -->
      <div class="quiz-topbar">
        <span class="q-progress">第 {{ current + 1 }} / {{ questions.length }} 题</span>
        <div class="progress-wrap">
          <el-progress :percentage="progressPercent" :stroke-width="6" color="#2f6bff" />
        </div>
        <span v-if="examMode" class="q-timer"><Timer :size="16" /> {{ formatTime(timeLeft) }}</span>
      </div>

      <!-- 题目 -->
      <div class="question-card">
        <div class="q-meta">
          <el-tag size="small" :type="typeTag(currentQ.type)">{{ typeLabel(currentQ.type) }}</el-tag>
          <el-tag size="small" type="info">难度 {{ currentQ.difficulty }}</el-tag>
        </div>
        <div class="q-stem">{{ currentQ.stem }}</div>

        <!-- 选项 -->
        <div class="q-options">
          <div
            v-for="opt in currentQ.options"
            :key="opt.key"
            class="q-option"
            :class="optionClass(opt.key)"
            @click="selectOption(opt.key)"
          >
            <span class="opt-key">{{ opt.key }}</span>
            <span class="opt-text">{{ opt.text }}</span>
          </div>
        </div>

        <!-- 答案反馈 -->
        <transition name="fade">
          <div v-if="answered" class="q-feedback" :class="{ correct: lastResult.correct, wrong: !lastResult.correct }">
            <div class="feedback-head">
              <span>{{ lastResult.correct ? '答对了！' : '答错了' }}</span>
              <span class="feedback-answer">正确答案：{{ lastResult.correct_answer }}</span>
            </div>
            <div v-if="lastResult.analysis" class="feedback-analysis">
              {{ lastResult.analysis }}
            </div>
          </div>
        </transition>
      </div>

      <!-- 操作栏 -->
      <div class="quiz-actions">
        <el-button @click="toggleMark">
          {{ marked.has(currentQ.id) ? '已标记' : '标记' }}
        </el-button>
        <el-button v-if="!answered" type="primary" :disabled="!userAnswer" @click="submitAnswer">
          提交答案
        </el-button>
        <el-button v-else type="primary" @click="nextQuestion">
          {{ current < questions.length - 1 ? '下一题 →' : '完成 →' }}
        </el-button>
      </div>

      <!-- 答题卡 -->
      <div class="answer-card">
        <div class="ac-title">答题卡</div>
        <div class="ac-grid">
          <span
            v-for="(q, i) in questions"
            :key="q.id"
            class="ac-cell"
            :class="cellClass(i)"
            @click="jumpTo(i)"
          >{{ i + 1 }}</span>
        </div>
        <div class="ac-legend">
          <span><i class="dot current"></i>当前</span>
          <span><i class="dot done"></i>已答</span>
          <span><i class="dot wrong"></i>错误</span>
          <span><i class="dot marked"></i>标记</span>
        </div>
      </div>
    </div>

    <!-- 结果页 -->
    <div v-else class="result-page">
      <div class="result-score">
        <div class="score-num" v-count="resultStats.correct">0</div>
        <div class="score-label">/ <span v-count="resultStats.total">0</span> 正确</div>
        <div class="score-rate"><span v-count="resultStats.rate">0</span>%</div>
      </div>
      <div class="result-actions">
        <el-button @click="restart">再来一组</el-button>
        <el-button type="primary" @click="$router.push('/learn/wrong')">查看错题本</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Timer } from 'lucide-vue-next'
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { learnApi, studyApi } from '../../api'

const route = useRoute()

const loading = ref(false)
const started = ref(false)
const finished = ref(false)
const questions = ref([])
const current = ref(0)
const config = ref({ count: 10, type: '', difficulty: null, knowledge_point_id: null, province: '' })
const knowledgeTree = ref([])

// 答题状态
const userAnswer = ref('')
const selectedKeys = ref([]) // 多选
const answered = ref(false)
const lastResult = ref(null)
const marked = ref(new Set())
const results = ref([]) // 每题结果

// 考试计时
const examMode = ref(false)
const timeLeft = ref(0)
let timer = null

const currentQ = computed(() => questions.value[current.value] || {})
const progressPercent = computed(() =>
  questions.value.length ? Math.round(((current.value) / questions.value.length) * 100) : 0
)

const resultStats = computed(() => {
  const correct = results.value.filter((r) => r.correct).length
  return {
    correct,
    total: results.value.length,
    rate: results.value.length ? Math.round((correct / results.value.length) * 100) : 0,
  }
})

const typeLabel = (t) => ({ single: '单选题', multiple: '多选题', judge: '判断题' }[t] || t)
const typeTag = (t) => ({ single: 'primary', multiple: 'success', judge: 'warning' }[t] || '')
const formatTime = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

const startQuiz = async () => {
  loading.value = true
  try {
    const params = {
      count: config.value.count,
      type: config.value.type || undefined,
      difficulty: config.value.difficulty || undefined,
      knowledge_point_id: config.value.knowledge_point_id || undefined,
      province: config.value.province || undefined,
    }
    questions.value = await learnApi.quiz(params)
    if (!questions.value.length) {
      ElMessage.warning('该筛选条件下暂无题目，试试放宽省份/难度')
      return
    }
    // 重置状态
    current.value = 0
    userAnswer.value = ''
    selectedKeys.value = []
    answered.value = false
    marked.value = new Set()
    results.value = []
    started.value = true
    finished.value = false

    if (examMode.value) {
      timeLeft.value = 90 * 60
      timer = setInterval(() => {
        timeLeft.value--
        if (timeLeft.value <= 0) finishQuiz()
      }, 1000)
    }
  } catch (e) {
    // 404 或空结果：定向练习(?kp=)时该知识点可能无题，给出明确提示而非静默失败
    const status = e.response?.status || e.status
    if (status === 404 || /404|not found/i.test(e.message || '')) {
      ElMessage.error('该筛选条件下暂无题目，试试放宽省份/难度')
    } else {
      ElMessage.error(e.message || '获取题目失败，请稍后重试')
    }
  } finally {
    loading.value = false
  }
}

const selectOption = (key) => {
  if (answered.value) return
  if (currentQ.value.type === 'multiple') {
    const idx = selectedKeys.value.indexOf(key)
    if (idx >= 0) selectedKeys.value.splice(idx, 1)
    else selectedKeys.value.push(key)
    userAnswer.value = [...selectedKeys.value].sort().join('')
  } else {
    userAnswer.value = key
    selectedKeys.value = [key]
  }
}

const optionClass = (key) => {
  const selected = currentQ.value.type === 'multiple'
    ? selectedKeys.value.includes(key)
    : userAnswer.value === key
  let cls = selected ? 'selected' : ''
  if (answered.value && lastResult.value) {
    const correctKeys = lastResult.value.correct_answer.replace(/\s/g, '').split('')
    if (correctKeys.includes(key)) cls += ' show-correct'
    else if (selected) cls += ' show-wrong'
  }
  return cls
}

const submitAnswer = async () => {
  if (!userAnswer.value) {
    ElMessage.warning('请先选择答案')
    return
  }
  try {
    lastResult.value = await learnApi.answer({
      question_id: currentQ.value.id,
      user_answer: userAnswer.value,
    })
    answered.value = true
    results.value[current.value] = {
      question_id: currentQ.value.id,
      correct: lastResult.value.correct,
      user_answer: userAnswer.value,
    }
  } catch (e) {
    ElMessage.error(e.message)
  }
}

const nextQuestion = () => {
  if (current.value < questions.value.length - 1) {
    current.value++
    resetCurrent()
  } else {
    finishQuiz()
  }
}

const finishQuiz = () => {
  if (timer) clearInterval(timer)
  finished.value = true
  if (examMode.value) {
    ElMessage.success(`考试完成！正确率 ${resultStats.value.rate}%`)
  }
}

const jumpTo = (i) => {
  current.value = i
  resetCurrent()
}

const resetCurrent = () => {
  userAnswer.value = ''
  selectedKeys.value = []
  answered.value = false
  lastResult.value = null
}

const toggleMark = () => {
  if (marked.value.has(currentQ.value.id)) marked.value.delete(currentQ.value.id)
  else marked.value.add(currentQ.value.id)
}

const restart = () => {
  started.value = false
  finished.value = false
}

const cellClass = (i) => {
  const cls = []
  if (i === current.value) cls.push('current')
  if (results.value[i]) cls.push(results.value[i].correct ? 'done' : 'wrong')
  if (marked.value.has(questions.value[i].id)) cls.push('marked')
  return cls
}

onMounted(async () => {
  // 读取URL参数
  if (route.query.count) config.value.count = Number(route.query.count)
  // ?kp= 既支持数字 id（如 KnowledgeBook 的"练本节"传 12），也支持 code 字符串
  // （如外部分享 mid_long_term）。数字直接用；非数字待 knowledgeTree 加载后
  // 通过 code→id 映射解析（见下方 try 块），避免 Number('mid_long_term')=NaN
  // 静默回退到默认题集。
  const kpParam = route.query.kp
  if (kpParam !== undefined && kpParam !== null && kpParam !== '') {
    const num = Number(kpParam)
    if (Number.isInteger(num) && num > 0) {
      config.value.knowledge_point_id = num
    }
  }
  if (route.query.difficulty) config.value.difficulty = Number(route.query.difficulty)
  if (route.query.province) config.value.province = route.query.province
  if (route.query.exam) examMode.value = true
  try {
    knowledgeTree.value = await learnApi.knowledgeTree()
    // 非数字 kp code → 经知识点树解析为 id（外部分享深链场景）
    if (kpParam && config.value.knowledge_point_id == null) {
      const codeMap = new Map()
      for (const kp of knowledgeTree.value) {
        if (kp.code) codeMap.set(String(kp.code), kp.id)
      }
      const resolved = codeMap.get(String(kpParam))
      if (resolved) {
        config.value.knowledge_point_id = resolved
      } else {
        // code 未命中任何知识点：提示用户，但保留默认题集的优雅回退
        ElMessage.warning(`未找到知识点：${kpParam}`)
      }
    }
    // 读取用户偏好作为默认值（URL参数优先）
    // 注意：通过 ?kp= 进入的"练本节"定向练习不应被省份/难度偏好收窄
    // —— 用户明确想要该知识点的题目，偏好筛选可能让结果集为零导致 404。
    const profile = await studyApi.profile()
    if (!route.query.kp && !route.query.difficulty && profile.preferred_difficulty > 0) {
      config.value.difficulty = profile.preferred_difficulty
    }
    // 不把 profile.home_province 作为省份硬过滤：设置面板没有省份控件，
    // 用户无从察觉/清除该过滤，且后端默认省份可能无题导致 404 死循环。
    // 省份仅由 ?province= 深链显式带入（见上方 route.query.province 分支）。
  } catch (e) {
    console.error(e)
  }
  // 若带参数则自动开始
  if (route.query.count || route.query.kp || route.query.exam) {
    startQuiz()
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.quiz-page { min-height: 70vh; }
/* 设置面板 */
.setup-panel {
  background: linear-gradient(120deg,#fff 0%,#fff 64%,#f2f4ff 100%);
  border:1px solid #e1e5f2;
  border-radius: 23px;
  padding: 38px 42px 42px;
  box-shadow:0 18px 44px rgba(31,41,90,.08);
  max-width: 920px;
  margin: 0 auto;
  position:relative;
  overflow:hidden;
}
.setup-panel::after{content:"";position:absolute;width:250px;height:250px;border:30px solid rgba(99,102,241,.055);border-radius:50%;right:-95px;top:-115px;pointer-events:none}
.setup-heading{position:relative;z-index:1;margin-bottom:30px;padding-bottom:22px;border-bottom:1px solid #eceef4}
.setup-kicker{display:block;font-size:10px;font-weight:850;letter-spacing:.15em;color:#5d66d9;margin-bottom:7px}
.setup-panel h2 { margin:0 0 7px; font-size:25px;letter-spacing:-.025em;color: var(--text-primary); }
.setup-heading p{font-size:12px;color:#81889b}
.setup-form { display:grid;grid-template-columns:1fr 1fr;gap: 22px 28px;position:relative;z-index:1 }
.form-row { display: flex; align-items: center; gap: 14px;min-width:0 }
.form-row label { width: 60px; color: var(--text-secondary); font-size: 14px; }
.setup-form .el-button { grid-column:span 2;justify-self:center;margin-top:10px;min-width:220px;border-radius:11px;box-shadow:0 9px 22px rgba(79,70,229,.18) }
.setup-form :deep(.el-radio-button__inner){padding-inline:13px}

/* 答题区 */
.quiz-main{max-width:960px;margin:0 auto}
.quiz-topbar {
  display: flex; align-items: center; gap: 16px; margin-bottom: 20px;
}
.q-progress { font-size: 14px; color: var(--text-secondary); white-space: nowrap; }
.progress-wrap { flex: 1; }
.q-timer { font-size: 15px; color: var(--accent-orange); font-weight: 600; white-space: nowrap; }

.question-card {
  background: var(--bg-card);
  border-radius: var(--radius);
  padding: 28px;
  box-shadow: var(--shadow-card);
  margin-bottom: 16px;
}
.q-meta { display: flex; gap: 8px; margin-bottom: 16px; }
.q-stem { font-size: 16px; line-height: 1.8; color: var(--text-primary); margin-bottom: 24px; }
.q-options { display: flex; flex-direction: column; gap: 10px; }
.q-option {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 16px;
  border: 2px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition:border-color .2s,background .2s,transform .2s,box-shadow .2s;
  background: var(--bg-card);
}
.q-option:hover { border-color: var(--accent); background: var(--bg-hover);transform:translateX(4px);box-shadow:0 7px 18px rgba(69,78,155,.08) }
.q-option.selected { border-color: var(--accent); background: var(--accent-soft); }
.q-option.show-correct { border-color: var(--accent-green); background: #e6fff5; }
.q-option.show-wrong { border-color: var(--accent-red); background: #fff0f0; }
.opt-key {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
  background: var(--bg-hover);
  color: var(--text-secondary);
  font-weight: 600; font-size: 14px;
  flex-shrink: 0;
}
.q-option.selected .opt-key { background: var(--accent); color: #fff; }
.q-option.show-correct .opt-key { background: var(--accent-green); color: #fff; }
.q-option.show-wrong .opt-key { background: var(--accent-red); color: #fff; }
.opt-text { font-size: 14px; color: var(--text-primary); }

.q-feedback {
  margin-top: 20px; padding: 16px;
  border-radius: var(--radius-sm);
  border-left: 4px solid;
}
.q-feedback.correct { background: #f0fff7; border-color: var(--accent-green); }
.q-feedback.wrong { background: #fff5f5; border-color: var(--accent-red); }
.feedback-head {
  display: flex; justify-content: space-between;
  font-weight: 600; margin-bottom: 8px; font-size: 14px;
}
.feedback-answer { color: var(--text-secondary); }
@media(max-width:780px){.setup-panel{padding:28px 22px}.setup-form{grid-template-columns:1fr}.setup-form .el-button{grid-column:auto}.form-row{align-items:flex-start;flex-direction:column}.form-row label{width:auto}.quiz-main{max-width:none}}
@media(prefers-reduced-motion:reduce){.q-option{transition:none}}
.feedback-analysis { font-size: 13px; color: var(--text-secondary); line-height: 1.7; }

.quiz-actions {
  display: flex; justify-content: center; gap: 12px; margin-bottom: 24px;
}

/* 答题卡 */
.answer-card {
  background: var(--bg-card);
  border-radius: var(--radius);
  padding: 20px;
  box-shadow: var(--shadow-card);
}
.ac-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--text-secondary); }
.ac-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(36px, 1fr)); gap: 8px; }
.ac-cell {
  height: 36px; display: flex; align-items: center; justify-content: center;
  border-radius: 6px; cursor: pointer;
  background: var(--bg-hover); color: var(--text-secondary);
  font-size: 13px; border: 2px solid transparent;
  transition: all 0.15s;
}
.ac-cell:hover { border-color: var(--accent); }
.ac-cell.current { background: var(--accent); color: #fff; }
.ac-cell.done { background: #d4f5e2; color: var(--accent-green); }
.ac-cell.wrong { background: #ffe0e0; color: var(--accent-red); }
.ac-cell.marked { position: relative; }
.ac-cell.marked::after {
  content: ''; position: absolute; top: -3px; right: -3px; width: 8px; height: 8px;
  border-radius: 50%; background: var(--accent-orange); border: 1px solid var(--bg-card);
}
.ac-legend {
  display: flex; gap: 16px; margin-top: 14px;
  font-size: 12px; color: var(--text-tertiary);
}
.ac-legend span { display: flex; align-items: center; gap: 4px; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.dot.current { background: var(--accent); }
.dot.done { background: #d4f5e2; }
.dot.wrong { background: #ffe0e0; }
.dot.marked { background: var(--accent-orange); }

/* 结果页 */
.result-page { text-align: center; padding: 60px 20px; }
.result-score { margin-bottom: 32px; }
.score-num { font-size: 64px; font-weight: 800; color: var(--accent); line-height: 1; }
.score-label { font-size: 16px; color: var(--text-secondary); margin-top: 8px; }
.score-rate { font-size: 24px; color: var(--accent-green); margin-top: 16px; font-weight: 600; }
.result-actions { display: flex; justify-content: center; gap: 12px; }
</style>
