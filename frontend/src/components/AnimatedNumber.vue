<template>
  <span ref="el">{{ displayValue }}</span>
</template>

<script setup>
/**
 * 数字滚动动画组件
 * 页面加载时数字从0滚动到目标值
 */
import { ref, onMounted, watch } from 'vue'
import { CountUp } from 'countup.js'

const props = defineProps({
  value: { type: Number, default: 0 },
  duration: { type: Number, default: 1.8 },
  decimals: { type: Number, default: 0 },
  prefix: { type: String, default: '' },
  suffix: { type: String, default: '' },
})

const el = ref(null)
const displayValue = ref('0')
let cu = null

onMounted(() => {
  if (el.value) {
    cu = new CountUp(el.value, props.value, {
      duration: props.duration,
      decimals: props.decimals,
      prefix: props.prefix,
      suffix: props.suffix,
      separator: ',',
      easingFn: (t, b, c, d) => {
        // easeOutExpo - 快速冲刺后减速
        return t === d ? b + c : c * (-Math.pow(2, -10 * t / d) + 1) + b
      },
    })
    if (!cu.error) cu.start()
  }
})

watch(() => props.value, (newVal) => {
  if (cu) cu.update(newVal)
})
</script>
