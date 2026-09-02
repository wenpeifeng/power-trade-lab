<template>
  <div class="exam-result" v-loading="loading">
    <div v-if="result">
      <!-- 得分卡片 -->
      <div class="score-card" :class="{ pass: result.passed }">
        <div class="score-label">{{ result.passed ? '恭喜通过' : '继续加油' }}</div>
        <div class="score-main">
          <span class="score-num">{{ result.score }}</span>
          <span class="score-total">/ {{ result.total_score }}</span>
        </div>
        <div class="score-passline">及格线 {{ result.total_score * 0.6 }} 分</div>
      </div>

      <!-- 答题统计 -->
      <div class="stats-section">
        <h3>答题统计</h3>
        <div class="stats-grid">
          <div class="stat-block single">
            <div class="stat-title">单选题</div>
            <div class="stat-detail">
              <span class="correct">对 {{ result.stats.correct.single }}</span>
              <span class="wrong">错 {{ result.stats.wrong.single }}</span>
            </div>
          </div>
          <div class="stat-block multiple">
            <div class="stat-title">多选题</div>
            <div class="stat-detail">
              <span class="correct">对 {{ result.stats.correct.multiple }}</span>
              <span class="wrong">错 {{ result.stats.wrong.multiple }}</span>
            </div>
          </div>
          <div class="stat-block judge">
            <div class="stat-title">判断题</div>
            <div class="stat-detail">
              <span class="correct">对 {{ result.stats.correct.judge }}</span>
              <span class="wrong">错 {{ result.stats.wrong.judge }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 薄弱点分析 -->
      <div class="weak-section" v-if="result.weak_points?.length">
        <h3>薄弱知识点（错误率 ≥ 40%）</h3>
        <p class="section-desc">这些是你本次考试失分集中的模块，建议针对性复习</p>
        <div class="weak-list">
          <div v-for="(w, i) in result.weak_points" :key="i" class="weak-item">
            <span class="weak-name">{{ w.knowledge_point }}</span>
            <div class="weak-bar-wrap">
              <div class="weak-bar" :style="{ width: w.wrong_rate + '%' }"></div>
              <span class="weak-rate">{{ w.wrong_rate }}% 错误</span>
            </div>
            <span class="weak-detail">{{ w.wrong }}/{{ w.total }}题错</span>
            <el-button size="small" type="primary" class="weak-drill"
              :disabled="!w.knowledge_point_id"
              @click="drillWeak(w)">去练习</el-button>
          </div>
        </div>
      </div>

      <!-- 逐题详情 -->
      <div class="detail-section" v-if="result.questions?.length">
        <h3>逐题详情</h3>
        <div class="q-list">
          <div v-for="(q, i) in result.questions" :key="q.question_id" class="q-item" :class="{ isWrong: !q.correct }">
            <div class="q-head">
              <span class="q-idx">第 {{ i + 1 }} 题</span>
              <span class="q-badge" :class="q.correct ? 'ok' : 'no'">{{ q.correct ? '答对' : '答错' }}</span>
            </div>
            <div class="q-stem">{{ q.stem }}</div>
            <div class="q-options" v-if="q.options?.length">
              <div v-for="opt in q.options" :key="opt.key" class="q-opt" :class="optClass(q, opt.key)">
                <span class="opt-key">{{ opt.key }}</span>
                <span class="opt-text">{{ opt.text }}</span>
                <span v-if="isAnswer(q, opt.key)" class="opt-tag correct">✓ 正确</span>
                <span v-else-if="isMyWrong(q, opt.key)" class="opt-tag wrong">✗ 你选的</span>
              </div>
            </div>
            <div v-if="q.analysis" class="q-analysis">解析：{{ q.analysis }}</div>
          </div>
        </div>
      </div>

      <!-- 操作 -->
      <div class="result-actions">
        <el-button @click="$router.push('/learn/exam')">再考一次</el-button>
        <el-button type="primary" @click="$router.push('/learn/wrong')">复习错题</el-button>
        <el-button @click="goStudyWeak" v-if="result.weak_points?.length">针对性学习</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { examApi } from '../../api'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const result = ref(null)

const goStudyWeak = () => {
  // 跳到学习模式，按最薄弱知识点针对性刷题（weak_points 已按 wrong_rate 倒序）
  const kp = result.value?.weak_points?.[0]?.knowledge_point_id
  router.push({ name: 'learn-quiz', query: kp ? { kp } : {} })
}

// 针对单个薄弱知识点跳转练习
const drillWeak = (w) => {
  if (!w?.knowledge_point_id) return
  router.push({ name: 'learn-quiz', query: { kp: w.knowledge_point_id } })
}

// 逐题对错的选项标注
const isAnswer = (q, key) => (q.answer || '').toUpperCase().includes(String(key).toUpperCase())
const isMyWrong = (q, key) => {
  const ua = (q.user_answer || '').toUpperCase()
  return ua.includes(String(key).toUpperCase()) && !isAnswer(q, key)
}
const optClass = (q, key) => ({ 'is-correct': isAnswer(q, key), 'is-wrong': isMyWrong(q, key) })

onMounted(async () => {
  // 优先按 session id 从后端重取完整结果（支持从历史记录进入回看逐题对错）
  const id = route.params.id
  if (id) {
    try {
      result.value = await examApi.examResult(id)
      loading.value = false
      return
    } catch (e) { /* 落到本地缓存 */ }
  }
  // 兜底：刚交卷时缓存的结果
  const cached = sessionStorage.getItem('last_exam_result')
  if (cached) {
    result.value = JSON.parse(cached)
    loading.value = false
  } else {
    ElMessage.info('请从考试入口重新开始')
    router.replace('/learn/exam')
  }
})

// 交卷页跳转前存一下结果
// (在 ExamPaper.vue submit 成功后存 sessionStorage)
</script>

<style scoped>
.exam-result { max-width: 700px; }
.score-card { text-align: center; padding: 40px 24px; background: var(--bg-card); border-radius: var(--radius); box-shadow: var(--shadow-card); margin-bottom: 24px; border-top: 4px solid var(--accent-red); }
.score-card.pass { border-top-color: var(--accent-green); }
.score-label { font-size: 16px; color: var(--text-secondary); margin-bottom: 12px; }
.score-main { margin-bottom: 8px; }
.score-num { font-size: 64px; font-weight: 800; color: var(--accent); }
.score-card.pass .score-num { color: var(--accent-green); }
.score-total { font-size: 24px; color: var(--text-secondary); }
.score-passline { font-size: 13px; color: var(--text-tertiary); }

.stats-section, .weak-section { background: var(--bg-card); border-radius: var(--radius); padding: 24px; box-shadow: var(--shadow-card); margin-bottom: 24px; }
.stats-section h3, .weak-section h3 { font-size: 16px; margin-bottom: 16px; color: var(--text-primary); }
.section-desc { font-size: 13px; color: var(--text-secondary); margin-bottom: 16px; margin-top: -8px; }
.stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.stat-block { padding: 16px; background: var(--bg-hover); border-radius: var(--radius-sm); text-align: center; }
.stat-title { font-size: 14px; color: var(--text-secondary); margin-bottom: 10px; }
.stat-detail { display: flex; justify-content: center; gap: 16px; font-size: 15px; font-weight: 600; }
.stat-detail .correct { color: var(--accent-green); }
.stat-detail .wrong { color: var(--accent-red); }

.weak-list { display: flex; flex-direction: column; gap: 14px; }
.weak-item { display: flex; align-items: center; gap: 12px; }
.weak-name { width: 140px; font-size: 13px; color: var(--text-primary); flex-shrink: 0; }
.weak-bar-wrap { flex: 1; height: 24px; background: var(--bg-hover); border-radius: 4px; position: relative; overflow: hidden; }
.weak-bar { height: 100%; background: var(--accent-red); border-radius: 4px; opacity: 0.7; }
.weak-rate { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); font-size: 12px; color: var(--text-primary); font-weight: 600; }
.weak-detail { font-size: 12px; color: var(--text-tertiary); white-space: nowrap; }
.weak-drill { flex-shrink: 0; }

.result-actions { display: flex; justify-content: center; gap: 12px; margin-top: 32px; }

/* 逐题详情 */
.detail-section { background: var(--bg-card); border-radius: var(--radius); padding: 24px; box-shadow: var(--shadow-card); margin-bottom: 24px; }
.detail-section h3 { font-size: 16px; font-weight: 700; color: var(--text-primary); margin-bottom: 16px; }
.q-list { display: flex; flex-direction: column; gap: 16px; }
.q-item { padding: 16px; border-radius: var(--radius-sm); border: 1px solid var(--border-light); border-left: 4px solid var(--accent-green); }
.q-item.isWrong { border-left-color: var(--accent-red); }
.q-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.q-idx { font-size: 13px; color: var(--text-tertiary); }
.q-badge { font-size: 12px; font-weight: 600; padding: 2px 10px; border-radius: 10px; }
.q-badge.ok { background: rgba(16, 185, 129, 0.12); color: var(--accent-green); }
.q-badge.no { background: rgba(245, 101, 101, 0.12); color: var(--accent-red); }
.q-stem { font-size: 15px; line-height: 1.7; color: var(--text-primary); margin-bottom: 12px; }
.q-options { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
.q-opt { display: flex; align-items: center; gap: 10px; padding: 9px 13px; border-radius: 8px; border: 1px solid var(--border-light); font-size: 14px; color: var(--text-primary); }
.q-opt.is-correct { border-color: var(--accent-green); background: rgba(16, 185, 129, 0.08); }
.q-opt.is-wrong { border-color: var(--accent-red); background: rgba(245, 101, 101, 0.08); }
.q-opt .opt-key { width: 24px; height: 24px; border-radius: 6px; flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center; background: var(--bg-hover); font-weight: 600; font-size: 13px; }
.q-opt.is-correct .opt-key { background: var(--accent-green); color: #fff; }
.q-opt.is-wrong .opt-key { background: var(--accent-red); color: #fff; }
.q-opt .opt-text { flex: 1; }
.q-opt .opt-tag { font-size: 12px; font-weight: 600; flex-shrink: 0; }
.q-opt .opt-tag.correct { color: var(--accent-green); }
.q-opt .opt-tag.wrong { color: var(--accent-red); }
.q-analysis { font-size: 13px; color: var(--text-secondary); line-height: 1.7; padding: 10px 12px; background: var(--bg-hover); border-radius: var(--radius-sm); }
</style>
