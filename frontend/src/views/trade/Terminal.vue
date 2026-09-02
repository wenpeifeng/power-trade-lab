<template>
  <div class="terminal">
    <!-- 顶栏 -->
    <header class="term-header">
      <div class="term-left">
        <span class="brand"><Zap :size="18" /> 电力交易终端</span>
      </div>
      <div class="term-right">
        <router-link to="/trade/lab" class="lab-link">进入全流程仿真 →</router-link>
        <span class="account-info">账户余额 ¥<span v-count="account.balance" data-count-decimals="0">0</span></span>
        <router-link to="/" class="back-home"><House :size="14" /> 返回门户</router-link>
      </div>
    </header>

    <div class="terminal-shell">
      <aside class="business-nav">
        <div class="nav-group-label">交易工作台</div>
        <router-link to="/trade/lab" class="business-link featured">
          <Orbit :size="17" /><span><strong>全流程仿真</strong><small>任务 · 出清 · 结算</small></span><ChevronRight :size="14" />
        </router-link>
        <div class="nav-group-label market-label">市场业务</div>
        <button
          v-for="market in markets"
          :key="market.id"
          class="market-nav-item"
          :class="{ active: market.id === marketId }"
          @click="switchMarket(market.id)"
        >
          <component :is="marketIcon(market.product)" :size="17" />
          <span><strong>{{ market.product_label }}</strong><small>{{ marketMeta[market.product]?.short || '交易品种' }}</small></span>
          <i v-if="market.id === marketId"></i>
        </button>
        <div class="nav-group-label tool-label">业务工具</div>
        <button class="market-nav-item" @click="scrollPositions">
          <Briefcase :size="17" /><span><strong>成交与持仓</strong><small>查看订单结果</small></span>
        </button>
        <button class="market-nav-item" @click="showReview = true">
          <ScanSearch :size="17" /><span><strong>策略复盘</strong><small>价差与改进建议</small></span>
        </button>
      </aside>
      <div class="terminal-workspace">
    <!-- 工具栏：品种 + 省份 + 日期 -->
    <div class="toolbar">
      <div class="tb-group">
        <span class="workspace-product">{{ currentMarket?.product_label || '交易市场' }}</span>
        <span class="product-scope">{{ currentMarketMeta.scope }}</span>
      </div>
      <div class="tb-group">
        <span class="tb-label">省份</span>
        <select v-model="selectedProvince" @change="reloadAll" class="tb-select">
          <option v-for="p in provinces" :key="p" :value="p">{{ p }}</option>
        </select>
      </div>
      <div class="tb-group">
        <span class="tb-label">交易日期</span>
        <select v-model="selectedDate" @change="loadQuote" class="tb-select">
          <option value="">最新</option>
          <option v-for="d in availableDates" :key="d" :value="d">{{ d }}</option>
        </select>
      </div>
      <div class="tb-group" v-if="quote.source_name">
        <span class="source-tag" :class="quote.provenance_level || quote.data_source">
          <MapPin :size="13" />
          {{ provenanceLabel(quote.provenance_level || quote.data_source) }} · {{ quote.source_name }}
        </span>
      </div>
    </div>

    <!-- 主体 -->
    <div class="term-body">
      <!-- 左栏：行情数据 -->
      <aside class="panel-left">
        <div class="section-label"><ChartBar :size="14" /> 行情概览</div>
        <div class="price-board">
          <div class="price-main">
            <div class="pm-label">出清均价</div>
            <div class="pm-value"><span v-if="quote.clearing_price" v-count="quote.clearing_price" data-count-decimals="1">0</span><span v-else>--</span></div>
            <div class="pm-unit">元/MWh</div>
          </div>
          <div class="price-row">
            <div class="pr-item up">
              <span class="pr-label">最高价</span>
              <span class="pr-val"><span v-if="quote.peak_price" v-count="quote.peak_price" data-count-decimals="1">0</span><span v-else>--</span></span>
            </div>
            <div class="pr-item down">
              <span class="pr-label">最低价</span>
              <span class="pr-val"><span v-if="quote.valley_price" v-count="quote.valley_price" data-count-decimals="1">0</span><span v-else>--</span></span>
            </div>
          </div>
          <div class="meta-row">
            <span>{{ selectedProvince }}</span>
            <span>{{ quote.trade_date || '最新' }}</span>
            <span>{{ quote.time_series?.length || 0 }}点/日</span>
          </div>
        </div>
      </aside>

      <!-- 中栏：行情图 -->
      <main class="panel-center">
        <div class="chart-header">
          <span class="chart-title"><Zap :size="14" /> {{ currentMarket?.product_label }} · {{ selectedProvince }} 分时电价</span>
          <span class="chart-date">{{ quote.trade_date || '最新日期' }}</span>
        </div>
        <div ref="chartRef" class="price-chart"></div>
      </main>

      <!-- 右栏：申报 -->
      <aside class="panel-right">
        <div class="section-label"><PenLine :size="14" /> 交易申报</div>
        <div class="order-form">
          <div class="form-row">
            <label>交易方向</label>
            <div class="dir-switch">
              <button class="dir-btn" :class="{active: orderForm.side === 'buy'}" @click="orderForm.side = 'buy'">
                买入（用电方）
              </button>
              <button class="dir-btn sell" :class="{active: orderForm.side === 'sell'}" @click="orderForm.side = 'sell'">
                卖出（发电方）
              </button>
            </div>
          </div>
          <div class="form-row">
            <label>申报价格 <span class="hint">元/MWh</span></label>
            <input v-model.number="orderForm.price" type="number" class="form-input" placeholder="如 320" />
          </div>
          <div class="form-row">
            <label>申报数量 <span class="hint">MWh</span></label>
            <input v-model.number="orderForm.volume" type="number" class="form-input" placeholder="如 500" />
          </div>
          <div class="form-summary" v-if="orderForm.price && orderForm.volume">
            预计金额: <strong>¥{{ (orderForm.price * orderForm.volume).toLocaleString() }}</strong>
          </div>
          <button class="submit-btn" :class="orderForm.side" :loading="submitting" @click="submitOrder" :disabled="submitting">
            {{ submitting ? '撮合中...' : `提交${orderForm.side === 'buy' ? '买入' : '卖出'}申报` }}
          </button>
          <button class="review-btn" @click="showReview = true"><ChartBar :size="14" /> 查看交易复盘</button>
        </div>
      </aside>
    </div>

    <!-- 成交记录栏 -->
    <div ref="positionsRef" class="positions-bar">
      <span class="pos-title"><Briefcase :size="14" /> 我的成交记录</span>
      <div class="pos-list" v-if="positions.trades?.length">
        <div v-for="t in positions.trades.slice(0, 8)" :key="t.id" class="pos-item">
          <span class="pos-dir" :class="t.side">{{ t.side === 'buy' ? '买' : '卖' }}</span>
            <span class="pos-vol"><span v-count="t.volume" data-count-decimals="1">0</span> MWh</span>
            <span class="pos-price">@ <span v-count="t.price" data-count-decimals="1">0</span> 元</span>
          <span class="pos-time">{{ formatTime(t.trade_time) }}</span>
        </div>
      </div>
      <div v-else class="pos-empty">暂无成交，在右侧提交你的第一笔申报</div>
    </div>
      </div>
    </div>

    <!-- 复盘抽屉 -->
    <el-drawer v-model="showReview" size="480px" direction="rtl" :with-header="false">
      <div class="review-panel" v-loading="reviewLoading">
        <div class="review-close" @click="showReview = false">✕</div>
        <h2 class="review-title"><ChartBar :size="18" /> 交易复盘报告</h2>
        <div v-if="review" class="review-body">
          <div class="review-summary">
            <div class="rs-item">
              <div class="rs-label">市场出清价</div>
              <div class="rs-value">{{ review.market_clearing_price }}</div>
            </div>
            <div class="rs-item">
              <div class="rs-label">总申报</div>
              <div class="rs-value">{{ review.total_orders }}笔</div>
            </div>
            <div class="rs-item">
              <div class="rs-label">策略盈亏</div>
              <div class="rs-value" :class="{ pos: review.total_pnl > 0, neg: review.total_pnl < 0 }">
                {{ review.total_pnl > 0 ? '+' : '' }}{{ review.total_pnl }}
              </div>
            </div>
          </div>
          <div class="review-advice">{{ review.summary }}</div>
          <div class="review-orders" v-if="review.orders?.length">
            <div class="ro-title">逐笔分析</div>
            <div v-for="o in review.orders" :key="o.order_id" class="ro-item">
              <span class="ro-side" :class="o.side">{{ o.side === 'buy' ? '买' : '卖' }}</span>
              <span class="ro-bid">报价{{ o.bid_price }}</span>
              <span class="ro-clearing">出清{{ o.market_clearing }}</span>
              <span class="ro-spread" :class="{ pos: o.spread > 0, neg: o.spread < 0 }">差{{ o.spread > 0 ? '+' : '' }}{{ o.spread }}</span>
              <small class="ro-advice">{{ o.advice }}</small>
            </div>
          </div>
          <div class="review-back-learn">
            <span class="rbl-label"><GraduationCap :size="14" /> 回到学习</span>
            <router-link to="/learn/wrong" class="rbl-link">去错题本复盘</router-link>
            <router-link to="/learn/exam" class="rbl-link">去考试中心</router-link>
          </div>
        </div>
        <div v-else-if="!reviewLoading" class="review-empty">暂无交易记录</div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import {
  Zap, MapPin, ChartBar, PenLine, Briefcase, House, Orbit, ChevronRight,
  Landmark, CalendarClock, Radio, Gauge, Leaf, ScanSearch, GraduationCap,
} from 'lucide-vue-next'
import { tradeApi } from '../../api'
import { startTradeGuide } from '../../guide/onboarding'

const markets = ref([])
const marketId = ref(2) // 默认日前现货
const currentMarket = ref(null)
const account = ref({ balance: 1000000 })
const quote = ref({})
const positions = ref({ trades: [] })
const submitting = ref(false)
const availableDates = ref([])
const selectedDate = ref('')
const provinces = ['山西', '山东', '广东', '浙江', '蒙西']
const selectedProvince = ref('山西')
const orderForm = reactive({ side: 'buy', price: 320, volume: 500 })
const showReview = ref(false)
const reviewLoading = ref(false)
const review = ref(null)
const chartRef = ref(null)
const positionsRef = ref(null)
let chart = null
const marketMeta = {
  mid_long_term: { short: '年度 / 月度 / 月内', scope: '当前开放：基础撮合演示', icon: Landmark },
  day_ahead: { short: '次日 24 时段计划', scope: '当前开放：分时行情与申报', icon: CalendarClock },
  realtime: { short: '运行日滚动调整', scope: '当前开放：分时行情与申报', icon: Radio },
  freq: { short: '调频容量与里程', scope: '当前开放：基础撮合演示', icon: Gauge },
  green: { short: '电能量与环境价值', scope: '当前开放：基础撮合演示', icon: Leaf },
}
const currentMarketMeta = computed(() => marketMeta[currentMarket.value?.product] || { short: '', scope: '基础撮合演示' })
const marketIcon = (product) => marketMeta[product]?.icon || Zap
const scrollPositions = () => positionsRef.value?.scrollIntoView({ behavior: 'smooth', block: 'center' })

const formatMoney = (n) => Number(n || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
const formatTime = (t) => t ? new Date(t).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''
const provenanceLabel = (level) => ({
  observed_public: '公开观测',
  observed_authorized: '授权观测',
  reconstructed: '重构数据',
  synthetic: '模拟数据',
})[level] || '来源待核验'

function switchMarket(id) {
  if (id === marketId.value) return
  marketId.value = id
  reloadAll()
}

async function reloadAll() {
  selectedDate.value = ''
  await loadAvailableDates()
  await loadQuote()
}

async function loadAvailableDates() {
  try {
    const res = await tradeApi.availableDates(marketId.value, selectedProvince.value)
    availableDates.value = res.dates || []
  } catch (e) { availableDates.value = [] }
}

async function loadQuote() {
  try {
    quote.value = await tradeApi.quote(marketId.value, selectedDate.value || undefined, selectedProvince.value)
    currentMarket.value = markets.value.find((m) => m.id === marketId.value)
    await nextTick()
    renderChart()
  } catch (e) { ElMessage.error('加载行情失败: ' + e.message) }
}

function renderChart() {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value, 'dark')
  const ts = quote.value.time_series || []
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 55, right: 25, top: 15, bottom: 35 },
    tooltip: { trigger: 'axis', formatter: (p) => `${p[0].axisValue}<br/>价格: <b>${p[0].value}</b> 元/MWh` },
    xAxis: {
      type: 'category', data: ts.map((t) => t.time),
      axisLabel: { interval: 11, color: '#8a8f9c', fontSize: 10 },
      axisLine: { lineStyle: { color: '#2a2e3a' } },
    },
    yAxis: {
      type: 'value', name: '元/MWh',
      nameTextStyle: { color: '#8a8f9c' },
      axisLabel: { color: '#8a8f9c' },
      splitLine: { lineStyle: { color: '#232730' } },
    },
    series: [{
      type: 'line', data: ts.map((t) => t.price), smooth: true, symbol: 'none',
      lineStyle: { color: '#5b8ff9', width: 2 },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(91,143,249,0.25)' },
        { offset: 1, color: 'rgba(91,143,249,0)' },
      ]) },
    }],
  })
}

async function submitOrder() {
  if (!orderForm.price || !orderForm.volume) {
    ElMessage.warning('请填写价格和数量')
    return
  }
  submitting.value = true
  try {
    const res = await tradeApi.submitOrder(
      marketId.value, orderForm.side,
      [{ price: orderForm.price, volume: orderForm.volume }]
    )
    ElMessage.success(`成交 ${res.filled_volume} MWh @ ${res.filled_price} 元/MWh`)
    loadPositions()
    account.value = await tradeApi.account()
  } catch (e) {
    ElMessage.error(e.message)
  }
  submitting.value = false
}

async function loadPositions() {
  try { positions.value = await tradeApi.positions() } catch (e) { console.error(e) }
}

async function loadReview() {
  reviewLoading.value = true
  try { review.value = await tradeApi.review(marketId.value) }
  catch (e) { ElMessage.error('复盘加载失败: ' + e.message) }
  reviewLoading.value = false
}

watch(showReview, (v) => { if (v) loadReview() })
const onResize = () => chart?.resize()

onMounted(async () => {
  try {
    const [mk, acc, pos] = await Promise.all([tradeApi.markets(), tradeApi.account(), tradeApi.positions()])
    markets.value = mk
    account.value = acc
    positions.value = pos
    currentMarket.value = mk.find(m => m.id === marketId.value)
    await reloadAll()
  } catch (e) {
    ElMessage.error('加载失败：' + e.message)
  }
  window.addEventListener('resize', onResize)
  // 首次进入触发交易引导
  setTimeout(() => startTradeGuide(), 800)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
})
</script>

<style scoped>
.terminal {
  min-height: 100vh; display: flex; flex-direction: column;
  background: #0f1320; color: #e0e3eb;
}

/* 顶栏 */
.term-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 0 24px; height: 52px; flex-shrink: 0;
  background: #1a1f2e; border-bottom: 1px solid #2a2e3a;
}
.brand { font-size: 17px; font-weight: 600; color: #5b8ff9; display: inline-flex; align-items: center; gap: 6px; }
.term-right { display: flex; align-items: center; gap: 16px; }
.lab-link { color: #07130f; border: 1px solid #5ce0b7; border-radius: 6px; padding: 7px 11px; text-decoration: none; font-size: 12px;font-weight:750;background:#5ce0b7;box-shadow:0 6px 15px rgba(92,224,183,.12) }
.lab-link:hover { background: #75e8c4; }
.account-info { font-size: 14px; color: #f0b042; font-weight: 600; }
.back-home { display:inline-flex;align-items:center;gap:6px;color:#fff;text-decoration:none;font-size:12px;font-weight:750;padding:7px 11px;border:1px solid #3f76de;border-radius:7px;background:#326bd4;box-shadow:0 7px 17px rgba(50,107,212,.24); }
.back-home:hover { color:#fff;border-color:#5489ec;background:#4079df;transform:translateY(-1px); }
.terminal-shell{min-height:calc(100vh - 52px);display:grid;grid-template-columns:218px minmax(0,1fr);flex:1}.business-nav{padding:14px 10px;border-right:1px solid #2a2e3a;background:#121725;overflow:auto}.terminal-workspace{min-width:0;display:flex;flex-direction:column}.nav-group-label{padding:7px 10px;color:#60697b;font:750 9px/1 ui-monospace;letter-spacing:.13em;text-transform:uppercase}.market-label,.tool-label{margin-top:13px}.business-link,.market-nav-item{width:100%;box-sizing:border-box;min-height:53px;padding:8px 9px;display:flex;align-items:center;gap:9px;border:0;border-radius:8px;background:transparent;color:#8993a7;text-decoration:none;text-align:left;cursor:pointer;position:relative;transition:.18s}.business-link:hover,.market-nav-item:hover{color:#dce5f3;background:#192132}.business-link>span,.market-nav-item>span{min-width:0;display:flex;flex-direction:column;flex:1}.business-link strong,.market-nav-item strong{font-size:12px;color:inherit}.business-link small,.market-nav-item small{margin-top:2px;color:#626d81;font-size:9px;white-space:nowrap}.business-link.featured{color:#62dfb8;border:1px solid rgba(92,224,183,.17);background:rgba(92,224,183,.055)}.business-link.featured small{color:#5a867a}.market-nav-item.active{color:#fff;background:linear-gradient(135deg,#25385d,#233157);box-shadow:inset 0 0 0 1px rgba(91,143,249,.25)}.market-nav-item.active>svg{color:#69a4ff}.market-nav-item.active small{color:#8ba0c1}.market-nav-item>i{position:absolute;right:0;top:13px;bottom:13px;width:2px;border-radius:2px;background:#5b8ff9;box-shadow:0 0 8px #5b8ff9}

/* 工具栏 */
.toolbar {
  display: flex; align-items: center; gap: 20px; flex-wrap: wrap;
  padding: 10px 24px; background: #161a28; border-bottom: 1px solid #2a2e3a;
}
.workspace-product{font-size:15px;font-weight:750;color:#e3e9f3}.product-scope{padding:3px 8px;border-radius:8px;color:#6f98dc;background:rgba(91,143,249,.1);font-size:10px}
.tb-group { display: flex; align-items: center; gap: 8px; }
.tb-label { font-size: 12px; color: #8a8f9c; }
.seg-control { display: flex; gap: 2px; background: #0f1320; border-radius: 6px; padding: 2px; }
.seg-btn {
  padding: 6px 14px; font-size: 13px; cursor: pointer; border-radius: 4px;
  color: #8a8f9c; transition: all 0.15s; border: none; background: transparent;
}
.seg-btn:hover { color: #e0e3eb; }
.seg-btn.active { background: #5b8ff9; color: #fff; }
.tb-select {
  background: #0f1320; color: #e0e3eb; border: 1px solid #2a2e3a;
  border-radius: 4px; padding: 5px 10px; font-size: 13px; cursor: pointer;
}
.source-tag { font-size: 12px; color: #5b8ff9; background: rgba(91,143,249,0.1); padding: 3px 10px; border-radius: 10px; display: inline-flex; align-items: center; gap: 4px; }
.source-tag.reconstructed { color: #f0b042; background: rgba(240,176,66,0.12); }
.source-tag.synthetic { color: #8a8f9c; background: rgba(138,143,156,0.12); }
.source-tag.observed_public,
.source-tag.observed_authorized { color: #26a69a; background: rgba(38,166,154,0.12); }

/* 主体三栏 */
.term-body {
  flex: 1; display: grid;
  grid-template-columns: 240px 1fr 280px;
  gap: 1px; background: #2a2e3a;
}
.panel-left, .panel-center, .panel-right {
  background: #161a28; padding: 16px;
}
.section-label { font-size: 13px; color: #8a8f9c; margin-bottom: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 5px; }

/* 左栏行情 */
.price-board { display: flex; flex-direction: column; gap: 12px; }
.price-main { text-align: center; padding: 16px 0; background: #0f1320; border-radius: 8px; }
.pm-label { font-size: 12px; color: #8a8f9c; }
.pm-value { font-size: 32px; font-weight: 700; color: #f0b042; margin: 4px 0; }
.pm-unit { font-size: 11px; color: #8a8f9c; }
.price-row { display: flex; gap: 8px; }
.pr-item { flex: 1; padding: 10px; background: #0f1320; border-radius: 6px; text-align: center; }
.pr-label { display: block; font-size: 11px; color: #8a8f9c; }
.pr-val { font-size: 16px; font-weight: 600; }
.pr-item.up .pr-val { color: #ef5350; }
.pr-item.down .pr-val { color: #26a69a; }
.meta-row { display: flex; justify-content: space-between; font-size: 11px; color: #8a8f9c; padding: 0 4px; }

/* 中栏图表 */
.chart-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.chart-title { font-size: 14px; font-weight: 600; display: inline-flex; align-items: center; gap: 5px; }
.chart-date { font-size: 12px; color: #5b8ff9; }
.price-chart { width: 100%; height: 360px; }

/* 右栏申报 */
.order-form { display: flex; flex-direction: column; gap: 14px; }
.form-row { display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 12px; color: #8a8f9c; }
.hint { font-size: 11px; color: #5a5f6c; }
.dir-switch { display: flex; gap: 6px; }
.dir-btn {
  flex: 1; padding: 10px; font-size: 13px; cursor: pointer; border-radius: 6px;
  border: 1px solid #2a2e3a; background: #0f1320; color: #8a8f9c; transition: all 0.15s;
}
.dir-btn.active { background: #ef5350; color: #fff; border-color: #ef5350; }
.dir-btn.sell.active { background: #26a69a; border-color: #26a69a; }
.form-input {
  background: #0f1320; color: #e0e3eb; border: 1px solid #2a2e3a;
  border-radius: 6px; padding: 10px 12px; font-size: 15px;
}
.form-input:focus { outline: none; border-color: #5b8ff9; }
.form-summary { font-size: 13px; color: #8a8f9c; text-align: right; }
.form-summary strong { color: #f0b042; }
.submit-btn {
  width: 100%; padding: 12px; font-size: 15px; font-weight: 600; cursor: pointer;
  border: none; border-radius: 6px; background: #ef5350; color: #fff; transition: all 0.15s;
}
.submit-btn.sell { background: #26a69a; }
.submit-btn:hover { opacity: 0.9; }
.submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.review-btn {
  width: 100%; padding: 10px; font-size: 13px; cursor: pointer;
  border: 1px solid #2a2e3a; border-radius: 6px; background: transparent; color: #8a8f9c;
  display: inline-flex; align-items: center; justify-content: center; gap: 5px;
}
.review-btn:hover { border-color: #5b8ff9; color: #5b8ff9; }

/* 成交记录栏 */
.positions-bar {
  padding: 12px 24px; background: #161a28; border-top: 1px solid #2a2e3a; flex-shrink: 0;
}
.pos-title { font-size: 13px; color: #8a8f9c; margin-bottom: 8px; display: inline-flex; align-items: center; gap: 5px; }
.pos-list { display: flex; gap: 12px; flex-wrap: wrap; }
.pos-item {
  display: flex; align-items: center; gap: 8px; padding: 6px 12px;
  background: #0f1320; border-radius: 6px; font-size: 12px;
}
.pos-dir { width: 20px; height: 20px; border-radius: 3px; display: flex; align-items: center; justify-content: center; font-size: 11px; color: #fff; }
.pos-dir.buy { background: #ef5350; }
.pos-dir.sell { background: #26a69a; }
.pos-vol { color: #e0e3eb; }
.pos-price { color: #8a8f9c; }
.pos-time { color: #5a5f6c; font-size: 11px; }
.pos-empty { font-size: 13px; color: #5a5f6c; }

/* 复盘抽屉 */
.review-panel { padding: 20px 24px; position: relative; color: #303133; }
.review-close { position: absolute; top: 16px; right: 16px; cursor: pointer; font-size: 18px; color: #909399; }
.review-title { font-size: 18px; margin: 0 0 16px; display: inline-flex; align-items: center; gap: 6px; }
.review-summary { display: flex; gap: 16px; margin-bottom: 16px; }
.rs-item { flex: 1; text-align: center; padding: 12px; background: #f5f7fa; border-radius: 8px; }
.rs-label { font-size: 11px; color: #909399; margin-bottom: 4px; }
.rs-value { font-size: 18px; font-weight: 700; }
.rs-value.pos { color: #26a69a; }
.rs-value.neg { color: #ef5350; }
.review-advice { padding: 12px; background: #e8f5e9; border-radius: 8px; font-size: 13px; line-height: 1.7; color: #2e7d32; margin-bottom: 16px; }
.review-orders { margin-top: 8px; }
.ro-title { font-size: 13px; font-weight: 600; margin-bottom: 8px; color: #606266; }
.ro-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; background: #f5f7fa; border-radius: 6px; margin-bottom: 4px; font-size: 12px; flex-wrap: wrap; }
.ro-side { width: 20px; height: 20px; border-radius: 3px; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 10px; }
.ro-side.buy { background: #ef5350; }
.ro-side.sell { background: #26a69a; }
.ro-spread { font-weight: 600; }
.ro-spread.pos { color: #26a69a; }
.ro-spread.neg { color: #ef5350; }
.ro-advice { width: 100%; color: #909399; font-size: 11px; }
.review-empty { text-align: center; color: #909399; padding: 40px; }
.review-back-learn { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-top:18px; padding-top:14px; border-top:1px solid #ebeef5; }
.rbl-label { display:inline-flex; align-items:center; gap:5px; font-size:11px; color:#909399; letter-spacing:.1em; font-weight:700; }
.rbl-link { display:inline-flex; align-items:center; gap:5px; padding:7px 12px; border-radius:6px; font-size:13px; text-decoration:none; color:#26a69a; border:1px solid #b7e8df; background:#f0faf8; font-weight:600; }
.rbl-link:hover { background:#d9f4ee; border-color:#8fd9cb; }
@media(max-width:900px){.terminal-shell{grid-template-columns:1fr}.business-nav{display:flex;gap:6px;overflow-x:auto;border-right:0;border-bottom:1px solid #2a2e3a;padding:8px}.nav-group-label,.tool-label{display:none}.market-nav-item,.business-link.featured{width:auto;min-width:145px}.term-right .account-info{display:none}.term-body{grid-template-columns:1fr}.panel-left,.panel-right{display:none}}
@media(max-width:620px){.term-header{padding:0 12px}.term-right{gap:6px}.back-home{font-size:0}.back-home svg{width:15px}.toolbar{padding:9px 12px}.tb-group:first-child{width:100%}.positions-bar{padding:12px}}
</style>
