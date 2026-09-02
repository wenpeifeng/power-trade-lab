<template>
  <div class="exam-home" v-loading="loading">
    <!-- 顶部：级别选择 + 题型配比 -->
    <div class="exam-header">
      <div>
        <span class="exam-kicker"><Sparkles :size="14" /> EXAM READINESS</span>
        <h2>考试备考中心</h2>
        <p class="hint">按真实统考配比组卷，AI 智能押题，针对高频考点强化</p>
      </div>
      <aside class="exam-level-panel" aria-label="选择备考级别">
        <div class="level-panel-head">
          <span><GraduationCap :size="15" /> 备考等级</span>
          <small>切换后同步组卷规则</small>
        </div>
        <div class="level-switch">
          <button :class="{ active: level === 'four' }" @click="changeLevel('four')">
            <i>四级</i>
            <span><strong>中级工</strong><small>当前主推荐</small></span>
            <Check v-if="level === 'four'" :size="15" />
          </button>
          <button :class="{ active: level === 'three' }" @click="changeLevel('three')">
            <i>三级</i>
            <span><strong>高级工</strong><small>进阶能力认证</small></span>
            <Check v-if="level === 'three'" :size="15" />
          </button>
        </div>
      </aside>
    </div>

    <!-- 真实题型配比 -->
    <div class="blueprint-card" v-if="blueprint">
      <div class="bp-title">真实考试题型配比（{{ blueprint.level_label }}）</div>
      <div class="bp-stats">
        <div class="bp-item single">
          <div class="bp-label">单选题</div>
          <div class="bp-count"><span v-count="blueprint.type_config.single.count">0</span><small>题</small></div>
          <div class="bp-score">{{ (blueprint.type_config.single.count * blueprint.type_config.single.score).toFixed(0) }}分</div>
          <div class="bp-bar"><div class="bp-fill" style="width:50%;background:#2f6bff"></div></div>
        </div>
        <div class="bp-item multiple">
          <div class="bp-label">多选题</div>
          <div class="bp-count"><span v-count="blueprint.type_config.multiple.count">0</span><small>题</small></div>
          <div class="bp-score">{{ (blueprint.type_config.multiple.count * blueprint.type_config.multiple.score).toFixed(0) }}分</div>
          <div class="bp-bar"><div class="bp-fill" style="width:30%;background:#00a870"></div></div>
        </div>
        <div class="bp-item judge">
          <div class="bp-label">判断题</div>
          <div class="bp-count"><span v-count="blueprint.type_config.judge.count">0</span><small>题</small></div>
          <div class="bp-score">{{ (blueprint.type_config.judge.count * blueprint.type_config.judge.score).toFixed(0) }}分</div>
          <div class="bp-bar"><div class="bp-fill" style="width:20%;background:#ff9500"></div></div>
        </div>
      </div>
      <div class="bp-summary">
        共 <strong>{{ blueprint.total_questions }}</strong> 题 · 满分 <strong>{{ blueprint.total_score }}</strong> 分 ·
        及格 <strong>{{ blueprint.pass_score }}</strong> 分 · 时长 <strong>{{ blueprint.duration_min }}</strong> 分钟
      </div>
    </div>

    <!-- 四种考试入口（中级为主，高级可选）-->
    <div class="mode-cards">
      <!-- 历年真题（首要入口）-->
      <div class="mode-card real" @click="startExam('real')">
        <div class="mode-icon"><BookOpen :size="40" /></div>
        <h3>历年真题</h3>
        <p>{{ levelLabel }}真题实战，熟悉真实出题风格与高频考点</p>
        <div class="real-years" v-if="realExamData">
          <span v-for="y in realExamData.years" :key="y.year" class="year-tag">
            {{ y.year }}年 · {{ y.total }}题
          </span>
        </div>
        <div class="mode-btn">开始真题 →</div>
      </div>
      <!-- 智能押题 -->
      <div class="mode-card predict" @click="startExam('predict')">
        <div class="mode-icon"><Sparkles :size="40" /></div>
        <h3>智能押题模考</h3>
        <p>按考点预测权重出题，重点练高频/新增考点</p>
        <div class="mode-btn">开始押题 →</div>
      </div>
      <!-- 标准全真模考 -->
      <div class="mode-card standard" @click="startExam('exam')">
        <div class="mode-icon"><FileText :size="40" /></div>
        <h3>标准全真模考</h3>
        <p>严格按官方题型配比与时长，还原真实统考</p>
        <div class="mode-btn">开始模考 →</div>
      </div>
      <!-- 薄弱点强化 -->
      <div class="mode-card weak" @click="startExam('predict', true)">
        <div class="mode-icon"><Dumbbell :size="40" /></div>
        <h3>薄弱点强化</h3>
        <p>针对你的错题和高频错误知识点，定向突破</p>
        <div class="mode-btn">强化练习 →</div>
      </div>
    </div>

    <!-- 考点预测报告 -->
    <section class="prediction-section" v-if="prediction">
      <h3 class="section-title">{{ prediction.level_label }} 考点预测</h3>
      <p class="section-desc">基于官方权重 + 政策更新趋势 + 历年真题分析</p>
      <div class="prediction-chart">
        <div v-for="m in prediction.modules" :key="m.module" class="pred-item">
          <div class="pred-label">
            <span class="pred-name">{{ m.module }}</span>
            <span class="pred-pct">{{ m.predicted_weight }}%</span>
          </div>
          <div class="pred-bar">
            <div class="pred-official" :style="{ width: m.official_weight + '%' }"></div>
            <div class="pred-boost" :style="{ width: m.prediction_boost + '%' }" v-if="m.prediction_boost"></div>
          </div>
          <div class="pred-meta">
            <span>官方{{ m.official_weight }}%</span>
            <span v-if="m.prediction_boost" class="boost">+预测{{ m.prediction_boost }}%</span>
            <span class="pred-count">{{ m.question_count }}题</span>
          </div>
        </div>
      </div>
      <div class="legend">
        <span><i class="dot official"></i>官方权重</span>
        <span><i class="dot boost"></i>政策预测加成</span>
      </div>
    </section>

    <!-- 历史成绩 -->
    <section class="history-section" v-if="history.length">
      <h3 class="section-title">历次模考成绩</h3>
      <div class="history-list">
        <div v-for="h in history" :key="h.id" class="history-item">
          <span class="hist-mode" :class="h.mode">{{ modeLabel(h.mode) }}</span>
          <span class="hist-score" :class="{ pass: h.score >= 60 }">{{ h.score }}分</span>
          <span class="hist-time">{{ fmtTime(h.finished_at) }}</span>
          <router-link :to="`/learn/exam/result/${h.id}`" class="hist-view">查看</router-link>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { BookOpen, Sparkles, FileText, Dumbbell, GraduationCap, Check } from 'lucide-vue-next'
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { examApi } from '../../api'

const router = useRouter()
const loading = ref(false)
const level = ref('four')  // 默认中级，高级可选
const blueprint = ref(null)
const prediction = ref(null)
const history = ref([])
const realExamData = ref(null)

const levelLabel = computed(() =>
  ({ four: '中级工', three: '高级工' }[level.value] || '')
)

const modeLabel = (m) => ({ predict: '押题', exam: '模考', real: '真题', study: '练习' }[m] || m)
const fmtTime = (t) => t ? new Date(t).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''

const startExam = (mode, focusWeak = false) => {
  router.push({ name: 'exam-paper', query: { mode, level: level.value, focus_weak: focusWeak ? 1 : 0, count: 50 } })
}
const changeLevel = (nextLevel) => {
  if (level.value === nextLevel) return
  level.value = nextLevel
  loadAll()
}

const loadAll = async () => {
  loading.value = true
  try {
    const [bp, pred, hist, real] = await Promise.all([
      examApi.blueprint(level.value),
      examApi.prediction(level.value),
      examApi.history(),
      examApi.realExamYears(level.value),
    ])
    blueprint.value = bp
    prediction.value = pred
    history.value = hist
    realExamData.value = real
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.exam-home { width:100%; min-height:70vh; }
.exam-header { min-height:190px; display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:42px;align-items:center; margin-bottom: 18px; padding:32px 38px; border:1px solid #d9def5; border-radius:22px; background:radial-gradient(circle at 88% 22%,rgba(99,102,241,.09),transparent 29%),linear-gradient(120deg,#fff,#f7f8ff 60%,#f0f2ff); box-shadow:0 13px 34px rgba(31,41,90,.07); position:relative; overflow:hidden; }
.exam-header::before{content:"";position:absolute;inset:0;background-image:linear-gradient(rgba(89,100,217,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(89,100,217,.035) 1px,transparent 1px);background-size:30px 30px;mask-image:linear-gradient(90deg,transparent 42%,#000)}
.exam-header::after{content:"";position:absolute;width:250px;height:250px;border:32px solid rgba(99,102,241,.045);border-radius:50%;right:-70px;top:-120px}.exam-header>div,.exam-level-panel{position:relative;z-index:1}
.exam-kicker{display:inline-flex;align-items:center;gap:7px;font-size:10px;letter-spacing:.14em;font-weight:850;color:#5d66d9;margin-bottom:8px}
.exam-header h2 { font-size: 25px; letter-spacing:-.025em; color: var(--text-primary); }
.hint { color: var(--text-secondary); font-size: 13px; margin-top: 6px; }
.exam-level-panel{padding:13px;border:1px solid #d9def1;border-radius:16px;background:rgba(255,255,255,.72);box-shadow:0 11px 28px rgba(55,65,135,.075);backdrop-filter:blur(10px)}.level-panel-head{display:flex;align-items:center;justify-content:space-between;padding:0 3px 9px}.level-panel-head>span{display:inline-flex;align-items:center;gap:6px;color:#4f5972;font-size:10px;font-weight:800}.level-panel-head>span svg{color:#5964d9}.level-panel-head>small{color:#9aa0b0;font-size:8px}.level-switch{display:grid;grid-template-columns:1fr 1fr;gap:7px}.level-switch button{min-height:72px;padding:10px;border:1px solid #e2e5f0;border-radius:11px;background:rgba(255,255,255,.7);display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:8px;color:#626a7e;text-align:left;cursor:pointer;transition:transform .2s,border-color .2s,box-shadow .2s,background .2s}.level-switch button:hover{transform:translateY(-2px);border-color:#aeb5ea;background:#fff}.level-switch button.active{color:#333d76;border-color:#8992e7;background:#f2f3ff;box-shadow:inset 0 0 0 1px rgba(89,100,217,.08),0 6px 14px rgba(66,76,171,.09)}.level-switch button>i{width:35px;height:35px;border-radius:10px;display:grid;place-items:center;background:#edf0f5;color:#7d8598;font-style:normal;font-size:10px;font-weight:800}.level-switch button.active>i{color:#fff;background:#5964d9}.level-switch button>span{min-width:0;display:flex;flex-direction:column;gap:3px}.level-switch strong{font-size:11px}.level-switch button small{color:#a0a5b3;font-size:8px;white-space:nowrap}.level-switch button>svg{color:#5964d9}

.blueprint-card { background: rgba(255,255,255,.88); border:1px solid #e5e7f0; border-radius: 18px; padding: 24px; box-shadow:0 9px 25px rgba(31,41,90,.05); margin-bottom: 28px; }
.bp-title { font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 18px; }
.bp-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 16px; }
.bp-item { text-align: center; padding: 16px; background: linear-gradient(145deg,#f7f8fc,#fff); border:1px solid #eceef4; border-radius: 13px; }
.bp-label { font-size: 13px; color: var(--text-secondary); margin-bottom: 8px; }
.bp-count { font-size: 28px; font-weight: 700; color: var(--text-primary); }
.bp-count small { font-size: 13px; font-weight: 400; color: var(--text-secondary); margin-left: 2px; }
.bp-score { font-size: 13px; color: var(--accent); margin: 4px 0 10px; }
.bp-bar { height: 6px; background: var(--border-color); border-radius: 3px; overflow: hidden; }
.bp-fill { height: 100%; border-radius: 3px; animation:barReveal 1s cubic-bezier(.16,1,.3,1) both; transform-origin:left; }
.bp-summary { text-align: center; font-size: 13px; color: var(--text-secondary); padding-top: 12px; border-top: 1px solid var(--border-light); }
.bp-summary strong { color: var(--text-primary); }

.mode-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 36px; }
.mode-card { min-height:236px; background: var(--bg-card); border-radius: 17px; padding: 22px 18px; cursor: pointer; box-shadow:0 8px 23px rgba(31,41,90,.05); transition:transform .3s cubic-bezier(.16,1,.3,1),box-shadow .3s,border-color .3s; border: 1px solid #e5e7ef; text-align: center; position:relative; overflow:hidden; }
.mode-card::before{content:"";position:absolute;width:120px;height:120px;border-radius:50%;right:-70px;top:-70px;background:#eef0ff;transition:transform .35s}.mode-card:hover { transform: translateY(-6px); box-shadow:0 18px 36px rgba(57,66,143,.12); }.mode-card:hover::before{transform:scale(1.28)}
.mode-card.real { background: linear-gradient(135deg, #fff0f5 0%, #ffffff 100%); }
.mode-card.real:hover { border-color: #e74c8b; }
.mode-card.predict:hover { border-color: #2f6bff; }
.mode-card.standard:hover { border-color: #00a870; }
.mode-card.weak:hover { border-color: #ff9500; }
.real-years { display: flex; flex-wrap: wrap; gap: 4px; justify-content: center; margin: 8px 0 12px; }
.year-tag { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #ffe0ec; color: #e74c8b; }
.mode-icon { width:54px;height:54px;border-radius:16px;display:grid;place-items:center;margin:0 auto 14px;color:#5963dc;background:#eef0ff;position:relative;z-index:1; }
.mode-card h3 { font-size: 16px; color: var(--text-primary); margin-bottom: 8px; }
.mode-card p { font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 16px; min-height: 50px; }
.mode-btn { font-size: 14px; font-weight: 600; color: var(--accent); }

.prediction-section, .history-section { background: rgba(255,255,255,.88); border:1px solid #e5e7ef; border-radius: 18px; padding: 25px; box-shadow:0 9px 25px rgba(31,41,90,.05); margin-bottom: 24px; }
.section-title { font-size: 17px; color: var(--text-primary); margin-bottom: 4px; }
.section-desc { font-size: 12px; color: var(--text-tertiary); margin-bottom: 18px; }
.prediction-chart { display: flex; flex-direction: column; gap: 14px; }
.pred-item { }
.pred-label { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px; }
.pred-name { color: var(--text-primary); }
.pred-pct { font-weight: 600; color: var(--accent); }
.pred-bar { height: 18px; background: var(--bg-hover); border-radius: 4px; overflow: hidden; display: flex; }
.pred-official { height: 100%; background: var(--accent); transition: width 0.5s; }
.pred-boost { height: 100%; background: var(--accent-orange); opacity: 0.8; }
.pred-meta { display: flex; gap: 12px; font-size: 11px; color: var(--text-tertiary); margin-top: 3px; }
.pred-meta .boost { color: var(--accent-orange); }
.pred-count { margin-left: auto; }
.legend { display: flex; gap: 16px; margin-top: 14px; font-size: 12px; color: var(--text-tertiary); }
.legend span { display: flex; align-items: center; gap: 4px; }
.legend .dot { width: 10px; height: 10px; border-radius: 2px; }
.legend .dot.official { background: var(--accent); }
.legend .dot.boost { background: var(--accent-orange); }

.history-list { display: flex; flex-direction: column; }
.history-item { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border-light); font-size: 13px; }
.hist-mode { padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.hist-mode.predict { background: #e8f0ff; color: var(--accent); }
.hist-mode.exam { background: #e6fff5; color: var(--accent-green); }
.hist-score { font-weight: 700; font-size: 15px; color: var(--accent-red); }
.hist-score.pass { color: var(--accent-green); }
.hist-time { color: var(--text-tertiary); flex: 1; }
.hist-view { color: var(--accent); text-decoration: none; }
@keyframes barReveal{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@media(max-width:980px){.mode-cards{grid-template-columns:1fr 1fr}}
@media(max-width:780px){.exam-header{grid-template-columns:1fr;padding:26px 22px;gap:22px}.exam-level-panel{width:100%}}
@media(max-width:640px){.level-switch{grid-template-columns:1fr}.bp-stats,.mode-cards{grid-template-columns:1fr}.mode-card{min-height:210px}}
@media(prefers-reduced-motion:reduce){.bp-fill{animation:none}.mode-card{transition:none}}
</style>
