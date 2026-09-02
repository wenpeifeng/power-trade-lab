<template>
  <div class="learn-home" v-loading="loading">
    <section class="learning-hero">
      <div class="hero-copy">
        <Transition name="hero-slide" mode="out-in">
          <div :key="heroIndex" class="hero-message" aria-live="polite">
            <span class="eyebrow"><Sparkles :size="14" /> {{ currentHero.kicker }}</span>
            <h1>{{ currentHero.title }}<br><em>{{ currentHero.emphasis }}</em></h1>
            <p>{{ currentHero.description }}</p>
          </div>
        </Transition>
        <div class="hero-actions">
          <el-button type="primary" size="large" @click="$router.push('/learn/study')">
            继续今日课程 <ArrowRight :size="16" />
          </el-button>
          <button class="text-action" @click="$router.push('/learn/study/diagnosis')">
            重新评估学习路径
          </button>
        </div>
        <div class="hero-pager" aria-label="切换学习中心介绍">
          <button
            v-for="(_, index) in heroSlides" :key="index"
            :class="{ active: heroIndex === index }"
            :aria-label="`第 ${index + 1} 张`"
            @click="selectHero(index)"
          ></button>
          <span>0{{ heroIndex + 1 }} / 0{{ heroSlides.length }}</span>
        </div>
      </div>

      <div class="power-map" aria-label="学习路径：认知、规则、交易、复盘">
        <div class="map-grid"></div>
        <div class="flow-line line-a"></div>
        <div class="flow-line line-b"></div>
        <div class="flow-pulse pulse-a"></div>
        <div class="flow-pulse pulse-b"></div>
        <div v-for="(node, index) in flowNodes" :key="node.label" class="flow-node" :class="`node-${index + 1}`">
          <span><component :is="node.icon" :size="17" /></span>
          <small>{{ node.label }}</small>
        </div>
        <div class="map-core">
          <span class="core-wave"></span>
          <strong><span v-count="overview.learn.progress">0</span>%</strong>
          <small>当前掌握度</small>
        </div>
        <span class="map-caption">知识流正在为你重新排序</span>
      </div>
    </section>

    <section class="status-rail">
      <div class="status-intro">
        <span class="live-dot"></span>
        <div><strong>今天的学习电流</strong><small>按“理解 → 判断 → 操作 → 复盘”推进</small></div>
      </div>
      <div class="metric">
        <strong v-count="overview.learn.total_questions">0</strong><span>题库资产</span>
      </div>
      <div class="metric">
        <strong v-count="overview.learn.answered">0</strong><span>累计作答</span>
      </div>
      <div class="metric warning" @click="$router.push('/learn/wrong')">
        <strong v-count="overview.learn.wrong_count">0</strong><span>待复习错题</span>
      </div>
      <div class="rail-progress"><i :style="{ width: `${overview.learn.progress}%` }"></i></div>
    </section>

    <section class="next-section">
      <div class="section-heading">
        <div><span class="section-kicker">NEXT ACTION</span><h2>不用找入口，下一步已经排好</h2></div>
        <span class="section-note">每一步都会回到知识与实操闭环</span>
      </div>
      <div class="action-grid" ref="actionGrid">
        <button class="action-card primary" @click="$router.push('/learn/study')">
          <span class="action-index">01</span>
          <div class="action-icon"><Route :size="23" /></div>
          <h3>系统引导学习</h3>
          <p>先建立业务全景，再逐课完成概念、数据观察和成果交付。</p>
          <span class="action-meta">推荐 · 约 25 分钟</span>
          <ArrowUpRight :size="18" class="action-arrow" />
        </button>
        <button class="action-card practice" @click="startDailyQuiz">
          <span class="action-index">02</span>
          <div class="action-icon"><Zap :size="23" /></div>
          <h3>今日即时检查</h3>
          <p>用 10 道题验证刚学内容，答错后自动进入可追踪复盘。</p>
          <span class="action-meta">轻量 · 约 8 分钟</span>
          <ArrowUpRight :size="18" class="action-arrow" />
        </button>
        <button class="action-card exam" @click="$router.push('/learn/exam')">
          <span class="action-index">03</span>
          <div class="action-icon"><BadgeCheck :size="23" /></div>
          <h3>考试能力校准</h3>
          <p>对照考试蓝图、考点权重和历史成绩，形成备考节奏。</p>
          <span class="action-meta">阶段性 · 中高级工</span>
          <ArrowUpRight :size="18" class="action-arrow" />
        </button>
        <button class="action-card books" @click="$router.push('/learn/books')">
          <span class="action-index">04</span>
          <div class="action-icon"><BookOpenCheck :size="23" /></div>
          <h3>教材工坊</h3>
          <p>导入电力行业 PDF 或 Word，转成可阅读、可练习、可追踪的章节课程。</p>
          <span class="action-meta">自定义 · MinerU 解析</span>
          <ArrowUpRight :size="18" class="action-arrow" />
        </button>
      </div>
    </section>

    <section class="knowledge-section">
      <div class="section-heading">
        <div><span class="section-kicker">KNOWLEDGE SYSTEM</span><h2>你的电力交易知识版图</h2></div>
        <span class="section-note">点击模块可按知识点专项练习</span>
      </div>
      <div class="knowledge-board">
        <div class="board-axis">
          <span>基础认知</span><i></i><span>市场机制</span><i></i><span>交易执行</span><i></i><span>风险复盘</span>
        </div>
        <div class="knowledge-grid" ref="knowledgeGrid">
          <button
            v-for="(kp, index) in knowledgeTree"
            :key="kp.id"
            class="knowledge-card"
            :class="{ disabled: !kp.question_count }"
            :style="knowledgeCardStyle(index)"
            @click="goQuiz(kp)"
          >
            <span class="kp-number">{{ String(index + 1).padStart(2, '0') }}</span>
            <div class="kp-copy">
              <div class="kp-title">
                <span><component :is="knowledgeIcons[index % knowledgeIcons.length]" :size="17" /></span>
                <strong>{{ kp.name }}</strong>
              </div>
              <p>{{ kp.description || '该模块内容正在持续补充' }}</p>
            </div>
            <div class="kp-foot">
              <span><span v-count="kp.question_count">0</span> 题</span>
              <span>{{ kp.question_count ? '进入专项 →' : '知识建设中' }}</span>
            </div>
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { portalApi, learnApi } from '../../api'
import { useStaggerChildren } from '../../composables/useAnim'
import {
  Sparkles, ArrowRight, ArrowUpRight, Route, Zap, BadgeCheck,
  Network, Scale, CandlestickChart, ChartNoAxesCombined, BookOpenCheck,
  Building2, Store, CalendarRange, Activity, RadioTower, Leaf, ShieldCheck,
} from 'lucide-vue-next'

const router = useRouter()
const loading = ref(false)
const overview = ref({ learn: { progress: 0, total_questions: 0, answered: 0, wrong_count: 0 } })
const knowledgeTree = ref([])
const actionGrid = ref(null)
const knowledgeGrid = ref(null)
const heroIndex = ref(0)
const heroSlides = [
  {
    kicker: 'PERSONAL LEARNING GRID',
    title: '把电力市场，学成一张',
    emphasis: '能操作的业务地图',
    description: '从电力系统认知，到中长期、现货与交易复盘。系统会告诉你今天学什么、为什么学、学完去哪里实操。',
  },
  {
    kicker: 'LEARN · SIMULATE · REVIEW',
    title: '先看懂规则，再完成一轮',
    emphasis: '可复盘的模拟交易',
    description: '每个知识点都连接业务步骤：理解交易品种、完成申报出清，再用结算结果检验自己的判断。',
  },
  {
    kicker: 'REAL DATA · REAL JUDGEMENT',
    title: '用真实数据，训练你的',
    emphasis: '电力交易判断力',
    description: '政策、市场公告、天气与行情不只是资料，它们会进入学习任务与仿真场景，形成可追踪的能力证据。',
  },
]
const currentHero = computed(() => heroSlides[heroIndex.value])
let heroTimer
const startHeroTimer = () => {
  window.clearInterval(heroTimer)
  heroTimer = window.setInterval(() => {
    heroIndex.value = (heroIndex.value + 1) % heroSlides.length
  }, 5200)
}
const selectHero = (index) => {
  heroIndex.value = index
  startHeroTimer()
}
const flowNodes = [
  { label: '系统认知', icon: Network },
  { label: '规则判断', icon: Scale },
  { label: '交易执行', icon: CandlestickChart },
  { label: '复盘决策', icon: ChartNoAxesCombined },
]
const knowledgeIcons = [
  Network, Building2, Store, CalendarRange, CandlestickChart,
  RadioTower, Leaf, ShieldCheck, Activity,
]
const knowledgePalettes = [
  ['#5964df', '#eef0ff', '89,100,223'],
  ['#3a7bd5', '#ebf5ff', '58,123,213'],
  ['#0c9a7a', '#e8f8f3', '12,154,122'],
  ['#8d5ac8', '#f5edff', '141,90,200'],
  ['#dc7d2c', '#fff3e8', '220,125,44'],
  ['#2d91aa', '#e9f8fb', '45,145,170'],
  ['#48a65b', '#edf9ef', '72,166,91'],
  ['#be5d68', '#fff0f2', '190,93,104'],
]
const knowledgeCardStyle = (index) => {
  const [accent, soft, rgb] = knowledgePalettes[index % knowledgePalettes.length]
  return { '--kp-accent': accent, '--kp-soft': soft, '--kp-rgb': rgb }
}

useStaggerChildren(actionGrid, 90)
useStaggerChildren(knowledgeGrid, 45)

const startDailyQuiz = () => router.push({ name: 'learn-quiz', query: { count: 10 } })
const goQuiz = (kp) => {
  if (kp.question_count > 0) router.push({ name: 'learn-quiz', query: { kp: kp.id } })
}

onMounted(async () => {
  startHeroTimer()
  loading.value = true
  try {
    const [ov, tree] = await Promise.all([portalApi.overview(), learnApi.knowledgeTree()])
    overview.value = ov
    knowledgeTree.value = tree
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
})
onUnmounted(() => window.clearInterval(heroTimer))
</script>

<style scoped>
.learn-home { color: var(--text-primary); }
.learning-hero {
  min-height: 390px;
  display: grid;
  grid-template-columns: 1.08fr .92fr;
  align-items: center;
  gap: 48px;
  padding: 52px 58px;
  border: 1px solid rgba(199, 210, 254, .72);
  border-radius: 28px;
  background:
    linear-gradient(120deg, rgba(255,255,255,.97), rgba(244,247,255,.94)),
    #fff;
  box-shadow: 0 28px 70px rgba(44, 55, 120, .1);
  position: relative;
  overflow: hidden;
}
.learning-hero::before {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background-image: linear-gradient(rgba(75,85,190,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(75,85,190,.035) 1px, transparent 1px);
  background-size: 34px 34px;
  mask-image: linear-gradient(90deg, transparent, #000 48%, #000);
}
.hero-copy { position: relative; z-index: 2; }
.hero-message{min-height:200px}
.eyebrow, .section-kicker {
  display: inline-flex; align-items: center; gap: 7px;
  color: #5962d8; font-size: 11px; letter-spacing: .15em; font-weight: 850;
}
.hero-copy h1 {
  margin: 14px 0 17px; font-size: clamp(34px, 3vw, 48px); line-height: 1.17;
  letter-spacing: -.045em; font-weight: 850; color: #17203c;
}
.hero-copy h1 em { color: #5962d8; font-style: normal; }
.hero-message > p { max-width: 590px; color: #667085; font-size: 15px; line-height: 1.8; }
.hero-actions { margin-top: 28px; display: flex; align-items: center; gap: 20px; }
.hero-actions :deep(.el-button) { border-radius: 11px; padding-inline: 22px; box-shadow: 0 9px 22px rgba(79,70,229,.2); }
.hero-actions :deep(.el-button span) { display: inline-flex; align-items: center; gap: 8px; }
.text-action { border: 0; background: none; color: #667085; cursor: pointer; font-size: 13px; }
.text-action:hover { color: #4f46e5; }
.hero-pager{margin-top:23px;display:flex;align-items:center;gap:7px}
.hero-pager button{width:20px;height:4px;padding:0;border:0;border-radius:4px;background:#d8dcf1;cursor:pointer;transition:width .28s,background .28s,box-shadow .28s}
.hero-pager button.active{width:42px;background:#5962d8;box-shadow:0 0 10px rgba(89,98,216,.25)}
.hero-pager span{margin-left:6px;color:#9ba2b5;font:700 9px/1 ui-monospace;letter-spacing:.08em}
.hero-slide-enter-active,.hero-slide-leave-active{transition:opacity .38s ease,transform .38s cubic-bezier(.16,1,.3,1),filter .38s}
.hero-slide-enter-from{opacity:0;transform:translateX(24px);filter:blur(3px)}
.hero-slide-leave-to{opacity:0;transform:translateX(-18px);filter:blur(2px)}

.power-map { height: 285px; position: relative; isolation: isolate; }
.map-grid { position:absolute; inset:9px; border-radius:50%; background:radial-gradient(circle,rgba(103,113,235,.15) 0 2px,transparent 3px); background-size:23px 23px; opacity:.45; mask-image:radial-gradient(circle,#000,transparent 68%); }
.map-core {
  position:absolute; left:50%; top:50%; transform:translate(-50%,-50%);
  width:126px; height:126px; border-radius:50%; display:flex; flex-direction:column;
  align-items:center; justify-content:center; color:#fff; z-index:3;
  background:linear-gradient(145deg,#202d71,#5864e6);
  box-shadow:0 0 0 15px rgba(99,102,241,.08),0 18px 38px rgba(44,55,160,.28);
}
.map-core strong { font-size:28px; line-height:1; font-variant-numeric:tabular-nums; }
.map-core small { margin-top:8px; color:rgba(255,255,255,.67); font-size:11px; }
.core-wave { width:48px; height:2px; margin-bottom:11px; background:linear-gradient(90deg,transparent,#8de2ff,transparent); box-shadow:0 0 11px #8de2ff; animation:coreWave 2s ease-in-out infinite; }
.flow-line { position:absolute; z-index:1; border:1px solid rgba(99,102,241,.2); border-radius:50%; left:50%; top:50%; transform:translate(-50%,-50%); }
.line-a { width:260px;height:180px;transform:translate(-50%,-50%) rotate(-10deg); }
.line-b { width:330px;height:240px;transform:translate(-50%,-50%) rotate(21deg); border-style:dashed; }
.flow-pulse { position:absolute; width:8px;height:8px;border-radius:50%;background:#6ce0ff;box-shadow:0 0 14px #3fc9ff;z-index:4; }
.pulse-a { animation:orbitA 6s linear infinite; }
.pulse-b { background:#8f96ff; animation:orbitB 8s linear infinite reverse; }
.flow-node { position:absolute; z-index:4; display:flex; align-items:center; gap:7px; padding:7px 10px 7px 7px; border:1px solid #e1e5f5; border-radius:12px; background:rgba(255,255,255,.9); box-shadow:0 9px 22px rgba(41,53,110,.1); }
.flow-node span { width:29px;height:29px;border-radius:9px;display:grid;place-items:center;color:#5560dc;background:#eef0ff; }
.flow-node small { color:#49516b;font-weight:700;white-space:nowrap; }
.node-1{left:4%;top:16%}.node-2{right:2%;top:12%}.node-3{right:1%;bottom:18%}.node-4{left:0;bottom:14%}
.map-caption { position:absolute;bottom:-2px;left:50%;transform:translateX(-50%);color:#9198ac;font-size:10px;letter-spacing:.08em;white-space:nowrap; }

.status-rail { margin:18px 0 48px; min-height:82px; padding:16px 20px; display:grid; grid-template-columns:minmax(260px,1.6fr) repeat(3,1fr); align-items:center; border:1px solid #e8eaf2; background:rgba(255,255,255,.84); border-radius:18px; box-shadow:0 9px 26px rgba(31,41,90,.05); position:relative; overflow:hidden; }
.status-intro { display:flex;align-items:center;gap:12px; }.status-intro div{display:flex;flex-direction:column}.status-intro strong{font-size:14px}.status-intro small{font-size:11px;color:#8b93a7;margin-top:3px}
.live-dot{width:10px;height:10px;border-radius:50%;background:#28c9a0;box-shadow:0 0 0 5px rgba(40,201,160,.12);animation:livePulse 2s infinite}
.metric{padding-left:24px;border-left:1px solid #eef0f5;display:flex;align-items:baseline;gap:8px;cursor:default}.metric strong{font-size:24px;color:#263056;font-variant-numeric:tabular-nums}.metric span{font-size:11px;color:#8b93a7}.metric.warning{cursor:pointer}.metric.warning strong{color:#ee7b4e}
.rail-progress{position:absolute;left:0;right:0;bottom:0;height:3px;background:#edf0f7}.rail-progress i{display:block;height:100%;background:linear-gradient(90deg,#4f5bd5,#66d4ef);transition:width 1.4s cubic-bezier(.16,1,.3,1)}

.next-section,.knowledge-section{margin-top:44px}.section-heading{display:flex;justify-content:space-between;align-items:end;margin-bottom:18px}.section-heading h2{font-size:23px;letter-spacing:-.025em;color:#20283f;margin:6px 0 0}.section-note{font-size:12px;color:#9198aa}
.action-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.action-card{min-height:238px;position:relative;text-align:left;padding:22px;border:1px solid #e4e7f0;border-radius:18px;background:#fff;color:#20283f;cursor:pointer;overflow:hidden;box-shadow:0 8px 23px rgba(31,41,90,.05);transition:transform .28s cubic-bezier(.16,1,.3,1),box-shadow .28s,border-color .28s}.action-card::after{content:"";position:absolute;width:160px;height:160px;border-radius:50%;right:-80px;top:-92px;background:var(--glow,#eef0ff);transition:transform .45s cubic-bezier(.16,1,.3,1)}.action-card:hover{transform:translateY(-6px);box-shadow:0 18px 38px rgba(54,64,135,.13);border-color:#c7cdf8}.action-card:hover::after{transform:scale(1.22)}.action-card.primary{--glow:#e7eaff}.action-card.practice{--glow:#e3f9f5}.action-card.exam{--glow:#fff2df}.action-card.books{--glow:#e8f6ff}.action-index{position:absolute;right:21px;top:18px;color:#a0a6b7;font:700 11px/1 ui-monospace}.action-icon{width:44px;height:44px;border-radius:13px;display:grid;place-items:center;color:#5661db;background:#eef0ff;margin-bottom:19px}.practice .action-icon{color:#0a9d7a;background:#e8faf5}.exam .action-icon{color:#dc8a17;background:#fff4e5}.books .action-icon{color:#2987be;background:#e8f6ff}.action-card h3{font-size:17px;margin:0 0 9px}.action-card p{font-size:12px;line-height:1.65;color:#757d91;max-width:94%}.action-meta{position:absolute;left:22px;bottom:22px;font-size:10px;color:#979daf}.action-arrow{position:absolute;right:21px;bottom:20px;color:#6872e4;transition:transform .25s}.action-card:hover .action-arrow{transform:translate(3px,-3px)}

.knowledge-board{padding:27px 24px 30px;border:1px solid #e1e5f1;border-radius:24px;background:radial-gradient(circle at 50% 0,rgba(99,102,241,.055),transparent 38%),linear-gradient(180deg,rgba(255,255,255,.88),rgba(247,249,255,.78));box-shadow:0 12px 32px rgba(31,41,90,.05);overflow:hidden}.board-axis{display:grid;grid-template-columns:auto 1fr auto 1fr auto 1fr auto;align-items:center;gap:10px;margin:2px 10px 31px;color:#7d859a;font-size:10px;font-weight:750;letter-spacing:.05em}.board-axis i{height:1px;background:linear-gradient(90deg,#d8dcef,#8f98ed,#d8dcef);position:relative}.board-axis i::after{content:"";position:absolute;width:5px;height:5px;border-radius:50%;background:#7984ed;right:45%;top:-2px;animation:axisFlow 2.8s ease-in-out infinite}
.knowledge-grid{display:grid;grid-template-columns:repeat(4,1fr);column-gap:13px;row-gap:34px;position:relative}.knowledge-card{min-height:144px;padding:0 12px;border:0;background:transparent;text-align:center;cursor:pointer;color:var(--text-primary);display:flex;align-items:center;flex-direction:column;position:relative;isolation:isolate;transition:transform .28s,color .28s}.knowledge-card::after{content:"";position:absolute;z-index:-1;left:calc(50% + 29px);right:calc(-50% + 29px);top:27px;height:2px;background:linear-gradient(90deg,rgba(var(--kp-rgb),.42),#d8ddeb);box-shadow:0 0 0 4px rgba(255,255,255,.7)}.knowledge-card:nth-child(4n)::after,.knowledge-card:last-child::after{display:none}.knowledge-card:hover:not(.disabled){transform:translateY(-5px);color:var(--kp-accent)}.knowledge-card.disabled{cursor:default;opacity:.58}.kp-number{position:absolute;left:calc(50% + 18px);top:-4px;z-index:3;min-width:22px;height:17px;padding:0 5px;border-radius:9px;display:grid;place-items:center;color:#fff;background:var(--kp-accent);box-shadow:0 4px 10px rgba(var(--kp-rgb),.2);font:700 8px/1 ui-monospace}.kp-copy{width:100%}.kp-title{display:flex;align-items:center;flex-direction:column;gap:10px}.kp-title>span{width:56px;height:56px;display:grid;place-items:center;border:1px solid rgba(var(--kp-rgb),.16);border-radius:18px;color:var(--kp-accent);background:linear-gradient(145deg,#fff,var(--kp-soft));box-shadow:0 8px 19px rgba(var(--kp-rgb),.1);transition:transform .3s cubic-bezier(.16,1,.3,1),box-shadow .3s}.knowledge-card:hover .kp-title>span{transform:scale(1.08) rotate(-3deg);box-shadow:0 14px 27px rgba(var(--kp-rgb),.18)}.kp-copy strong{display:block;font-size:13px}.kp-copy p{max-width:210px;margin:7px auto 0;font-size:10px;color:#858da0;line-height:1.5;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.kp-foot{margin-top:11px;display:flex;justify-content:center;gap:13px;color:var(--kp-accent);font-size:10px}.kp-foot span:last-child{font-weight:700}

@keyframes coreWave{0%,100%{transform:scaleX(.5);opacity:.45}50%{transform:scaleX(1.25);opacity:1}}
@keyframes orbitA{0%{left:16%;top:48%}25%{left:48%;top:16%}50%{left:82%;top:49%}75%{left:50%;top:79%}100%{left:16%;top:48%}}
@keyframes orbitB{0%{left:7%;top:66%}25%{left:48%;top:9%}50%{left:91%;top:34%}75%{left:62%;top:91%}100%{left:7%;top:66%}}
@keyframes livePulse{50%{box-shadow:0 0 0 9px rgba(40,201,160,0)}}
@keyframes axisFlow{0%,100%{transform:translateX(-42px);opacity:0}50%{transform:translateX(42px);opacity:1}}
@media(max-width:1100px){.action-grid{grid-template-columns:1fr 1fr}}
@media(max-width:980px){.learning-hero{grid-template-columns:1fr;padding:38px}.power-map{height:260px}.status-rail{grid-template-columns:1fr repeat(3,auto);gap:14px}.status-intro{min-width:220px}.metric{padding-left:14px}.knowledge-grid{grid-template-columns:1fr 1fr}.knowledge-card:nth-child(4n)::after{display:block}.knowledge-card:nth-child(2n)::after{display:none}}
@media(max-width:680px){.learning-hero{padding:28px 22px;border-radius:20px}.hero-copy h1{font-size:31px}.power-map{display:none}.status-rail{grid-template-columns:1fr 1fr}.status-intro{grid-column:span 2}.metric{border:0;padding:0}.action-grid{grid-template-columns:1fr}.section-heading{align-items:flex-start;flex-direction:column;gap:7px}.board-axis{display:none}.knowledge-board{padding:20px 12px}.knowledge-grid{grid-template-columns:1fr}.knowledge-card{min-height:125px}.knowledge-card::after,.knowledge-card:nth-child(4n)::after{display:none}.kp-copy p{white-space:normal}}
@media(prefers-reduced-motion:reduce){.core-wave,.flow-pulse,.live-dot,.board-axis i::after{animation:none}.action-card,.knowledge-card,.kp-title>span,.hero-slide-enter-active,.hero-slide-leave-active{transition:none}}
</style>
