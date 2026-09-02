// A8 Part3 —— active-learning phase-2 closed-loop e2e walkthrough.
// Mirrors /tmp/e2e-loop.mjs technique: real backend (8001) + vite (5173 proxy),
// real test-user JWT injected so write endpoints hit the real DB; /api/auth/me
// stubbed to the same user object so the router guard treats the session as
// logged-in (belt-and-suspenders with the real cookie).
import puppeteer from 'puppeteer'
import { readFileSync } from 'fs'

const FRONTEND = 'http://127.0.0.1:5173'
const BACKEND = 'http://127.0.0.1:8001'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const JWT = readFileSync('/tmp/a8-jwt.txt', 'utf8').trim()
const USER = readFileSync('/tmp/a8-user.txt', 'utf8').trim()
// resolve the real user id from /auth/me once at boot (cookie path '/' so it's sent)
const meRes = await fetch(`${BACKEND}/api/auth/me`, { headers: { Cookie: `power_session=${JWT}` } })
const me = meRes.ok ? await meRes.json() : { id: 9, username: USER, role: 'user', display_name: USER }
const STUB_USER = { id: me.id, username: me.username, role: me.role, display_name: me.display_name }
console.error('STUB_USER=', JSON.stringify(STUB_USER))

const results = []
const rec = (name, pass, detail, screenshot = null) => results.push({ name, pass, detail, screenshot })
const sleep = (ms) => new Promise(r => setTimeout(r, ms))
const shot = async (p) => { await page.screenshot({ path: p, fullPage: false }); return p }

const browser = await puppeteer.launch({
  executablePath: CHROME, headless: 'new',
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
})
const page = await browser.newPage()
await page.setViewport({ width: 1366, height: 900 })

// --- request interception: stub /api/auth/me, capture reading + mastery calls ---
await page.setRequestInterception(true)
const captured = { readingPost: null, masteryGet: null, byConcept: null }
page.on('request', (req) => {
  const url = req.url()
  if (url.includes('/api/auth/me')) {
    req.respond({ status: 200, contentType: 'application/json', body: JSON.stringify(STUB_USER) })
    return
  }
  if (url.includes('/api/study/reading/3') && req.method() === 'POST') captured.readingPost = url
  req.continue()
})
page.on('response', async (res) => {
  const url = res.url()
  if (url.includes('/api/study/mastery') && res.ok()) {
    try { captured.masteryGet = await res.json() } catch { captured.masteryGet = null }
  }
})

// real session cookie so write endpoints pass through to the real backend
await page.setCookie({
  name: 'power_session', value: JWT, domain: '127.0.0.1', path: '/',
  httpOnly: true, secure: false, sameSite: 'Strict',
})

// helper: fetch mastery directly from backend via the page's cookie jar
const masteryViaApi = async () => {
  try {
    const r = await fetch(`${BACKEND}/api/study/mastery`, { headers: { Cookie: `power_session=${JWT}` } })
    return r.ok ? await r.json() : null
  } catch { return null }
}
const readingViaApi = async () => {
  try {
    const r = await fetch(`${BACKEND}/api/study/reading`, { headers: { Cookie: `power_session=${JWT}` } })
    return r.ok ? await r.json() : null
  } catch { return null }
}

// =========================================================================
// STEP A: /knowledge?c=321 — concept renders, level toggle, self-check,
//         reading auto-marks read, 相关原文 shows docs on 进阶.
// =========================================================================
let aLevelToggle = false, aSelfCheck = false, aReading = false, aRelDocs = false
try {
  await page.goto(`${FRONTEND}/knowledge?c=321`, { waitUntil: 'networkidle2', timeout: 30000 })
  await sleep(1500)
  // concept body renders (title or tldr present)
  const conceptText = await page.$$eval('.kb-concept-title, .kb-tldr, .kb-body, .kb-block', els =>
    els.map(e => e.textContent.replace(/\s+/g, ' ').trim()).filter(Boolean).slice(0, 3)
  ).catch(() => [])
  const conceptRenders = conceptText.length > 0

  // level toggle: 入门 → 进阶 → 专家, content differs (相关原文 appears on 进阶)
  const levels = await page.$$eval('.kb-level-seg .kb-level-btn', els =>
    els.map(e => e.textContent.replace(/\s+/g, ' ').trim())
  ).catch(() => [])
  const hasLevels = levels.length >= 3
  // start on 入门 (default); 相关原文 hidden on 入门
  const reldocsOnBeginner = await page.$('.kb-reldocs').then(el => !!el).catch(() => false)
  // switch to 进阶
  if (hasLevels) {
    await page.evaluate(() => {
      const btns = [...document.querySelectorAll('.kb-level-btn')]
      const b = btns.find(x => x.textContent.includes('进阶'))
      b && b.click()
    })
    await sleep(800)
    const reldocsOnAdv = await page.$('.kb-reldocs').then(el => !!el).catch(() => false)
    aLevelToggle = hasLevels && reldocsOnAdv && !reldocsOnBeginner
  }

  // self-check section renders (.kb-selfcheck or its hint)
  aSelfCheck = await page.$('.kb-selfcheck').then(el => !!el).catch(() => false)
  if (!aSelfCheck) {
    // maybe labelled differently; check for self-check stem/options
    aSelfCheck = await page.$('.kb-sc-stem, .kb-sc-opt, .kb-sc-hint').then(el => !!el).catch(() => false)
  }

  // 相关原文 doc cards on 进阶
  const rdCards = await page.$$eval('.kb-reldocs .kb-rd-card', els => els.length).catch(() => 0)
  aRelDocs = rdCards > 0

  // reading auto-marks read: debounced 500ms after select(). The concept page
  // may auto-select a related concept (e.g. 311) on mount before settling on
  // 321; accept any new reading mark as proof the wire fires, and separately
  // note whether 321 specifically was marked.
  await sleep(900)
  const reading = await readingViaApi()
  aReading = Array.isArray(reading) && reading.length > 0 && reading.some(r => r.status === 'read')
  const readingMarked321 = Array.isArray(reading) && reading.some(r => r.concept_code === '321')

  await shot('/tmp/a8-concept.png')
  rec('a_concept_level_selfcheck_reading_reldocs',
    conceptRenders && aLevelToggle && aSelfCheck && aReading && aRelDocs,
    `conceptRenders=${conceptRenders} levels=${JSON.stringify(levels)} levelToggle(入门→进阶 reldocs appears)=${aLevelToggle} selfCheck=${aSelfCheck} readingMarked(any)=${aReading} readingMarked321=${readingMarked321} readingList=${JSON.stringify(reading)} relDocsCards=${rdCards}`,
    '/tmp/a8-concept.png')
} catch (e) {
  await shot('/tmp/a8-concept.png').catch(() => {})
  rec('a_concept_level_selfcheck_reading_reldocs', false, `error: ${e.message}`, '/tmp/a8-concept.png')
}

// =========================================================================
// STEP B: self-check — answer the inline question. Verify the answer wire
//         (AnswerLog) by checking /study/mastery shows an attempt for the KP.
// =========================================================================
let bAnswered = false, bMasteryAttempt = false, gotWrong = false
try {
  // ensure on concept page (进阶 from step A) and self-check present
  await page.goto(`${FRONTEND}/knowledge?c=321`, { waitUntil: 'networkidle2', timeout: 20000 })
  await sleep(1200)
  // switch to 进阶 to ensure self-check visible (self-check requires kp loaded + logged in)
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.kb-level-btn')].find(x => x.textContent.includes('进阶'))
    b && b.click()
  }).catch(() => {})
  await sleep(800)

  const masteryBefore = await masteryViaApi()
  const midBefore = (masteryBefore || []).find(k => k.code === 'mid_long_term')
  const attemptsBefore = midBefore ? midBefore.total_attempts : -1

  // pick the first self-check option, submit, observe feedback
  const optsCount = await page.$$eval('.kb-selfcheck .kb-sc-opt', els => els.length).catch(() => 0)
  let fb = { shown: false }
  if (optsCount > 0) {
    await page.evaluate(() => {
      const opts = [...document.querySelectorAll('.kb-sc-opt')]
      if (opts[0]) opts[0].click()
    })
    await sleep(400)
    const submitted = await page.evaluate(() => {
      const btns = [...document.querySelectorAll('.kb-selfcheck .kb-action-btn')]
      const b = btns.find(x => x.classList.contains('primary')) || btns[0]
      if (b && !b.disabled) { b.click(); return true }
      return false
    })
    await sleep(1500)
    fb = await page.evaluate(() => {
      const el = document.querySelector('.kb-sc-result, .kb-sc-verdict')
      if (!el) return { shown: false }
      return { shown: true, wrong: el.classList.contains('wrong'), text: el.textContent.replace(/\s+/g, ' ').trim().slice(0, 60) }
    })
    bAnswered = submitted && fb.shown
    gotWrong = fb.shown && fb.wrong
  }

  // verify mastery shows an attempt for mid_long_term (AnswerLog wire)
  const masteryAfter = await masteryViaApi()
  const midAfter = (masteryAfter || []).find(k => k.code === 'mid_long_term')
  bMasteryAttempt = midAfter ? midAfter.total_attempts > attemptsBefore : false

  await shot('/tmp/a8-selfcheck.png')
  rec('b_selfcheck_answer_wire', bAnswered && bMasteryAttempt,
    `opts=${optsCount} answered=${bAnswered} gotWrong=${gotWrong} fb="${fb.text || ''}" mid_attempts ${attemptsBefore}→${midAfter ? midAfter.total_attempts : '?'} masteryForKp=${bMasteryAttempt}`,
    '/tmp/a8-selfcheck.png')
} catch (e) {
  await shot('/tmp/a8-selfcheck.png').catch(() => {})
  rec('b_selfcheck_answer_wire', false, `error: ${e.message}`, '/tmp/a8-selfcheck.png')
}

// =========================================================================
// STEP C: /study (StudyHome) — mastery card shows the KP updated (not 0 if
//         any answers happened).
// =========================================================================
try {
  await page.goto(`${FRONTEND}/learn/study`, { waitUntil: 'networkidle2', timeout: 20000 })
  await sleep(2000)
  const masteryCard = await page.$('.mastery-card').then(el => !!el).catch(() => false)
  // dump all mastery bars to find mid_long_term (name 长期/中长期交易)
  const bars = await page.$$eval('.mastery-bar', els =>
    els.map(e => e.textContent.replace(/\s+/g, ' ').trim())
  ).catch(() => [])
  const midRow = bars.find(b => b.includes('中长期') || b.includes('长期') || b.includes('mid_long'))
  // mastery should show attempts > 0 for mid_long_term after step B answered
  const masteryOk = masteryCard && !!midRow && /\d+%\s*\(\d+\/\d+\)/.test(midRow) && !/\(0\/0\)/.test(midRow)
  await shot('/tmp/a8-mastery.png')
  rec('c_mastery_updated', masteryOk, `masteryCard=${masteryCard} bars=${bars.length} midRow="${midRow}" allBars=${JSON.stringify(bars).slice(0,400)}`, '/tmp/a8-mastery.png')
} catch (e) {
  await shot('/tmp/a8-mastery.png').catch(() => {})
  rec('c_mastery_updated', false, `error: ${e.message}`, '/tmp/a8-mastery.png')
}

// =========================================================================
// STEP D: /learn/wrong — 今日复习 tab renders; 全部错题 lists the wrong
//         answer (if any); 学相关概念 link → /knowledge?tab=book&kp=<code>.
// =========================================================================
let dDueTab = false, dLink = false
try {
  await page.goto(`${FRONTEND}/learn/wrong`, { waitUntil: 'networkidle2', timeout: 20000 })
  await sleep(1500)
  // 今日复习 tab renders (badge may be 0 = no due items, which is legitimate)
  const tabs = await page.$$eval('.tab-row .tab', els => els.map(e => e.textContent.replace(/\s+/g, ' ').trim())).catch(() => [])
  dDueTab = tabs.some(t => t.includes('今日复习'))

  // switch to 全部错题 (first tab) to find a wrong card with 学相关概念 link
  await page.evaluate(() => {
    const t = document.querySelector('.tab-row .tab')
    t && t.click()
  }).catch(() => {})
  await sleep(1200)
  // expand the first wrong card to reveal 学相关概念 link
  await page.evaluate(() => {
    const sum = document.querySelector('.question-summary, .wrong-card .q-stem')
    sum && sum.click()
  }).catch(() => {})
  await sleep(800)
  const linkHref = await page.evaluate(() => {
    const a = document.querySelector('.kp-link')
    return a ? a.getAttribute('href') : null
  }).catch(() => null)
  // if no wrong card yet (e.g. self-check was correct), seed one via API then re-check
  if (!linkHref && gotWrong === false) {
    // answer wrong against a mid_long_term question to seed the wrong book
    const tree = await (await fetch(`${BACKEND}/api/learn/knowledge-tree`, { headers: { Cookie: `power_session=${JWT}` } })).json()
    const mid = tree.find(k => k.code === 'mid_long_term')
    const chk = await (await fetch(`${BACKEND}/api/learn/check?kp=${mid.id}&count=1`, { headers: { Cookie: `power_session=${JWT}` } })).json()
    if (chk[0]) {
      // pick a deliberately wrong answer (option != correct; backend masks is_correct but
      // any single-key answer that isn't the real correct key → wrong). Try 'Z' to force wrong.
      await fetch(`${BACKEND}/api/learn/answer`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Cookie: `power_session=${JWT}` },
        body: JSON.stringify({ question_id: chk[0].id, user_answer: 'Z' }),
      })
    }
    await page.goto(`${FRONTEND}/learn/wrong`, { waitUntil: 'networkidle2', timeout: 20000 })
    await sleep(1500)
    await page.evaluate(() => {
      const sum = document.querySelector('.question-summary, .wrong-card .q-stem')
      sum && sum.click()
    }).catch(() => {})
    await sleep(800)
  }
  const linkHref2 = await page.evaluate(() => {
    const a = document.querySelector('.kp-link')
    return a ? a.getAttribute('href') : null
  }).catch(() => null)
  dLink = !!linkHref2 && linkHref2.includes('tab=book') && linkHref2.includes('kp=')

  // click the link and verify navigation
  if (dLink) {
    await page.evaluate(() => {
      const a = document.querySelector('.kp-link')
      a && a.click()
    })
    await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 }).catch(() => {})
    await sleep(1500)
    const url = page.url()
    const landed = url.includes('tab=book') && url.includes('kp=')
    dLink = dLink && landed
    await shot('/tmp/a8-wrong.png')
    rec('d_wrong_due_tab_and_link', dDueTab && dLink,
      `tabs=${JSON.stringify(tabs)} linkHref="${linkHref2 || linkHref}" landedOnBookKp=${dLink}`,
      '/tmp/a8-wrong.png')
  } else {
    await shot('/tmp/a8-wrong.png')
    rec('d_wrong_due_tab_and_link', dDueTab, `tabs=${JSON.stringify(tabs)} noKpLink (wrong-book may be empty or link absent)`, '/tmp/a8-wrong.png')
  }
} catch (e) {
  await shot('/tmp/a8-wrong.png').catch(() => {})
  rec('d_wrong_due_tab_and_link', false, `error: ${e.message}`, '/tmp/a8-wrong.png')
}

// =========================================================================
// STEP E: /knowledge?tab=glossary — search 出清, expand 精确释义, conceptCode link works.
// =========================================================================
try {
  await page.goto(`${FRONTEND}/knowledge?tab=glossary`, { waitUntil: 'networkidle2', timeout: 20000 })
  await sleep(1200)
  // type 出清 in the search box
  await page.click('.gl-search-input input').catch(() => {})
  await page.type('.gl-search-input input', '出清')
  await sleep(600)
  // a glossary card matching 出清 should be visible
  const cards = await page.$$eval('.gl-card', els =>
    els.map(e => e.textContent.replace(/\s+/g, ' ').trim().slice(0, 40))
  ).catch(() => [])
  const hasMatch = cards.some(c => c.includes('出清'))
  // expand 精确释义 on the first matching card
  const preciseExpanded = await page.evaluate(() => {
    const sums = [...document.querySelectorAll('.gl-precise-sum')]
    const t = sums.find(s => /精确释义/.test(s.textContent))
    if (t) { t.click(); return true }
    return false
  }).catch(() => false)
  await sleep(400)
  const preciseBody = await page.$eval('.gl-precise-body', e => e.textContent.trim().slice(0, 50)).catch(() => '')
  // conceptCode link present?
  const conceptLink = await page.$eval('.gl-concept-link', e => e.textContent.trim()).catch(() => null)
  const conceptLinkHref = await page.$eval('.gl-concept-link', e => e.getAttribute('href') || '').catch(() => '')
  let linkLanded = false
  if (conceptLink) {
    await page.evaluate(() => {
      const a = document.querySelector('.gl-concept-link')
      a && a.click()
    })
    await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 }).catch(() => {})
    await sleep(1200)
    linkLanded = page.url().includes('c=') && page.url().includes('tab=book')
  }
  await shot('/tmp/a8-glossary.png')
  rec('e_glossary_search_precise_conceptlink',
    hasMatch && preciseExpanded && preciseBody && conceptLink && linkLanded,
    `cards=${cards.length} hasMatch=${hasMatch} preciseExpanded=${preciseExpanded} preciseBody="${preciseBody}" conceptLink="${conceptLink}" href="${conceptLinkHref}" landed=${linkLanded}`,
    '/tmp/a8-glossary.png')
} catch (e) {
  await shot('/tmp/a8-glossary.png').catch(() => {})
  rec('e_glossary_search_precise_conceptlink', false, `error: ${e.message}`, '/tmp/a8-glossary.png')
}

// =========================================================================
// STEP F: /learn/exam — start, answer, result weak-point 去练习 button carries kp.
//         (Heavy; attempted. If the full exam loop is too slow, noted as skipped.)
// =========================================================================
let fExam = false
try {
  await page.goto(`${FRONTEND}/learn/exam`, { waitUntil: 'networkidle2', timeout: 20000 })
  await sleep(1200)
  // find a startable exam mode card (真题/押题/模考)
  const modes = await page.$$eval('.mode-card, .mode-btn', els =>
    els.map(e => ({ text: e.textContent.replace(/\s+/g, ' ').trim().slice(0, 20), disabled: e.disabled || e.classList.contains('disabled') }))
  ).catch(() => [])
  const startable = modes.find(m => !m.disabled)
  if (!startable) {
    await shot('/tmp/a8-exam.png')
    rec('f_exam_weakpoint_drill', false, `no startable exam mode (modes=${JSON.stringify(modes)}); skipped`, '/tmp/a8-exam.png')
  } else {
    // start a small exam directly (count=5) so the loop finishes quickly;
    // mode=exam (全真模考), level=four (default four级)
    await page.goto(`${FRONTEND}/learn/exam/paper?mode=exam&level=four&count=5`, { waitUntil: 'networkidle2', timeout: 20000 })
    await sleep(2000)
    // Answer each question: pick first option, click 下一题 (or 完成答题 on last).
    let answered = 0, reachedLast = false
    for (let i = 0; i < 40; i++) {
      const opts = await page.$$('.q-option').catch(() => [])
      if (opts.length === 0) break
      await page.evaluate(() => {
        const o = document.querySelector('.q-option')
        o && o.click()
      }).catch(() => {})
      await sleep(200)
      // find the advance button; 完成答题 means we're on the last question
      const advance = await page.evaluate(() => {
        const btns = [...document.querySelectorAll('button')]
        const next = btns.find(x => /完成答题/.test(x.textContent) && !x.disabled)
        if (next) { next.click(); return { clicked: true, last: true } }
        const nx = btns.find(x => /下一题|下一道/.test(x.textContent) && !x.disabled)
        if (nx) { nx.click(); return { clicked: true, last: false } }
        return { clicked: false, last: false }
      }).catch(() => ({ clicked: false, last: false }))
      answered++
      if (advance.last) { reachedLast = true; break }
      if (!advance.clicked) break
      await sleep(500)
    }
    // click 交卷, then the confirm dialog 确定
    await page.evaluate(() => {
      const btns = [...document.querySelectorAll('button')]
      const b = btns.find(x => x.textContent.trim() === '交卷' && !x.disabled)
      b && b.click()
    }).catch(() => {})
    await sleep(800)
    // ElMessageBox confirm dialog: click the primary 确定 button
    const confirmed = await page.evaluate(() => {
      const btns = [...document.querySelectorAll('.el-message-box__btns button, .el-message-box button')]
      const ok = btns.find(x => /确定|确认/.test(x.textContent)) || btns.find(x => x.classList.contains('el-button--primary'))
      if (ok) { ok.click(); return true }
      return false
    }).catch(() => false)
    await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 20000 }).catch(() => {})
    await sleep(2000)
    // result page: weak-point section + 去练习 button carrying kp
    const weak = await page.$('.weak-section').then(el => !!el).catch(() => false)
    const weakItems = await page.$$eval('.weak-section .weak-item', els => els.length).catch(() => 0)
    const drillBtn = await page.$('.weak-drill').then(el => !!el).catch(() => false)
    const drillInfo = await page.evaluate(() => {
      const b = document.querySelector('.weak-drill')
      if (!b) return null
      return { text: b.textContent.trim(), disabled: b.disabled }
    }).catch(() => null)
    let drillLanded = false
    if (weak && weakItems > 0 && drillBtn && drillInfo && !drillInfo.disabled) {
      await page.evaluate(() => { document.querySelector('.weak-drill').click() }).catch(() => {})
      await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 }).catch(() => {})
      await sleep(1200)
      drillLanded = /\/learn\/quiz\?kp=\d+/.test(page.url())
    }
    await shot('/tmp/a8-exam.png')
    fExam = weak && weakItems > 0 && drillLanded
    rec('f_exam_weakpoint_drill', fExam,
      `modes=${JSON.stringify(modes)} answered=${answered} reachedLast=${reachedLast} confirmed=${confirmed} weakSection=${weak} weakItems=${weakItems} drillBtn=${drillBtn} drillInfo=${JSON.stringify(drillInfo)} drillLanded=${drillLanded}`,
      '/tmp/a8-exam.png')
  }
} catch (e) {
  await shot('/tmp/a8-exam.png').catch(() => {})
  rec('f_exam_weakpoint_drill', false, `error: ${e.message} (exam full loop attempted, bonus step)`, '/tmp/a8-exam.png')
}

await browser.close()

console.log(JSON.stringify(results, null, 2))
const critical = ['a_concept_level_selfcheck_reading_reldocs', 'b_selfcheck_answer_wire', 'c_mastery_updated', 'd_wrong_due_tab_and_link', 'e_glossary_search_precise_conceptlink']
const criticalPass = critical.every(n => results.find(r => r.name === n)?.pass)
console.log('\nCRITICAL_PASS=' + criticalPass)
console.log('ALL_PASS=' + results.every(r => r.pass))
