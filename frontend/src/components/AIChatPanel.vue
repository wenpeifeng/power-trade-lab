<template>
  <teleport to="body">
    <transition name="panel-drop">
      <div v-if="show" class="chat-overlay" @click.self="$emit('close')">
        <div class="chat-panel">
          <!-- 头部 -->
          <header class="cp-header">
            <div class="cp-bot-info">
              <svg viewBox="0 0 44 44" class="cp-bot-avatar">
                <rect x="8" y="9" width="28" height="26" rx="8" fill="#fff" stroke="#3b82f6" stroke-width="1.5" />
                <line x1="22" y1="4" x2="22" y2="9" stroke="#3b82f6" stroke-width="1.5" />
                <circle cx="22" cy="4" r="2" fill="#3b82f6" />
                <rect x="12" y="14" width="20" height="12" rx="4" fill="#1e293b" />
                <circle cx="17" cy="20" r="2.5" fill="#3b82f6" />
                <circle cx="27" cy="20" r="2.5" fill="#3b82f6" />
                <path d="M17 29 Q22 32 27 29" stroke="#3b82f6" stroke-width="1.5" fill="none" />
              </svg>
              <div>
                <div class="cp-title">AI 智能助手</div>
                <div class="cp-status"><span class="dot"></span>在线 · 基于电力交易知识库</div>
              </div>
            </div>
            <button class="cp-close" @click="$emit('close')">✕</button>
          </header>

          <!-- 消息 -->
          <div class="cp-body" ref="msgBox">
            <!-- 欢迎 -->
            <div v-if="!messages.length && !loading" class="cp-welcome">
              <div class="wb-icon"><Bot :size="32" /></div>
              <h3>你好！我是 AI 助手</h3>
              <p>基于电力交易知识库，帮你了解系统、学习交易、解答疑问</p>
              <div class="welcome-cards">
                <button v-for="q in suggestions" :key="q.text" class="wc-item" @click="askQuick(q)">
                  <span class="wc-icon"><component :is="q.iconComp" :size="18" /></span>
                  <div><div class="wc-title">{{ q.title }}</div><div class="wc-desc">{{ q.desc }}</div></div>
                </button>
              </div>
            </div>

            <!-- 对话 -->
            <template v-for="msg in messages" :key="msg.id">
              <div class="cp-msg user" v-if="msg.role === 'user'"><div class="ub">{{ msg.content }}</div></div>
              <div class="cp-msg bot" v-else>
                <div class="bb">{{ msg.content }}
                  <div class="bb-src" v-if="msg.sources?.length">
                    <span class="src-label">引用来源</span>
                    <a v-for="(s,i) in msg.sources.slice(0,3)" :key="i" class="src-chip" @click="goSource(s.doc_id)">{{ s.title?.slice(0,14) }}</a>
                  </div>
                </div>
              </div>
            </template>
            <div v-if="loading" class="cp-msg bot"><div class="bb"><span class="dots"><i></i><i></i><i></i></span></div></div>
          </div>

          <!-- 输入 -->
          <footer class="cp-footer">
            <input v-model="input" placeholder="问我任何电力交易问题…" @keyup.enter="send" :disabled="loading" />
            <button class="send" @click="send" :disabled="loading || !input.trim()">→</button>
          </footer>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { aiApi } from '../api'
import { Bot, BookOpen, Lightbulb, ChartBar, Compass } from 'lucide-vue-next'

defineEmits(['close'])
const show = ref(false)
const input = ref('')
const messages = ref([])
const loading = ref(false)
const msgBox = ref(null)
let msgId = 0

const suggestions = [
  { iconComp: Compass, title: '系统功能介绍', desc: '这个系统有什么用', text: '请介绍这个系统的功能和用法，我是新手该怎么开始？' },
  { iconComp: BookOpen, title: '学习路径规划', desc: '零基础到交易员', text: '我零基础想考电力交易员，该怎么规划学习？' },
  { iconComp: Lightbulb, title: '现货市场入门', desc: '核心概念解释', text: '什么是电力现货市场？和中长期交易有什么区别？' },
  { iconComp: ChartBar, title: '报价策略指导', desc: '怎么报价才能成交', text: '电力交易中怎么报价才能提高成交率？' },
]

onMounted(() => { show.value = true; loadHistory() })

function askQuick(q) { input.value = q.text; send() }
async function send() {
  const q = input.value.trim()
  if (!q || loading.value) return
  messages.value.push({ id: ++msgId, role: 'user', content: q })
  input.value = ''; loading.value = true; scrollBottom()
  try {
    const history = messages.value.slice(-6).map(m => ({ role: m.role, content: m.content }))
    const res = await aiApi.chat(q, history)
    messages.value.push({ id: ++msgId, role: 'assistant', content: res.answer, sources: res.sources })
  } catch (e) { messages.value.push({ id: ++msgId, role: 'assistant', content: `抱歉：${e.message}` }) }
  loading.value = false; scrollBottom()
}
async function loadHistory() {
  try {
    const res = await aiApi.history()
    if (res.history?.length) {
      messages.value = []
      for (const h of res.history.slice(-6)) {
        messages.value.push({ id: ++msgId, role: 'user', content: h.question })
        messages.value.push({ id: ++msgId, role: 'assistant', content: h.answer, sources: h.sources })
      }
      scrollBottom()
    }
  } catch {}
}
function scrollBottom() { nextTick(() => { if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight }) }
function goSource(docId) { window.open(`/knowledge?doc=${docId}`, '_blank') }
</script>

<style scoped>
.chat-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(100, 116, 139, 0.15); backdrop-filter: blur(4px);
  display: flex; justify-content: flex-end; align-items: stretch;
}
.chat-panel {
  width: 440px; max-width: 90vw; height: 100vh;
  background: #fff; border-left: 1px solid #e2e8f0;
  display: flex; flex-direction: column; overflow: hidden;
  box-shadow: -8px 0 40px rgba(0, 0, 0, 0.08);
}

/* 头部 */
.cp-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 18px 22px; border-bottom: 1px solid #f1f5f9;
  background: linear-gradient(135deg, #eff6ff, #fff);
}
.cp-bot-info { display: flex; align-items: center; gap: 12px; }
.cp-bot-avatar { width: 40px; height: 40px; }
.cp-title { font-size: 16px; font-weight: 700; color: #0f172a; }
.cp-status { font-size: 11px; color: #10b981; display: flex; align-items: center; gap: 4px; margin-top: 2px; }
.dot { width: 6px; height: 6px; background: #10b981; border-radius: 50%; }
.cp-close {
  width: 30px; height: 30px; border: none; background: #f1f5f9;
  color: #64748b; border-radius: 8px; cursor: pointer; font-size: 14px;
}
.cp-close:hover { background: #fee2e2; color: #ef4444; }

/* 消息区 */
.cp-body { flex: 1; overflow-y: auto; padding: 20px 22px; }

/* 欢迎 */
.cp-welcome { text-align: center; padding: 16px 0; }
.wb-icon { font-size: 40px; margin-bottom: 12px; }
.cp-welcome h3 { font-size: 17px; color: #0f172a; margin: 0 0 8px; }
.cp-welcome p { font-size: 13px; color: #64748b; margin: 0 0 20px; line-height: 1.6; }
.welcome-cards { display: flex; flex-direction: column; gap: 10px; text-align: left; }
.wc-item {
  display: flex; align-items: center; gap: 12px; padding: 14px;
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px;
  cursor: pointer; transition: all 0.15s;
}
.wc-item:hover { border-color: #93c5fd; background: #eff6ff; }
.wc-icon { font-size: 22px; }
.wc-title { font-size: 14px; font-weight: 600; color: #1e293b; }
.wc-desc { font-size: 12px; color: #94a3b8; margin-top: 2px; }

/* 消息气泡 */
.cp-msg { display: flex; margin-bottom: 12px; }
.cp-msg.user { justify-content: flex-end; }
.ub {
  max-width: 75%; background: #2563eb; color: #fff;
  padding: 10px 14px; border-radius: 16px 16px 4px 16px; font-size: 14px;
}
.bb {
  max-width: 80%; background: #f8fafc; border: 1px solid #e2e8f0;
  padding: 12px 14px; border-radius: 4px 16px 16px 16px;
  font-size: 13px; color: #334155; line-height: 1.6; white-space: pre-wrap;
}
.bb-src { margin-top: 8px; padding-top: 8px; border-top: 1px solid #e2e8f0; }
.src-label { font-size: 11px; color: #94a3b8; display: block; margin-bottom: 4px; }
.src-chip {
  display: inline-block; font-size: 11px; color: #2563eb; margin-right: 6px;
  padding: 2px 8px; background: #eff6ff; border-radius: 6px; cursor: pointer;
}
.dots { display: inline-flex; gap: 4px; }
.dots i { width: 7px; height: 7px; border-radius: 50%; background: #94a3b8; animation: bounce 1.4s infinite; display: inline-block; }
.dots i:nth-child(2) { animation-delay: 0.15s; }
.dots i:nth-child(3) { animation-delay: 0.3s; }
@keyframes bounce { 0%,70%,100%{opacity:0.3;transform:translateY(0)} 35%{opacity:1;transform:translateY(-4px)} }

/* 输入区 */
.cp-footer {
  display: flex; gap: 8px; padding: 14px 22px;
  border-top: 1px solid #f1f5f9; background: #fff;
}
.cp-footer input {
  flex: 1; background: #f8fafc; border: 1px solid #e2e8f0;
  border-radius: 12px; padding: 11px 14px; font-size: 14px; color: #1e293b;
}
.cp-footer input:focus { outline: none; border-color: #3b82f6; background: #fff; }
.send {
  width: 42px; height: 42px; border: none; cursor: pointer; border-radius: 12px;
  background: #2563eb; color: #fff; font-size: 18px;
}
.send:disabled { opacity: 0.3; cursor: not-allowed; }

/* 动画：遮罩渐入 + 面板从右划入 */
.panel-drop-enter-active { transition: opacity 0.3s ease; }
.panel-drop-leave-active { transition: opacity 0.2s ease; }
.panel-drop-enter-from, .panel-drop-leave-to { opacity: 0; }
.panel-drop-enter-active .chat-panel { animation: slide-in-right 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
.panel-drop-leave-active .chat-panel { animation: slide-in-right 0.25s ease reverse; }
@keyframes slide-in-right {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}
</style>
