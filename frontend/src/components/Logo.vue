<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 64 64"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    class="app-logo"
  >
    <defs>
      <linearGradient :id="gid + '-bg'" x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
        <stop offset="0" stop-color="#0A1628" />
        <stop offset="1" stop-color="#13284A" />
      </linearGradient>
      <linearGradient :id="gid + '-bolt'" x1="20" y1="8" x2="44" y2="56" gradientUnits="userSpaceOnUse">
        <stop offset="0" stop-color="#00D4FF" />
        <stop offset="0.5" stop-color="#0EA5E9" />
        <stop offset="1" stop-color="#2563EB" />
      </linearGradient>
      <linearGradient :id="gid + '-chart'" x1="12" y1="48" x2="52" y2="20" gradientUnits="userSpaceOnUse">
        <stop offset="0" stop-color="#10B981" stop-opacity="0.9" />
        <stop offset="1" stop-color="#059669" stop-opacity="0.7" />
      </linearGradient>
      <filter :id="gid + '-glow'" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="1.5" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>

    <!-- 六边形外框（能源科技感） -->
    <path
      d="M32 2 L58 17 L58 47 L32 62 L6 47 L6 17 Z"
      :fill="`url(#${gid}-bg)`"
      stroke="url(#${gid}-bolt)"
      stroke-width="1.5"
      stroke-opacity="0.4"
    />

    <!-- 底部趋势线（交易上升） -->
    <polyline
      points="14,46 22,40 28,42 34,34 40,30 50,20"
      :stroke="`url(#${gid}-chart)`"
      stroke-width="2"
      fill="none"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
    <!-- 趋势线上的数据点 -->
    <circle cx="14" cy="46" r="1.5" fill="#10B981" opacity="0.6" />
    <circle cx="22" cy="40" r="1.5" fill="#10B981" opacity="0.7" />
    <circle cx="28" cy="42" r="1.5" fill="#10B981" opacity="0.75" />
    <circle cx="34" cy="34" r="1.5" fill="#10B981" opacity="0.8" />
    <circle cx="40" cy="30" r="1.5" fill="#10B981" opacity="0.85" />
    <circle cx="50" cy="20" r="2" fill="#10B981" />

    <!-- 闪电（电力核心） -->
    <path
      d="M36 8 L22 34 L31 34 L27 54 L43 26 L33 26 L37 8 Z"
      :fill="`url(#${gid}-bolt)`"
      :filter="`url(#${gid}-glow)`"
    />

    <!-- 六边形顶点装饰 -->
    <circle cx="32" cy="2" r="1.5" fill="#00D4FF" opacity="0.8" />
    <circle cx="58" cy="17" r="1.5" fill="#0EA5E9" opacity="0.6" />
    <circle cx="6" cy="17" r="1.5" fill="#2563EB" opacity="0.6" />
  </svg>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({
  size: { type: Number, default: 40 },
})
// 唯一ID（防多实例冲突）
const gid = computed(() => 'logo' + Math.random().toString(36).slice(2, 8))
</script>

<style scoped>
.app-logo { display: inline-block; vertical-align: middle; }
</style>
