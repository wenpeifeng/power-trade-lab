/**
 * 新手引导系统 —— 动态定位到具体功能元素
 *
 * 核心原则：每一步都高亮页面上真实的按钮/卡片，箭头指向它，
 * 告诉用户"这就是XX功能，点这里"。不是中间弹个说明书。
 *
 * 引导状态用 localStorage 记忆，不打扰老用户。
 */
import { driver } from 'driver.js'
import 'driver.js/dist/driver.css'
import './driver-dark.css'

const GUIDE_KEY = 'power_guide_done_v2'

export function isGuideDone(name) {
  try { return (JSON.parse(localStorage.getItem(GUIDE_KEY) || '{}'))[name] === true }
  catch { return false }
}
export function markGuideDone(name) {
  try {
    const d = JSON.parse(localStorage.getItem(GUIDE_KEY) || '{}')
    d[name] = true; localStorage.setItem(GUIDE_KEY, JSON.stringify(d))
  } catch {}
}
export function resetAllGuides() { localStorage.removeItem(GUIDE_KEY) }

const commonOpts = {
  showProgress: true,
  allowClose: true,
  nextBtnText: '下一步 →',
  prevBtnText: '← 上一步',
  doneBtnText: '完成 ✓',
}

// ============ 门户首页引导（定位到具体功能）============

export function startPortalGuide() {
  if (isGuideDone('portal')) return

  const d = driver({
    ...commonOpts,
    steps: [
      {
        // 定位到导航栏整体
        element: '.nav-bar',
        popover: {
          title: '欢迎来到电力交易中枢',
          description: '这是顶部导航栏，系统的所有功能都能从这里进入。下面我带你逐个认识。',
          side: 'bottom',
        },
      },
      {
        // 定位到"学习中心"导航项
        element: '.nav-menu .nav-item[href="/learn"], .nav-menu .nav-item:nth-child(1)',
        popover: {
          title: '📚 学习中心',
          description: '点这里进入学习：能力诊断、刷题练习、模拟考试。新手第一步推荐先做能力诊断。',
          side: 'bottom',
        },
      },
      {
        // 定位到"交易终端"导航项
        element: '.nav-menu .nav-item[href="/trade"], .nav-menu .nav-item:nth-child(2)',
        popover: {
          title: '📈 交易终端',
          description: '点这里模拟电力交易：看真实行情、报量报价、撮合成交、复盘分析。',
          side: 'bottom',
        },
      },
      {
        // 定位到新手任务区
        element: '.tasks-section',
        popover: {
          title: '🔰 新手任务清单',
          description: '这里有4个引导任务，完成一个打个勾。建议按顺序做完，快速上手系统。',
          side: 'top',
        },
      },
      {
        // 定位到学习模块卡片
        element: '.module-card.mc-learn',
        popover: {
          title: '从这里开始',
          description: '点这张卡片直接进入学习考试中心。系统会先帮你做个8题的能力诊断，判断你的起点。',
          side: 'top',
        },
      },
      {
        // 定位到交易模块卡片
        element: '.module-card.mc-trade',
        popover: {
          title: '学完来这练手',
          description: '点这里进入交易终端。用真实市场出清价做撮合，你报量报价，系统帮你成交。',
          side: 'top',
        },
      },
      {
        // 定位到用户头像（引导看右上角）
        element: '.user-chip',
        popover: {
          title: '随时找到我',
          description: '点你的头像可以：重新看引导、进入数据资产中心、退出登录。',
          side: 'bottom',
        },
      },
      {
        // 最后一步不定位元素，给总结
        popover: {
          title: '准备好了！',
          description: '右侧的 AI 助手随时可以问问题。\n\n建议现在就去点「学习中心」，做个能力诊断开始你的旅程。',
        },
      },
    ],
    onDestroyed: () => markGuideDone('portal'),
  })
  d.drive()
}

// ============ 学习中心引导 ============

export function startLearnGuide() {
  if (isGuideDone('learn')) return

  const d = driver({
    ...commonOpts,
    steps: [
      {
        popover: {
          title: '📚 学习中心',
          description: '这里是你学习电力交易的主阵地。让我带你认识核心功能。',
        },
      },
      {
        element: '.path-card.study-path',
        popover: {
          title: '🧭 分层学习',
          description: '点这里做能力诊断，系统会判断你是零基础/进阶/老手，然后推荐对应的学习路线。',
          side: 'bottom',
        },
      },
      {
        element: '.path-card.exam-path',
        popover: {
          title: '🎯 考试备考',
          description: '学完觉得自己行了？点这里模拟真实考试：90分钟计时，自动判分，还有薄弱点分析。',
          side: 'bottom',
        },
      },
    ],
    onDestroyed: () => markGuideDone('learn'),
  })
  d.drive()
}

// ============ 交易终端引导 ============

export function startTradeGuide() {
  if (isGuideDone('trade')) return

  const d = driver({
    ...commonOpts,
    steps: [
      {
        popover: {
          title: '📈 交易终端',
          description: '这是模拟电力交易的终端。让我带你认识界面布局和操作流程。',
        },
      },
      {
        // 定位到工具栏
        element: '.toolbar',
        popover: {
          title: '第一步：选品种和省份',
          description: '在这里选择：交易品种（日前/中长期）、省份（不同省份电价不同）、日期（可回看历史）。',
          side: 'bottom',
        },
      },
      {
        // 定位到左栏行情
        element: '.panel-left',
        popover: {
          title: '第二步：看懂行情',
          description: '左栏显示当前出清均价、最高价、最低价。不同省份价格差异很大。',
          side: 'right',
        },
      },
      {
        // 定位到中间图表
        element: '.panel-center',
        popover: {
          title: '中间：电价曲线',
          description: '一天96个点（每15分钟一个）的电价走势。能看到早晚两个用电高峰。',
          side: 'right',
        },
      },
      {
        // 定位到右栏申报
        element: '.panel-right',
        popover: {
          title: '第三步：在这里申报',
          description: '操作：选买入/卖出 → 填价格 → 填数量 → 点提交。\n\n技巧：报价高于出清价容易成交但成本高，低于出清价便宜但可能抢不到量。',
          side: 'left',
        },
      },
      {
        // 定位到复盘按钮
        element: '.review-btn',
        popover: {
          title: '最后：看复盘报告',
          description: '交易完成后点这里，系统分析你的报价策略，告诉你得失。',
          side: 'left',
        },
      },
    ],
    onDestroyed: () => markGuideDone('trade'),
  })
  d.drive()
}
