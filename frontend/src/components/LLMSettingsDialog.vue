<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="v => emit('update:modelValue', v)"
    title="个人设置 · AI 模型"
    width="600px"
    class="brand-dialog"
    @open="loadStatus"
  >
    <div class="llm-set">
      <div class="cur" v-if="status">
        <span>仅对当前账号生效：</span>
        <b>{{ providerName(status.provider) }}</b>
        <span class="cur-model">{{ status.model || '—' }}</span>
        <el-tag v-if="status.api_key_set" type="success" size="small" effect="light">Key 已配置</el-tag>
        <el-tag v-else type="info" size="small" effect="light">未配置 Key</el-tag>
      </div>

      <div class="privacy-note">
        Key 会先加密再保存，接口只显示末四位；其他账号、日志和开源代码都无法读取明文。
      </div>

      <el-form label-position="top">
        <el-form-item label="模型厂商">
          <el-select v-model="providerKey" @change="onProviderChange" style="width:100%">
            <el-option v-for="p in PROVIDERS" :key="p.key" :label="p.name" :value="p.key" />
          </el-select>
        </el-form-item>
        <el-form-item label="接口地址（Base URL）">
          <el-input v-model="form.base_url" placeholder="厂商 API 地址" />
        </el-form-item>
        <el-form-item label="模型">
          <el-select
            v-if="curProvider.models.length"
            v-model="form.model" filterable allow-create default-first-option
            style="width:100%" placeholder="选择或输入模型"
          >
            <el-option v-for="m in curProvider.models" :key="m" :label="m" :value="m" />
          </el-select>
          <el-input v-else v-model="form.model" placeholder="模型名称" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="form.api_key" type="password" show-password
            :placeholder="status && status.api_key_set ? '已配置，留空表示不修改' : '粘贴你的 API Key'"
          />
        </el-form-item>
      </el-form>

      <div class="tip" v-if="curProvider.hint">{{ curProvider.hint }}</div>
      <div class="test-result" v-if="testResult" :class="testResult.ok ? 'ok' : 'err'">
        {{ testResult.ok ? '✓ 连接成功：' + testResult.text : '✗ 连接失败：' + testResult.text }}
      </div>
    </div>

    <template #footer>
      <el-button v-if="status?.api_key_set" type="danger" plain @click="removeConfig" :loading="removing">删除个人 Key</el-button>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button @click="doTest" :loading="testing">测试连接</el-button>
      <el-button type="primary" @click="doSave" :loading="saving">保存并启用</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { aiApi } from '../api'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue'])

// 常见厂商预设。provider 字段对齐后端 call_llm 识别：ollama / zhipu / deepseek / 其余 OpenAI 兼容用 openai
const PROVIDERS = [
  { key: 'zhipu', name: '智谱 GLM', provider: 'zhipu', base_url: 'https://open.bigmodel.cn/api/paas/v4', models: ['glm-4-flash', 'glm-4-plus', 'glm-4'], hint: 'glm-4-flash 免费额度大，推荐先用它跑通' },
  { key: 'dashscope', name: '阿里百炼（通义千问）', provider: 'openai', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: ['qwen-turbo', 'qwen-plus', 'qwen-max'], hint: '百炼 OpenAI 兼容模式；qwen-turbo 有免费额度，可先用' },
  { key: 'deepseek', name: 'DeepSeek', provider: 'deepseek', base_url: 'https://api.deepseek.com', models: ['deepseek-chat', 'deepseek-reasoner'], hint: '' },
  { key: 'moonshot', name: 'Kimi（Moonshot）', provider: 'openai', base_url: 'https://api.moonshot.cn/v1', models: ['moonshot-v1-8k', 'moonshot-v1-32k'], hint: '' },
  { key: 'openai', name: 'OpenAI', provider: 'openai', base_url: 'https://api.openai.com/v1', models: ['gpt-4o-mini', 'gpt-4o'], hint: '需要能访问 OpenAI 的网络环境' },
  { key: 'ollama', name: '本地 Ollama', provider: 'ollama', base_url: 'http://localhost:11434', models: ['qwen2.5:7b', 'qwen2.5:3b', 'llama3.1'], hint: '需本地已启动 Ollama 并 pull 对应模型' },
  { key: 'custom', name: '自定义 / 代理路由', provider: 'openai', base_url: '', models: [], hint: 'OpenAI 兼容接口，填你的路由地址（如 cc-switch 的 base_url）' },
]

const providerKey = ref('zhipu')
const curProvider = computed(() => PROVIDERS.find(p => p.key === providerKey.value) || PROVIDERS[0])
const form = reactive({ base_url: PROVIDERS[0].base_url, model: PROVIDERS[0].models[0], api_key: '' })
const status = ref(null)
const testing = ref(false)
const saving = ref(false)
const testResult = ref(null)
const removing = ref(false)

function providerName(prov) {
  const p = PROVIDERS.find(x => x.provider === prov || x.key === prov)
  return p ? p.name : prov
}
function onProviderChange() {
  form.base_url = curProvider.value.base_url
  form.model = curProvider.value.models[0] || ''
  testResult.value = null
}
async function loadStatus() {
  try {
    status.value = await aiApi.llmStatus()
    if (status.value?.enabled) {
      const matched = PROVIDERS.find(p =>
        p.provider === status.value.provider &&
        (!status.value.base_url || p.base_url === status.value.base_url)
      ) || PROVIDERS.find(p => p.provider === status.value.provider)
      if (matched) providerKey.value = matched.key
      form.base_url = status.value.base_url || matched?.base_url || ''
      form.model = status.value.model || matched?.models?.[0] || ''
      form.api_key = ''
    }
  } catch (e) { /* ignore */ }
}
function buildPayload() {
  const p = { provider: curProvider.value.provider, base_url: form.base_url, model: form.model }
  if (form.api_key) p.api_key = form.api_key
  return p
}
async function doSave() {
  if (!form.model) { ElMessage.warning('请填写模型名'); return }
  saving.value = true
  try {
    await aiApi.configLLM(buildPayload())
    ElMessage.success('已保存并启用')
    loadStatus()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  } finally { saving.value = false }
}
async function doTest() {
  testing.value = true
  testResult.value = null
  try {
    await aiApi.configLLM(buildPayload()) // 先落配置，再测当前生效项
    const r = await aiApi.testLLM()
    testResult.value = r.ok ? { ok: true, text: (r.response || '').slice(0, 60) } : { ok: false, text: r.error }
    loadStatus()
  } catch (e) {
    testResult.value = { ok: false, text: e.message || String(e) }
  } finally { testing.value = false }
}
async function removeConfig() {
  removing.value = true
  try {
    await aiApi.deleteLLM()
    ElMessage.success('个人 AI Key 已删除')
    testResult.value = null
    await loadStatus()
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.message || e))
  } finally { removing.value = false }
}
</script>

<style scoped>
.cur {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  font-size: 13px; color: #606266; margin-bottom: 16px;
  padding: 10px 12px; background: #f5f7fa; border-radius: 8px;
}
.cur-model { color: #6366f1; font-weight: 600; }
.privacy-note { margin:-5px 0 15px; padding:10px 12px; color:#52617a; background:#f3f7ff; border:1px solid #dbe7ff; border-radius:8px; font-size:12px; line-height:1.6; }
.tip { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #909399; margin-top: 2px; }
.test-result { margin-top: 12px; padding: 10px 12px; border-radius: 8px; font-size: 13px; line-height: 1.5; }
.test-result.ok { background: #f0f9eb; color: #529b2e; }
.test-result.err { background: #fef0f0; color: #c45656; }
</style>
