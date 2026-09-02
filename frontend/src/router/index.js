import { createRouter, createWebHistory } from 'vue-router'
import { authApi, currentUser } from '../api'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/auth/Login.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/',
    name: 'portal',
    component: () => import('../views/portal/Portal.vue'),
    meta: { theme: 'learn', title: '首页' },
  },
  {
    path: '/learn',
    component: () => import('../views/learn/Layout.vue'),
    meta: { theme: 'learn', title: '学习中心' },
    children: [
      { path: '', name: 'learn-home', component: () => import('../views/learn/Home.vue') },
      { path: 'quiz', name: 'learn-quiz', component: () => import('../views/learn/Quiz.vue') },
      { path: 'wrong', name: 'learn-wrong', component: () => import('../views/learn/WrongBook.vue') },
      { path: 'books', name: 'learn-books', component: () => import('../views/learn/BookStudio.vue') },
      { path: 'books/:bookId', name: 'learn-book-reader', component: () => import('../views/learn/BookReader.vue') },
      // 考试备考（独立路径，与学习刷题分流）
      { path: 'exam', name: 'learn-exam', component: () => import('../views/learn/ExamHome.vue') },
      { path: 'exam/paper', name: 'exam-paper', component: () => import('../views/learn/ExamPaper.vue') },
      { path: 'exam/result/:id', name: 'exam-result', component: () => import('../views/learn/ExamResult.vue') },
      // 分层学习（L1/L2/L3 + 诊断 + 省份）
      { path: 'study', name: 'learn-study', component: () => import('../views/learn/StudyHome.vue') },
      { path: 'study/diagnosis', name: 'study-diagnosis', component: () => import('../views/learn/Diagnosis.vue') },
      { path: 'study/lesson/:code', name: 'study-lesson', component: () => import('../views/learn/GuidedLesson.vue') },
    ],
  },
  {
    path: '/trade',
    name: 'trade',
    component: () => import('../views/trade/Terminal.vue'),
    meta: { theme: 'trade', title: '交易终端' },
  },
  {
    path: '/trade/lab',
    name: 'trade-lab',
    component: () => import('../views/trade/SimulationLab.vue'),
    meta: { theme: 'trade', title: '交易仿真实验室' },
  },
  {
    path: '/policy',
    component: () => import('../views/policy/Layout.vue'),
    meta: { theme: 'knowledge', title: '政策公告' },
    children: [
      { path: '', name: 'policy-list', component: () => import('../views/policy/List.vue') },
    ],
  },
  {
    path: '/admin',
    name: 'admin',
    component: () => import('../views/admin/Dashboard.vue'),
    meta: { theme: 'learn', title: '管理后台', requiresAdmin: true },
  },
  {
    path: '/asset',
    name: 'asset-center',
    component: () => import('../views/admin/AssetCenter.vue'),
    meta: { theme: 'asset', title: '数据资产中心' },
  },
  {
    path: '/assistant',
    name: 'ai-assistant',
    component: () => import('../views/ai/Assistant.vue'),
    meta: { theme: 'knowledge', title: 'AI助手' },
  },
  {
    path: '/knowledge',
    name: 'knowledge',
    component: () => import('../views/knowledge/Layout.vue'),
    meta: { theme: 'knowledge', title: '知识库' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.fullPath !== from.fullPath) return { left: 0, top: 0, behavior: 'auto' }
    return false
  },
})

// 路由切换时：登录检查 + 主题设置
let sessionValidated = false

router.beforeEach(async (to) => {
  // 每次页面加载只向后端核验一次 HttpOnly 会话；本地用户资料不作为授权依据。
  if (!sessionValidated) {
    try {
      const user = await authApi.me()
      localStorage.setItem('user', JSON.stringify(user))
    } catch {
      localStorage.removeItem('user')
    }
    sessionValidated = true
  }
  const user = currentUser()
  if (!to.meta.public && !user) {
    return { name: 'login' }
  }
  // 已登录用户访问登录页 → 跳首页
  if (to.name === 'login' && user) {
    return { name: 'portal' }
  }
  // 前端只负责隐藏错误入口；真正的权限边界由后端 require_admin 保证。
  if (to.meta.requiresAdmin) {
    if (user?.role !== 'admin') return { name: 'portal' }
  }

  const theme = to.meta.theme || 'learn'
  document.documentElement.setAttribute('data-theme', theme)
  if (to.meta.title) {
    document.title = `${to.meta.title} · 电力交易模拟系统`
  }
})

export default router
