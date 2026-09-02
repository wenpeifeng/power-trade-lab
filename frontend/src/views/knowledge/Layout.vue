<template>
  <div class="kb-layout">
    <header class="kb-header">
      <div class="kb-header-left">
        <router-link :to="{ path: '/knowledge', query: { tab: 'feed' } }" class="brand">
          <span class="brand-mark"><BookOpen :size="18" /></span>
          <span><strong>电力知识库</strong><small>KNOWLEDGE INDEX</small></span>
        </router-link>
        <span class="brand-sub">规则、政策与业务知识的统一索引</span>
      </div>
      <div class="kb-header-right">
        <span class="data-count" v-if="tab==='feed' && totalDocs"><i></i>{{ totalDocs }} 篇可信文档</span>
        <router-link to="/" class="portal-link"><House :size="14" /> 返回门户</router-link>
      </div>
    </header>
    <nav class="kb-tabs" aria-label="知识中心模块">
      <button class="kb-tab" :class="{active: tab==='feed'}" @click="setTab('feed')">
        <Newspaper :size="14" /> 资讯·爬取
      </button>
      <button class="kb-tab" :class="{active: tab==='book'}" @click="setTab('book')">
        <BookOpen :size="14" /> 知识库
      </button>
      <button class="kb-tab" :class="{active: tab==='glossary'}" @click="setTab('glossary')">
        <BookMarked :size="14" /> 术语表
      </button>
    </nav>
    <main class="kb-body" :class="`tab-${tab}`">
      <KnowledgeBook v-if="tab==='book'" />
      <Glossary v-else-if="tab==='glossary'" />
      <Browse v-else :total-docs-handler="setTotalDocs" />
    </main>
  </div>
</template>
<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BookOpen, House, Newspaper, BookMarked } from 'lucide-vue-next'
import KnowledgeBook from './KnowledgeBook.vue'
import Glossary from './Glossary.vue'
import Browse from './Browse.vue'

const route = useRoute()
const router = useRouter()

const VALID_TABS = ['feed', 'book', 'glossary']
// ?c=/?kp= 是知识书概念深链；无显式 tab 时应落到 book，否则概念页不挂载、深链白屏到资讯流。
const defaultTab = () => (route.query.c || route.query.kp ? 'book' : 'feed')
const tab = ref(VALID_TABS.includes(route.query.tab) ? route.query.tab : defaultTab())
// 出站动作（如 KnowledgeBook 「看真实原文」router.push 到 ?tab=feed）复用同一 Layout，
// 不触发 remount；这里同步 query.tab → tab，保证视图能切出。
watch(() => route.query.tab, (t) => { tab.value = VALID_TABS.includes(t) ? t : defaultTab() })
const setTab = (t) => {
  tab.value = t
  router.replace({ query: { ...route.query, tab: t } })
}

const totalDocs = ref(0)
const setTotalDocs = (n) => { totalDocs.value = n }
</script>
<style scoped>
.kb-layout {
  height: 100vh;
  height: 100dvh;
  background:
    radial-gradient(circle at 12% 0, rgba(65,104,220,.09), transparent 27rem),
    radial-gradient(circle at 88% 10%, rgba(22,166,169,.065), transparent 24rem),
    var(--bg-page);
  display: flex;
  flex-direction: column;
  overflow-x: clip;
}
.kb-header {
  display: flex; justify-content: space-between; align-items: center;
  gap: 18px;
  padding: 0 max(24px, calc((100vw - 1440px) / 2)); height: 68px; flex-shrink: 0;
  background: var(--bg-header); border-bottom: 1px solid rgba(214,224,242,.9);
  box-shadow: 0 7px 25px rgba(50,78,145,.065);
  backdrop-filter: blur(18px) saturate(140%);
  position: sticky; top: 0; z-index: 100; transform: translateZ(0);
}
.kb-header-left { display: flex; align-items: center; gap: 13px; min-width:0; }
.brand {
  display:inline-flex;align-items:center;gap:9px;
  color:var(--text-primary);text-decoration:none;white-space:nowrap;
}
.brand-mark{
  width:35px;height:35px;display:grid;place-items:center;border-radius:11px;color:#fff;
  background:linear-gradient(145deg,#5278e5,#3459c6 62%,#1ba3ad);
  box-shadow:0 8px 19px rgba(57,89,198,.24);position:relative;
}
.brand-mark::after{
  content:"";position:absolute;inset:-5px;border:1px solid rgba(65,104,220,.22);
  border-radius:15px;animation:knowledgePulse 2.8s ease-out infinite;
}
.brand>span:last-child{display:flex;flex-direction:column}
.brand strong{font-size:16px;line-height:1.2;letter-spacing:-.02em}
.brand small{margin-top:3px;color:#8996ad;font:700 7px/1 ui-monospace;letter-spacing:.15em}
.brand-sub { font-size: 12px; color: var(--text-secondary); }
.kb-header-right { display: flex; align-items: center; gap: 10px;white-space:nowrap }
.data-count { display:inline-flex;align-items:center;gap:7px;font-size:11px;color:var(--text-secondary) }
.data-count i{width:7px;height:7px;border-radius:50%;background:#18aca8;box-shadow:0 0 0 0 rgba(24,172,168,.35);animation:countPulse 2s infinite}
.portal-link{
  min-height:34px;padding:0 11px;display:inline-flex;align-items:center;gap:6px;
  color:#fff;text-decoration:none;font-size:12px;font-weight:700;
  border:1px solid #4168dc;border-radius:10px;background:#4168dc;
  box-shadow:0 7px 17px rgba(65,104,220,.2);
}
.portal-link:hover{color:#fff;background:#3152b9;border-color:#3152b9;transform:translateY(-1px)}

/* 模块导航：扁平页签与内容入口区分，不再做成三张悬浮按钮。 */
.kb-tabs {
  display: flex; gap: 24px; align-items: center;
  min-height: 50px;
  padding: 0 max(24px, calc((100vw - 1440px) / 2));
  background: rgba(250,252,255,.88);
  border-bottom: 1px solid #dce5f3;
  flex-shrink: 0;
  backdrop-filter: blur(12px);
}
.kb-tab{
  position:relative;
  display:inline-flex;align-items:center;gap:7px;
  align-self:stretch;padding:0 2px;border:0;
  background:transparent;color:#71809a;font-size:13px;font-weight:650;
  cursor:pointer;font-family:inherit;
  transition:color .16s ease;
}
.kb-tab::after{
  content:"";position:absolute;left:0;right:0;bottom:-1px;height:3px;
  border-radius:3px 3px 0 0;background:linear-gradient(90deg,#4168dc,#18a6ae);
  transform:scaleX(0);transition:transform .18s ease;
}
.kb-tab:hover{color:#3152b9}
.kb-tab.active{
  color:#21324e;
}
.kb-tab.active::after{transform:scaleX(1)}

.kb-body { flex: 1; min-height: 0; }
.kb-body.tab-book,.kb-body.tab-feed { overflow: hidden; }
.kb-body.tab-glossary { overflow-y: auto; }
@keyframes knowledgePulse{0%{transform:scale(.88);opacity:.7}70%,100%{transform:scale(1.18);opacity:0}}
@keyframes countPulse{70%{box-shadow:0 0 0 7px rgba(24,172,168,0)}}
@media(max-width:1120px){.brand-sub,.data-count{display:none}}
@media(max-width:850px){.kb-header,.kb-tabs{padding-inline:14px}}
@media(max-width:620px){.portal-link{font-size:0}.brand small{display:none}.kb-tabs{gap:18px}.kb-tab{font-size:12px}}
@media(prefers-reduced-motion:reduce){.brand-mark::after,.data-count i{animation:none}}
</style>
