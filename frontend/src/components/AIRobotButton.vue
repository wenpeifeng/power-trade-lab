<template>
  <div class="robot-dock" @mouseenter="hovered = true" @mouseleave="hovered = false">
    <!-- 滑出提示条 -->
    <transition name="slide-fade">
      <div v-show="hovered" class="dock-tip" @click="$emit('open')">
        <div class="tip-body">
          <span class="tip-label">AI 助手</span>
          <span class="tip-msg">{{ tip }}</span>
        </div>
        <ChevronLeft :size="16" class="tip-arrow" />
      </div>
    </transition>

    <!-- 机器人按钮 -->
    <button class="robot-btn" :class="{ hovered }" @click="$emit('open')">
      <div class="robot-face">
        <BrainCircuit :size="26" class="robot-icon" />
      </div>
      <!-- 在线状态：用一个容器让绿点和光圈圆心对齐 -->
      <span class="online-wrap">
        <span class="online-ring"></span>
        <span class="online-dot"></span>
      </span>
    </button>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ChevronLeft, BrainCircuit } from 'lucide-vue-next'
defineEmits(['open'])
const hovered = ref(false)
const tips = ['有问题随时问我', '不知道怎么用？问我', '电力交易问题，有问必答']
const tip = ref(tips[0])
onMounted(() => {
  let i = 0
  setInterval(() => { i = (i + 1) % tips.length; if (!hovered.value) tip.value = tips[i] }, 5000)
})
</script>

<style scoped>
.robot-dock {
  position: fixed; right: 0; top: 50%; transform: translateY(-50%);
  z-index: 9998; display: flex; align-items: center; gap: 10px;
}

/* 提示条 */
.dock-tip {
  display: flex; align-items: center; gap: 10px; cursor: pointer;
  padding: 12px 16px; background: #fff;
  border: 1px solid #f4f4f5; border-radius: 14px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  transition: all 0.2s;
}
.dock-tip:hover { background: #fafafa; }
.tip-body { display: flex; flex-direction: column; gap: 1px; }
.tip-label { font-size: 13px; font-weight: 700; color: #6366f1; white-space: nowrap; }
.tip-msg { font-size: 12px; color: #71717a; white-space: nowrap; }
.tip-arrow { color: #6366f1; flex-shrink: 0; }

/* 机器人按钮 */
.robot-btn {
  position: relative; width: 52px; height: 52px; border: none;
  background: transparent; cursor: pointer; padding: 0;
  margin-right: -2px; overflow: visible;
  transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.robot-btn.hovered {
  transform: scale(1.2) translateX(-8px);
}
.robot-face {
  width: 52px; height: 52px; border-radius: 14px 0 0 14px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid #e4e4e7; border-right: none;
  display: flex; align-items: center; justify-content: center;
  box-shadow: -4px 0 16px rgba(0, 0, 0, 0.06);
  transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.robot-btn.hovered .robot-face {
  border-color: #c4b5fd;
  box-shadow: -6px 0 24px rgba(99, 102, 241, 0.15);
}
.robot-svg { width: 36px; height: 36px; }

/* 在线绿点容器 — 固定在按钮右下角 */
.online-wrap {
  position: absolute; bottom: 4px; right: 4px;
  width: 10px; height: 10px; z-index: 100;
  display: flex; align-items: center; justify-content: center;
}
.online-dot {
  position: relative; z-index: 2;
  width: 8px; height: 8px; border-radius: 50%;
  background: #10b981;
}
.online-ring {
  position: absolute; z-index: 1;
  width: 8px; height: 8px; border-radius: 50%;
  background: #10b981;
  animation: onlineSpread 2s ease-out infinite;
}
@keyframes onlineSpread {
  0% { transform: scale(1); opacity: 0.5; }
  100% { transform: scale(2.5); opacity: 0; }
}

/* 滑出动画 */
.slide-fade-enter-active { transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
.slide-fade-leave-active { transition: all 0.2s ease; }
.slide-fade-enter-from, .slide-fade-leave-to { opacity: 0; transform: translateX(30px); }
</style>
