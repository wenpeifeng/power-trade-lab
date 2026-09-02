<template>
  <div class="portal">
    <!-- 导航栏 -->
    <header class="nav glass fade-up">
      <div class="nav-left">
        <Logo :size="30" />
        <span class="brand-stack"><strong class="brand-name">电力交易中枢</strong><small>POWER MARKET OS</small></span>
      </div>
      <nav class="nav-menu" aria-label="系统入口">
        <span class="nav-caption">
          <LayoutGrid :size="14" />
          <span><strong>系统入口</strong><small>WORKSPACES</small></span>
        </span>
        <router-link to="/learn" class="nav-item"><BookOpen :size="17" /><span><strong>学习中心</strong><small>LEARN</small></span></router-link>
        <router-link to="/trade/lab" class="nav-item"><Orbit :size="17" /><span><strong>仿真交易</strong><small>SIMULATE</small></span></router-link>
        <router-link to="/trade" class="nav-item"><TrendingUp :size="17" /><span><strong>行情终端</strong><small>MARKET</small></span></router-link>
        <router-link to="/knowledge" class="nav-item"><Library :size="17" /><span><strong>知识库</strong><small>KNOWLEDGE</small></span></router-link>
        <router-link :to="{ name: 'asset-center' }" class="nav-item"><DatabaseZap :size="17" /><span><strong>数据资产</strong><small>DATA</small></span></router-link>
        <router-link to="/policy" class="nav-item"><Bell :size="17" /><span><strong>政策公告</strong><small>POLICY</small></span><span v-if="overview.policy.unread" class="badge-wrap"><span class="badge-dot"></span><span class="badge-ring"></span></span></router-link>
      </nav>
      <div class="nav-right">
        <div class="market-clock" :class="{ open: marketOpen }" :title="marketOpen ? '交易时段进行中' : '当前为休市时段'">
          <span class="mk-dot"></span>
          <span class="mk-status">{{ marketOpen ? '实时市场·开盘中' : '休市中' }}</span>
          <span class="mk-sep"></span>
          <span class="mk-time">{{ nowText }}</span>
        </div>
        <el-dropdown trigger="click">
          <div class="user-chip"><span class="user-avatar">{{ (user?.display_name || user?.username || '?')[0] }}</span></div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="replayGuide">重新看引导</el-dropdown-item>
              <el-dropdown-item @click="goToAsset">数据资产中心</el-dropdown-item>
              <el-dropdown-item @click="settingsOpen = true">系统设置</el-dropdown-item>
              <el-dropdown-item divided @click="handleLogout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <!-- Hero 渐变色块（全宽，与下面白色内容区形成对比） -->
    <section class="hero">
      <div class="hero-deco">
        <div class="orb orb-1"></div>
        <div class="orb orb-2"></div>
        <div class="orb orb-3"></div>
      </div>
        <div class="hero-inner">
          <div class="hero-copy">
            <p class="hero-greeting fade-up"><Sparkles :size="14" /> {{ greeting }}，系统已为你重排今日路径</p>
            <h1 class="hero-name fade-up-1">{{ user?.display_name || user?.username || '交易员' }}，从理解市场到<br><em>独立完成一轮交易</em></h1>
            <p class="hero-tagline fade-up-2">学习、数据与仿真不再是三个孤岛，每一次操作都会留下可复盘的能力证据。</p>
            <div class="hero-actions fade-up-3">
              <button @click="$router.push('/learn/study')">继续今日路径 <ArrowRight :size="15" /></button>
              <button class="secondary" @click="$router.push('/trade/lab')">进入仿真交易</button>
            </div>
          </div>
          <div class="portal-flow" aria-label="学习、数据和仿真的智能闭环">
            <div class="flow-orbit orbit-one"></div>
            <div class="flow-orbit orbit-two"></div>
            <span class="flow-particle particle-one"></span>
            <span class="flow-particle particle-two"></span>
            <div class="portal-core">
              <span></span>
              <strong><span v-count="overview.learn.progress">0</span>%</strong>
              <small>能力进度</small>
            </div>
            <div class="portal-node node-learn"><BookOpenCheck :size="16" /><span>学习路径</span></div>
            <div class="portal-node node-data"><DatabaseZap :size="16" /><span>真实数据</span></div>
            <div class="portal-node node-trade"><CandlestickChart :size="16" /><span>交易实操</span></div>
            <div class="portal-node node-review"><ScanSearch :size="16" /><span>复盘反馈</span></div>
            <small class="flow-caption">能力闭环正在运行</small>
          </div>
          <div class="hero-metrics fade-up-3">
            <div class="hm" @click="$router.push('/learn')"><span class="hm-num" v-count="overview.learn.total_questions">0</span><span class="hm-lbl">题库总量</span></div>
            <span class="hm-div"></span>
            <div class="hm" @click="$router.push('/learn/study')"><span class="hm-num"><span v-count="overview.learn.progress">0</span>%</span><span class="hm-lbl">学习进度</span></div>
            <span class="hm-div"></span>
            <div class="hm" @click="$router.push('/trade')"><span class="hm-num">¥{{ formatMoney(overview.trade.balance) }}</span><span class="hm-lbl">模拟资金</span></div>
            <span class="hm-div"></span>
            <button type="button" class="hm" @click="goToAsset"><span class="hm-num" v-count="docCount">0</span><span class="hm-lbl">数据资产</span></button>
          </div>
        </div>
    </section>

    <main class="main">
      <!-- 新手任务 -->
      <section class="tasks fade-up-4" v-if="showTasks" ref="taskSection">
        <div class="sec-head">
          <h2><Sparkles :size="16" /> 新手任务<span class="progress-badge">{{ doneCount }}/{{ tasks.length }}</span></h2>
          <span class="dismiss" @click="dismissTasks">跳过</span>
        </div>
        <div class="task-grid" ref="taskGrid">
          <div v-for="(t, i) in tasks" :key="i" class="task-card " :class="{done: t.done}" @click="doTask(t)">
            <div class="task-icon" :class="{done: t.done}">
              <component :is="t.iconComp" :size="18" v-if="!t.done" />
              <Check :size="18" v-else />
            </div>
            <div class="task-text"><div class="t-label">{{ t.label }}</div><div class="t-hint">{{ t.hint }}</div></div>
            <ChevronRight :size="16" class="t-arrow" v-if="!t.done" />
          </div>
        </div>
      </section>

      <!-- 功能模块 -->
      <section class="modules" ref="moduleSection">
        <div class="sec-head"><h2><LayoutGrid :size="16" /> 核心功能</h2></div>
        <div class="module-grid" ref="moduleGrid">
          <!-- 学习考试中心 -->
          <div class="module-card mc-learn" @click="$router.push('/learn')">
            <div class="mc-glow"></div>
            <div class="mc-icon"><GraduationCap :size="24" /></div>
            <h3>学习考试中心</h3>
            <p>能力诊断 · 分层学习 · 刷题备考 · 模拟考试</p>
            <div class="mc-tags"><span>诊断</span><span>刷题</span><span>考试</span><span>错题本</span></div>
            <div class="mc-bottom">
              <span v-if="overview.learn.wrong_count" class="mc-warn">{{ overview.learn.wrong_count }} 题待复习</span>
              <span v-else class="mc-muted">开始你的第一次诊断</span>
              <span class="mc-go arrow-follow">进入 <ArrowRight :size="14" /></span>
            </div>
          </div>
          <!-- 交易模拟终端 -->
          <div class="module-card mc-trade" @click="$router.push('/trade/lab')">
            <div class="mc-glow"></div>
            <div class="mc-icon"><CandlestickChart :size="24" /></div>
            <h3>全流程仿真交易</h3>
            <p>场景简报 · 分时申报 · 封盘出清 · 结算与策略复盘</p>
            <div class="mc-tags"><span>角色</span><span>申报</span><span>出清</span><span>结算</span></div>
            <div class="mc-bottom">
              <button class="terminal-shortcut" @click.stop="$router.push('/trade')">查看行情终端</button>
              <span class="mc-go arrow-follow">开始任务 <ArrowRight :size="14" /></span>
            </div>
          </div>
          <!-- 数据资产中心 -->
          <button type="button" class="module-card mc-data" @click="goToAsset">
            <div class="mc-glow"></div>
            <div class="mc-icon"><DatabaseZap :size="24" /></div>
            <h3>数据资产中心</h3>
            <p>真实来源 · 增量采集 · 质量治理 · 全链路追踪</p>
            <div class="mc-tags"><span>采集</span><span>去重</span><span>审核</span><span>溯源</span></div>
            <div class="mc-bottom"><span class="mc-muted">{{ docCount }} 项数据资产</span><span class="mc-go arrow-follow">进入治理 <ArrowRight :size="14" /></span></div>
          </button>
          <!-- 知识库 -->
          <div class="module-card mc-knowledge" @click="$router.push('/knowledge')">
            <div class="mc-glow"></div>
            <div class="mc-icon"><Library :size="24" /></div>
            <h3>知识库</h3>
            <p>业务规则与政策文档 · 分类浏览 · 语义检索 · AI问答</p>
            <div class="mc-tags"><span>分类浏览</span><span>混合检索</span><span>AI问答</span></div>
            <div class="mc-bottom"><button class="terminal-shortcut" @click.stop="$router.push('/assistant')">问AI助手</button><span class="mc-go arrow-follow">浏览知识 <ArrowRight :size="14" /></span></div>
          </div>
        </div>
      </section>

      <!-- 公告 -->
      <section class="news" v-if="overview.policy.latest?.length">
        <div class="sec-head"><h2><Newspaper :size="16" /> 最新政策公告</h2><router-link to="/policy" class="view-all arrow-follow">查看全部 <ArrowRight :size="13" /></router-link></div>
        <div class="news-list">
          <div v-for="item in overview.policy.latest.slice(0, 4)" :key="item.id" class="news-item" @click="$router.push('/policy')">
            <span class="news-type" :class="item.category">{{ categoryLabel(item.category) }}</span>
            <span class="news-title">{{ item.title }}</span>
            <span class="news-date">{{ item.publish_date }}</span>
          </div>
        </div>
      </section>
    </main>
    <LLMSettingsDialog v-model="settingsOpen" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { assetApi, portalApi, currentUser, logout } from '../../api'
import { startPortalGuide, resetAllGuides } from '../../guide/onboarding'
import { useStaggerChildren } from '../../composables/useAnim'
import Logo from '../../components/Logo.vue'
import LLMSettingsDialog from '../../components/LLMSettingsDialog.vue'
import {
  GraduationCap, CandlestickChart, BrainCircuit, Library,
  BookOpen, TrendingUp, Database,
  Bell, FileText, Target, Wallet,
  Sparkles, Check, ChevronRight, LayoutGrid, ArrowRight, Newspaper, Compass, PenTool,
  Orbit, BookOpenCheck, DatabaseZap, ScanSearch,
} from 'lucide-vue-next'

const overview = ref({ learn: { total_questions: 0, wrong_count: 0, progress: 0 }, trade: { balance: 1000000 }, policy: { unread: 0, latest: [] } })
const router = useRouter()
const user = ref(currentUser())
const docCount = ref(41)
const settingsOpen = ref(false)

function goToAsset() {
  return router.push({ name: 'asset-center' })
}

// 子元素交错渐入（暂时禁用排查白屏）
const taskGrid = ref(null)
const moduleGrid = ref(null)
// useStaggerChildren(taskGrid, 80)
// useStaggerChildren(moduleGrid, 100)

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'; if (h < 12) return '上午好'; if (h < 14) return '中午好'; if (h < 18) return '下午好'; return '晚上好'
})

// 顶栏实时市场指示器：时钟 + 交易时段状态
const now = ref(new Date())
let clockTimer = null
const pad2 = (n) => String(n).padStart(2, '0')
const nowText = computed(() => {
  const d = now.value
  const week = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()]
  return `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} 周${week} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
})
// 交易时段：工作日 08:00–17:00 视为「实时市场·开盘中」（可后续接真实市场日历）
const marketOpen = computed(() => {
  const d = now.value
  const day = d.getDay(), h = d.getHours()
  return day >= 1 && day <= 5 && h >= 8 && h < 17
})
const handleLogout = () => logout()
const replayGuide = () => { resetAllGuides(); startPortalGuide() }
const formatMoney = (n) => Number(n || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
const categoryMap = { national: '国家政策', market: '市场公告', clearing: '出清结果', regulation: '交易规则' }
const categoryLabel = (c) => categoryMap[c] || c

const TASK_KEY = 'power_onboarding_tasks'
const tasks = ref([
  { iconComp: Compass, label: '能力诊断', hint: '8题判断你的起点', done: false, route: '/learn/study/diagnosis' },
  { iconComp: PenTool, label: '刷题体验', hint: '做10道题试试', done: false, route: '/learn/quiz' },
  { iconComp: Orbit, label: '模拟交易', hint: '完成一轮场景任务', done: false, route: '/trade/lab' },
  { iconComp: BrainCircuit, label: '问AI助手', hint: '提一个问题', done: false, route: '/assistant' },
])
const showTasks = ref(true)
const doneCount = computed(() => tasks.value.filter(t => t.done).length)
function loadTaskStatus() {
  try { const s = JSON.parse(localStorage.getItem(TASKE_KEY_FIX()) || '{}'); if (s.dismissed) { showTasks.value = false; return } tasks.value.forEach(t => t.done = s[t.label] || false); if (doneCount.value === tasks.value.length) showTasks.value = false } catch {}
}
function TASKE_KEY_FIX() { return TASK_KEY }
function saveTaskStatus() { const d = { dismissed: !showTasks.value }; tasks.value.forEach(t => d[t.label] = t.done); localStorage.setItem(TASK_KEY, JSON.stringify(d)) }
function doTask(t) { if (t.done) return; t.done = true; saveTaskStatus(); window.location.href = t.route }
function dismissTasks() { showTasks.value = false; saveTaskStatus() }

onMounted(async () => {
  clockTimer = setInterval(() => { now.value = new Date() }, 15000)
  loadTaskStatus()
  try {
    overview.value = await portalApi.overview()
    const stats = await assetApi.stats().catch(() => ({}))
    if (stats.total) docCount.value = stats.total
  } catch (e) { console.error(e) }
  await nextTick(); setTimeout(() => startPortalGuide(), 800)
})

onUnmounted(() => { if (clockTimer) clearInterval(clockTimer) })
</script>

<style scoped>
.portal {
  min-height: 100vh; color: #18181b; overflow-x: hidden;
  background:
    radial-gradient(circle at 9% 20%, rgba(89,100,223,.045), transparent 25rem),
    radial-gradient(circle at 91% 42%, rgba(44,196,211,.035), transparent 25rem),
    #f6f7fb;
}

/* 导航 — Linear风格：纯白毛玻璃 */
.nav {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 max(28px, calc((100vw - 1200px) / 2)); height: 62px;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(20px) saturate(180%);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  position: sticky; top: 0; z-index: 100;
}
.nav.glass { background: rgba(255, 255, 255, 0.72); backdrop-filter: blur(20px) saturate(180%); }
.nav-left { display: flex; align-items: center; gap: 10px; }
.brand-stack{display:flex;flex-direction:column}.brand-stack small{margin-top:1px;color:#a0a6b4;font:700 7px/1 ui-monospace;letter-spacing:.14em}
.brand-name { font-size: 15px; font-weight: 600; color: #18181b; letter-spacing: -0.3px; }
.nav-menu {
  position:relative;
  display:flex;
  align-items:center;
  gap:6px;
  height:52px;
  padding:5px;
  border:1px solid rgba(211,219,238,.92);
  border-radius:13px;
  background:rgba(255,255,255,.74);
  box-shadow:0 7px 22px rgba(50,65,115,.07),inset 0 1px 0 rgba(255,255,255,.94);
}
.nav-menu::before{display:none}
.nav-caption{
  height:38px;
  padding:0 11px 0 7px;
  display:flex;
  align-items:center;
  gap:7px;
  color:#66718a;
  border-right:1px solid #e1e6f1;
  user-select:none;
}
.nav-caption>svg{color:#5965dc}
.nav-caption>span{display:flex;flex-direction:column;gap:2px}
.nav-caption strong{font-size:11px;line-height:1;font-weight:800;white-space:nowrap}
.nav-caption small{font:700 6px/1 ui-monospace;letter-spacing:.12em;color:#a0a8b9}
.nav-item {
  --nav-tone:#4f5bd4;
  position:relative;
  z-index:1;
  min-width:92px;
  height:40px;
  padding:0 9px 0 6px;
  display:flex;
  align-items:center;
  gap:7px;
  color:#313b52;
  text-decoration:none;
  border:1px solid #e3e8f2;
  border-radius:9px;
  background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(247,249,253,.96));
  box-shadow:0 2px 5px rgba(43,56,99,.04);
  transition:color .2s,border-color .2s,background .2s,transform .2s,box-shadow .2s;
}
.nav-item+.nav-item::before{display:none}
.nav-item>svg{
  width:29px;height:29px;
  padding:6px;
  box-sizing:border-box;
  flex:none;
  color:#4f5bd4;
  border-radius:8px;
  background:#edf0ff;
  border:1px solid #dfe4ff;
  transition:color .22s,background .22s,transform .22s,box-shadow .22s;
}
.nav-item>span:not(.badge-wrap){display:flex;flex-direction:column;gap:2px;min-width:0}
.nav-item strong{font-size:12px;line-height:1;font-weight:800;white-space:nowrap}
.nav-item small{font:700 7px/1 ui-monospace;letter-spacing:.11em;color:#a1a9ba;transition:color .22s}
.nav-item::after{
  display:none;
}
.nav-item:hover{
  color:#fff;
  border-color:#5965dc;
  background:linear-gradient(135deg,#6571ec,#4a56cf);
  transform:translateY(-2px);
  box-shadow:0 9px 18px rgba(79,89,207,.22);
}
.nav-item:hover>svg{
  color:#fff;
  background:rgba(255,255,255,.14);
  border-color:rgba(255,255,255,.22);
  transform:scale(1.06);
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.05);
}
.nav-item:hover small{color:#d9defe}
.nav-item.router-link-active{color:#fff;border-color:#5965dc;background:linear-gradient(135deg,#6571ec,#4a56cf);box-shadow:0 7px 16px rgba(79,89,207,.2)}
.nav-item.router-link-active>svg{color:#fff;background:rgba(255,255,255,.14);border-color:rgba(255,255,255,.22)}
.nav-item.router-link-active small{color:#d9defe}
.badge-wrap { position: absolute; top: 4px; right: 6px; width: 7px; height: 7px; }
.badge-dot { position: absolute; width: 7px; height: 7px; border-radius: 50%; background: #f43f5e; z-index: 2; }
.badge-ring {
  position: absolute; width: 7px; height: 7px; border-radius: 50%; background: #f43f5e;
  z-index: 1; animation: ringGrow 1.6s ease-out infinite;
}
@keyframes ringGrow {
  0% { transform: scale(1); opacity: 0.7; }
  100% { transform: scale(3.5); opacity: 0; }
}
.nav-right { display: flex; align-items: center; gap: 14px; }

/* 实时市场指示器 */
.market-clock {
  display: flex; align-items: center; gap: 8px;
  padding: 5px 12px; border-radius: 20px;
  background: #f4f4f5; border: 1px solid #ececed;
  font-size: 12px; color: #71717a; user-select: none;
  font-variant-numeric: tabular-nums;
  transition: background 0.3s ease, border-color 0.3s ease;
}
.market-clock.open {
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.22);
}
.mk-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #a1a1aa; flex-shrink: 0;
}
.market-clock.open .mk-dot {
  background: #10b981;
  box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.5);
  animation: mkPulse 2s ease-out infinite;
}
@keyframes mkPulse {
  0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.5); }
  70% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
  100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}
.market-clock.open .mk-status { color: #059669; font-weight: 600; }
.mk-sep { width: 1px; height: 11px; background: currentColor; opacity: 0.25; }
.mk-time { color: #52525b; font-weight: 500; letter-spacing: 0.2px; }
@media (max-width: 900px) {
  .mk-status, .mk-sep { display: none; }
}
.user-avatar {
  width: 32px; height: 32px; border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #a855f7);
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600; color: #fff; cursor: pointer;
  transition: transform 0.2s;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.25);
}
.user-avatar:hover { transform: scale(1.08); }

/* Hero — 晨曦极光渐变分区，向下淡出到内容区 */
.hero {
  position: relative; padding: 58px 36px 46px;
  overflow: hidden;
  background:
    radial-gradient(120% 90% at 15% 0%, rgba(99, 102, 241, 0.20) 0%, rgba(99, 102, 241, 0) 55%),
    radial-gradient(110% 80% at 85% 8%, rgba(77, 205, 224, 0.13) 0%, rgba(77,205,224, 0) 52%),
    linear-gradient(180deg, #edf0ff 0%, #f2f4fc 48%, #f6f7fb 100%);
}
.hero-deco { position: absolute; inset: 0; overflow: hidden; pointer-events: none; }
.orb { position: absolute; border-radius: 50%; filter: blur(90px); }
.orb-1 { width: 380px; height: 380px; background: rgba(99, 102, 241, 0.08); top: -120px; left: 10%; animation: float 10s ease-in-out infinite; }
.orb-2 { width: 300px; height: 300px; background: rgba(77, 205, 224, 0.08); top: -60px; right: 12%; animation: float 12s ease-in-out infinite reverse; }
.orb-3 { width: 240px; height: 240px; background: rgba(59, 130, 246, 0.06); bottom: -60px; left: 38%; animation: float 14s ease-in-out infinite; }
.hero-inner { position: relative; z-index: 1; max-width: 1200px; margin: 0 auto; display:grid; grid-template-columns:1.05fr .95fr; gap:36px 58px; align-items:center; }
.hero-copy { text-align:left; }
.hero-greeting { display:flex;align-items:center;gap:7px;font-size: 13px; color: #5962d8; margin: 0 0 12px; font-weight: 750; letter-spacing: 0.2px; }
.hero-name { font-size: clamp(32px,3vw,44px);line-height:1.2;font-weight: 820; color: #17203c; margin: 0 0 14px; letter-spacing: -1.4px; }
.hero-name em { color:#5962d8;font-style:normal; }
.hero-tagline { max-width:590px;font-size: 14px;line-height:1.75;color: #687086; margin: 0; }
.hero-actions{display:flex;align-items:center;gap:12px;margin-top:24px}.hero-actions button{height:40px;padding:0 18px;border:0;border-radius:11px;display:inline-flex;align-items:center;gap:8px;color:#fff;background:linear-gradient(135deg,#5964df,#4652c9);font-weight:720;cursor:pointer;box-shadow:0 9px 22px rgba(79,89,207,.19)}.hero-actions button.secondary{color:#5360d2;background:rgba(255,255,255,.72);box-shadow:inset 0 0 0 1px rgba(89,100,223,.15)}
.portal-flow{height:265px;position:relative;isolation:isolate}.portal-flow::before{content:"";position:absolute;inset:9px;border-radius:50%;background:radial-gradient(circle,rgba(89,100,223,.15) 0 2px,transparent 3px);background-size:23px 23px;opacity:.38;mask-image:radial-gradient(circle,#000,transparent 68%)}.portal-core{position:absolute;left:50%;top:48%;transform:translate(-50%,-50%);width:118px;height:118px;border-radius:50%;z-index:3;color:#fff;display:flex;align-items:center;justify-content:center;flex-direction:column;background:linear-gradient(145deg,#1e2a68,#5864e6);box-shadow:0 0 0 14px rgba(99,102,241,.08),0 18px 38px rgba(44,55,160,.25)}.portal-core>span{width:45px;height:2px;margin-bottom:10px;background:linear-gradient(90deg,transparent,#7de2f2,transparent);box-shadow:0 0 10px #7de2f2;animation:coreWave 2s ease-in-out infinite}.portal-core strong{font-size:27px}.portal-core small{font-size:10px;color:rgba(255,255,255,.65);margin-top:6px}.flow-orbit{position:absolute;left:50%;top:48%;transform:translate(-50%,-50%);border:1px solid rgba(89,100,223,.2);border-radius:50%}.orbit-one{width:270px;height:175px;transform:translate(-50%,-50%) rotate(-8deg)}.orbit-two{width:355px;height:230px;transform:translate(-50%,-50%) rotate(20deg);border-style:dashed}.flow-particle{position:absolute;z-index:4;width:8px;height:8px;border-radius:50%;background:#65d9ee;box-shadow:0 0 13px #45c5de}.particle-one{animation:portalOrbit 6s linear infinite}.particle-two{background:#8b93f4;animation:portalOrbitWide 8s linear infinite reverse}.portal-node{position:absolute;z-index:5;display:flex;align-items:center;gap:7px;padding:8px 11px;border:1px solid #e0e4f2;border-radius:12px;background:rgba(255,255,255,.88);box-shadow:0 9px 22px rgba(41,53,110,.09);font-size:11px;font-weight:700;color:#4d566e}.portal-node svg{color:#5964df}.node-learn{left:2%;top:13%}.node-data{right:0;top:12%}.node-trade{right:0;bottom:20%}.node-review{left:0;bottom:17%}.flow-caption{position:absolute;bottom:-1px;left:50%;transform:translateX(-50%);color:#9198ac;font-size:10px;letter-spacing:.08em;white-space:nowrap}
/* Hero 关键指标行（纯排版，不套卡片，全站只此一处） */
.hero-metrics { grid-column:1/-1;display:flex; align-items: center; gap: 34px; flex-wrap: wrap; justify-content: center;padding-top:24px;border-top:1px solid rgba(89,100,223,.09); }
.hm { display: flex; flex-direction: column; align-items: center; gap: 3px; padding:0; border:0; color:inherit; background:transparent; font:inherit; cursor: pointer; transition: transform 0.2s ease; }
.hm:hover { transform: translateY(-2px); }
.hm:hover .hm-num { color: #4f46e5; }
.hm-num { font-size: 27px; font-weight: 700; color: #18181b; font-variant-numeric: tabular-nums; letter-spacing: -0.5px; transition: color 0.2s ease; }
.hm-lbl { font-size: 12px; color: #8b8b93; }
.hm-div { width: 1px; height: 30px; background: rgba(99, 102, 241, 0.16); }


/* 内容区 */
.main { max-width: 1240px; margin: 0 auto; padding: 32px 40px 60px; }

/* Section 头 */
.sec-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.sec-head h2 { font-size: 16px; font-weight: 600; color: #18181b; margin: 0; display: flex; align-items: center; gap: 7px; letter-spacing: -0.2px; }
.progress-badge { font-size: 12px; color: #6366f1; background: #f5f3ff; padding: 2px 8px; border-radius: 6px; margin-left: 4px; }
.dismiss { font-size: 13px; color: #94a3b8; cursor: pointer; }
.dismiss:hover { color: #64748b; }
.view-all { font-size: 13px; color: #6366f1; text-decoration: none; display: flex; align-items: center; gap: 4px; }

/* 任务 */
.tasks { margin-bottom: 32px; }
.task-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.task-card {
  position: relative; overflow: hidden;
  display: flex; align-items: center; gap: 12px; padding: 14px;
  background: #fff; border: 1px solid #eef0f5; border-radius: 12px;
  cursor: pointer;
  transition: transform 0.24s cubic-bezier(0.22, 0.61, 0.36, 1), box-shadow 0.24s ease, border-color 0.24s ease;
}
/* 左侧品牌色条，hover 时从上滑入 */
.task-card::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: linear-gradient(180deg, #6366f1, #818cf8);
  transform: scaleY(0); transform-origin: top;
  transition: transform 0.24s ease;
}
.task-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 14px 30px rgba(99, 102, 241, 0.18);
  border-color: #c7d2fe;
}
.task-card:hover::before { transform: scaleY(1); }
.task-card.done { opacity: 0.5; cursor: default; }
.task-card.done:hover { transform: none; box-shadow: none; border-color: #eef0f5; }
.task-card.done:hover::before { transform: scaleY(0); }
.task-icon {
  width: 34px; height: 34px; border-radius: 10px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; color: #6366f1; background: #eff6ff;
  transition: transform 0.24s cubic-bezier(0.34, 1.56, 0.64, 1), background 0.24s ease, color 0.24s ease, box-shadow 0.24s ease;
}
.task-card:hover .task-icon {
  transform: scale(1.1) rotate(-4deg);
  background: #6366f1; color: #fff;
  box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4);
}
.task-icon.done { background: #d1fae5; color: #059669; }
.task-text { flex: 1; min-width: 0; }
.t-label { font-size: 14px; font-weight: 600; color: #1e293b; transition: color 0.24s ease; }
.task-card:hover .t-label { color: #4f46e5; }
.t-hint { font-size: 11px; color: #94a3b8; margin-top: 2px; }
.t-arrow { color: #6366f1; flex-shrink: 0; transition: transform 0.24s cubic-bezier(0.22, 0.61, 0.36, 1); }
.task-card:hover .t-arrow { transform: translateX(5px); }

/* 模块 */
.modules { margin-bottom: 32px; }
.module-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
.mc-muted { font-size: 12px; color: #a1a1aa; }
.terminal-shortcut{border:0;background:transparent;color:#7c8496;font-size:12px;cursor:pointer;padding:0}.terminal-shortcut:hover{color:#5964df}
/* 模块卡片 — 每个有独立的品牌色 */
.module-card {
  position: relative; width:100%; padding: 28px; border-radius: 16px; cursor: pointer;
  color:inherit; font:inherit; text-align:left;
  background: #fff; border: 1px solid; border-top: 3px solid;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
/* 学习 — 靛蓝 */
.mc-learn { border-color: #e0e7ff; border-top-color: #6366f1; }
.mc-learn .mc-glow { background: #6366f1; }
.mc-learn .mc-icon { background: #eef2ff; color: #6366f1; }
.mc-learn .mc-go { color: #6366f1; }
.mc-learn .mc-tags span { background: #eef2ff; color: #6366f1; }
/* 交易 — 琥珀 */
.mc-trade { border-color: #fef3c7; border-top-color: #f59e0b; }
.mc-trade .mc-glow { background: #f59e0b; }
.mc-trade .mc-icon { background: #fffbeb; color: #d97706; }
.mc-trade .mc-go { color: #d97706; }
.mc-trade .mc-tags span { background: #fffbeb; color: #d97706; }
/* AI — 青色 */
.mc-ai { border-color: #cffafe; border-top-color: #06b6d4; }
.mc-ai .mc-glow { background: #06b6d4; }
.mc-ai .mc-icon { background: #ecfeff; color: #0891b2; }
.mc-ai .mc-go { color: #0891b2; }
.mc-ai .mc-tags span { background: #ecfeff; color: #0891b2; }
/* 数据资产 — 电气蓝/实时青 */
.mc-data { border-color:#d8eaff;border-top-color:#1976d2 }
.mc-data .mc-glow{background:#169bc1}
.mc-data .mc-icon{background:#eaf5ff;color:#1976d2}
.mc-data .mc-go{color:#1976d2}
.mc-data .mc-tags span{background:#eaf5ff;color:#176caf}
/* 知识库 — 绿色 */
.mc-knowledge { border-color: #dfe6fb; border-top-color: #4168dc; }
.mc-knowledge .mc-glow { background: #4168dc; }
.mc-knowledge .mc-icon { background: #edf1ff; color: #4168dc; }
.mc-knowledge .mc-go { color: #4168dc; }
.mc-knowledge .mc-tags span { background: #edf1ff; color: #4168dc; }

.module-card:hover {
  transform: translateY(-6px) scale(1.04);
  box-shadow: 0 16px 40px rgba(0,0,0,0.1);
}
.mc-glow { position: absolute; top: -30%; right: -15%; width: 200px; height: 200px; border-radius: 50%; filter: blur(55px); opacity: 0; pointer-events:none; transition: opacity 0.2s; }
.module-card:hover .mc-glow { opacity: 0.15; }
.mc-icon {
  width: 50px; height: 50px; border-radius: 14px; margin-bottom: 16px;
  display: flex; align-items: center; justify-content: center;
  transition: transform 0.2s ease;
}
.module-card:hover .mc-icon { transform: scale(1.1); }
.module-card h3 { font-size: 17px; font-weight: 700; margin: 0 0 6px; color: #0f172a; }
.module-card p { font-size: 13px; color: #64748b; margin: 0 0 12px; line-height: 1.5; }
.mc-tags { display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 14px; }
.mc-tags span { font-size: 11px; padding: 2px 9px; border-radius: 8px; background: #f1f5f9; color: #64748b; }
.mc-bottom { display: flex; justify-content: space-between; align-items: center; padding-top: 10px; border-top: 1px solid #f1f5f9; }
.mc-warn { font-size: 12px; color: #f59e0b; }
.mc-fund { font-size: 14px; font-weight: 600; color: #d97706; }
.mc-go { font-size: 13px; color: #6366f1; font-weight: 600; display: flex; align-items: center; gap: 4px; }

/* 公告 */
.news { margin-bottom: 20px; }
/* 政策公告：单一列表容器 + 细线分隔（不再每条一个卡片框） */
.news-list {
  display: flex; flex-direction: column;
  background: #fff; border: 1px solid #eef0f5; border-radius: 14px; overflow: hidden;
}
.news-item {
  display: flex; align-items: center; gap: 12px; padding: 15px 18px;
  cursor: pointer; border-bottom: 1px solid #f3f4f8; position: relative;
  transition: background 0.18s ease, padding-left 0.18s ease;
}
.news-item::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: #6366f1; transform: scaleY(0); transform-origin: center;
  transition: transform 0.18s ease;
}
.news-item:last-child { border-bottom: none; }
.news-item:hover { background: #f8f9fd; padding-left: 24px; }
.news-item:hover::before { transform: scaleY(1); }
.news-type { font-size: 11px; padding: 2px 8px; border-radius: 4px; white-space: nowrap; font-weight: 500; }
.news-type.national { background: #fee2e2; color: #dc2626; }
.news-type.market { background: #fef3c7; color: #d97706; }
.news-type.regulation { background: #ede9fe; color: #7c3aed; }
.news-type.clearing { background: #d1fae5; color: #059669; }
.news-title { flex: 1; font-size: 14px; color: #334155; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.news-date { font-size: 12px; color: #94a3b8; }

@media (max-width: 900px) {
  .task-grid { grid-template-columns: repeat(2, 1fr); }
  .module-grid { grid-template-columns: 1fr; }
  .hero-metrics { gap: 20px; }
  .nav-menu { display: none; }
  .hero-inner{grid-template-columns:1fr}.portal-flow{max-width:520px;width:100%;margin:auto}.hero-copy{text-align:center}.hero-greeting{justify-content:center}.hero-tagline{margin-inline:auto}.hero-actions{justify-content:center}
}
@media(max-width:620px){.nav{padding:0 16px}.market-clock{display:none}.hero{padding:40px 20px}.hero-name{font-size:31px}.portal-flow{display:none}.hero-metrics{gap:18px}.hm-div{display:none}.main{padding:26px 18px 50px}.task-grid{grid-template-columns:1fr}}
@keyframes coreWave{0%,100%{transform:scaleX(.5);opacity:.45}50%{transform:scaleX(1.25);opacity:1}}
@keyframes portalOrbit{0%{left:18%;top:48%}25%{left:48%;top:17%}50%{left:81%;top:48%}75%{left:50%;top:77%}100%{left:18%;top:48%}}
@keyframes portalOrbitWide{0%{left:8%;top:65%}25%{left:48%;top:8%}50%{left:91%;top:33%}75%{left:62%;top:88%}100%{left:8%;top:65%}}
@media(prefers-reduced-motion:reduce){.portal-core>span,.flow-particle,.orb,.mk-dot,.badge-ring{animation:none}}
</style>
