<template>
  <div class="admin-page">
    <header class="admin-header">
      <span class="brand"><Settings :size="18" /> 管理后台</span>
      <router-link to="/" class="back-home">← 返回门户</router-link>
    </header>

    <main class="admin-main" v-loading="loading">
      <!-- 题库统计 -->
      <section class="stats-section">
        <h3><BarChart3 :size="18" /> 题库与数据统计</h3>
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-num">{{ stats.questions?.total || 0 }}</div>
            <div class="stat-label">总题数</div>
          </div>
          <div class="stat-card real">
            <div class="stat-num">{{ stats.questions?.real_exam || 0 }}</div>
            <div class="stat-label">历年真题</div>
          </div>
          <div class="stat-card ai">
            <div class="stat-num">{{ stats.questions?.ai_generated || 0 }}</div>
            <div class="stat-label">AI生成</div>
          </div>
          <div class="stat-card crawler">
            <div class="stat-num">{{ stats.questions?.crawler || 0 }}</div>
            <div class="stat-label">爬虫抓取</div>
          </div>
          <div class="stat-card policy">
            <div class="stat-num">{{ stats.policies?.total || 0 }}</div>
            <div class="stat-label">政策数</div>
          </div>
        </div>
      </section>

      <!-- 爬虫管理 -->
      <section class="crawler-section">
        <div class="section-head">
          <h3><Bug :size="18" /> 数据源爬虫</h3>
          <div class="sched-status">
            <span class="dot" :class="{ on: sources?.scheduler?.running }"></span>
            调度器{{ sources?.scheduler?.running ? '运行中' : '已停止' }}
          </div>
        </div>
        <div class="crawler-list">
          <div v-for="s in sources?.sources || []" :key="s.name" class="crawler-card">
            <div class="cc-info">
              <div class="cc-name">{{ s.label }}</div>
              <div class="cc-desc">{{ s.desc }}</div>
              <div class="cc-sched"><Clock :size="12" /> {{ s.schedule }}</div>
            </div>
            <el-button
              size="small" type="primary" plain
              :loading="running[s.name]"
              @click="runCrawler(s.name)"
            >立即运行</el-button>
          </div>
        </div>
        <div v-if="runResult" class="run-result" :class="{ ok: !runResult.errors }">
          {{ runResult.source }}: 政策+{{ runResult.policies_new || 0 }} 题+{{ runResult.questions_new || 0 }}
          <span v-if="runResult.error_msg">（{{ runResult.error_msg }}）</span>
        </div>
      </section>

      <!-- AI生题 -->
      <section class="ai-section">
        <h3><Bot :size="18" /> AI智能生题</h3>
        <p class="section-desc">基于政策原文或知识点，用LLM自动生成题目并标注考点</p>
        <div class="ai-tabs">
          <div class="ai-card">
            <div class="ai-title">基于政策生题</div>
            <div class="ai-form">
              <el-input-number v-model="aiPolicy.id" :min="1" size="small" placeholder="政策ID" />
              <el-input-number v-model="aiPolicy.count" :min="1" :max="10" size="small" />
              <el-button size="small" type="primary" :loading="aiPolicy.loading" @click="genFromPolicy">生成</el-button>
            </div>
            <div v-if="aiPolicy.result" class="ai-result">
              生成 {{ aiPolicy.result.generated }} 题
              <div v-for="q in aiPolicy.result.questions" :key="q.id" class="gen-q">
                [{{ q.type }}] {{ q.stem.slice(0, 40) }}...
              </div>
            </div>
          </div>
          <div class="ai-card">
            <div class="ai-title">基于知识点生题</div>
            <div class="ai-form">
              <el-select v-model="aiKp.code" size="small" placeholder="选知识点" style="width:140px">
                <el-option v-for="kp in knowledgeTree" :key="kp.code" :label="kp.name" :value="kp.code" />
              </el-select>
              <el-input-number v-model="aiKp.count" :min="1" :max="10" size="small" />
              <el-button size="small" type="primary" :loading="aiKp.loading" @click="genFromKp">生成</el-button>
            </div>
            <div v-if="aiKp.result" class="ai-result">
              生成 {{ aiKp.result.generated }} 题
              <div v-for="q in aiKp.result.questions" :key="q.id" class="gen-q">
                [{{ q.type }}] {{ q.stem.slice(0, 40) }}...
              </div>
            </div>
          </div>
        </div>
        <div class="llm-hint">
          <Lightbulb class="hint-icon" :size="14" />
          当前LLM: <strong>{{ llmProvider }}</strong>
          <span v-if="llmProvider === 'none'">（未配置LLM，使用模板降级生题。配置 .env 的 LLM_* 可启用高质量AI生题）</span>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Settings, BarChart3, Bot, Bug, Lightbulb, Clock } from 'lucide-vue-next'
import { adminApi, learnApi } from '../../api'

const loading = ref(false)
const stats = ref(null)
const sources = ref(null)
const knowledgeTree = ref([])
const running = reactive({})
const runResult = ref(null)

const aiPolicy = reactive({ id: 1, count: 3, loading: false, result: null })
const aiKp = reactive({ code: 'spot', count: 3, loading: false, result: null })

const llmProvider = ref('none')

const loadAll = async () => {
  loading.value = true
  try {
    const [s, src, tree] = await Promise.all([
      adminApi.stats(),
      adminApi.crawlerSources(),
      learnApi.knowledgeTree(),
    ])
    stats.value = s
    sources.value = src
    knowledgeTree.value = tree
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

const runCrawler = async (name) => {
  running[name] = true
  runResult.value = null
  try {
    const res = await adminApi.runCrawler(name)
    runResult.value = res.stats || res
    ElMessage.success('爬虫执行完成')
    stats.value = await adminApi.stats()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    running[name] = false
  }
}

const genFromPolicy = async () => {
  aiPolicy.loading = true
  aiPolicy.result = null
  try {
    aiPolicy.result = await adminApi.aiGenFromPolicy(aiPolicy.id, aiPolicy.count)
    ElMessage.success(`生成 ${aiPolicy.result.generated} 题`)
    stats.value = await adminApi.stats()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    aiPolicy.loading = false
  }
}

const genFromKp = async () => {
  if (!aiKp.code) {
    ElMessage.warning('请选择知识点')
    return
  }
  aiKp.loading = true
  aiKp.result = null
  try {
    aiKp.result = await adminApi.aiGenFromKnowledge(aiKp.code, aiKp.count)
    ElMessage.success(`生成 ${aiKp.result.generated} 题`)
    stats.value = await adminApi.stats()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    aiKp.loading = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.admin-page { min-height: 100vh; background: var(--bg-page); }
.admin-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 0 32px; height: 60px;
  background: var(--bg-header); border-bottom: 1px solid var(--border-color);
}
.brand { font-size: 18px; font-weight: 700; display: inline-flex; align-items: center; gap: 6px; }
.back-home {
  min-height:34px;padding:0 12px;display:inline-flex;align-items:center;
  color:#fff;text-decoration:none;font-size:12px;font-weight:750;
  border:1px solid #4f5bd4;border-radius:9px;background:#4f5bd4;
  box-shadow:0 7px 17px rgba(79,91,212,.2);
}
.back-home:hover{color:#fff;background:#3f49ba;border-color:#3f49ba;transform:translateY(-1px)}
.admin-main { max-width: 900px; margin: 0 auto; padding: 32px 24px; }
h3 { font-size: 18px; color: var(--text-primary); margin-bottom: 16px; display: inline-flex; align-items: center; gap: 6px; }
.section-desc { font-size: 13px; color: var(--text-secondary); margin-bottom: 16px; margin-top: -8px; }

.stats-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 32px; }
.stat-card { background: var(--bg-card); border-radius: var(--radius); padding: 20px; text-align: center; box-shadow: var(--shadow-card); }
.stat-num { font-size: 28px; font-weight: 700; color: var(--accent); }
.stat-card.real .stat-num { color: #e74c8b; }
.stat-card.ai .stat-num { color: #2f6bff; }
.stat-card.crawler .stat-num { color: #ff9500; }
.stat-card.policy .stat-num { color: #00a870; }
.stat-label { font-size: 12px; color: var(--text-secondary); margin-top: 6px; }

.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.section-head h3 { margin-bottom: 0; }
.sched-status { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-secondary); }
.sched-status .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-tertiary); }
.sched-status .dot.on { background: var(--accent-green); }

.crawler-list { display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px; }
.crawler-card { display: flex; justify-content: space-between; align-items: center; background: var(--bg-card); border-radius: var(--radius); padding: 16px 20px; box-shadow: var(--shadow-card); }
.cc-name { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.cc-desc { font-size: 13px; color: var(--text-secondary); margin: 4px 0; }
.cc-sched { font-size: 12px; color: var(--accent); display: inline-flex; align-items: center; gap: 3px; }
.run-result { font-size: 13px; padding: 10px 14px; border-radius: var(--radius-sm); background: var(--bg-hover); }
.run-result.ok { color: var(--accent-green); }

.ai-tabs { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.ai-card { background: var(--bg-card); border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow-card); }
.ai-title { font-size: 15px; font-weight: 600; margin-bottom: 12px; }
.ai-form { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.ai-result { font-size: 13px; color: var(--accent-green); }
.gen-q { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
.llm-hint { font-size: 12px; color: var(--text-secondary); padding: 10px 14px; background: var(--bg-hover); border-radius: var(--radius-sm); display: flex; align-items: flex-start; gap: 4px; }
.hint-icon { flex-shrink: 0; margin-top: 1px; }
</style>
