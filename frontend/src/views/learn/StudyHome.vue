<template>
  <div class="study-home" v-loading="loading">
    <section v-if="todayPlan?.unit" class="today-mission">
      <div class="mission-copy">
        <span class="mission-kicker">TODAY · 系统已为你排好</span>
        <h2>{{ todayPlan.unit.title }}</h2>
        <p>{{ todayPlan.unit.subtitle }}</p>
        <div class="mission-tasks">
          <span v-for="task in todayPlan.tasks" :key="task.key">
            <CheckCircle2 :size="14" /> {{ task.label }} · {{ task.minutes }}分钟
          </span>
        </div>
      </div>
      <div class="mission-progress">
        <strong><span v-count="todayPlan.completed_units">0</span>/<span v-count="todayPlan.total_units">0</span></strong>
        <small>课程进度</small>
        <el-button type="primary" @click="openLesson(todayPlan.unit.code)">
          {{ todayPlan.unit.progress.status === 'in_progress' ? '继续今日课程' : '开始今日课程' }} →
        </el-button>
      </div>
    </section>

    <!-- 未诊断：引导诊断 -->
    <div v-if="!profile?.diagnosed" class="diagnosis-guide">
      <div class="guide-icon"><Compass :size="56" /></div>
      <h2>先做能力诊断</h2>
      <p>8道梯度题，3分钟判定你是零基础/进阶/老手，系统据此推荐最适合你的学习路径</p>
      <el-button type="primary" size="large" @click="$router.push('/learn/study/diagnosis')">
        开始诊断 →
      </el-button>
    </div>

    <!-- 已诊断：展示对应层级内容 -->
    <template v-else>
      <!-- 层级状态条 -->
      <div class="level-bar">
        <div class="level-info">
          <span class="level-badge" :class="profile.level">{{ profile.level }}</span>
          <span class="level-name">{{ profile.level_label }}</span>
          <span v-if="profile.manual_level" class="manual-tag">手动选择</span>
          <span v-else class="auto-tag">诊断推荐</span>
          <span class="level-province">{{ profile.home_province }}</span>
        </div>
        <div class="level-actions">
          <el-button size="small" @click="showPrefs = true">偏好设置</el-button>
          <el-button size="small" plain @click="$router.push('/learn/study/diagnosis')">重新诊断</el-button>
        </div>
      </div>

      <!-- A4：我的掌握度总览（L1/L2/L3 全可见） -->
      <section v-if="masteryVisible" class="mastery-card">
        <div class="mastery-head">
          <h3>我的掌握度</h3>
          <span class="mastery-hint">掌握度≥60% 解锁下一级学习路径</span>
        </div>
        <div class="mastery-bars">
          <div v-for="kp in masteryList" :key="kp.kp_id" class="mastery-bar">
            <span class="mb-label">{{ kp.name }}</span>
            <div class="mb-track">
              <div class="mb-fill" :style="{ width: kp.mastery_pct + '%', background: masteryColor(kp.mastery_pct) }"></div>
            </div>
            <span class="mb-stat">{{ kp.mastery_pct }}% ({{ kp.correct_attempts }}/{{ kp.total_attempts }})</span>
          </div>
        </div>
      </section>

      <!-- L1 零基础：引导式路线图 -->
      <div v-if="dashboard?.level === 'L1'" class="l1-content">
        <h3>从零开始，循序渐进</h3>
        <p class="section-desc">每学完一个知识点并达标(≥60%)，自动解锁下一步</p>
        <div class="roadmap">
          <div
            v-for="step in dashboard.roadmap"
            :key="step.step"
            class="roadmap-item"
            :class="{ locked: !step.unlocked, done: step.mastery >= 60 }"
          >
            <div class="step-num">{{ step.step }}</div>
            <div class="step-body">
              <div class="step-title">{{ step.title }}</div>
              <div class="step-desc">{{ step.desc }}</div>
              <div class="step-meta">
                <span>{{ step.question_count }}题可练</span>
                <span v-if="step.mastery > 0">掌握{{ step.mastery }}%</span>
              </div>
            </div>
            <el-button
              v-if="step.unlocked && step.question_count > 0"
              size="small" type="primary" plain
              @click="studyStep(step)"
            >{{ step.mastery >= 60 ? '复习' : '开始学习' }}</el-button>
            <span v-else-if="!step.unlocked" class="lock-icon"><Lock :size="18" /></span>
            <span v-else class="lock-icon" style="opacity:0.3">—</span>
          </div>
        </div>
      </div>

      <!-- L2 进阶：系统学习+主省份 -->
      <div v-else-if="dashboard?.level === 'L2'" class="l2-content">
        <h3>系统学习 + {{ dashboard.home_province }}规则深入</h3>
        <div class="l2-grid">
          <div class="l2-main">
            <div class="section-title">交易品种深化</div>
            <div class="module-list">
              <div v-for="m in dashboard.modules" :key="m.id" class="module-item" @click="studyModule(m)">
                <span class="mod-name">{{ m.name }}</span>
                <span class="mod-count">{{ m.question_count }}题</span>
                <span class="mod-go">→</span>
              </div>
            </div>
          </div>
          <div class="l2-side">
            <div class="section-title">主省份：{{ dashboard.home_province }}</div>
            <div class="province-card" v-if="dashboard.home_config">
              <div class="pc-row"><span>电网</span><strong>{{ gridLabel(dashboard.home_config.grid) }}</strong></div>
              <div class="pc-row"><span>现货</span><strong>{{ dashboard.home_config.spot_status }}</strong></div>
              <div class="pc-rule">{{ dashboard.home_config.rule_summary }}</div>
            </div>
            <div class="section-title" style="margin-top:16px">其他省份对比</div>
            <div class="compare-list">
              <div v-for="p in dashboard.other_provinces.slice(0,6)" :key="p.code" class="compare-item">
                <span>{{ p.name }}</span>
                <span class="cmp-status">{{ p.spot_status || '-' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- L3 老手：四功能速查 -->
      <div v-else-if="dashboard?.level === 'L3'" class="l3-content">
        <h3>老手速查 · 只看变化</h3>
        <div class="l3-grid">
          <!-- 最新政策变动 -->
          <div class="l3-card" @click="$router.push('/policy')">
            <div class="l3-head"><ScrollText :size="16" /> 最新政策变动 <span class="l3-count">{{ dashboard.latest_policies.length }}</span></div>
            <div class="l3-list">
              <div v-for="p in dashboard.latest_policies.slice(0,4)" :key="p.id" class="l3-item">
                <span class="l3-cat" :class="p.category">{{ catLabel(p.category) }}</span>
                <span class="l3-title">{{ p.title }}</span>
                <span class="l3-date">{{ p.publish_date }}</span>
              </div>
            </div>
          </div>
          <!-- 省份动态 -->
          <div class="l3-card">
            <div class="l3-head"><MapPinned :size="16" /> 省份动态 · {{ dashboard.home_province }}</div>
            <div class="l3-list">
              <div v-for="p in dashboard.province_dynamics.home.slice(0,4)" :key="p.id" class="l3-item" @click="$router.push('/policy')">
                <span class="l3-title">{{ p.title }}</span>
                <span class="l3-date">{{ p.publish_date }}</span>
              </div>
              <div v-if="!dashboard.province_dynamics.home.length" class="l3-empty">暂无</div>
            </div>
            <div class="l3-head" style="margin-top:10px"><ClipboardList :size="16" /> 其他省份</div>
            <div class="l3-list">
              <div v-for="p in dashboard.province_dynamics.others.slice(0,3)" :key="p.id" class="l3-item" @click="$router.push('/policy')">
                <span class="l3-prov">{{ p.province }}</span>
                <span class="l3-title">{{ p.title }}</span>
              </div>
            </div>
          </div>
          <!-- 新增考点速刷 -->
          <div class="l3-card">
            <div class="l3-head"><Flame :size="16" /> 新增考点速刷 <span class="l3-count">{{ dashboard.new_questions.length }}</span></div>
            <div class="l3-list">
              <div v-for="q in dashboard.new_questions.slice(0,5)" :key="q.id" class="l3-item">
                <span class="l3-tag" v-for="t in (q.prediction_tags||[])" :key="t">{{ t }}</span>
                <span class="l3-title">{{ q.stem }}</span>
              </div>
            </div>
            <el-button size="small" type="warning" plain @click="quizNew">速刷新增考点 →</el-button>
          </div>
          <!-- 情景演练 -->
          <div class="l3-card">
            <div class="l3-head"><Target :size="16" /> 政策情景演练 <span class="l3-count">{{ dashboard.scenario_questions.length }}</span></div>
            <div class="l3-list">
              <div v-for="q in dashboard.scenario_questions.slice(0,4)" :key="q.id" class="l3-item">
                <span class="l3-diff">{{ q.difficulty }}</span>
                <span class="l3-title">{{ q.stem }}</span>
              </div>
            </div>
            <el-button size="small" type="primary" plain @click="quizScenario">开始演练 →</el-button>
          </div>
        </div>
      </div>
    </template>

    <section v-if="guided?.units?.length" class="guided-system">
      <div class="guided-heading">
        <div>
          <span class="mission-kicker">GUIDED PATH · 从小白到可独立复盘</span>
          <h3>完整业务学习路径</h3>
          <p class="section-desc">每课都包含讲解、真实数据观察、即时检查和可保存的业务成果，不再只是刷题。</p>
        </div>
        <div class="guided-total"><span v-count="guided.completed">0</span> / <span v-count="guided.total">0</span> 已完成</div>
      </div>
      <div class="unit-grid">
        <button v-for="unit in guided.units" :key="unit.code" :disabled="!unit.unlocked"
          :class="{ complete: unit.progress.status === 'completed' }" @click="openLesson(unit.code)">
          <span class="unit-order">{{ String(unit.order).padStart(2, '0') }}</span>
          <div>
            <strong>{{ unit.title }}</strong>
            <small>{{ unit.subtitle }}</small>
            <em>{{ unit.duration_min }}分钟 · {{ unit.progress.status === 'completed' ? `查看复盘${unit.progress.wrong_count != null ? ` · 错${unit.progress.wrong_count}题` : ''}` : unit.unlocked ? '可学习' : '待解锁' }}</em>
          </div>
          <ArrowRight :size="17" />
        </button>
      </div>
    </section>

    <!-- 偏好设置面板 -->
    <PrefsPanel v-model="showPrefs" :profile="profile" :provinces="provinces" @changed="loadAll" />
  </div>
</template>

<script setup>
import { Compass, Lock, ScrollText, MapPinned, ClipboardList, Flame, Target, CheckCircle2, ArrowRight } from 'lucide-vue-next'
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { studyApi } from '../../api'
import PrefsPanel from './PrefsPanel.vue'

const router = useRouter()
const loading = ref(false)
const profile = ref(null)
const dashboard = ref(null)
const provinces = ref([])
const guided = ref(null)
const todayPlan = ref(null)
const showPrefs = ref(false)
const masteryList = ref([])        // A4：各知识点掌握度（/study/mastery）
const masteryVisible = ref(false) // A4：拉取失败则隐藏整卡

const gridLabel = (g) => ({ sgcc: '国家电网', csg: '南方电网', impc: '蒙西电网' }[g] || g)
const catLabel = (c) => ({ national: '国家', market: '市场', clearing: '出清', regulation: '规则' }[c] || c)
// A4：掌握度配色 0-40 红 / 40-70 琥珀 / 70+ 绿
const masteryColor = (pct) => pct >= 70 ? '#67c23a' : pct >= 40 ? '#e6a23c' : '#f56c6c'

const studyStep = (step) => {
  const unit = guided.value?.units?.[Math.max(0, step.step - 1)]
  if (unit?.unlocked) openLesson(unit.code)
  else router.push({ name: 'learn-quiz', query: { kp: step.knowledge_point_id, count: 5 } })
}
const openLesson = (code) => router.push({ name: 'study-lesson', params: { code } })
const studyModule = (m) => {
  router.push({ name: 'learn-quiz', query: { kp: m.id, count: 10 } })
}
const quizNew = () => {
  router.push({ name: 'exam-paper', query: { mode: 'predict', level: 'four', count: 10 } })
}
const quizScenario = () => {
  router.push({ name: 'learn-quiz', query: { count: 5 } })
}

const loadAll = async () => {
  loading.value = true
  try {
    profile.value = await studyApi.profile()
    const [provinceData, guidedData, todayData] = await Promise.all([
      studyApi.provinces(), studyApi.guided(), studyApi.today(),
    ])
    provinces.value = provinceData
    guided.value = guidedData
    todayPlan.value = todayData
    if (profile.value.diagnosed) {
      dashboard.value = await studyApi.dashboard()
      // A4：掌握度总览——独立拉取，失败仅隐藏卡片，不影响主流程
      try {
        masteryList.value = await studyApi.mastery()
        masteryVisible.value = masteryList.value.length > 0
      } catch {
        masteryList.value = []
        masteryVisible.value = false
      }
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.study-home { min-height: 70vh; color:var(--text-primary); }
.today-mission { display: flex; justify-content: space-between; gap: 30px; padding: 36px 42px; margin-bottom: 20px; min-height:240px; align-items:center; border-radius: 24px; color: #fff; background: linear-gradient(120deg, #172554, #3f49cb 58%, #6871f0, #3f49cb); background-size:180% 100%; box-shadow: 0 20px 48px rgba(42,55,159,.2); overflow: hidden; position: relative; animation:missionGradient 9s ease-in-out infinite alternate; }
.today-mission::before { content:""; position:absolute; inset:-40% -20%; pointer-events:none; background:linear-gradient(105deg,transparent 42%,rgba(255,255,255,.07) 48%,transparent 54%); transform:translateX(-50%); animation:missionScan 6s ease-in-out infinite; }
.today-mission::after { content:""; width:220px; height:220px; border:2px dashed rgba(255,255,255,.15); border-radius:50%; position:absolute; right:-22px; top:-52px; box-shadow:0 0 0 36px rgba(255,255,255,.035),0 0 0 76px rgba(255,255,255,.022); animation:missionOrbit 18s linear infinite; }
.mission-copy { position: relative; z-index: 1; }.mission-kicker { display:block; font-size:11px; letter-spacing:.14em; font-weight:800; color:#aebaff; margin-bottom:7px; }
.today-mission h2 { margin:0 0 5px; font-size:25px; }.today-mission p { margin:0; color:rgba(255,255,255,.74); font-size:13px; }
.mission-tasks { display:flex; flex-wrap:wrap; gap:14px; margin-top:20px; }.mission-tasks span { display:inline-flex; gap:6px; align-items:center; font-size:12px; color:rgba(255,255,255,.86); }
.mission-progress { position:relative; z-index:1; min-width:185px; min-height:150px; display:flex; flex-direction:column; justify-content:center; align-items:flex-end; isolation:isolate; }.mission-progress::before{content:"";position:absolute;z-index:-1;width:145px;height:145px;right:-12px;top:2px;border:1px solid rgba(255,255,255,.12);border-radius:50%;box-shadow:inset 0 0 34px rgba(132,221,255,.055);animation:progressBreathe 3.8s ease-in-out infinite}.mission-progress::after{content:"";position:absolute;width:7px;height:7px;border-radius:50%;right:63px;top:0;background:#8de2ff;box-shadow:0 0 13px #8de2ff;animation:progressDot 4.8s ease-in-out infinite}.mission-progress strong { font-size:30px; font-variant-numeric:tabular-nums; }.mission-progress small { color:rgba(255,255,255,.65); margin-bottom:14px; }
.guided-system { margin-top:42px; }.guided-heading { display:flex; justify-content:space-between; align-items:end; margin-bottom:18px; }.guided-heading h3 { margin:4px 0 3px; }.guided-total { color:#5860d9; font-size:13px; font-weight:700; }
.unit-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:11px; }.unit-grid button { min-height:100px; border:1px solid #e5e7f0; background:var(--bg-card); border-radius:15px; padding:18px; text-align:left; display:flex; align-items:center; gap:14px; cursor:pointer; box-shadow:0 7px 20px rgba(31,41,90,.05); color:var(--text-primary); transition:transform .28s cubic-bezier(.16,1,.3,1),border-color .25s,box-shadow .25s; position:relative; overflow:hidden; }
.unit-grid button::before { content:""; position:absolute; width:90px; height:90px; border-radius:50%; right:-54px; top:-54px; background:#eef0ff; transition:transform .35s; }.unit-grid button:hover:not(:disabled) { transform:translateY(-4px); border-color:#aab0ef; box-shadow:0 15px 30px rgba(63,72,153,.11); }.unit-grid button:hover:not(:disabled)::before{transform:scale(1.3)}.unit-grid button:disabled { opacity:.46; cursor:not-allowed; }.unit-grid button.complete { border-color:#9bdac8; background:linear-gradient(135deg,#fff,#f6fdfb); }
.unit-order { width:36px; height:36px; border-radius:10px; display:grid; place-items:center; flex:none; background:#eef0ff; color:#555ed8; font-size:12px; font-weight:800; }.unit-grid button.complete .unit-order{background:#e5f7ef;color:#19835f}
.unit-grid button div { flex:1; display:flex; flex-direction:column; gap:4px; position:relative;z-index:1 }.unit-grid strong { font-size:14px; }.unit-grid small { color:var(--text-secondary); }.unit-grid em { font-style:normal; color:var(--text-tertiary); font-size:11px; }.unit-grid button>svg{position:relative;z-index:1;transition:transform .22s}.unit-grid button:hover>svg{transform:translateX(4px)}
@media(max-width:760px){.today-mission{flex-direction:column}.mission-progress{align-items:flex-start}.unit-grid{grid-template-columns:1fr}}

/* 诊断引导 */
.diagnosis-guide { text-align: center; padding: 60px 20px; }
.guide-icon { font-size: 56px; margin-bottom: 20px; }
.diagnosis-guide h2 { font-size: 24px; color: var(--text-primary); margin-bottom: 12px; }
.diagnosis-guide p { color: var(--text-secondary); margin-bottom: 28px; font-size: 14px; }

/* 层级状态条 */
.level-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; padding: 15px 20px; background: rgba(255,255,255,.88); border:1px solid #e7e9f1; border-radius: 15px; box-shadow: 0 7px 20px rgba(31,41,90,.045); }
.level-info { display: flex; align-items: center; gap: 12px; }
.level-badge { padding: 4px 12px; border-radius: 12px; font-size: 13px; font-weight: 700; color: #fff; }
.level-badge.L1 { background: #00a870; }
.level-badge.L2 { background: #2f6bff; }
.level-badge.L3 { background: #ff9500; }
.level-name { font-size: 16px; font-weight: 600; color: var(--text-primary); }
.level-reason { font-size: 13px; color: var(--text-secondary); }
.level-actions { display: flex; gap: 8px; }

/* 通用标题 */
h3 { font-size: 20px; color: var(--text-primary); margin-bottom: 6px; }
.section-desc { font-size: 13px; color: var(--text-secondary); margin-bottom: 20px; }
.section-title { font-size: 14px; font-weight: 600; color: var(--text-secondary); margin-bottom: 12px; }

/* L1 路线图 */
.roadmap { display: flex; flex-direction: column; gap: 12px; }
.roadmap-item { display: flex; align-items: center; gap: 16px; padding: 16px 20px; background: var(--bg-card); border-radius: var(--radius); box-shadow: var(--shadow-card); border-left: 4px solid var(--accent); }
.roadmap-item.locked { opacity: 0.45; border-left-color: var(--text-tertiary); }
.roadmap-item.done { border-left-color: var(--accent-green); }
.step-num { width: 36px; height: 36px; border-radius: 50%; background: var(--accent); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 700; flex-shrink: 0; }
.roadmap-item.done .step-num { background: var(--accent-green); }
.step-body { flex: 1; }
.step-title { font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.step-desc { font-size: 13px; color: var(--text-secondary); margin-bottom: 4px; }
.step-meta { display: flex; gap: 12px; font-size: 12px; color: var(--text-tertiary); }
.lock-icon { font-size: 18px; }

/* L2 */
.l2-grid { display: grid; grid-template-columns: 1fr 300px; gap: 20px; }
.module-list { display: flex; flex-direction: column; gap: 8px; }
.module-item { display: flex; align-items: center; gap: 12px; padding: 14px 18px; background: var(--bg-card); border-radius: var(--radius-sm); box-shadow: var(--shadow-card); cursor: pointer; transition: all 0.15s; border: 1px solid var(--border-light); }
.module-item:hover { border-color: var(--accent); transform: translateX(4px); }
.mod-name { flex: 1; font-size: 14px; color: var(--text-primary); }
.mod-count { font-size: 12px; color: var(--text-secondary); }
.mod-go { color: var(--accent); }
.province-card { background: var(--bg-card); border-radius: var(--radius-sm); padding: 16px; box-shadow: var(--shadow-card); }
.pc-row { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 8px; }
.pc-row span { color: var(--text-secondary); }
.pc-rule { font-size: 13px; color: var(--text-primary); line-height: 1.6; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border-light); }
.compare-list { display: flex; flex-direction: column; gap: 6px; }
.compare-item { display: flex; justify-content: space-between; padding: 8px 12px; background: var(--bg-card); border-radius: var(--radius-sm); font-size: 13px; box-shadow: var(--shadow-card); }
.cmp-status { color: var(--text-secondary); font-size: 12px; }

/* L3 */
.l3-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.l3-card { background: var(--bg-card); border-radius: 16px; padding: 20px; border:1px solid #e7e9f1; box-shadow:0 8px 24px rgba(31,41,90,.05); transition:transform .24s,box-shadow .24s; }
.l3-card:hover { transform:translateY(-3px); box-shadow:0 15px 32px rgba(53,63,133,.09); }
.l3-head { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 12px; }
.l3-count { margin-left: auto; font-size: 12px; padding: 2px 8px; border-radius: 10px; background: var(--accent-soft); color: var(--accent); }
.l3-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.l3-item { display: flex; align-items: center; gap: 8px; padding: 8px; border-radius: var(--radius-sm); cursor: pointer; font-size: 13px; transition: background 0.15s; }
.l3-item:hover { background: var(--bg-hover); }
.l3-cat { font-size: 11px; padding: 1px 6px; border-radius: 8px; background: var(--accent-soft); color: var(--accent); white-space: nowrap; }
.l3-cat.national { background: #fff0f5; color: #e74c8b; }
.l3-cat.clearing { background: #fff5e6; color: #ff9500; }
.l3-prov { font-size: 11px; color: var(--text-secondary); white-space: nowrap; }
.l3-title { flex: 1; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.l3-date { font-size: 11px; color: var(--text-tertiary); white-space: nowrap; }
.l3-tag { font-size: 10px; padding: 1px 6px; border-radius: 8px; background: #fff5e6; color: #ff9500; white-space: nowrap; }
.l3-diff { font-size: 11px; color: var(--accent-orange); }
.l3-empty { text-align: center; color: var(--text-tertiary); font-size: 12px; padding: 16px; }

@media (max-width: 900px) {
  .l2-grid, .l3-grid { grid-template-columns: 1fr; }
}

/* A4：我的掌握度总览 */
.mastery-card { margin-bottom: 30px; padding: 20px 24px; background: rgba(255,255,255,.88); border:1px solid #e7e9f1; border-radius: 15px; box-shadow: 0 7px 20px rgba(31,41,90,.045); }
.mastery-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16px; }
.mastery-head h3 { margin: 0; }
.mastery-hint { font-size: 12px; color: var(--text-tertiary); }
.mastery-bars { display: flex; flex-direction: column; gap: 10px; }
.mastery-bar { display: grid; grid-template-columns: 110px 1fr 130px; align-items: center; gap: 12px; }
.mb-label { font-size: 13px; color: var(--text-primary); }
.mb-track { height: 10px; border-radius: 5px; background: var(--bg-hover, #f0f2f8); overflow: hidden; }
.mb-fill { height: 100%; border-radius: 5px; transition: width .4s ease; }
.mb-stat { font-size: 12px; color: var(--text-secondary); font-variant-numeric: tabular-nums; white-space: nowrap; text-align: right; }
@media (max-width: 760px) {
  .mastery-bar { grid-template-columns: 1fr; gap: 4px; }
  .mb-stat { text-align: left; }
}
@keyframes missionScan { 0%,38%{transform:translateX(-58%)} 70%,100%{transform:translateX(58%)} }
@keyframes missionGradient{from{background-position:0 50%}to{background-position:100% 50%}}@keyframes missionOrbit{to{transform:rotate(360deg)}}@keyframes progressBreathe{0%,100%{transform:scale(.94);opacity:.55}50%{transform:scale(1.06);opacity:1}}@keyframes progressDot{0%,100%{transform:translate(0,0);opacity:.55}25%{transform:translate(62px,54px);opacity:1}50%{transform:translate(3px,118px)}75%{transform:translate(-59px,55px);opacity:1}}
@media(prefers-reduced-motion:reduce){.today-mission,.today-mission::before,.today-mission::after,.mission-progress::before,.mission-progress::after{animation:none}.unit-grid button,.l3-card{transition:none}}
</style>
