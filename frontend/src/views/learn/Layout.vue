<template>
  <div class="learn-layout" :class="layoutTone">
    <header class="learn-header">
      <div class="header-inner">
        <div class="header-left">
          <router-link to="/learn" class="brand">
            <span class="brand-mark"><BookOpen :size="18" /></span>
            <span>学习中心</span>
          </router-link>
        </div>
        <nav class="header-nav">
          <router-link to="/learn" :class="{ active: route.name === 'learn-home' }">首页</router-link>
          <router-link to="/learn/study" :class="{ active: ['learn-study', 'study-diagnosis', 'study-lesson'].includes(route.name) }">引导学习</router-link>
          <router-link to="/learn/quiz" :class="{ active: route.name === 'learn-quiz' }">自由刷题</router-link>
          <router-link to="/learn/exam" :class="{ active: route.name === 'learn-exam' || route.name === 'exam-paper' || route.name === 'exam-result' }">考试备考</router-link>
          <router-link to="/learn/wrong" :class="{ active: route.name === 'learn-wrong' }">错题本</router-link>
          <router-link to="/learn/books" :class="{ active: ['learn-books', 'learn-book-reader'].includes(route.name) }">教材工坊</router-link>
        </nav>
        <div class="header-right">
          <router-link to="/" class="back-home"><House :size="15" /> 返回门户</router-link>
        </div>
      </div>
    </header>
    <main class="learn-main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { BookOpen, House } from 'lucide-vue-next'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
const route = useRoute()
const layoutTone = computed(() => {
  if (route.name === 'learn-wrong') return 'tone-review'
  if (['learn-books', 'learn-book-reader'].includes(route.name)) return 'tone-book'
  return 'tone-guided'
})
</script>

<style scoped>
.learn-layout {
  min-height: 100vh;
  overflow-x: clip;
  --section-accent: #4f5bd4;
  --section-accent-soft: #eef0ff;
  --section-glow: rgba(79, 91, 212, .06);
  --section-shadow: rgba(71, 81, 193, .1);
  background:
    radial-gradient(circle at 12% 0%, var(--section-glow), transparent 27rem),
    radial-gradient(circle at 90% 18%, rgba(14, 165, 233, .04), transparent 24rem),
    var(--bg-page);
  --learn-shell: 1200px;
}
.learn-layout.tone-review {
  --section-accent: #93586a;
  --section-accent-soft: #fbf0f2;
  --section-glow: rgba(162, 88, 104, .055);
  --section-shadow: rgba(126, 72, 91, .11);
}
.learn-layout.tone-book {
  --section-accent: #287f91;
  --section-accent-soft: #eaf6f7;
  --section-glow: rgba(38, 143, 160, .055);
  --section-shadow: rgba(33, 111, 127, .11);
}
.learn-header {
  height: 68px;
  background: rgba(255, 255, 255, .88);
  border-bottom: 1px solid rgba(226, 232, 240, .92);
  position: sticky;
  top: 0;
  z-index: 100;
  backdrop-filter: blur(18px) saturate(145%);
  transform: translateZ(0);
  overflow-anchor: none;
}
.header-inner {
  width: min(calc(100% - 48px), var(--learn-shell));
  height: 100%;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.brand {
  font-size: 17px;
  font-weight: 800;
  color: var(--text-primary);
  display: inline-flex;
  align-items: center;
  gap: 9px;
  text-decoration: none;
  white-space: nowrap;
  letter-spacing: -.02em;
}
.brand-mark {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  color: #fff;
  border-radius: 11px;
  background: linear-gradient(145deg, #6671ee, #3d49cc);
  box-shadow: 0 7px 18px rgba(78, 88, 209, .2);
}
.header-nav {
  display: flex;
  gap: 4px;
  padding: 4px;
  border-radius: 14px;
  background: rgba(241, 245, 249, .7);
}
.header-nav a {
  padding: 8px 11px;
  border-radius: 10px;
  text-decoration: none;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 650;
  transition: color .2s, background .2s, box-shadow .2s, transform .2s;
  white-space: nowrap;
}
.header-nav a:hover {
  color: var(--section-accent);
  background: color-mix(in srgb, var(--section-accent-soft) 58%, transparent);
  transform: translateY(-1px);
}
.header-nav a.active {
  background: var(--section-accent-soft);
  color: var(--section-accent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--section-accent) 24%, transparent), 0 4px 14px var(--section-shadow);
  position: relative;
}
.header-nav a.active::after {
  content: "";
  position: absolute;
  left: 13px;
  right: 13px;
  bottom: 4px;
  height: 2px;
  border-radius: 2px;
  background: var(--section-accent);
}
.header-nav a:focus { outline: none; }
.header-nav a:focus-visible {
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--section-accent) 18%, transparent);
}
.header-right { display: flex; align-items: center; gap: 7px; }
.back-home {
  min-height: 34px;
  padding: 0 10px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #fff;
  text-decoration: none;
  font-size: 12px;
  font-weight: 680;
  border: 1px solid transparent;
  border-radius: 10px;
  background: var(--section-accent);
  box-shadow: 0 6px 15px var(--section-shadow);
  white-space: nowrap;
  transition: .2s;
}
.back-home:hover {
  color: #fff;
  transform: translateY(-1px);
  filter: brightness(1.08);
  box-shadow: 0 8px 18px var(--section-shadow);
}
.learn-main {
  width: min(calc(100% - 48px), var(--learn-shell));
  min-height: calc(100vh - 68px);
  overflow-anchor: none;
  margin: 0 auto;
  padding: 36px 0 56px;
}
@media (max-width: 900px) {
  .header-inner,
  .learn-main { width: min(calc(100% - 28px), var(--learn-shell)); }
  .back-home{font-size:0;padding:0 9px}
  .header-inner { gap: 12px; }
  .header-nav { overflow-x: auto; justify-content: flex-start; }
  .header-nav a { padding: 8px 11px; }
}
@media (max-width: 680px) {
  .learn-header { height: auto; }
  .header-inner { padding: 10px 0; align-items: flex-start; flex-direction: column; }
  .header-nav { width: 100%; }
  .learn-main { padding-top: 22px; }
}
@media (prefers-reduced-motion: reduce) {
  .header-nav a { transition: none; }
}
</style>
