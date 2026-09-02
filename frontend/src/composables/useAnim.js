/**
 * 全局动画工具 + 指令
 *
 * v-count 指令：任何元素加 v-count="数字" 就自动从0滚动到该值
 * 用法：<span v-count="1234"></span>
 *       <span v-count="99.5" v-count-decimals="1"></span>
 *       <span v-count="1000000" v-count-prefix="¥"></span>
 *
 * useReveal: 元素进入视口时渐入
 * useStaggerChildren: 子元素交错渐入
 */
import { ref, onMounted, onUnmounted } from 'vue'

/**
 * v-count 数字滚动指令
 * 在 main.js 注册：app.directive('count', CountDirective)
 */
export const CountDirective = {
  mounted(el, binding) {
    animateCount(el, binding.value, binding)
  },
  updated(el, binding) {
    if (binding.value !== binding.oldValue) {
      animateCount(el, binding.value, binding, true)
    }
  },
}

function animateCount(el, end, binding, isUpdate = false) {
  const decimals = parseInt(el.getAttribute('data-count-decimals') || binding.modifiers?.decimals ? 1 : 0) || 0
  const prefix = el.getAttribute('data-count-prefix') || ''
  const suffix = el.getAttribute('data-count-suffix') || ''
  const duration = isUpdate ? 0.8 : 1.8
  const startVal = isUpdate ? parseFloat(el.textContent.replace(/[^\d.-]/g, '')) || 0 : 0

  const startTime = performance.now()

  function easeOutExpo(t) { return t === 1 ? 1 : 1 - Math.pow(2, -10 * t) }

  function tick(now) {
    const elapsed = (now - startTime) / 1000
    const progress = Math.min(elapsed / duration, 1)
    const eased = easeOutExpo(progress)
    const current = startVal + (end - startVal) * eased

    el.textContent = prefix + formatNumber(current, decimals) + suffix

    if (progress < 1) {
      requestAnimationFrame(tick)
    } else {
      el.textContent = prefix + formatNumber(end, decimals) + suffix
    }
  }
  requestAnimationFrame(tick)
}

function formatNumber(num, decimals) {
  return Number(num).toLocaleString('zh-CN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

/**
 * 元素进入视口时添加动画class
 */
export function useReveal(elRef, animClass = 'fade-up') {
  let observer = null
  onMounted(() => {
    if (!elRef.value) return
    elRef.value.style.opacity = '0'
    observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add(animClass)
          entry.target.style.opacity = ''
          observer.unobserve(entry.target)
        }
      })
    }, { threshold: 0.1 })
    observer.observe(elRef.value)
  })
  onUnmounted(() => observer?.disconnect())
}

/**
 * 子元素交错渐入
 */
export function useStaggerChildren(containerRef, delay = 60) {
  let observer = null
  onMounted(() => {
    if (!containerRef.value) return
    const children = containerRef.value.children
    Array.from(children).forEach((child, i) => {
      child.style.opacity = '0'
      child.style.transform = 'translateY(20px)'
      child.style.transition = `opacity 0.5s cubic-bezier(0.16, 1, 0.3, 1) ${i * delay}ms, transform 0.5s cubic-bezier(0.16, 1, 0.3, 1) ${i * delay}ms`
    })
    observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          Array.from(children).forEach((child) => {
            child.style.opacity = '1'
            child.style.transform = 'translateY(0)'
            // 动画结束后彻底清除所有内联样式，让 CSS :hover 完全接管
            child.addEventListener('transitionend', function handler() {
              child.style.transform = ''
              child.style.transition = ''
              child.style.opacity = ''
              child.removeEventListener('transitionend', handler)
            })
          })
          observer.disconnect()
        }
      })
    }, { threshold: 0.1 })
    observer.observe(containerRef.value)
  })
  onUnmounted(() => observer?.disconnect())
}
