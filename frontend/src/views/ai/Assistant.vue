<template>
  <div class="ai-page">
    <header class="ai-header">
      <router-link to="/assistant" class="brand">
        <span class="brand-mark"><Bot :size="18" /></span>
        <span><strong>AI 电力交易助手</strong><small>KNOWLEDGE COPILOT</small></span>
      </router-link>
      <span class="sub">基于可信知识库回答政策、规则与交易问题</span>
      <router-link to="/" class="back-home"><House :size="14" /> 返回门户</router-link>
    </header>

    <main class="ai-main">
      <!-- 消息区 -->
      <div class="messages" ref="msgBox">
        <!-- 欢迎语 -->
        <div v-if="!messages.length" class="welcome">
          <Bot class="welcome-icon" :size="56" />
          <h2>你好，我是电力交易AI助手</h2>
          <p>我可以基于知识库回答你关于电力市场、交易规则、政策法规的问题。</p>

          <div class="suggestions" v-if="suggList.length">
            <div class="sugg-title"><Lightbulb :size="14" /> 你可以问我：</div>
            <div class="sugg-grid">
              <div v-for="q in suggList" :key="q" class="sugg-card" @click="askSuggestion(q)">
                {{ q }}
              </div>
            </div>
          </div>
        </div>

        <!-- 对话气泡 -->
        <div v-for="msg in messages" :key="msg.id" class="msg-row" :class="msg.role">
          <div class="msg-avatar"><component :is="msg.role === 'user' ? User : Bot" :size="24" /></div>
          <div class="msg-content">
            <div class="msg-text">{{ msg.content }}</div>
            <!-- 引用来源 -->
            <div v-if="msg.sources && msg.sources.length" class="msg-sources">
              <div class="src-title"><BookOpen :size="13" /> 引用来源：</div>
              <div v-for="(s, i) in msg.sources" :key="i" class="src-item"
                   @click="goSource(s.doc_id)">
                <span class="src-score">{{ (s.score * 100).toFixed(0) }}%</span>
                <span class="src-title-text">{{ s.title }}</span>
              </div>
            </div>
            <div v-if="msg.mode === 'fallback_chunk'" class="msg-mode"><AlertTriangle :size="12" /> 当前为知识库片段直返模式（未接入LLM）</div>
          </div>
        </div>

        <!-- 加载中 -->
        <div v-if="loading" class="msg-row assistant">
          <div class="msg-avatar"><Bot :size="24" /></div>
          <div class="msg-content">
            <div class="typing">正在检索知识库并生成回答<span class="dots">...</span></div>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="input-bar">
        <el-input
          v-model="input" placeholder="输入你的问题，如：什么是节点边际电价？"
          @keyup.enter="send" size="large" :disabled="loading"
        >
          <template #append>
            <el-button :loading="loading" @click="send" type="primary">发送</el-button>
          </template>
        </el-input>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Bot, BookOpen, Lightbulb, User, AlertTriangle, House } from 'lucide-vue-next'
import { aiApi } from '../../api'

const input = ref('')
const messages = ref([])
const loading = ref(false)
const suggList = ref([])
const msgBox = ref(null)

let msgId = 0

onMounted(async () => {
  try {
    const res = await aiApi.suggestions()
    suggList.value = res.questions || []
  } catch (e) { /* ignore */ }
  // 加载历史
  try {
    const res = await aiApi.history()
    if (res.history && res.history.length) {
      for (const h of res.history.slice(-6)) {
        messages.value.push({ id: ++msgId, role: 'user', content: h.question })
        messages.value.push({
          id: ++msgId, role: 'assistant', content: h.answer,
          sources: h.sources, mode: h.mode,
        })
      }
      scrollBottom()
    }
  } catch (e) { /* ignore */ }
})

function askSuggestion(q) {
  input.value = q
  send()
}

async function send() {
  const q = input.value.trim()
  if (!q || loading.value) return

  messages.value.push({ id: ++msgId, role: 'user', content: q })
  input.value = ''
  loading.value = true
  scrollBottom()

  try {
    const history = messages.value.slice(-6).map(m => ({ role: m.role, content: m.content }))
    const res = await aiApi.chat(q, history)
    messages.value.push({
      id: ++msgId, role: 'assistant', content: res.answer,
      sources: res.sources, mode: res.mode,
    })
  } catch (e) {
    messages.value.push({
      id: ++msgId, role: 'assistant', content: `抱歉，出了点问题：${e.message}`,
    })
  }
  loading.value = false
  scrollBottom()
}

function scrollBottom() {
  nextTick(() => {
    if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight
  })
}

function goSource(docId) {
  window.open(`/knowledge?doc=${docId}`, '_blank')
}
</script>

<style scoped>
.ai-page {
  height:100vh;display:flex;flex-direction:column;
  background:
    radial-gradient(circle at 12% 0,rgba(65,104,220,.1),transparent 27rem),
    radial-gradient(circle at 88% 14%,rgba(22,166,169,.07),transparent 24rem),
    var(--bg-page);
}
.ai-header {
  display: flex; align-items: center; gap: 14px;
  padding:0 max(24px,calc((100vw - 1400px)/2));height:68px;flex-shrink:0;
  background:var(--bg-header,#fff);border-bottom:1px solid #dfe6f3;
  box-shadow:0 7px 25px rgba(50,78,145,.065);backdrop-filter:blur(18px);
}
.brand{display:inline-flex;align-items:center;gap:9px;color:var(--text-primary);text-decoration:none;white-space:nowrap}
.brand-mark{width:35px;height:35px;display:grid;place-items:center;border-radius:11px;color:#fff;background:linear-gradient(145deg,#5278e5,#3459c6 62%,#1ba3ad);box-shadow:0 8px 19px rgba(57,89,198,.24)}
.brand>span:last-child{display:flex;flex-direction:column}
.brand strong{font-size:15px;line-height:1.1}.brand small{margin-top:4px;color:#8b98af;font:700 7px/1 ui-monospace;letter-spacing:.12em}
.sub { font-size: 11px; color: var(--text-secondary, #909399); flex: 1; }
.back-home{height:34px;padding:0 10px;display:inline-flex;align-items:center;gap:5px;color:#fff;text-decoration:none;font-size:11px;font-weight:700;border:1px solid #4168dc;border-radius:9px;background:#4168dc;box-shadow:0 7px 17px rgba(65,104,220,.2)}
.back-home:hover{color:#fff;background:#3152b9;border-color:#3152b9;transform:translateY(-1px)}

.ai-main { flex: 1; display: flex; flex-direction: column; max-width: 980px; margin: 0 auto; width: 100%; }

.messages { flex: 1; overflow-y: auto; padding: 20px; }

/* 欢迎区 */
.welcome {
  position:relative;overflow:hidden;text-align:center;margin-top:24px;padding:56px 34px;
  border:1px solid #dae3f4;border-radius:20px;
  background:radial-gradient(circle at 50% 24%,rgba(65,104,220,.13),transparent 24%),linear-gradient(145deg,#fff,#f3f7ff);
  box-shadow:0 16px 40px rgba(47,75,140,.09);
}
.welcome::before{content:"";position:absolute;left:50%;top:80px;width:150px;height:150px;border:1px dashed rgba(65,104,220,.24);border-radius:50%;transform:translate(-50%,-50%);animation:copilotOrbit 15s linear infinite}
.welcome-icon { position:relative;z-index:1;margin: 0 auto; padding:14px;box-sizing:content-box;border-radius:20px;color:#fff;background:linear-gradient(145deg,#4168dc,#1aa3ad);box-shadow:0 0 0 12px rgba(65,104,220,.07),0 14px 28px rgba(53,82,175,.2) }
.welcome h2 { margin: 16px 0 8px; font-size: 22px; }
.welcome p { color: var(--text-secondary, #909399); font-size: 14px; }
.suggestions { margin-top: 28px; text-align: left; }
.sugg-title { font-size: 14px; color: var(--text-secondary, #909399); margin-bottom: 10px; display: inline-flex; align-items: center; gap: 5px; }
.sugg-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.sugg-card {
  padding: 12px 16px; background: var(--bg-card, #fff); border-radius: 10px;
  border: 1px solid var(--border-light, #ebeef5); cursor: pointer; font-size: 13px;
  transition: all 0.15s;
}
.sugg-card:hover { border-color: var(--accent, #2f6bff); color: var(--accent, #2f6bff); transform: translateY(-3px);box-shadow:0 11px 24px rgba(50,78,145,.11) }

/* 消息气泡 */
.msg-row { display: flex; gap: 10px; margin-bottom: 20px; }
.msg-avatar { width: 36px; height: 36px; flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center; }
.msg-content { flex: 1; max-width: 75%; }
.msg-row.user { flex-direction: row-reverse; }
.msg-row.user .msg-content { text-align: right; }
.msg-row.user .msg-text {
  display: inline-block; text-align: left;
  background: var(--accent, #2f6bff); color: #fff;
  padding: 10px 16px; border-radius: 16px 16px 4px 16px;
}
.msg-row.assistant .msg-text {
  background: var(--bg-card, #fff); color: var(--text-primary, #303133);
  padding: 12px 16px; border-radius: 16px 16px 16px 4px;
  border: 1px solid var(--border-light, #ebeef5);
  white-space: pre-wrap; line-height: 1.7; font-size: 14px;
}
.msg-sources { margin-top: 8px; text-align: left; }
.src-title { font-size: 12px; color: var(--text-tertiary, #c0c4cc); margin-bottom: 4px; display: inline-flex; align-items: center; gap: 4px; }
.src-item {
  display: inline-flex; align-items: center; gap: 4px; margin-right: 6px; margin-bottom: 4px;
  padding: 3px 8px; border-radius: 4px; background: var(--bg-hover, #f5f7fa);
  font-size: 12px; cursor: pointer; color: var(--text-secondary, #606266);
}
.src-item:hover { background: var(--accent-soft, #e8f0ff); color: var(--accent, #2f6bff); }
.src-score { color: var(--accent, #2f6bff); font-weight: 600; font-size: 11px; }
.msg-mode { font-size: 11px; color: #e6a23c; margin-top: 4px; display: inline-flex; align-items: center; gap: 3px; }

.typing { color: var(--text-secondary, #909399); font-size: 14px; padding: 12px 16px; }
.dots { animation: blink 1.4s infinite; }
@keyframes blink { 0%,100%{opacity:.2} 50%{opacity:1} }

/* 输入栏 */
.input-bar { padding: 12px 20px 20px; flex-shrink: 0; }
@keyframes copilotOrbit{to{transform:translate(-50%,-50%) rotate(360deg)}}
@media(max-width:900px){.sub{display:none}.ai-header{padding-inline:14px}.ai-main{padding-inline:14px}.welcome{margin-top:14px}}
@media(prefers-reduced-motion:reduce){.welcome::before{animation:none}}
</style>
