<template>
  <div class="sim-lab" v-loading="busy">
    <header class="lab-header">
      <div>
        <span class="eyebrow">POWER MARKET PRACTICE LAB</span>
        <h1>交易仿真实验室</h1>
        <p>单人即可完成：场景简报 → 分时申报 → 封盘 → 市场出清 → 计量结算 → 策略复盘</p>
      </div>
      <nav>
        <router-link to="/trade">行情终端</router-link>
        <router-link to="/" class="portal-link"><House :size="14" /> 返回门户</router-link>
      </nav>
    </header>

    <div class="stage-rail">
      <div v-for="(item, index) in stages" :key="item.key" :class="{ active: stageIndex >= index, current: session?.stage === item.key }">
        <i>{{ index + 1 }}</i><span>{{ item.label }}</span>
      </div>
    </div>

    <section v-if="!session" class="scenario-select">
      <div class="section-title"><span>01</span><div><h2>选择你的交易角色</h2><p>每个任务拥有独立输入快照、规则版本和随机种子，可重复核验。</p></div></div>
      <div class="scenario-grid">
        <article v-for="scenario in scenarios" :key="scenario.code">
          <span class="role">{{ scenario.role === 'retailer' ? 'BUY SIDE · 售电侧' : 'SELL SIDE · 发电侧' }}</span>
          <h3>{{ scenario.title }}</h3>
          <p>{{ scenario.subtitle }}</p>
          <dl><div><dt>目标</dt><dd>{{ scenario.objective }}</dd></div><div><dt>颗粒度</dt><dd>{{ scenario.period_count }}时段 · 1-5段报价</dd></div></dl>
          <button @click="createTask(scenario.code)">创建仿真任务 →</button>
        </article>
      </div>
    </section>

    <template v-else>
      <div class="task-bar">
        <div><strong>任务 #{{ session.id }}</strong><span>{{ session.scenario.title }} · {{ session.province }} · {{ session.trade_date }}</span></div>
        <div class="audit"><span>{{ provenanceLabel(session.input.provenance.level) }}</span><small>{{ session.input.provenance.source_name }}</small></div>
        <button @click="resetTask">新建任务</button>
      </div>

      <section v-if="session.stage === 'briefing'" class="briefing-grid">
        <div class="brief-card main-brief">
          <span class="eyebrow">MARKET BRIEFING</span>
          <h2>{{ session.scenario.objective }}</h2>
          <div v-for="(item,index) in session.scenario.briefing" :key="item" class="brief-point"><b>0{{ index+1 }}</b><p>{{ item }}</p></div>
          <button class="primary" @click="openTask">我已读懂简报，进入24时段报价 →</button>
        </div>
        <div class="brief-card">
          <h3>任务边界</h3>
          <dl class="constraints">
            <div><dt>交易方向</dt><dd>{{ session.side === 'buy' ? '买入 / 用电侧' : '卖出 / 发电侧' }}</dd></div>
            <div><dt>时段上限</dt><dd>{{ session.input.constraints.max_volume_per_period }} MWh</dd></div>
            <div><dt>价格范围</dt><dd>0—3000 元/MWh</dd></div>
            <div><dt>规则版本</dt><dd>{{ session.rules_version }}</dd></div>
            <div><dt>引擎版本</dt><dd>{{ session.engine_version }}</dd></div>
            <div><dt>可复现种子</dt><dd>{{ session.random_seed }}</dd></div>
          </dl>
          <p class="source-note">{{ session.input.provenance.source_note }}</p>
        </div>
      </section>

      <section v-if="session.stage === 'bidding'" class="bid-workbench">
        <div class="workbench-head">
          <div><span class="eyebrow">BIDDING WORKBENCH</span><h2>24时段分段申报</h2><p>第一段保障核心电量，第二段用于表达边际策略；空着第二段即可按单段提交。</p></div>
          <div class="legend"><span class="forecast-dot"></span>{{ session.input.reference_curve_label }}<span class="price-dot"></span>参考价（非出清价）</div>
        </div>
        <div class="bid-table">
          <div class="bid-row bid-head"><span>时段</span><span>预测量</span><span>第一段电量</span><span>第一段价格</span><span>第二段电量</span><span>第二段价格</span><span>参考价</span></div>
          <div v-for="row in bids" :key="row.period" class="bid-row">
            <strong>{{ String(row.period).padStart(2,'0') }}:00</strong>
            <span class="forecast">{{ row.forecast }}</span>
            <input v-model.number="row.volume1" type="number" min="0" step="1" />
            <input v-model.number="row.price1" type="number" min="0" max="3000" step="1" />
            <input v-model.number="row.volume2" type="number" min="0" step="1" placeholder="可选" />
            <input v-model.number="row.price2" type="number" min="0" max="3000" step="1" placeholder="可选" />
            <span class="reference">{{ row.reference }}</span>
          </div>
        </div>
        <div class="sticky-actions"><span>总申报 {{ totalBidVolume.toFixed(1) }} MWh</span><button @click="saveBids">保存申报</button><button class="danger" @click="sealTask">封盘并停止修改 →</button></div>
      </section>

      <section v-if="session.stage === 'sealed'" class="action-stage">
        <span class="stamp">SEALED</span><h2>申报已封盘</h2><p>你的量价曲线已经固化。执行出清后，隐藏的市场出清价格才会揭示。</p>
        <button class="primary" @click="clearTask">执行市场出清 →</button>
      </section>

      <section v-if="session.stage === 'cleared'" class="result-stage">
        <div class="result-summary">
          <div><small>总申报</small><strong>{{ session.clearing.requested_volume }}</strong><span>MWh</span></div>
          <div><small>出清电量</small><strong>{{ session.clearing.cleared_volume }}</strong><span>MWh</span></div>
          <div><small>出清率</small><strong>{{ session.clearing.fill_rate }}</strong><span>%</span></div>
          <div><small>加权出清价</small><strong>{{ session.clearing.weighted_price ?? '--' }}</strong><span>元/MWh</span></div>
        </div>
        <h2>逐时出清结果</h2>
        <div class="compact-table">
          <div v-for="row in session.clearing.periods" :key="row.period">
            <span>{{ row.time }}</span><span>出清价 {{ row.clearing_price }}</span><span>{{ row.cleared_volume }}/{{ row.requested_volume }} MWh</span><b :class="{ low: row.fill_rate < 90 }">{{ row.fill_rate }}%</b>
          </div>
        </div>
        <div class="next-action"><p>下一步将生成可复现的实际计量偏差，并按偏差价格计算费用。</p><button class="primary" @click="settleTask">进入计量结算 →</button></div>
      </section>

      <section v-if="session.stage === 'settled'" class="settled-stage">
        <div class="score-card">
          <span>STRATEGY SCORE</span><strong>{{ session.review.score }}</strong><em>/100 · {{ session.review.grade }}</em>
          <p>{{ session.review.summary }}</p>
        </div>
        <div class="settlement-card">
          <h2>结算对账</h2>
          <dl><div><dt>电能量金额</dt><dd>¥{{ money(session.settlement.energy_amount) }}</dd></div><div><dt>总偏差电量</dt><dd>{{ session.settlement.total_deviation }} MWh</dd></div><div><dt>偏差费用</dt><dd>¥{{ money(session.settlement.deviation_charge) }}</dd></div><div class="total"><dt>{{ session.settlement.amount_label }}</dt><dd>¥{{ money(session.settlement.net_amount) }}</dd></div></dl>
        </div>
        <div class="review-card">
          <div><h3>需要补强的知识</h3><template v-for="g in gaps" :key="g.text"><router-link v-if="g.kpId" :to="{path:'/learn/quiz', query:{kp:g.kpId}}" class="gap-link">{{ g.text }}</router-link><span v-else>{{ g.text }}</span></template></div>
          <div><h3>下一轮动作</h3><p v-for="action in session.review.next_actions" :key="action">→ {{ action }}</p></div>
          <span class="review-status">复盘已保存至本次仿真记录</span>
          <div class="back-to-learn">
            <span class="btl-label"><GraduationCap :size="14" /> 回到学习</span>
            <router-link to="/learn/wrong">去错题本复盘</router-link>
            <router-link to="/learn/exam">去考试中心</router-link>
          </div>
        </div>
        <details><summary>查看逐时结算明细</summary><div class="compact-table"><div v-for="row in session.settlement.periods" :key="row.period"><span>{{ row.time }}</span><span>实际 {{ row.actual_volume }}</span><span>偏差 {{ row.deviation_volume }}</span><b>¥{{ money(row.deviation_charge) }}</b></div></div></details>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { tradeApi, learnApi } from '../../api'
import { House, GraduationCap } from 'lucide-vue-next'

const route = useRoute()
const busy = ref(false)
const scenarios = ref([])
const session = ref(null)
const bids = ref([])
// 知识点 name → id 映射，按 name 长度降序（优先更具体的长名匹配）。
// 在结算复盘阶段把 knowledge_gaps 字符串解析为可点击的练本节入口。
const kpEntries = ref([])  // [{name, id}]
const gaps = computed(() => {
  const list = session.value?.review?.knowledge_gaps || []
  return list.map(text => {
    let kpId = null
    for (const { name, id } of kpEntries.value) {
      if (name && (text.includes(name) || name.includes(text))) { kpId = id; break }
    }
    return { text, kpId }
  })
})
const stages = [
  { key:'briefing', label:'场景简报' }, { key:'bidding', label:'分时申报' }, { key:'sealed', label:'封盘' },
  { key:'cleared', label:'市场出清' }, { key:'settled', label:'结算复盘' },
]
const stageIndex = computed(() => Math.max(0, stages.findIndex(item => item.key === session.value?.stage)))
const totalBidVolume = computed(() => bids.value.reduce((sum,row) => sum + Number(row.volume1||0) + Number(row.volume2||0), 0))
const provenanceLabel = (level) => ({ observed_public:'公开观测',observed_authorized:'授权观测',reconstructed:'公开数据重构',synthetic:'教学模拟' }[level] || '来源待核验')
const money = (n) => Number(n || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })

function initBids() {
  if (!session.value) return
  if (session.value.bids) {
    bids.value = session.value.bids.map(row => ({
      period: row.period, forecast: session.value.input.forecast_curve[row.period],
      reference: session.value.input.price_reference[row.period],
      volume1: row.segments[0]?.volume || '', price1: row.segments[0]?.price || '',
      volume2: row.segments[1]?.volume || '', price2: row.segments[1]?.price || '',
    }))
    return
  }
  const buy = session.value.side === 'buy'
  bids.value = session.value.input.forecast_curve.map((forecast, period) => ({
    period, forecast, reference: session.value.input.price_reference[period],
    volume1: Number((forecast * .8).toFixed(1)),
    price1: Math.round(session.value.input.price_reference[period] + (buy ? 18 : -18)),
    volume2: Number((forecast * .2).toFixed(1)),
    price2: Math.round(session.value.input.price_reference[period] + (buy ? -8 : 8)),
  }))
}
function payloadBids() {
  return bids.value.map(row => {
    const segments = [{ volume:Number(row.volume1), price:Number(row.price1) }]
    if (Number(row.volume2) > 0) segments.push({ volume:Number(row.volume2), price:Number(row.price2) })
    return { period:row.period, segments }
  })
}
async function loadScenarios() {
  const res = await tradeApi.simulationScenarios()
  scenarios.value = res.scenarios
  if (route.query.scenario && scenarios.value.some(s => s.code === route.query.scenario)) await createTask(route.query.scenario)
}
async function createTask(code) {
  busy.value = true
  try { session.value = await tradeApi.createSimulation({ scenario_code:code, province:'山西' }) }
  catch(e){ ElMessage.error(e.message) } finally { busy.value = false }
}
async function openTask() {
  busy.value = true
  try { session.value = await tradeApi.openSimulation(session.value.id); initBids() }
  catch(e){ ElMessage.error(e.message) } finally { busy.value = false }
}
async function saveBids(showMessage=true) {
  busy.value = true
  try {
    session.value = await tradeApi.saveSimulationBids(session.value.id, payloadBids())
    if(showMessage) ElMessage.success('24时段申报已保存')
    return true
  } catch(e){ ElMessage.error(e.message); return false } finally { busy.value = false }
}
async function sealTask() {
  const saved = await saveBids(false)
  if (!saved) return
  try {
    await ElMessageBox.confirm('封盘后不能再修改报价，确认继续？','确认封盘',{type:'warning'})
    busy.value = true
    session.value = await tradeApi.sealSimulation(session.value.id)
  } catch(e) { if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || '操作失败') } finally { busy.value=false }
}
async function clearTask() { busy.value=true; try{session.value=await tradeApi.clearSimulation(session.value.id)}catch(e){ElMessage.error(e.message)}finally{busy.value=false} }
async function settleTask() { busy.value=true; try{session.value=await tradeApi.settleSimulation(session.value.id)}catch(e){ElMessage.error(e.message)}finally{busy.value=false} }
function resetTask(){ session.value=null; bids.value=[] }
onMounted(async()=>{
  busy.value=true
  // 知识点树与场景并行加载；树加载失败不阻断仿真主流程
  learnApi.knowledgeTree()
    .then(tree => {
      kpEntries.value = (tree || [])
        .filter(kp => kp && kp.name)
        .map(kp => ({ name: kp.name, id: kp.id }))
        .sort((a, b) => b.name.length - a.name.length)
    })
    .catch(() => {})
  try{await loadScenarios()}catch(e){ElMessage.error(e.message)}finally{busy.value=false}
})
</script>

<style scoped>
.sim-lab{min-height:100vh;padding:34px 4vw 70px;color:#e8edf8;background:#070d18;font-family:Inter,"PingFang SC",sans-serif}.lab-header{max-width:1440px;margin:auto;display:flex;justify-content:space-between;gap:40px;align-items:flex-end}.eyebrow{font-size:10px;letter-spacing:.2em;color:#54d8b1;font-weight:800}.lab-header h1{font-size:36px;margin:8px 0 5px}.lab-header p,.section-title p,.workbench-head p{color:#7f8ba2;margin:0}.lab-header nav{display:flex;align-items:center;gap:10px}.lab-header a{display:inline-flex;align-items:center;gap:6px;color:#8d99ae;text-decoration:none;font-size:13px;padding:7px 10px;border-radius:7px}.lab-header a:hover{color:#d9e2ef;background:#101b2b}.lab-header .portal-link{color:#07130f;background:#4fd5ad;font-weight:750}.lab-header .portal-link:hover{color:#07130f;background:#67dfbb}.stage-rail{max-width:1050px;margin:42px auto;display:grid;grid-template-columns:repeat(5,1fr);position:relative}.stage-rail:before{content:"";position:absolute;top:17px;left:10%;right:10%;height:1px;background:#263249}.stage-rail div{position:relative;z-index:1;text-align:center;color:#57657b;font-size:11px}.stage-rail i{display:grid;place-items:center;width:35px;height:35px;margin:0 auto 7px;border-radius:50%;font-style:normal;background:#111b2c;border:1px solid #2b3850}.stage-rail .active{color:#aab7ca}.stage-rail .active i{color:#07120f;background:#51d4ac;border-color:#51d4ac}.stage-rail .current i{box-shadow:0 0 0 7px rgba(81,212,172,.12)}section,.task-bar{max-width:1380px;margin:0 auto}.section-title{display:flex;gap:18px;align-items:start;margin-bottom:22px}.section-title>span{color:#48d4a8;font-size:12px}.section-title h2{margin:0 0 6px}.scenario-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}.scenario-grid article,.brief-card,.settlement-card,.review-card{padding:28px;border:1px solid #1c2a3e;border-radius:14px;background:linear-gradient(145deg,#0d1625,#0a111d)}.role{color:#56d9b2;font-size:10px;letter-spacing:.13em}.scenario-grid h3{font-size:22px;margin:13px 0 7px}.scenario-grid p{color:#8290a7}.scenario-grid dl{margin:24px 0}.scenario-grid dl div{padding:9px 0;border-top:1px solid #1b293b}.scenario-grid dt{color:#58667b;font-size:11px}.scenario-grid dd{margin:4px 0;color:#bdc7d6}.scenario-grid button,.primary,.sticky-actions button{border:0;border-radius:7px;padding:11px 16px;background:#4fd5ad;color:#07130f;font-weight:750;cursor:pointer}.task-bar{display:flex;align-items:center;gap:24px;margin-bottom:20px;padding:15px 18px;background:#0d1624;border:1px solid #1c2a3e;border-radius:10px}.task-bar>div:first-child{display:flex;gap:12px;flex:1}.task-bar span,.task-bar small{color:#8290a7}.audit{display:flex;flex-direction:column;text-align:right}.audit span{color:#4fd5ad}.task-bar button{background:none;border:1px solid #344258;color:#a9b4c6;border-radius:6px;padding:7px 12px;cursor:pointer}.briefing-grid{display:grid;grid-template-columns:1.55fr 1fr;gap:18px}.main-brief h2{font-size:27px;max-width:700px}.brief-point{display:flex;gap:16px;padding:17px 0;border-top:1px solid #1d2a3c}.brief-point b{color:#4fd5ad}.brief-point p{margin:0;color:#a7b2c4;line-height:1.65}.constraints div{display:flex;justify-content:space-between;padding:11px 0;border-bottom:1px solid #1c293b}.constraints dt{color:#718097}.constraints dd{margin:0}.source-note{padding:14px;color:#75839a;background:#09101b;font-size:12px;line-height:1.6}.workbench-head{display:flex;justify-content:space-between;align-items:end;margin-bottom:18px}.workbench-head h2{margin:6px 0}.legend{font-size:11px;color:#728097}.legend span{display:inline-block;width:7px;height:7px;border-radius:50%;margin:0 6px 0 15px}.forecast-dot{background:#4fd5ad}.price-dot{background:#f0b65d}.bid-table{border:1px solid #1d2a3d;border-radius:10px;overflow:hidden}.bid-row{display:grid;grid-template-columns:80px repeat(6,minmax(100px,1fr));gap:9px;align-items:center;padding:8px 12px;border-bottom:1px solid #172337;background:#0b1421}.bid-row:nth-child(odd){background:#0d1725}.bid-head{position:sticky;top:0;background:#142034!important;color:#75849b;font-size:11px}.bid-row input{width:100%;box-sizing:border-box;background:#07101c;border:1px solid #27364c;border-radius:5px;color:#dce5f2;padding:8px}.forecast{color:#4fd5ad}.reference{color:#e7ad55}.sticky-actions{position:sticky;bottom:14px;margin-top:16px;padding:13px 16px;background:rgba(16,26,42,.94);backdrop-filter:blur(12px);border:1px solid #26364c;border-radius:9px;display:flex;align-items:center;justify-content:flex-end;gap:10px}.sticky-actions span{margin-right:auto}.sticky-actions .danger{background:#ecb65f}.action-stage{text-align:center;padding:90px 20px;border:1px solid #1d2c40;background:#0c1522;border-radius:14px}.stamp{display:inline-block;padding:8px 18px;color:#ecb45d;border:2px solid #ecb45d;transform:rotate(-4deg);letter-spacing:.17em}.action-stage h2{font-size:30px}.action-stage p{color:#8491a6}.result-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:28px}.result-summary>div{padding:20px;background:#0e1827;border:1px solid #1c2b3f;border-radius:10px}.result-summary small{display:block;color:#718097}.result-summary strong{font-size:28px;color:#4fd5ad;margin-right:5px}.result-summary span{font-size:11px;color:#77849a}.compact-table{border:1px solid #1d2b3f;border-radius:9px;max-height:390px;overflow:auto}.compact-table>div{display:grid;grid-template-columns:80px 1fr 1fr 80px;padding:10px 14px;border-bottom:1px solid #18263a;color:#9da9bb}.compact-table b{color:#4fd5ad}.compact-table b.low{color:#efaa61}.next-action{display:flex;justify-content:space-between;align-items:center;margin-top:18px}.next-action p{color:#75839a}.settled-stage{display:grid;grid-template-columns:.8fr 1.2fr;gap:18px}.score-card{padding:32px;border-radius:14px;background:linear-gradient(145deg,#12362f,#0d201f);border:1px solid #25604f}.score-card>span{display:block;letter-spacing:.16em;font-size:10px;color:#65dab9}.score-card strong{display:block;font-size:76px;line-height:1;color:#58dbb3;margin-top:20px}.score-card em{font-style:normal;color:#a7cfc2}.score-card p{color:#89ad9f;line-height:1.7}.settlement-card dl div{display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid #1b293c}.settlement-card dt{color:#7e8ba0}.settlement-card dd{margin:0}.settlement-card .total{font-size:17px;color:#52d7af}.review-card{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr auto;gap:24px;align-items:center}.review-card span{display:inline-block;padding:5px 9px;margin:3px;color:#e9b45c;background:#30281c;border-radius:5px;font-size:12px}.review-card p{color:#9da9bb}.review-card a{color:#58dbb3;text-decoration:none}
.review-card a.gap-link{display:inline-block;padding:5px 9px;margin:3px;background:rgba(88,219,179,.08);border:1px solid rgba(88,219,179,.25);border-radius:5px;font-size:12px;color:#58dbb3;text-decoration:none;cursor:pointer}
.review-card a.gap-link:hover{background:rgba(88,219,179,.16);border-color:rgba(88,219,179,.4)}details{grid-column:1/-1}summary{cursor:pointer;color:#8e9aaf;padding:13px 0}
.review-card .review-status{color:#58dbb3;background:rgba(88,219,179,.08);border:1px solid rgba(88,219,179,.18);white-space:nowrap}
.review-card .back-to-learn{grid-column:1/-1;display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:14px 0 4px;border-top:1px solid #1b293c}
.review-card .btl-label{display:inline-flex;align-items:center;gap:6px;color:#7f8ba0;font-size:11px;letter-spacing:.12em;font-weight:700}
.review-card .back-to-learn a{display:inline-flex;align-items:center;gap:5px;padding:8px 13px;border:1px solid #25604f;border-radius:7px;background:rgba(88,219,179,.06);font-size:13px;font-weight:650}
.review-card .back-to-learn a:hover{background:rgba(88,219,179,.14)}
@media(max-width:900px){.lab-header,.workbench-head{align-items:flex-start;flex-direction:column}.scenario-grid,.briefing-grid,.settled-stage{grid-template-columns:1fr}.bid-table{overflow-x:auto}.bid-row{min-width:850px}.result-summary{grid-template-columns:repeat(2,1fr)}.review-card{grid-template-columns:1fr}.stage-rail span{display:none}}
</style>
