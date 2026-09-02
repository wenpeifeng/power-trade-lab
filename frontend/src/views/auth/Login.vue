<template>
  <main
    class="auth-page"
    :style="pointerStyle"
    @pointermove="handlePointerMove"
    @pointerleave="resetPointer"
  >
    <div class="page-grid" aria-hidden="true"></div>
    <div class="page-glow" aria-hidden="true"></div>

    <div class="brand-corner auth-reveal">
      <Logo :size="40" />
      <div>
        <strong>电力交易中枢</strong>
        <span>POWER MARKET OS</span>
      </div>
    </div>

    <div class="auth-layout">
      <section class="auth-panel auth-reveal delay-1" aria-label="账号入口">
        <div class="panel-context">
          <span><ShieldCheck :size="14" /> 统一身份入口</span>
          <small>安全会话</small>
        </div>

        <Transition name="heading-swap" mode="out-in">
          <div :key="mode" class="panel-heading">
            <h1>{{ mode === 'login' ? '登录' : '创建账号' }}</h1>
            <p>
              {{ mode === 'login'
                ? '进入电力交易学习与仿真平台。'
                : '建立学习档案和模拟交易账户。' }}
            </p>
          </div>
        </Transition>

        <form class="auth-form" novalidate @submit.prevent="submit">
          <label class="field" :class="{ invalid: fieldErrors.username }">
            <span class="field-label">用户名</span>
            <span class="field-control">
              <UserRound :size="18" />
              <input
                v-model.trim="form.username"
                type="text"
                placeholder="输入用户名"
                autocomplete="username"
                maxlength="32"
                @input="clearFieldError('username')"
              />
              <Check v-if="usernameReady" :size="16" class="field-check" />
            </span>
            <small v-if="fieldErrors.username" class="field-error">{{ fieldErrors.username }}</small>
            <small v-else-if="mode === 'register'" class="field-hint">3–32 个字符，支持中英文、数字、下划线和短横线</small>
          </label>

          <label class="field" :class="{ invalid: fieldErrors.password }">
            <span class="field-label">密码</span>
            <span class="field-control">
              <LockKeyhole :size="18" />
              <input
                v-model="form.password"
                :type="showPassword ? 'text' : 'password'"
                :placeholder="mode === 'login' ? '输入密码' : '设置至少 8 位密码'"
                :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
                @input="clearFieldError('password')"
                @keydown="detectCapsLock"
                @keyup="detectCapsLock"
                @blur="capsLock = false"
              />
              <button
                type="button"
                class="password-toggle"
                :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                @click="showPassword = !showPassword"
              >
                <EyeOff v-if="showPassword" :size="17" />
                <Eye v-else :size="17" />
              </button>
            </span>
            <small v-if="fieldErrors.password" class="field-error">{{ fieldErrors.password }}</small>
            <small v-else-if="capsLock" class="caps-hint">大写锁定已开启</small>
            <div v-else-if="mode === 'register' && form.password" class="password-strength" :data-score="passwordScore">
              <span><i></i><i></i><i></i><i></i></span>
              <small>{{ passwordStrengthLabel }}</small>
            </div>
          </label>

          <Transition name="register-fields">
            <div v-if="mode === 'register'" class="register-grid">
              <label class="field compact">
                <span class="field-label">显示名 <em>选填</em></span>
                <span class="field-control">
                  <CircleUserRound :size="17" />
                  <input v-model.trim="form.display_name" type="text" placeholder="如何称呼你" autocomplete="name" />
                </span>
              </label>

              <label class="field compact">
                <span class="field-label">所在省份 <em>选填</em></span>
                <span class="field-control select-control">
                  <MapPin :size="17" />
                  <select v-model="form.home_province" aria-label="所在省份">
                    <option value="">选择省份</option>
                    <option v-for="province in provinces" :key="province" :value="province">{{ province }}</option>
                  </select>
                  <ChevronDown :size="15" />
                </span>
              </label>
            </div>
          </Transition>

          <div v-if="error" class="auth-error" role="alert">
            <CircleAlert :size="16" />
            <span>{{ error }}</span>
          </div>

          <button type="submit" class="submit-btn" :class="{ loading }" :disabled="loading">
            <span v-if="loading" class="button-spinner" aria-hidden="true"></span>
            <span>{{ loading ? (mode === 'login' ? '正在登录' : '正在建立账号') : (mode === 'login' ? '登录并进入门户' : '创建账号') }}</span>
            <ArrowRight v-if="!loading" :size="18" />
          </button>
        </form>

        <div class="mode-switch">
          <span>{{ mode === 'login' ? '还没有账号？' : '已经有账号？' }}</span>
          <button type="button" @click="switchMode(mode === 'login' ? 'register' : 'login')">
            {{ mode === 'login' ? '创建账号' : '返回登录' }}
          </button>
        </div>

        <p class="panel-footnote">
          {{ mode === 'login'
            ? '登录后先进入门户，再选择学习、仿真、行情或知识数据模块。'
            : '平台内交易资金与交易结果均为教学仿真。' }}
        </p>
      </section>

      <section class="identity-scene auth-reveal delay-2" aria-labelledby="scene-title">
        <div class="scene-copy">
          <span>IDENTITY BUS / 统一身份母线</span>
          <h2 id="scene-title">一次登录，连接完整的<br />学习与仿真过程</h2>
          <p>身份只负责安全进入，具体工作在门户中选择。</p>
        </div>

        <div class="single-line" aria-label="统一身份连接规则数据、学习、仿真与复盘">
          <div class="bus-line" aria-hidden="true">
            <i class="energy-flow flow-one"></i>
            <i class="energy-flow flow-two"></i>
          </div>

          <div class="bus-node node-rules">
            <span><DatabaseZap :size="17" /></span>
            <strong>规则数据</strong>
            <small>SOURCE</small>
          </div>
          <div class="bus-node node-learning">
            <span><BookOpenCheck :size="17" /></span>
            <strong>学习测评</strong>
            <small>LEARN</small>
          </div>
          <div class="identity-node">
            <span><Fingerprint :size="23" /></span>
            <strong>身份已连接</strong>
            <small>IDENTITY GATE</small>
          </div>
          <div class="bus-node node-simulation">
            <span><Orbit :size="17" /></span>
            <strong>交易仿真</strong>
            <small>SIMULATE</small>
          </div>
          <div class="bus-node node-review">
            <span><ScanSearch :size="17" /></span>
            <strong>结算复盘</strong>
            <small>REVIEW</small>
          </div>
        </div>

        <div class="scene-principles">
          <span><Check :size="13" /> 规则有版本</span>
          <span><Check :size="13" /> 数据有来源</span>
          <span><Check :size="13" /> 过程可回放</span>
        </div>
      </section>
    </div>

    <footer class="page-footer">
      <span>POWER TRADING LEARNING & SIMULATION</span>
      <span><ShieldCheck :size="12" /> 登录凭证通过安全会话传输</span>
    </footer>
  </main>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowRight, BookOpenCheck, Check, ChevronDown, CircleAlert, CircleUserRound,
  DatabaseZap, Eye, EyeOff, Fingerprint, LockKeyhole, MapPin, Orbit, ScanSearch,
  ShieldCheck, UserRound,
} from 'lucide-vue-next'
import { authApi } from '../../api'
import Logo from '../../components/Logo.vue'

const router = useRouter()
const mode = ref('login')
const loading = ref(false)
const error = ref('')
const showPassword = ref(false)
const capsLock = ref(false)
const pointer = reactive({ x: 72, y: 28 })
const fieldErrors = reactive({ username: '', password: '' })
const provinces = ['山西', '山东', '广东', '浙江', '蒙西', '上海', '江苏', '福建', '安徽', '吉林', '辽宁', '黑龙江', '江西', '云南', '广西']
const form = reactive({ username: '', password: '', display_name: '', home_province: '' })

const pointerStyle = computed(() => ({ '--pointer-x': `${pointer.x}%`, '--pointer-y': `${pointer.y}%` }))
const usernameReady = computed(() => {
  if (mode.value === 'login') return form.username.length > 0
  return /^[\w\-\u4e00-\u9fff]{3,32}$/u.test(form.username)
})
const passwordScore = computed(() => {
  const value = form.password
  if (!value) return 0
  return Math.min(4, [value.length >= 8, /[a-z]/i.test(value), /\d/.test(value), /[^\w\s]/.test(value)].filter(Boolean).length)
})
const passwordStrengthLabel = computed(() => ['待设置', '较弱', '一般', '良好', '较强'][passwordScore.value])

function handlePointerMove(event) {
  pointer.x = Math.round((event.clientX / window.innerWidth) * 100)
  pointer.y = Math.round((event.clientY / window.innerHeight) * 100)
}

function resetPointer() {
  pointer.x = 72
  pointer.y = 28
}

function switchMode(nextMode) {
  if (mode.value === nextMode) return
  mode.value = nextMode
  error.value = ''
  fieldErrors.username = ''
  fieldErrors.password = ''
  capsLock.value = false
}

function clearFieldError(field) {
  fieldErrors[field] = ''
  error.value = ''
}

function detectCapsLock(event) {
  capsLock.value = event.getModifierState?.('CapsLock') || false
}

function validate() {
  fieldErrors.username = ''
  fieldErrors.password = ''
  if (!form.username) fieldErrors.username = '请输入用户名'
  else if (mode.value === 'register' && !/^[\w\-\u4e00-\u9fff]{3,32}$/u.test(form.username)) {
    fieldErrors.username = '用户名格式不符合要求'
  }
  if (!form.password) fieldErrors.password = '请输入密码'
  else if (mode.value === 'register' && form.password.length < 8) fieldErrors.password = '密码至少需要 8 个字符'
  return !fieldErrors.username && !fieldErrors.password
}

async function submit() {
  if (!validate()) return
  loading.value = true
  error.value = ''
  try {
    const api = mode.value === 'login' ? authApi.login : authApi.register
    const payload = mode.value === 'login'
      ? { username: form.username, password: form.password }
      : {
          username: form.username,
          password: form.password,
          display_name: form.display_name || undefined,
          home_province: form.home_province || undefined,
        }
    const response = await api(payload)
    localStorage.setItem('user', JSON.stringify(response.user))
    ElMessage.success(mode.value === 'login' ? '登录成功，正在进入门户' : '账号已创建，正在进入门户')
    await router.replace({ name: 'portal' })
  } catch (submitError) {
    error.value = submitError.message || '请求未完成，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  --ink: #17203c;
  --muted: #6f798e;
  --line: #dfe5ef;
  --indigo: #5964df;
  position: relative;
  min-height: 100svh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  color: var(--ink);
  background:
    radial-gradient(circle at var(--pointer-x) var(--pointer-y), rgba(77,205,224,.1), transparent 24rem),
    linear-gradient(135deg, #f1f4fb 0%, #f8f9fc 52%, #edf1fb 100%);
  font-family: "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
}

.page-grid {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: .45;
  background-image:
    linear-gradient(rgba(78,94,157,.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(78,94,157,.035) 1px, transparent 1px);
  background-size: 54px 54px;
  mask-image: linear-gradient(90deg, transparent 0%, #000 35%, #000 100%);
}

.page-glow {
  position: absolute;
  right: -160px;
  top: -220px;
  width: 720px;
  height: 720px;
  border-radius: 50%;
  border: 1px solid rgba(89,100,223,.08);
  box-shadow: 0 0 0 90px rgba(89,100,223,.025), 0 0 0 190px rgba(89,100,223,.018);
  pointer-events: none;
  animation: haloDrift 14s ease-in-out infinite;
}

.brand-corner {
  position: absolute;
  z-index: 10;
  top: clamp(25px, 4vh, 44px);
  left: clamp(26px, 4.6vw, 78px);
  display: flex;
  align-items: center;
  gap: 11px;
}
.brand-corner > div { display: flex; flex-direction: column; gap: 3px; }
.brand-corner strong { color: #1b2237; font-size: 16px; font-weight: 760; letter-spacing: -.02em; }
.brand-corner span { color: #9aa3b4; font: 700 7px/1 ui-monospace, monospace; letter-spacing: .15em; }

.auth-layout {
  position: relative;
  z-index: 2;
  width: min(1120px, calc(100% - 48px));
  margin: auto;
  padding: 110px 0 72px;
  display: grid;
  grid-template-columns: 430px minmax(0, 1fr);
  align-items: center;
  gap: clamp(72px, 9vw, 130px);
}

.auth-panel {
  position: relative;
  width: 100%;
  padding: 31px 33px 27px;
  border: 1px solid rgba(211,219,234,.96);
  border-radius: 20px;
  background: rgba(255,255,255,.92);
  box-shadow: 0 24px 64px rgba(51,64,116,.13), inset 0 1px 0 #fff;
  backdrop-filter: blur(22px) saturate(145%);
}
.auth-panel::before { content: ""; position: absolute; top: 0; left: 40px; right: 40px; height: 2px; border-radius: 0 0 3px 3px; background: linear-gradient(90deg,transparent,#6571e6,#53cad9,transparent); }
.panel-context { display: flex; align-items: center; justify-content: space-between; margin-bottom: 21px; }
.panel-context > span { display: inline-flex; align-items: center; gap: 6px; color: #5964c9; font-size: 10px; font-weight: 750; }
.panel-context small { color: #a0a9b8; font: 700 8px/1 ui-monospace,monospace; letter-spacing: .08em; }
.panel-heading { margin-bottom: 24px; }
.panel-heading h1 { margin: 0 0 9px; color: #17203c; font-size: 30px; line-height: 1.2; font-weight: 790; letter-spacing: -.04em; }
.panel-heading p { margin: 0; color: #778297; font-size: 12px; line-height: 1.7; }
.auth-form { display: flex; flex-direction: column; gap: 17px; }
.field { display: flex; flex-direction: column; gap: 7px; }
.field-label { display: flex; justify-content: space-between; color: #465269; font-size: 12px; font-weight: 700; }
.field-label em { color: #a3abba; font-size: 10px; font-style: normal; font-weight: 500; }
.field-control { height: 49px; padding: 0 13px; display: flex; align-items: center; gap: 10px; border: 1px solid #dfe5ef; border-radius: 11px; color: #9aa5b7; background: #fafbfe; transition: border-color .22s, box-shadow .22s, background .22s, transform .22s; }
.field:focus-within .field-control { border-color: #717de4; color: #5360d1; background: #fff; box-shadow: 0 0 0 4px rgba(86,99,220,.09); transform: translateY(-1px); }
.field.invalid .field-control { border-color: #dd7474; background: #fffafa; box-shadow: 0 0 0 3px rgba(221,96,96,.07); }
.field-control input, .field-control select { min-width: 0; flex: 1; height: 100%; border: 0; outline: 0; appearance: none; color: #1f2b43; background: transparent; font: 500 14px/1.4 inherit; }
.field-control input::placeholder { color: #b0b8c6; }
.select-control select { cursor: pointer; }
.select-control > svg:last-child { pointer-events: none; }
.field-check { color: #18a889; }
.password-toggle { width: 30px; height: 30px; flex: none; display: grid; place-items: center; border: 0; border-radius: 8px; color: #8e99aa; background: transparent; cursor: pointer; }
.password-toggle:hover { color: #5360d1; background: #eef1ff; }
.field-error, .caps-hint, .field-hint { padding-left: 2px; font-size: 10px; line-height: 1.4; }
.field-error { color: #cc5353; }
.caps-hint { color: #bd7a24; }
.field-hint { color: #9ca6b7; }
.password-strength { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.password-strength > span { flex: 1; display: grid; grid-template-columns: repeat(4,1fr); gap: 4px; }
.password-strength i { height: 3px; border-radius: 2px; background: #e4e8ef; }
.password-strength small { min-width: 25px; color: #98a2b3; font-size: 9px; }
.password-strength[data-score="1"] i:nth-child(-n+1), .password-strength[data-score="2"] i:nth-child(-n+2) { background: #e18c5b; }
.password-strength[data-score="3"] i:nth-child(-n+3) { background: #d1a33c; }
.password-strength[data-score="4"] i:nth-child(-n+4) { background: #23ac8f; }
.register-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.field.compact .field-control { height: 45px; padding-inline: 11px; }
.auth-error { padding: 11px 12px; display: flex; align-items: flex-start; gap: 9px; border: 1px solid #f1d0d0; border-radius: 10px; color: #bd4c4c; background: #fff7f7; font-size: 11px; line-height: 1.5; }
.auth-error svg { flex: none; margin-top: 1px; }
.submit-btn { position: relative; height: 51px; margin-top: 1px; padding: 0 18px; overflow: hidden; display: flex; align-items: center; justify-content: center; gap: 10px; border: 0; border-radius: 11px; color: #fff; background: linear-gradient(135deg,#5964df,#4652c9); box-shadow: 0 11px 23px rgba(79,89,207,.22); cursor: pointer; font: 750 14px/1 inherit; transition: transform .2s,box-shadow .2s; }
.submit-btn::before { content: ""; position: absolute; inset: 0; transform: translateX(-105%); background: linear-gradient(100deg,transparent 30%,rgba(255,255,255,.2),transparent 70%); transition: transform .55s ease; }
.submit-btn:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 15px 29px rgba(79,89,207,.29); }
.submit-btn:hover:not(:disabled)::before { transform: translateX(105%); }
.submit-btn:active:not(:disabled) { transform: translateY(0) scale(.985); }
.submit-btn:disabled { cursor: wait; opacity: .78; }
.submit-btn > * { position: relative; z-index: 1; }
.button-spinner { width: 17px; height: 17px; border: 2px solid rgba(255,255,255,.35); border-top-color: #fff; border-radius: 50%; animation: buttonSpin .7s linear infinite; }
.mode-switch { margin-top: 20px; padding-top: 18px; display: flex; align-items: center; justify-content: center; gap: 5px; border-top: 1px solid #edf0f5; color: #8a93a5; font-size: 11px; }
.mode-switch button { padding: 2px 3px; border: 0; color: #5360d1; background: transparent; cursor: pointer; font: 750 11px/1 inherit; }
.mode-switch button:hover { color: #3947bb; text-decoration: underline; text-underline-offset: 3px; }
.panel-footnote { margin-top: 11px; color: #a0a8b7; font-size: 9px; line-height: 1.55; text-align: center; }

.identity-scene { min-width: 0; padding-top: 12px; }
.scene-copy > span { color: #6f7ab1; font: 750 9px/1 ui-monospace,monospace; letter-spacing: .15em; }
.scene-copy h2 { max-width: 590px; margin: 15px 0 12px; color: #202944; font-size: clamp(30px,3vw,43px); line-height: 1.24; font-weight: 790; letter-spacing: -.045em; }
.scene-copy p { margin: 0; color: #7b8497; font-size: 13px; }
.single-line { position: relative; height: 310px; margin: 25px 0 3px; }
.bus-line { position: absolute; left: 5%; right: 4%; top: 52%; height: 2px; overflow: visible; background: linear-gradient(90deg,rgba(89,100,223,.08),#aab4dd 16%,#6876dc 50%,#aab4dd 84%,rgba(89,100,223,.08)); box-shadow: 0 0 0 5px rgba(255,255,255,.35); }
.bus-line::before, .bus-line::after { content: ""; position: absolute; top: -44px; width: 1px; height: 90px; background: linear-gradient(transparent,#8f9ad0,transparent); }
.bus-line::before { left: 27%; }
.bus-line::after { right: 25%; }
.energy-flow { position: absolute; top: -3px; width: 8px; height: 8px; border-radius: 50%; background: #4fc9d8; box-shadow: 0 0 14px #40bccd; animation: energyFlow 4.6s linear infinite; }
.flow-two { animation-delay: -2.3s; }
.identity-node { position: absolute; z-index: 4; left: 50%; top: 52%; width: 130px; height: 130px; transform: translate(-50%,-50%); clip-path: polygon(50% 0,90% 23%,90% 77%,50% 100%,10% 77%,10% 23%); display: flex; align-items: center; justify-content: center; flex-direction: column; color: #fff; background: linear-gradient(145deg,#5260d4,#3442aa); box-shadow: 0 18px 40px rgba(63,76,181,.25); }
.identity-node::before { content: ""; position: absolute; inset: 10px; clip-path: inherit; border: 1px solid rgba(255,255,255,.14); }
.identity-node > span { width: 36px; height: 36px; display: grid; place-items: center; margin-bottom: 5px; border-radius: 50%; background: rgba(255,255,255,.1); }
.identity-node strong { font-size: 11px; }
.identity-node small { margin-top: 4px; color: rgba(255,255,255,.55); font: 700 7px/1 ui-monospace,monospace; letter-spacing: .1em; }
.bus-node { position: absolute; z-index: 3; width: 88px; display: flex; align-items: center; flex-direction: column; color: #5964c9; text-align: center; }
.bus-node::after { content: ""; position: absolute; left: 50%; width: 1px; height: 39px; background: #aeb7d7; }
.bus-node > span { width: 42px; height: 42px; display: grid; place-items: center; border: 1px solid #d9dfef; border-radius: 12px; background: rgba(255,255,255,.83); box-shadow: 0 7px 17px rgba(57,72,132,.08); }
.bus-node strong { margin-top: 7px; color: #596277; font-size: 10px; }
.bus-node small { margin-top: 3px; color: #a1a9b8; font: 700 7px/1 ui-monospace,monospace; letter-spacing: .08em; }
.node-rules { left: 2%; top: 31px; }
.node-rules::after, .node-learning::after { top: 106px; }
.node-learning { left: 24%; top: 31px; }
.node-simulation { right: 22%; bottom: 10px; }
.node-review { right: 0; bottom: 10px; }
.node-simulation::after, .node-review::after { bottom: 106px; }
.scene-principles { display: flex; gap: 9px; flex-wrap: wrap; }
.scene-principles span { padding: 7px 10px; display: inline-flex; align-items: center; gap: 5px; border: 1px solid #dde3ef; border-radius: 9px; color: #7c8598; background: rgba(255,255,255,.5); font-size: 9px; }
.scene-principles svg { color: #22aa91; }

.page-footer { position: absolute; z-index: 4; left: clamp(26px,4.6vw,78px); right: clamp(26px,4.6vw,78px); bottom: 22px; display: flex; justify-content: space-between; gap: 20px; color: #9ba3b2; font: 700 8px/1 ui-monospace,monospace; letter-spacing: .1em; }
.page-footer span:last-child { display: inline-flex; align-items: center; gap: 6px; }
.auth-reveal { animation: authReveal .65s cubic-bezier(.16,1,.3,1) both; }
.delay-1 { animation-delay: .08s; }
.delay-2 { animation-delay: .16s; }
.heading-swap-enter-active, .heading-swap-leave-active { transition: opacity .18s ease,transform .22s ease; }
.heading-swap-enter-from { opacity: 0; transform: translateY(7px); }
.heading-swap-leave-to { opacity: 0; transform: translateY(-5px); }
.register-fields-enter-active, .register-fields-leave-active { overflow: hidden; transition: opacity .26s ease,transform .32s cubic-bezier(.16,1,.3,1),max-height .32s ease; }
.register-fields-enter-from, .register-fields-leave-to { opacity: 0; transform: translateY(-9px); max-height: 0; }
.register-fields-enter-to, .register-fields-leave-from { max-height: 90px; }
@keyframes authReveal { from{opacity:0;transform:translateY(15px)} to{opacity:1;transform:translateY(0)} }
@keyframes haloDrift { 50%{transform:translate(-18px,20px) scale(1.04)} }
@keyframes energyFlow { from{left:0;opacity:0} 12%{opacity:1} 88%{opacity:1} to{left:100%;opacity:0} }
@keyframes buttonSpin { to{transform:rotate(360deg)} }
/* 文本输入的焦点由外层 .field-control 统一表达，避免浏览器在 input 本体再画一层矩形。 */
.field-control input:focus-visible,
.field-control select:focus-visible { outline: none; }
button:focus-visible { outline: 2px solid #7684ea; outline-offset: 3px; }

@media (max-width: 940px) {
  .auth-page { overflow: auto; }
  .auth-layout { width: min(560px,calc(100% - 36px)); padding: 112px 0 78px; grid-template-columns: 1fr; gap: 42px; }
  .auth-panel { width: min(440px,100%); margin: 0 auto; }
  .identity-scene { text-align: center; }
  .scene-copy h2 { margin-inline: auto; }
  .single-line { max-width: 560px; margin-inline: auto; }
  .scene-principles { justify-content: center; }
  .page-footer { position: static; width: min(560px,calc(100% - 36px)); margin: -40px auto 20px; }
}

@media (max-width: 540px) {
  .brand-corner { top: 22px; left: 20px; }
  .brand-corner :deep(.app-logo) { width: 36px; height: 36px; }
  .auth-layout { padding-top: 92px; gap: 30px; }
  .auth-panel { padding: 28px 22px 24px; }
  .panel-heading h1 { font-size: 27px; }
  .register-grid { grid-template-columns: 1fr; }
  .register-fields-enter-to, .register-fields-leave-from { max-height: 180px; }
  .scene-copy h2 { font-size: 29px; }
  .single-line { height: 250px; transform: scale(.92); transform-origin: center top; }
  .node-learning { left: 20%; }
  .node-simulation { right: 18%; }
  .page-footer { justify-content: center; }
  .page-footer span:first-child { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .auth-page *,.auth-page *::before,.auth-page *::after { animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important; }
}
</style>
