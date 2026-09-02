<template>
  <router-view v-slot="{ Component }">
    <component :is="Component" />
  </router-view>
  <!-- 全局右侧AI机器人 -->
  <AIRobotButton v-if="showRobot" @open="aiOpen = true" />
  <AIChatPanel v-if="aiOpen" @close="aiOpen = false" />
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AIRobotButton from './components/AIRobotButton.vue'
import AIChatPanel from './components/AIChatPanel.vue'
import { isLoggedIn } from './api'

const route = useRoute()
const aiOpen = ref(false)
const showRobot = ref(false)

// 登录后显示机器人，登录页不显示
watch(() => route.path, (p) => {
  showRobot.value = isLoggedIn() && p !== '/login'
}, { immediate: true })
</script>
