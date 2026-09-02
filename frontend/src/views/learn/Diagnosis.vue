<template>
  <div class="diagnosis-page" v-loading="loading">
    <!-- 未开始：说明 -->
    <div v-if="!started && !result" class="intro">
      <div class="intro-icon"><Compass :size="56" /></div>
      <h2>能力诊断</h2>
      <p>8道梯度题（3基础+3进阶+2老手），约3分钟</p>
      <p class="intro-tip">如实作答，系统将判定你的层级并推荐学习路径</p>
      <el-button type="primary" size="large" @click="start">开始诊断</el-button>
    </div>

    <!-- 答题中 -->
    <div v-else-if="started && !result" class="quiz">
      <div class="quiz-topbar">
        <span>第 {{ idx + 1 }} / {{ questions.length }} 题</span>
        <el-progress :percentage="progress" :stroke-width="4" color="#2f6bff" :show-text="false" />
        <span class="tier-tag" :class="currentQ.tier">{{ tierLabel(currentQ.tier) }}</span>
      </div>
      <div class="q-card">
        <div class="q-stem">{{ currentQ.stem }}</div>
        <div class="q-options">
          <div
            v-for="opt in currentQ.options"
            :key="opt.key"
            class="q-opt"
            :class="{ selected: selected === opt.key }"
            @click="selected = opt.key"
          >
            <span class="opt-key">{{ opt.key }}</span>
            <span>{{ opt.text }}</span>
          </div>
        </div>
      </div>
      <div class="quiz-actions">
        <el-button type="primary" :disabled="!selected" @click="next">下一题 →</el-button>
      </div>
    </div>

    <!-- 诊断结果 -->
    <div v-else-if="result" class="result">
      <div class="result-icon"><component :is="levelIcon(result.level)" :size="64" /></div>
      <div class="result-level" :class="result.level">{{ result.level }} · {{ result.level_label }}</div>
      <p class="result-reason">{{ result.reason }}</p>
      <div class="result-scores">
        <div class="score-item">
          <div class="score-label">基础概念</div>
          <div class="score-bar"><div class="score-fill" :style="{ width: result.tier_rates.basic + '%', background: '#00a870' }"></div></div>
          <div class="score-pct">{{ result.tier_rates.basic }}%</div>
        </div>
        <div class="score-item">
          <div class="score-label">进阶实操</div>
          <div class="score-bar"><div class="score-fill" :style="{ width: result.tier_rates.intermediate + '%', background: '#2f6bff' }"></div></div>
          <div class="score-pct">{{ result.tier_rates.intermediate }}%</div>
        </div>
        <div class="score-item">
          <div class="score-label">政策敏感</div>
          <div class="score-bar"><div class="score-fill" :style="{ width: result.tier_rates.advanced + '%', background: '#ff9500' }"></div></div>
          <div class="score-pct">{{ result.tier_rates.advanced }}%</div>
        </div>
      </div>
      <div class="result-actions">
        <el-button type="primary" size="large" @click="$router.replace('/learn/study')">
          进入我的学习路径 →
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Compass, Sprout, BookOpen, Zap } from 'lucide-vue-next'
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { studyApi } from '../../api'

const router = useRouter()
const loading = ref(false)
const started = ref(false)
const result = ref(null)
const questions = ref([])
const idx = ref(0)
const selected = ref('')
const answers = ref([])

const currentQ = computed(() => questions.value[idx.value] || {})
const progress = computed(() =>
  questions.value.length ? Math.round((idx.value / questions.value.length) * 100) : 0
)

const tierLabel = (t) => ({ basic: '基础', intermediate: '进阶', advanced: '老手' }[t] || t)
const levelIcon = (l) => ({ L1: Sprout, L2: BookOpen, L3: Zap }[l] || Sprout)

const start = async () => {
  loading.value = true
  try {
    const data = await studyApi.diagnosisPaper()
    questions.value = data.questions
    started.value = true
    idx.value = 0
    selected.value = ''
    answers.value = []
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

const next = async () => {
  answers.value.push({
    question_id: currentQ.value.id,
    user_answer: selected.value,
    tier: currentQ.value.tier,
  })
  if (idx.value < questions.value.length - 1) {
    idx.value++
    selected.value = ''
  } else {
    // 提交评估
    loading.value = true
    try {
      result.value = await studyApi.evaluate(answers.value)
      started.value = false
    } catch (e) {
      ElMessage.error(e.message)
    } finally {
      loading.value = false
    }
  }
}

onMounted(() => {
  // 直接进入诊断
  start()
})
</script>

<style scoped>
.diagnosis-page { max-width: 680px; min-height: 70vh; }

/* 介绍 */
.intro { text-align: center; padding: 80px 20px; }
.intro-icon { font-size: 56px; margin-bottom: 20px; }
.intro h2 { font-size: 24px; color: var(--text-primary); margin-bottom: 12px; }
.intro p { color: var(--text-secondary); font-size: 14px; margin-bottom: 8px; }
.intro-tip { color: var(--text-tertiary) !important; font-size: 13px !important; margin-bottom: 28px !important; }

/* 答题 */
.quiz-topbar { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
.quiz-topbar > span:first-child { font-size: 14px; color: var(--text-secondary); white-space: nowrap; }
.tier-tag { font-size: 12px; padding: 2px 10px; border-radius: 10px; white-space: nowrap; }
.tier-tag.basic { background: #e6fff5; color: #00a870; }
.tier-tag.intermediate { background: #e8f0ff; color: #2f6bff; }
.tier-tag.advanced { background: #fff5e6; color: #ff9500; }
.q-card { background: var(--bg-card); border-radius: var(--radius); padding: 28px; box-shadow: var(--shadow-card); margin-bottom: 20px; }
.q-stem { font-size: 16px; line-height: 1.8; color: var(--text-primary); margin-bottom: 24px; }
.q-options { display: flex; flex-direction: column; gap: 10px; }
.q-opt { display: flex; align-items: center; gap: 12px; padding: 14px 16px; border: 2px solid var(--border-color); border-radius: var(--radius-sm); cursor: pointer; transition: all 0.15s; }
.q-opt:hover { border-color: var(--accent); background: var(--bg-hover); }
.q-opt.selected { border-color: var(--accent); background: var(--accent-soft); }
.opt-key { width: 28px; height: 28px; border-radius: 50%; background: var(--bg-hover); color: var(--text-secondary); display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 14px; }
.q-opt.selected .opt-key { background: var(--accent); color: #fff; }
.quiz-actions { text-align: center; }

/* 结果 */
.result { text-align: center; padding: 40px 20px; }
.result-icon { font-size: 64px; margin-bottom: 16px; }
.result-level { font-size: 28px; font-weight: 800; margin-bottom: 12px; }
.result-level.L1 { color: #00a870; }
.result-level.L2 { color: #2f6bff; }
.result-level.L3 { color: #ff9500; }
.result-reason { color: var(--text-secondary); font-size: 14px; margin-bottom: 32px; line-height: 1.6; }
.result-scores { display: flex; flex-direction: column; gap: 16px; max-width: 400px; margin: 0 auto 32px; }
.score-item { text-align: left; }
.score-label { font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }
.score-bar { height: 20px; background: var(--bg-hover); border-radius: 4px; overflow: hidden; }
.score-fill { height: 100%; border-radius: 4px; transition: width 0.6s; }
.score-pct { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-top: 4px; text-align: right; }
.result-actions { margin-top: 20px; }
</style>
