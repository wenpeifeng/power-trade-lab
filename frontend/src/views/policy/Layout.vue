<template>
  <div class="policy-layout">
    <header class="policy-header">
      <router-link to="/policy" class="brand">
        <span class="brand-mark"><Megaphone :size="18" /></span>
        <span><strong>政策公告中心</strong><small>POLICY INTELLIGENCE</small></span>
      </router-link>
      <span class="brand-sub">按发布日期、重要性与来源追踪电力市场规则变化</span>
      <div class="header-right">
        <router-link to="/" class="back-home"><House :size="14" /> 返回门户</router-link>
      </div>
    </header>
    <main class="policy-main">
      <router-view />
    </main>
  </div>
</template>
<script setup>
import { Megaphone, House } from 'lucide-vue-next'
</script>
<style scoped>
.policy-layout {
  min-height:100vh;
  background:
    radial-gradient(circle at 12% 0,rgba(65,104,220,.09),transparent 27rem),
    radial-gradient(circle at 89% 18%,rgba(22,166,169,.055),transparent 24rem),
    var(--bg-page);
}
.policy-header {
  display:flex;align-items:center;gap:14px;
  padding:0 max(24px,calc((100vw - 1400px)/2));height:68px;
  background:var(--bg-header);border-bottom:1px solid #dfe6f3;
  box-shadow:0 7px 25px rgba(50,78,145,.065);backdrop-filter:blur(18px);
  position:sticky;top:0;z-index:100;
}
.brand{display:inline-flex;align-items:center;gap:9px;color:var(--text-primary);text-decoration:none;white-space:nowrap}
.brand-mark{width:35px;height:35px;display:grid;place-items:center;border-radius:11px;color:#fff;background:linear-gradient(145deg,#5278e5,#3459c6 62%,#9b5576);box-shadow:0 8px 19px rgba(57,89,198,.22)}
.brand>span:last-child{display:flex;flex-direction:column}
.brand strong{font-size:15px;line-height:1.1}.brand small{margin-top:4px;color:#8b98af;font:700 7px/1 ui-monospace;letter-spacing:.12em}
.brand-sub{flex:1;color:var(--text-secondary);font-size:11px}
.header-right{display:flex;align-items:center;gap:4px}
.header-right a{height:34px;padding:0 10px;display:inline-flex;align-items:center;gap:5px;color:#66738a;text-decoration:none;font-size:11px;font-weight:700;border-radius:9px}
.header-right a:hover{color:#4168dc;background:#f0f4ff}
.header-right .back-home{margin-left:5px;color:#fff;border:1px solid #4168dc;background:#4168dc;box-shadow:0 7px 17px rgba(65,104,220,.2)}
.header-right .back-home:hover{color:#fff;background:#3152b9;border-color:#3152b9;transform:translateY(-1px)}
.policy-main { max-width: 1120px; margin: 0 auto; padding: 26px 24px 60px; }
@media(max-width:860px){.brand-sub{display:none}.policy-header{padding-inline:14px}.policy-main{padding-inline:14px}}
</style>
