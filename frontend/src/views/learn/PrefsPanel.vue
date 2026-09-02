<template>
  <el-drawer v-model="visible" title="学习偏好设置" size="420px" direction="rtl">
    <div class="prefs-form" v-if="prefs">
      <!-- 主省份 -->
      <div class="pref-section">
        <div class="pref-label">主省份</div>
        <div class="pref-desc">深入学习的省份，影响L2/L3内容和省份动态</div>
        <el-select v-model="prefs.home_province" @change="onHomeProvinceChange" style="width: 100%">
          <el-option v-for="p in provinces" :key="p.name" :label="`${p.name}（${p.grid_label}）`" :value="p.name" />
        </el-select>
      </div>

      <!-- 学习层级 -->
      <div class="pref-section">
        <div class="pref-label">学习层级</div>
        <div class="pref-desc">
          诊断推荐：<strong>{{ profile?.diagnosed_level_label || '未诊断' }}</strong>
          <span v-if="profile?.manual_level" class="override-hint">（已手动覆盖）</span>
        </div>
        <el-radio-group v-model="levelChoice" @change="onLevelChange">
          <el-radio-button value="">跟随诊断</el-radio-button>
          <el-radio-button value="L1">L1 零基础</el-radio-button>
          <el-radio-button value="L2">L2 进阶</el-radio-button>
          <el-radio-button value="L3">L3 老手</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 偏好难度 -->
      <div class="pref-section">
        <div class="pref-label">刷题难度</div>
        <div class="pref-desc">控制自由刷题和诊断题的难度倾向</div>
        <el-radio-group v-model="prefs.preferred_difficulty" @change="savePrefs({ preferred_difficulty: prefs.preferred_difficulty })">
          <el-radio-button :value="0">自适应</el-radio-button>
          <el-radio-button :value="1">简单</el-radio-button>
          <el-radio-button :value="2">中等</el-radio-button>
          <el-radio-button :value="3">困难</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 关注省份 -->
      <div class="pref-section">
        <div class="pref-label">关注省份</div>
        <div class="pref-desc">L3老手的"省份动态"会展示这些省份的最新公告</div>
        <el-select
          v-model="prefs.watched_provinces"
          multiple
          filterable
          @change="savePrefs({ watched_provinces: prefs.watched_provinces })"
          style="width: 100%"
          placeholder="选择关注的省份"
        >
          <el-option v-for="p in provinces" :key="p.name" :label="p.name" :value="p.name" />
        </el-select>
      </div>

      <!-- 每日目标 -->
      <div class="pref-section">
        <div class="pref-label">每日刷题目标</div>
        <div class="pref-desc">设定每日学习目标，养成习惯</div>
        <el-slider
          v-model="prefs.daily_goal"
          :min="5" :max="50" :step="5"
          show-stops
          @change="savePrefs({ daily_goal: prefs.daily_goal })"
        />
        <div class="goal-display">每天 {{ prefs.daily_goal }} 题</div>
      </div>

      <!-- 内容偏好 -->
      <div class="pref-section">
        <div class="pref-label">关注内容类型</div>
        <div class="pref-desc">选择你最关心的内容，系统会优先推荐</div>
        <el-checkbox-group v-model="prefs.content_interests" @change="savePrefs({ content_interests: prefs.content_interests })">
          <el-checkbox value="all">全部</el-checkbox>
          <el-checkbox value="policy">政策法规</el-checkbox>
          <el-checkbox value="quiz">刷题练习</el-checkbox>
          <el-checkbox value="scenario">情景演练</el-checkbox>
          <el-checkbox value="province">省份动态</el-checkbox>
        </el-checkbox-group>
      </div>
    </div>

    <template #footer>
      <div class="footer-actions">
        <el-button @click="visible = false">关闭</el-button>
        <el-button type="primary" @click="visible = false">完成</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { studyApi } from '../../api'

const props = defineProps({
  modelValue: Boolean,
  profile: Object,
  provinces: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'changed'])

const visible = ref(props.modelValue)
watch(() => props.modelValue, (v) => { visible.value = v })
watch(visible, (v) => emit('update:modelValue', v))

const prefs = ref(null)
const levelChoice = ref('')

// 初始化偏好
watch(() => props.profile, (p) => {
  if (p) {
    prefs.value = {
      home_province: p.home_province,
      preferred_difficulty: p.preferred_difficulty ?? 0,
      watched_provinces: p.watched_provinces || [],
      content_interests: p.content_interests || ['all'],
      daily_goal: p.daily_goal || 10,
    }
    levelChoice.value = p.manual_level || ''
  }
}, { immediate: true })

const onHomeProvinceChange = async (val) => {
  await savePrefs({ home_province: val })
}

const onLevelChange = async (val) => {
  // val="" 表示跟随诊断 → 后端收到空串会清空手选
  await savePrefs({ manual_level: val || '' })
}

const savePrefs = async (data) => {
  try {
    await studyApi.updatePrefs(data)
    emit('changed')
    ElMessage.success('设置已保存')
  } catch (e) {
    ElMessage.error(e.message)
  }
}
</script>

<style scoped>
.prefs-form { display: flex; flex-direction: column; gap: 24px; }
.pref-section { }
.pref-label { font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.pref-desc { font-size: 12px; color: var(--text-secondary); margin-bottom: 10px; line-height: 1.5; }
.override-hint { color: var(--accent-orange); font-size: 11px; }
.goal-display { text-align: center; font-size: 14px; color: var(--accent); font-weight: 600; margin-top: 4px; }
.footer-actions { display: flex; justify-content: flex-end; gap: 12px; }
</style>
