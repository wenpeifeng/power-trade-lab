<template>
  <div class="kb-book">
    <!-- ============ 左栏：章节树 ============ -->
    <aside class="kb-tree" :class="{ open: drawerOpen }">
      <div class="kb-tree-head"><FolderTree :size="14" /> 章节导航</div>
      <el-input
        v-model="filter" placeholder="搜索章节/概念…" size="small" clearable
        class="kb-tree-filter"
      />
      <!-- ?kp 筛选退出 chip -->
      <div v-if="kpFilterCode" class="kb-kpfilter-chip" @click="clearKpFilter">
        <span>仅看知识点 {{ kpFilterCode }}</span>
        <span class="kb-kpfilter-x">×</span>
      </div>
      <div class="kb-tree-list">
        <template v-for="ch in CURRICULUM" :key="ch.code">
          <div
            v-if="conceptFilterActive ? chapterHasKpHit(ch) : (!filter || ch.title.includes(filter) || chapterHasHit(ch))"
            class="kb-ch"
            :class="{ open: openChs.has(ch.code) }"
            @click="toggleCh(ch.code)"
          >
            <ChevronRight :size="13" class="kb-ch-chev" />
            <span class="kb-ch-code">{{ ch.code }}</span>
            <span class="kb-ch-title">{{ ch.title }}</span>
            <span
              v-if="readingEnabled && chapterProgress(ch).total"
              class="kb-ch-prog"
              :title="`已读 ${chapterProgress(ch).read}/${chapterProgress(ch).total}`"
            >
              <span class="kb-ch-prog-bar">
                <span
                  class="kb-ch-prog-fill"
                  :style="{ width: chapterProgressPct(ch) + '%' }"
                />
              </span>
              <span class="kb-ch-prog-num">{{ chapterProgress(ch).read }}/{{ chapterProgress(ch).total }}</span>
            </span>
          </div>
          <div
            v-show="openChs.has(ch.code) && (conceptFilterActive ? chapterHasKpHit(ch) : (!filter || chapterHasHit(ch)))"
            class="kb-sec-list"
          >
            <div v-for="sec in visibleSections(ch)" :key="sec.code" class="kb-sec">
              <div class="kb-sec-title">{{ sec.title }}</div>
              <div
                v-for="c in visibleConcepts(sec)" :key="c.code"
                class="kb-concept"
                :class="{
                  active: current === c.code,
                  'is-read': readingStatus(c.code) === 'read',
                  'is-understood': readingStatus(c.code) === 'understood',
                }"
                @click="select(c.code)"
              >
                <span
                  v-if="readingEnabled && readingStatus(c.code)"
                  class="kb-concept-mark"
                  :class="{ solid: readingStatus(c.code) === 'understood' }"
                >{{ readingStatus(c.code) === 'understood' ? '✓' : '·' }}</span>
                <span class="kb-concept-title">{{ c.title }}</span>
                <span
                  v-if="masteryEnabled && masteryPctForKp(c.kp) !== null"
                  class="kb-mastery-chip"
                  :class="masteryClass(masteryPctForKp(c.kp))"
                >{{ masteryPctForKp(c.kp) }}%</span>
              </div>
            </div>
          </div>
        </template>
        <div v-if="(filter || conceptFilterActive) && !anyHit" class="kb-tree-empty">无匹配章节</div>
      </div>
    </aside>

    <!-- 移动端遮罩 -->
    <div v-if="drawerOpen" class="kb-drawer-mask" @click="drawerOpen = false"></div>

    <!-- ============ 主阅读区 ============ -->
    <main class="kb-reader">
      <!-- 移动端目录开关 -->
      <button class="kb-tree-toggle" @click="drawerOpen = true">
        <FolderTree :size="14" /> 目录
      </button>

      <!-- 学习路线卡（无选中概念时首屏） -->
      <!-- 注意分支依据是 current 而非 cur：
           current 有值但 cur 解析不到（如 ?c=junk）时应进兜底面板，
           而非学习路线卡。 -->
      <section v-if="!current" class="kb-path-card">
        <header class="kpc-intro">
          <div class="kpc-head"><Sparkles :size="14" /> 推荐学习路径</div>
          <h1>先建立全景，再进入交易机制</h1>
          <p class="kpc-sub">章节是知识边界，下面的概念才是可阅读入口。建议按章推进，也可以从左侧目录直接定位。</p>
        </header>
        <div class="kpc-stages">
          <section v-for="(group, groupIndex) in learningPathGroups" :key="group.code" class="kpc-stage">
            <header class="kpc-stage-head">
              <span class="kpc-stage-no">{{ String(groupIndex + 1).padStart(2, '0') }}</span>
              <div>
                <span class="kpc-stage-kicker">第 {{ group.code }} 章</span>
                <h2>{{ group.title }}</h2>
              </div>
              <span class="kpc-stage-count">{{ group.concepts.length }} 节</span>
            </header>
            <div class="kpc-concepts">
              <button
                v-for="(item, itemIndex) in group.concepts" :key="item.code"
                class="kpc-concept-link"
                @click="select(item.code)"
              >
                <span class="kpc-concept-no">{{ String(itemIndex + 1).padStart(2, '0') }}</span>
                <span>{{ item.title }}</span>
                <ChevronRight :size="14" />
              </button>
            </div>
          </section>
        </div>
      </section>

      <!-- 概念正文 -->
      <article v-else-if="cur" class="kb-article">
        <div class="kb-bc">
          <button class="kb-bc-link" @click="clearCurrent">知识库</button>
          <span class="kb-bc-sep">/</span>
          <span>{{ conceptPath(current).chapter }}</span>
          <span class="kb-bc-sep">/</span>
          <span>{{ conceptPath(current).section }}</span>
          <span class="kb-bc-sep">/</span>
          <span class="kb-bc-current">{{ cur.title }}</span>
        </div>

        <h2 class="kb-title">{{ cur.title }}</h2>

        <!-- 难度视图切换：入门 / 进阶 / 专家 -->
        <div class="kb-level">
          <div class="kb-level-seg" role="tablist" aria-label="难度视图">
            <button
              v-for="item in LEVEL_META" :key="item.name"
              class="kb-level-btn"
              :class="{ active: level === item.name }"
              role="tab"
              :aria-selected="level === item.name"
              @click="setLevel(item.name)"
            ><strong>{{ item.name }}</strong><small>{{ item.short }}</small></button>
          </div>
          <div class="kb-level-hint"><strong>本层重点</strong>{{ activeLevelMeta.description }}</div>
        </div>

        <!-- 状态条：阅读进度 + 我懂了 + 掌握度迷你条 -->
        <div v-if="readingEnabled || masteryEnabled" class="kb-status-bar">
          <span
            v-if="readingEnabled && readingStatus(current) === 'read'"
            class="kb-rd-badge read"
          >已读</span>
          <span
            v-else-if="readingEnabled && readingStatus(current) === 'understood'"
            class="kb-rd-badge understood"
          >已掌握</span>
          <button
            v-if="readingEnabled && readingStatus(current) !== 'understood'"
            class="kb-action-btn small"
            :disabled="rdMarking"
            @click="markUnderstood"
          >
            <CheckCircle2 :size="14" /> 我懂了
          </button>
          <span
            v-if="masteryEnabled && masteryPctForCur !== null"
            class="kb-mastery-mini"
            :class="masteryClass(masteryPctForCur)"
            :title="`该知识点掌握度 ${masteryPctForCur}%`"
          >
            <span class="kb-mastery-mini-bar">
              <span class="kb-mastery-mini-fill" :style="{ width: masteryPctForCur + '%' }" />
            </span>
            <span class="kb-mastery-mini-num">掌握 {{ masteryPctForCur }}%</span>
          </span>
        </div>

        <div class="kb-tldr">
          <span class="kb-block-label"><Lightbulb :size="14" /> 一句话懂了</span>
          <p>{{ cur.tldr }}</p>
        </div>

        <div v-if="cur.analogy" class="kb-analogy">
          <span class="kb-block-label"><Coffee :size="14" /> 生活类比</span>
          <p>{{ cur.analogy }}</p>
        </div>

        <div v-if="cur.prereq && cur.prereq.length" class="kb-prereq">
          <span class="kb-block-label"><GitBranch :size="14" /> 先懂这些</span>
          <div class="kb-chips">
            <button
              v-for="p in cur.prereq" :key="p"
              class="kb-chip"
              :disabled="!isConceptCode(p)"
              @click="select(p)"
            >{{ resolveTitle(p) }}<ChevronRight v-if="isConceptCode(p)" :size="12" /></button>
          </div>
        </div>

        <!-- 专家层先呈现新增内容，不让用户翻到末尾才发现差异。 -->
        <section v-if="level === '专家' && cur.deepDive" class="kb-deepdive">
          <div class="kb-block-label"><Microscope :size="14" /> 专家层新增：公式、依据与边界</div>
          <div v-if="cur.deepDive.formula" class="kb-dd-item">
            <span class="kb-dd-label">公式与算法</span>
            <p v-html="inlineHtml(cur.deepDive.formula)"></p>
          </div>
          <div v-if="cur.deepDive.policyCite" class="kb-dd-item">
            <span class="kb-dd-label">规则与依据</span>
            <p v-if="Array.isArray(cur.deepDive.policyCite)">
              <span v-for="(c, i) in cur.deepDive.policyCite" :key="i">{{ c }}<br v-if="i < cur.deepDive.policyCite.length - 1" /></span>
            </p>
            <p v-else>{{ cur.deepDive.policyCite }}</p>
          </div>
          <div v-if="cur.deepDive.sourceLinks?.length" class="kb-dd-item">
            <span class="kb-dd-label">可核验来源</span>
            <div class="kb-source-links">
              <a v-for="source in cur.deepDive.sourceLinks" :key="source.url" :href="source.url" target="_blank" rel="noopener noreferrer">
                <span>{{ source.title }}</span><ArrowUpRight :size="13" />
              </a>
            </div>
          </div>
          <div v-if="cur.deepDive.edgeCases && cur.deepDive.edgeCases.length" class="kb-dd-item">
            <span class="kb-dd-label">边界情形</span>
            <ul class="kb-dd-list">
              <li v-for="(e, i) in cur.deepDive.edgeCases" :key="i" v-html="inlineHtml(e)"></li>
            </ul>
          </div>
          <div v-if="cur.deepDive.crossProvince" class="kb-dd-item">
            <span class="kb-dd-label">适用范围</span>
            <p>{{ cur.deepDive.crossProvince }}</p>
          </div>
        </section>
        <section v-else-if="level === '专家'" class="kb-deepdive kb-deepdive-empty">
          <div class="kb-block-label"><Microscope :size="14" /> 专家层尚待校准</div>
          <p>该词条目前只有进阶内容，尚未补齐可核验的公式、规则依据与适用边界，因此不重复扩写。你仍可查看下方的进阶内容。</p>
        </section>

        <div v-if="fieldAt('进阶')" class="kb-def">
          <span class="kb-block-label"><BookOpen :size="14" /> 定义</span>
          <p v-html="inlineHtml(cur.definition)"></p>
        </div>

        <div v-if="cur.keyPoints && cur.keyPoints.length" class="kb-kp">
          <span class="kb-block-label"><ListChecks :size="14" /> 要点</span>
          <ul class="kb-kp-list">
            <li v-for="(k, i) in cur.keyPoints" :key="i" v-html="inlineHtml(k)"></li>
          </ul>
        </div>

        <!-- 对比表：动态列（a/b 或 a/b/c） -->
        <div v-if="fieldAt('进阶') && cur.compare && cur.compare.length" class="kb-cmp-wrap">
          <span class="kb-block-label"><Columns3 :size="14" /> 易混对比</span>
          <div class="kb-cmp-scroll">
            <table class="kb-cmp">
              <thead>
                <tr>
                  <th>维度</th>
                  <th v-for="key in cmpKeys" :key="key">{{ cmpHeader(key) }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, i) in cur.compare" :key="i">
                  <td class="kb-cmp-dim">{{ row.dim }}</td>
                  <td v-for="key in cmpKeys" :key="key" v-html="inlineHtml(cmpCell(row, key))"></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- 💡 实例 -->
        <div v-if="cur.example" class="kb-example">
          <span class="kb-block-label"><Lightbulb :size="14" /> 💡 实例</span>
          <p v-html="inlineHtml(cur.example)"></p>
        </div>

        <!-- 🪜 怎么运转 -->
        <div v-if="fieldAt('进阶') && cur.walkthrough" class="kb-walk">
          <span class="kb-block-label"><GitBranch :size="14" /> 🪜 怎么运转</span>
          <p v-html="inlineHtml(cur.walkthrough)"></p>
        </div>

        <!-- ⚠️ 易踩的坑 -->
        <div v-if="fieldAt('进阶') && cur.pitfalls && cur.pitfalls.length" class="kb-pitfalls">
          <span class="kb-block-label"><AlertTriangle :size="14" /> ⚠️ 易踩的坑</span>
          <ul class="kb-pitfalls-list">
            <li v-for="(p, i) in cur.pitfalls" :key="i" v-html="inlineHtml(p)"></li>
          </ul>
        </div>

        <!-- ❓ 常见疑问 -->
        <div v-if="fieldAt('进阶') && cur.faq && cur.faq.length" class="kb-faq">
          <span class="kb-block-label"><HelpCircle :size="14" /> ❓ 常见疑问</span>
          <div class="kb-faq-list">
            <details v-for="(item, i) in cur.faq" :key="i" class="kb-faq-item">
              <summary class="kb-faq-q">{{ item.q }}</summary>
              <p class="kb-faq-a">{{ item.a }}</p>
            </details>
          </div>
        </div>

        <div v-if="fieldAt('进阶') && cur.link2sim" class="kb-sim">
          <span class="kb-block-label"><MonitorPlay :size="14" /> 对应仿真</span>
          <p>{{ cur.link2sim }}</p>
        </div>

        <!-- ============ 本节自检 ============ -->
        <section v-if="showSelfCheck" class="kb-selfcheck">
          <div class="kb-block-label"><BrainCircuit :size="14" /> 本节自检</div>
          <div v-if="scLoading" class="kb-sc-hint">出题中…</div>
          <div v-else-if="scQuestion" class="kb-sc-body">
            <div class="kb-sc-stem">{{ scQuestion.stem }}</div>
            <div class="kb-sc-options">
              <label
                v-for="opt in scQuestion.options" :key="opt.key"
                class="kb-sc-opt"
                :class="scOptClass(opt.key)"
              >
                <input
                  v-if="scIsMultiple"
                  type="checkbox"
                  :checked="scSelectedArr.includes(opt.key)"
                  :disabled="scAnswered"
                  @change="toggleMulti(opt.key)"
                />
                <input
                  v-else
                  type="radio"
                  name="kb-sc"
                  :value="opt.key"
                  v-model="scSelectedStr"
                  :disabled="scAnswered"
                />
                <span class="kb-sc-key">{{ opt.key }}</span>
                <span class="kb-sc-text">{{ opt.text }}</span>
              </label>
            </div>
            <transition name="fade">
              <div v-if="scResult" class="kb-sc-result" :class="{ correct: scResult.correct, wrong: !scResult.correct }">
                <div class="kb-sc-result-head">
                  <span class="kb-sc-verdict">{{ scResult.correct ? '答对了' : '答错了' }}</span>
                  <span class="kb-sc-answer">正确答案：{{ scResult.correct_answer }}</span>
                </div>
                <div v-if="scResult.analysis" class="kb-sc-analysis">{{ scResult.analysis }}</div>
              </div>
            </transition>
            <div class="kb-sc-actions">
              <button
                v-if="!scAnswered"
                class="kb-action-btn primary"
                :disabled="!scCanSubmit || scSubmitting"
                @click="submitSelfCheck"
              >
                <ClipboardCheck :size="14" /> {{ scSubmitting ? '提交中…' : '提交' }}
              </button>
              <button class="kb-action-btn" :disabled="scLoading" @click="fetchSelfCheck">
                <RefreshCw :size="14" /> 换一道
              </button>
              <button class="kb-action-btn" @click="goQuiz">
                <ClipboardPen :size="14" /> 去完整刷题
              </button>
            </div>
          </div>
          <div v-else class="kb-sc-hint">本知识点暂无自检题，<a class="kb-sc-link" @click="goQuiz">去刷题</a></div>
        </section>

        <div v-if="cur.related && cur.related.length" class="kb-rel">
          <span class="kb-block-label"><Link2 :size="14" /> 相关概念</span>
          <div class="kb-chips">
            <button
              v-for="r in cur.related" :key="r"
              class="kb-chip"
              :disabled="!isConceptCode(r)"
              @click="select(r)"
            >{{ resolveTitle(r) }}<ChevronRight v-if="isConceptCode(r)" :size="12" /></button>
          </div>
        </div>

        <!-- 📄 相关原文（进阶/专家级溯源；入门隐藏；空结果隐藏） -->
        <section v-if="fieldAt('进阶') && relDocsVisible" class="kb-reldocs">
          <div class="kb-block-label"><FileText :size="14" /> 📄 相关原文</div>
          <div v-if="relDocsLoading" class="kb-rd-hint">检索原文中…</div>
          <div v-else class="kb-rd-list">
            <a
              v-for="d in relDocs" :key="d.id"
              class="kb-rd-card"
              :href="docSrcUrl(d)"
              target="_blank" rel="noopener noreferrer"
            >
              <div class="kb-rd-head">
                <span class="kb-rd-title">{{ d.title }}</span>
                <span v-if="d.doc_type" class="kb-rd-type">{{ d.doc_type }}</span>
              </div>
              <div class="kb-rd-meta">
                <span v-if="d.source">{{ d.source }}</span>
                <span v-if="d.publish_date" class="kb-rd-sep">·</span>
                <span v-if="d.publish_date">{{ d.publish_date }}</span>
              </div>
              <p v-if="d.ai_summary" class="kb-rd-sum">{{ truncate(d.ai_summary, 80) }}</p>
              <span class="kb-rd-link">查看原文</span>
            </a>
          </div>
        </section>

        <!-- 出站动作：练本节 / 看真实原文 / 去仿真 —— 依据 kp / scenario 条件渲染 -->
        <div
          v-if="cur && (cur.kp || cur.scenario)"
          class="kb-actions"
        >
          <template v-if="cur.kp">
            <button
              class="kb-action-btn primary"
              :disabled="!kpIdReady"
              :title="kpIdReady ? '跳转到本知识点的刷题' : '知识点映射加载中/未配置'"
              @click="goQuiz"
            >
              <ClipboardPen :size="14" /> 练本节
            </button>
            <button
              class="kb-action-btn"
              :title="`查看 ${cur.kp} 知识点的真实原文`"
              @click="goFeed"
            >
              <FileText :size="14" /> 看真实原文
            </button>
          </template>
          <button
            v-if="cur.scenario"
            class="kb-action-btn accent"
            :title="`进入 ${cur.scenario} 市场仿真`"
            @click="goSim"
          >
            <MonitorPlay :size="14" /> 去仿真
          </button>
        </div>

        <div class="kb-nav">
          <button class="kb-nav-btn" :disabled="!hasPrev" @click="goPrev">
            <ChevronLeft :size="14" /> 上一节
          </button>
          <span class="kb-nav-pos">{{ flatOrder.indexOf(current) + 1 }} / {{ flatOrder.length }}</span>
          <button class="kb-nav-btn" :disabled="!hasNext" @click="goNext">
            下一节 <ChevronRight :size="14" />
          </button>
        </div>
      </article>

      <!-- 兜底：current 有值但解析不到概念 -->
      <div v-else class="kb-fallback">
        <Inbox :size="40" />
        <p>未找到概念「{{ current }}」</p>
        <button class="kb-nav-btn" @click="clearCurrent">返回学习路线</button>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  FolderTree, Sparkles, ChevronRight, ChevronLeft, Lightbulb, Coffee,
  GitBranch, BookOpen, ListChecks, Columns3, MonitorPlay, Link2, Inbox,
  ClipboardPen, FileText, CheckCircle2, BrainCircuit, ClipboardCheck, RefreshCw,
  AlertTriangle, HelpCircle, Microscope, ArrowUpRight,
} from 'lucide-vue-next'
import { CURRICULUM, LEARNING_PATH } from '../../knowledge/curriculum'
import { inlineHtml } from '../../utils/markdown'
import { learnApi, studyApi, knowledgeApi, isLoggedIn } from '../../api'

const route = useRoute()
const router = useRouter()

const filter = ref('')
const drawerOpen = ref(false)
// 默认展开第一章；若 URL 带了概念，select() 会自动展开所属章
const openChs = ref(new Set([CURRICULUM[0]?.code].filter(Boolean)))
const current = ref(route.query.c || '')

// ---- 难度视图：入门 / 进阶 / 专家（持久化到 localStorage kb-level）----
const LEVEL_META = [
  { name: '入门', short: '先看懂', description: '生活类比、核心要点和一个可感知的例子。' },
  { name: '进阶', short: '懂机制', description: '补充精确定义、运转机制、易混对比和常见误区。' },
  { name: '专家', short: '可核验', description: '在进阶基础上增加公式、规则来源、边界条件和适用范围。' },
]
const LEVELS = LEVEL_META.map(item => item.name)
const level = ref(LEVELS.includes(localStorage.getItem('kb-level')) ? localStorage.getItem('kb-level') : '入门')
const activeLevelMeta = computed(() => LEVEL_META.find(item => item.name === level.value) || LEVEL_META[0])
function setLevel(lv) {
  if (!LEVELS.includes(lv) || lv === level.value) return
  level.value = lv
  try { localStorage.setItem('kb-level', lv) } catch (e) { /* 静默 */ }
}
const levelRank = computed(() => LEVELS.indexOf(level.value))
// 字段可见性：入门仅 tldr/analogy/example/keyPoints；进阶在入门基础上加 definition/compare/walkthrough/pitfalls/faq/link2sim；专家再加 deepDive
function fieldAt(minLevel) {
  const min = LEVELS.indexOf(minLevel)
  return min < 0 ? true : levelRank.value >= min
}

// ---- 扁平索引 ----
const CONCEPTS = new Map()   // code -> concept
const CHAPTERS = new Map()   // code -> chapter
const OWNERS = new Map()     // conceptCode -> { chapter, section, chCode, secCode }
const FLAT = []              // 全部概念 code，按 CURRICULUM 顺序
for (const ch of CURRICULUM) {
  CHAPTERS.set(ch.code, ch)
  for (const sec of ch.sections) {
    for (const c of sec.concepts) {
      CONCEPTS.set(c.code, c)
      OWNERS.set(c.code, {
        chapter: ch.title, section: sec.title,
        chCode: ch.code, secCode: sec.code,
      })
      FLAT.push(c.code)
    }
  }
}

const cur = computed(() => CONCEPTS.get(current.value))
const flatOrder = FLAT

// ---- 知识点 code -> id 映射（用于"练本节"跳转 quiz）----
// curriculum 里只存了 KP 的 code（如 'mid_long_term'），quiz 需要 numeric id。
const kpCodeToId = ref({})
const kpMapLoading = ref(true)

// ---- 概念阅读进度（read/understood）----
// code -> 'read' | 'understood'；fetch 失败则 readingEnabled=false 静默隐藏徽章
const readingMap = ref({})
const readingEnabled = ref(true)
const readingLoaded = ref(false)   // readingMap 是否已加载完成；未加载前不上报，避免把 understood 降级
const rdMarking = ref(false)   // 「我懂了」按钮防抖

// ---- 掌握度：kp code -> {pct, total, correct} ----
const masteryMap = ref({})
const masteryEnabled = ref(true)

onMounted(() => {
  learnApi.knowledgeTree()
    .then((tree) => {
      const m = {}
      for (const p of tree || []) m[p.code] = p.id
      kpCodeToId.value = m
    })
    .catch(() => {})
    .finally(() => { kpMapLoading.value = false })

  if (!isLoggedIn()) { readingEnabled.value = false; masteryEnabled.value = false }
  // 概念阅读状态（登录后才有意义；失败静默降级）
  if (isLoggedIn()) {
    studyApi.reading()
      .then((rows) => {
        const m = {}
        for (const r of rows || []) m[r.concept_code] = r.status
        readingMap.value = m
        readingLoaded.value = true
        // 深链 (?c=code) 直接打开：readingMap 已就绪、已知先验状态，
        // 此时再上报 'read'（guard 会避免把 understood 降级）
        if (current.value && isConceptCode(current.value)) {
          scheduleReadingMark(current.value)
        }
      })
      .catch(() => { readingEnabled.value = false })
    studyApi.mastery()
      .then((rows) => {
        const m = {}
        for (const r of rows || []) {
          m[r.code] = {
            pct: r.mastery_pct ?? 0,
            total: r.total_attempts ?? 0,
            correct: r.correct_attempts ?? 0,
          }
        }
        masteryMap.value = m
      })
      .catch(() => { masteryEnabled.value = false })
  }

  // ?kp=<code> 筛选：自动选中第一个匹配概念
  applyKpFilterAuto()
})

// "练本节"是否可点：映射已加载且当前概念 kp 在映射中
const kpIdReady = computed(() => {
  if (!cur.value?.kp) return false
  if (kpMapLoading.value) return false
  return Object.prototype.hasOwnProperty.call(kpCodeToId.value, cur.value.kp)
})

// ---- ?kp=<code> 筛选 ----
const kpFilterCode = computed(() => (typeof route.query.kp === 'string' ? route.query.kp : ''))
const conceptFilterActive = computed(() => !!kpFilterCode.value)

function conceptMatchesKpFilter(c) {
  if (!kpFilterCode.value) return true
  return c.kp === kpFilterCode.value
}
function chapterHasKpHit(ch) {
  return ch.sections.some(sec => sec.concepts.some(c => conceptMatchesKpFilter(c)))
}
function applyKpFilterAuto() {
  if (!kpFilterCode.value) return
  const first = FLAT.find(code => {
    const c = CONCEPTS.get(code)
    return c && conceptMatchesKpFilter(c)
  })
  if (first) {
    // 展开所属章
    select(first)
  }
}
function clearKpFilter() {
  const q = { ...route.query }
  delete q.kp
  router.replace({ query: q })
}

// ?kp 反向同步（外部导航/前进后退变更）
watch(kpFilterCode, () => {
  if (kpFilterCode.value) applyKpFilterAuto()
})

// ---- 阅读进度辅助 ----
function readingStatus(code) {
  return readingMap.value[code] || null
}
function chapterProgress(ch) {
  let total = 0, read = 0  // read 含 understood
  for (const sec of ch.sections) {
    for (const c of sec.concepts) {
      total++
      if (readingMap.value[c.code]) read++
    }
  }
  return { total, read }
}
function chapterProgressPct(ch) {
  const { total, read } = chapterProgress(ch)
  if (!total) return 0
  return Math.round((read / total) * 100)
}

// ---- 掌握度辅助 ----
function masteryForKp(kpCode) {
  if (!kpCode) return null
  return masteryMap.value[kpCode] || null
}
function masteryPctForKp(kpCode) {
  const m = masteryForKp(kpCode)
  return m ? m.pct : null
}
const masteryPctForCur = computed(() => {
  if (!cur.value?.kp) return null
  return masteryPctForKp(cur.value.kp)
})
function masteryClass(pct) {
  if (pct == null) return ''
  if (pct >= 70) return 'good'
  if (pct >= 40) return 'mid'
  return 'low'
}

// ---- 辅助 ----
const isConceptCode = (code) => CONCEPTS.has(code)
const isChapterCode = (code) => CHAPTERS.has(code) && !CONCEPTS.has(code)

// 裸章 code（'1'..'13'）渲染章名；概念 code 取概念名；其余原样返回
function resolveTitle(code) {
  const c = CONCEPTS.get(code)
  if (c) return c.title
  const ch = CHAPTERS.get(code)
  if (ch) return ch.title
  return code
}

// 学习路线按章分组：章标题只承担层级说明，概念才提供点击入口。
const learningPathGroups = []
let activePathGroup = null
for (const code of LEARNING_PATH) {
  if (isChapterCode(code)) {
    activePathGroup = { code, title: resolveTitle(code), concepts: [] }
    learningPathGroups.push(activePathGroup)
  } else if (isConceptCode(code) && activePathGroup) {
    activePathGroup.concepts.push({ code, title: resolveTitle(code) })
  }
}

function conceptPath(code) {
  const o = OWNERS.get(code)
  if (o) return { chapter: o.chapter, section: o.section }
  // 兜底：可能是章/节 code
  const ch = CHAPTERS.get(code)
  if (ch) return { chapter: ch.title, section: '—' }
  return { chapter: '—', section: '—' }
}

// ---- 章节树过滤 ----
const anyHit = computed(() =>
  CURRICULUM.some(ch =>
    ch.title.includes(filter.value) ||
    ch.sections.some(sec =>
      sec.title.includes(filter.value) ||
      sec.concepts.some(c => c.title.includes(filter.value))
    )
  )
)
function chapterHasHit(ch) {
  const f = filter.value
  if (!f) return true
  return ch.title.includes(f) ||
    ch.sections.some(sec =>
      sec.title.includes(f) ||
      sec.concepts.some(c => c.title.includes(f))
    )
}
function visibleSections(sec_ch) {
  // 这里 sec_ch 是 chapter
  const f = filter.value
  if (!f) return sec_ch.sections
  return sec_ch.sections.filter(sec =>
    sec.title.includes(f) || sec.concepts.some(c => c.title.includes(f))
  )
}
function visibleConcepts(sec) {
  const f = filter.value
  if (!f) return sec.concepts
  return sec.concepts.filter(c => c.title.includes(f) || sec.title.includes(f))
}

// ---- compare 动态列 ----
// 数据形态：每行 { dim, a, b } 或 { dim, a, b, c }（如 851 结算规则）
// 值里普遍是 "列名：内容" 格式，列名取首行前缀，单元格去掉前缀
const cmpKeys = computed(() => {
  const arr = cur.value?.compare
  if (!arr || !arr.length) return []
  // 取所有行 value key 的并集（排除 dim），保持出现顺序
  const keys = []
  for (const row of arr) {
    for (const k of Object.keys(row)) {
      if (k !== 'dim' && !keys.includes(k)) keys.push(k)
    }
  }
  return keys
})
function cmpHeader(key) {
  const arr = cur.value?.compare
  if (!arr || !arr.length) return key.toUpperCase()
  // 该列可能只出现在后续行（arr[0] 没有），扫全部行取首个字符串值的"："前缀
  for (const row of arr) {
    const v = row[key]
    if (typeof v !== 'string') continue
    const idx = v.indexOf('：')
    if (idx > 0) return v.slice(0, idx)
  }
  // 所有行该列都没有前缀冒号：用通用列名
  return ({ a: 'A', b: 'B', c: 'C' })[key] || key.toUpperCase()
}
function cmpCell(row, key) {
  const v = row[key]
  if (typeof v !== 'string') return ''
  const idx = v.indexOf('：')
  if (idx > 0) return v.slice(idx + 1)
  return v
}

// ---- 交互 ----
function toggleCh(code) {
  const s = new Set(openChs.value)
  if (s.has(code)) s.delete(code)
  else s.add(code)
  openChs.value = s
}
function select(code) {
  if (!isConceptCode(code)) return
  current.value = code
  const o = OWNERS.get(code)
  if (o) {
    const s = new Set(openChs.value)
    s.add(o.chCode)
    openChs.value = s
  }
  router.replace({ query: { ...route.query, c: code } })
  drawerOpen.value = false
  // 滚回顶部
  nextTick(() => {
    const el = document.querySelector('.kb-reader')
    if (el) el.scrollTop = 0
  })
  // 阅读上报（防抖 500ms）：仅首次阅读上报 'read'，不把 understood 降级回 read
  scheduleReadingMark(code)
}
function clearCurrent() {
  current.value = ''
  router.replace({ query: { ...route.query, c: undefined } })
}
const flatIndex = computed(() => FLAT.indexOf(current.value))
const hasPrev = computed(() => flatIndex.value > 0)
const hasNext = computed(() => flatIndex.value >= 0 && flatIndex.value < FLAT.length - 1)
function goPrev() {
  if (hasPrev.value) select(FLAT[flatIndex.value - 1])
}
function goNext() {
  if (hasNext.value) select(FLAT[flatIndex.value + 1])
}

// ---- 出站动作 ----
function goQuiz() {
  const code = cur.value?.kp
  if (!code) return
  const id = kpCodeToId.value[code]
  if (id === undefined) return
  router.push({ path: '/learn/quiz', query: { kp: id } })
}
function goFeed() {
  const code = cur.value?.kp
  if (!code) return
  router.push({ path: '/knowledge', query: { tab: 'feed', kp: code } })
}
function goSim() {
  const s = cur.value?.scenario
  if (!s) return
  router.push({ path: '/trade', query: { market: s } })
}

// ---- 阅读进度上报 ----
let readTimer = null
function scheduleReadingMark(code) {
  if (readTimer) clearTimeout(readTimer)
  // 未加载前跳过：避免在 readingMap 还没拿到时把已 understood 的概念降级为 read。
  // 深链场景由 onMounted 在 reading() resolve 后补报；prev/next 在 select() 调用，
  // 若仍处于初始加载窗口（readingLoaded=false），这里跳过，等 mount 流程上报一次即可。
  if (!readingLoaded.value) return
  readTimer = setTimeout(() => {
    // 仅未上报过(read/understood)才上报 'read'，避免把 understood 降级
    if (!readingEnabled.value) return
    if (readingMap.value[code]) return
    studyApi.markReading(code, 'read')
      .then(() => {
        if (!readingMap.value[code]) readingMap.value = { ...readingMap.value, [code]: 'read' }
      })
      .catch(() => {})
  }, 500)
}
async function markUnderstood() {
  const code = current.value
  if (!code || !readingEnabled.value) return
  rdMarking.value = true
  try {
    await studyApi.markReading(code, 'understood')
    readingMap.value = { ...readingMap.value, [code]: 'understood' }
  } catch (e) {
    // 静默：不阻断阅读
  } finally {
    rdMarking.value = false
  }
}

// ---- 本节自检 ----
// 仅当当前概念有 kp、kpCodeToId 已就绪、用户已登录时显示
const showSelfCheck = computed(() => {
  if (!cur.value?.kp) return false
  if (kpMapLoading.value) return false
  if (!Object.prototype.hasOwnProperty.call(kpCodeToId.value, cur.value.kp)) return false
  return isLoggedIn()
})
// 触发自检刷新的 kp id：随当前概念或映射变化
const scKpId = computed(() => {
  if (!showSelfCheck.value) return null
  return kpCodeToId.value[cur.value.kp] ?? null
})
const scQuestion = ref(null)
const scLoading = ref(false)
const scSubmitting = ref(false)
const scAnswered = ref(false)
const scResult = ref(null)
const scSelectedStr = ref('')       // single/judge
const scSelectedArr = ref([])        // multiple
const scIsMultiple = computed(() => scQuestion.value?.type === 'multiple')

function resetSelfCheckState() {
  scQuestion.value = null
  scAnswered.value = false
  scResult.value = null
  scSelectedStr.value = ''
  scSelectedArr.value = []
}
async function fetchSelfCheck() {
  if (scKpId.value == null) { resetSelfCheckState(); return }
  scLoading.value = true
  resetSelfCheckState()
  try {
    const list = await learnApi.check(scKpId.value, 1)
    scQuestion.value = (list && list.length) ? list[0] : null
  } catch (e) {
    // 404「该知识点暂无题目」等：静默，渲染"暂无自检题"
    scQuestion.value = null
  } finally {
    scLoading.value = false
  }
}
function toggleMulti(key) {
  if (scAnswered.value) return
  const idx = scSelectedArr.value.indexOf(key)
  if (idx >= 0) scSelectedArr.value = scSelectedArr.value.filter(k => k !== key)
  else scSelectedArr.value = [...scSelectedArr.value, key]
}
const scCanSubmit = computed(() => {
  if (scIsMultiple.value) return scSelectedArr.value.length > 0
  return !!scSelectedStr.value
})
async function submitSelfCheck() {
  if (!scQuestion.value || !scCanSubmit.value) return
  const userAnswer = scIsMultiple.value
    ? [...scSelectedArr.value].sort().join('')
    : scSelectedStr.value
  scSubmitting.value = true
  try {
    const res = await learnApi.answer({
      question_id: scQuestion.value.id,
      user_answer: userAnswer,
    })
    scResult.value = res
    scAnswered.value = true
  } catch (e) {
    // 提交失败不阻断换题
  } finally {
    scSubmitting.value = false
  }
}
function scOptClass(key) {
  const cls = []
  const selected = scIsMultiple.value
    ? scSelectedArr.value.includes(key)
    : scSelectedStr.value === key
  if (selected) cls.push('selected')
  if (scAnswered.value && scResult.value) {
    const correctKeys = (scResult.value.correct_answer || '').replace(/\s/g, '').split('')
    if (correctKeys.includes(key)) cls.push('show-correct')
    else if (selected) cls.push('show-wrong')
  }
  return cls.join(' ')
}

watch(scKpId, () => { fetchSelfCheck() })

// ---- 相关原文（D2：概念级溯源）----
// 仅进阶/专家级、且当前概念有 kp 或有意义的 title 时召回；空结果/失败隐藏。
const relDocs = ref([])
const relDocsLoading = ref(false)
const relDocsVisible = computed(() => {
  if (relDocsLoading.value) return true
  return relDocs.value.length > 0
})
function docSrcUrl(d) {
  return d.source_url || `/knowledge?tab=feed&doc=${d.id}`
}
function truncate(s, n) {
  if (!s) return ''
  return s.length > n ? s.slice(0, n) + '…' : s
}
async function fetchRelDocs() {
  const c = cur.value
  if (!c) { relDocs.value = []; return }
  if (level.value === '入门') { relDocs.value = []; return }
  // 有 kp 或 title 非空即召回（title 描述性概念如「双边协商」即可命中）
  if (!c.kp && !c.title) { relDocs.value = []; return }
  relDocsLoading.value = true
  try {
    const res = await knowledgeApi.byConcept(c.title, c.kp || undefined, 3)
    relDocs.value = (res && res.items) ? res.items : []
  } catch (e) {
    // 静默：不展示空盒
    relDocs.value = []
  } finally {
    relDocsLoading.value = false
  }
}
// 当前概念变化时召回
watch(() => [cur.value?.code, cur.value?.kp, level.value], () => {
  fetchRelDocs()
}, { immediate: false })

onMounted(() => { fetchRelDocs() })

// URL 反向同步（浏览器前进/后退）
watch(() => route.query.c, (c) => {
  if ((c || '') !== current.value) current.value = c || ''
})

// 选中变化时确保所属章展开 + 滚顶 + 上报阅读进度
watch(current, () => {
  if (current.value && isConceptCode(current.value)) {
    const o = OWNERS.get(current.value)
    if (o) {
      const s = new Set(openChs.value)
      s.add(o.chCode)
      openChs.value = s
    }
    // 浏览器前进/后退或程序内切换：readingLoaded 为真时上报，
    // 否则交给 onMounted 在 readingMap 就绪后补报（见 scheduleReadingMark 注释）
    scheduleReadingMark(current.value)
  }
})

onBeforeUnmount(() => {
  if (readTimer) clearTimeout(readTimer)
})
</script>

<style scoped>
.kb-book {
  display: grid;
  grid-template-columns: 260px 1fr;
  height: 100%;
  max-width: 1440px;
  margin: 0 auto;
  background: rgba(255, 255, 255, .38);
}

/* ============ 左栏章节树 ============ */
.kb-tree {
  border-right: 1px solid #dce5f3;
  padding: 20px 17px;
  overflow-y: auto;
  height: 100%;
  background: linear-gradient(180deg, rgba(245, 248, 255, .96), rgba(250, 252, 255, .92));
}
.kb-tree-head {
  font-size: 11px;
  font-weight: 700;
  color: #50617c;
  padding: 0 4px 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  text-transform: uppercase;
  letter-spacing: .1em;
}
.kb-tree-filter {
  margin-bottom: 12px;
}
.kb-tree-filter :deep(.el-input__wrapper) {
  min-height: 38px;
  border-radius: 11px;
  box-shadow: 0 0 0 1px #dce5f2, 0 5px 14px rgba(54, 80, 137, .045);
}
.kb-tree-filter :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 2px rgba(65, 104, 220, .3);
}

.kb-tree-list { display: flex; flex-direction: column; gap: 2px; }

.kb-ch {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 8px;
  cursor: pointer;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  color: #21324e;
  transition: background .15s, transform .15s;
}
.kb-ch:hover { background: #edf2ff; }
.kb-ch.open .kb-ch-chev { transform: rotate(90deg); }
.kb-ch-chev {
  flex-shrink: 0;
  color: #94a0b4;
  transition: transform .18s ease;
}
.kb-ch-code {
  font-size: 10px;
  font-weight: 700;
  color: #4168dc;
  background: #eaf0ff;
  border-radius: 5px;
  padding: 1px 6px;
  min-width: 18px;
  text-align: center;
}
.kb-ch-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.kb-sec-list {
  padding: 4px 0 6px 22px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.kb-sec-title {
  font-size: 11px;
  font-weight: 600;
  color: #94a0b4;
  padding: 2px 6px;
  letter-spacing: .02em;
}
.kb-concept {
  font-size: 12.5px;
  color: #52647e;
  padding: 6px 10px;
  border-radius: 7px;
  cursor: pointer;
  transition: background .15s, color .15s, transform .15s;
  line-height: 1.4;
}
.kb-concept:hover { background: #f4f7ff; color: #4168dc; transform: translateX(2px); }
.kb-concept.active {
  background: linear-gradient(90deg, #e7edff, #f2f6ff);
  color: #4168dc;
  font-weight: 700;
  box-shadow: inset 3px 0 0 #4168dc;
}
.kb-tree-empty {
  text-align: center;
  color: #94a0b4;
  font-size: 12px;
  padding: 24px 0;
}

/* ============ 主阅读区 ============ */
.kb-reader {
  padding: 22px 28px 48px;
  overflow-y: auto;
  height: 100%;
  position: relative;
}
.kb-tree-toggle {
  display: none;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border: 1px solid #dce5f3;
  border-radius: 9px;
  background: rgba(255, 255, 255, .9);
  color: #50617c;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  margin-bottom: 12px;
}

/* 学习路线：首页只用章卡承载层级，概念采用轻量链接行。 */
.kb-path-card {
  max-width: 1100px;
  padding: 6px 4px 42px;
  position: relative;
}
.kpc-intro {
  margin-bottom: 24px;
  padding: 20px 22px;
  border-left: 3px solid #4168dc;
  background: linear-gradient(90deg, rgba(234,240,255,.88), rgba(244,250,252,.42), transparent);
}
.kpc-head {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: #4168dc;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .16em;
}
.kpc-intro h1 {
  margin: 9px 0 5px;
  color: #172847;
  font-size: 24px;
  line-height: 1.3;
  letter-spacing: -.025em;
}
.kpc-sub {
  color: #687891;
  font-size: 13px;
  margin: 0;
  line-height: 1.7;
}
.kpc-stages {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 18px;
}
.kpc-stage {
  overflow: hidden;
  border: 1px solid #dce5f3;
  border-radius: 14px;
  background: rgba(255,255,255,.82);
  box-shadow: 0 6px 18px rgba(43,67,122,.045);
}
.kpc-stage-head {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 11px;
  padding: 14px 15px;
  border-bottom: 1px solid #e6ebf4;
  background: linear-gradient(115deg, #f4f7ff, #f4fbfb);
}
.kpc-stage-no {
  color: #4168dc;
  font: 800 18px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
}
.kpc-stage-kicker {
  display: block;
  margin-bottom: 2px;
  color: #91a0b7;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: .12em;
}
.kpc-stage-head h2 {
  margin: 0;
  color: #21324e;
  font-size: 14px;
  line-height: 1.35;
}
.kpc-stage-count {
  color: #8390a5;
  font-size: 10px;
  white-space: nowrap;
}
.kpc-concepts { padding: 5px 14px 8px; }
.kpc-concept-link {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 36px;
  padding: 6px 2px;
  border: 0;
  border-bottom: 1px solid #edf0f6;
  background: transparent;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  color: #455671;
  font-size: 12.5px;
  transition: color .15s, padding-left .15s;
}
.kpc-concept-link:last-child { border-bottom: 0; }
.kpc-concept-link:hover {
  color: #3152b9;
  padding-left: 5px;
}
.kpc-concept-link > span:nth-child(2) { flex: 1; }
.kpc-concept-no {
  color: #a3afc1;
  font: 700 10px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
}

/* 概念正文 */
.kb-article { max-width: 820px; }
.kb-bc {
  font-size: 12px;
  color: #94a0b4;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 14px;
}
.kb-bc-link {
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: #64789a;
  font: inherit;
  cursor: pointer;
}
.kb-bc-link:hover { color: #3152b9; text-decoration: underline; text-underline-offset: 3px; }
.kb-bc-current { color: #21324e; font-weight: 650; }
.kb-bc-sep { color: #c8d2e3; }

.kb-title {
  font-size: 26px;
  font-weight: 800;
  color: #172847;
  letter-spacing: -.02em;
  line-height: 1.25;
  margin-bottom: 20px;
}

.kb-block-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 800;
  color: #4168dc;
  letter-spacing: .06em;
  margin-bottom: 8px;
}
.kb-tldr, .kb-analogy, .kb-def, .kb-sim {
  border: 1px solid #e1e7f2;
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 14px;
  background: #fff;
  box-shadow: 0 5px 17px rgba(43, 67, 122, .035);
}
.kb-tldr {
  background: linear-gradient(125deg, #fff, #f3f7ff);
  border-color: #c5d0f5;
}
.kb-tldr p, .kb-analogy p, .kb-def p, .kb-sim p {
  font-size: 14px;
  line-height: 1.75;
  color: #21324e;
}
.kb-def p :deep(code), .kb-kp-list :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: #eef3ff;
  color: #3152b9;
  border-radius: 4px;
  padding: 1px 5px;
  font-size: .92em;
}
.kb-def p :deep(strong), .kb-kp-list :deep(strong) { color: #4168dc; font-weight: 700; }

.kb-prereq, .kb-rel { margin-bottom: 16px; }
.kb-chips { display: flex; flex-wrap: wrap; gap: 7px; }
.kb-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  padding: 5px 11px;
  border: 1px solid #e0e5ef;
  border-radius: 9px;
  background: #fff;
  color: #657086;
  cursor: pointer;
  transition: transform .16s, border-color .16s, color .16s, background .16s, box-shadow .16s;
}
.kb-chip:hover {
  border-color: #4168dc;
  color: #4168dc;
  transform: translateY(-1px);
  background: #eaf0ff;
  box-shadow: 0 4px 12px rgba(65, 104, 220, .1);
}
.kb-chip:disabled {
  cursor: default;
  color: #94a0b4;
  background: #f4f6f9;
}
.kb-chip:disabled:hover { transform: none; border-color: #e0e5ef; color: #94a0b4; background: #f4f6f9; box-shadow: none; }

.kb-kp { margin-bottom: 16px; }
.kb-kp-list {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.kb-kp-list li {
  font-size: 13px;
  line-height: 1.7;
  color: #3a4a63;
  padding: 8px 12px 8px 28px;
  background: #f8faff;
  border-radius: 8px;
  position: relative;
}
.kb-kp-list li::before {
  content: "";
  position: absolute;
  left: 12px;
  top: 15px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #4168dc;
  box-shadow: 0 0 0 3px rgba(65, 104, 220, .15);
}

/* 对比表 */
.kb-cmp-wrap { margin-bottom: 16px; }
.kb-cmp-scroll { overflow-x: auto; border-radius: 12px; border: 1px solid #e1e7f2; box-shadow: 0 5px 17px rgba(43, 67, 122, .035); }

/* ============ 实例 / 运转 / 坑 / 疑问（B5 新增） ============ */
.kb-example {
  border: 1px solid #f0d9a8;
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 14px;
  background: linear-gradient(125deg, #fffaf0, #fff7e8);
  box-shadow: 0 5px 17px rgba(199, 152, 41, .06);
}
.kb-example p {
  font-size: 14px;
  line-height: 1.75;
  color: #5a4416;
}
.kb-example :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: #fdf3d6;
  color: #9a6a00;
  border-radius: 4px;
  padding: 1px 5px;
  font-size: .92em;
}

.kb-walk {
  border: 1px solid #d4defb;
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 14px;
  background: linear-gradient(125deg, #f7faff, #eef9fb);
  box-shadow: 0 5px 17px rgba(43, 67, 122, .04);
}
.kb-walk p {
  font-size: 14px;
  line-height: 1.85;
  color: #21324e;
  white-space: pre-line;
}

.kb-pitfalls {
  border: 1px solid #f0c9c9;
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 14px;
  background: linear-gradient(125deg, #fff5f5, #fdf0f0);
  box-shadow: 0 5px 17px rgba(180, 60, 60, .05);
}
.kb-pitfalls .kb-block-label { color: #c94545; }
.kb-pitfalls-list {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.kb-pitfalls-list li {
  font-size: 13px;
  line-height: 1.7;
  color: #6a3838;
  padding: 8px 12px 8px 28px;
  background: #fff;
  border-radius: 8px;
  position: relative;
}
.kb-pitfalls-list li::before {
  content: "!";
  position: absolute;
  left: 10px;
  top: 8px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #d64545;
  color: #fff;
  font-size: 11px;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 0 3px rgba(214, 69, 69, .12);
}

.kb-faq {
  border: 1px solid #e1e7f2;
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 14px;
  background: #fff;
  box-shadow: 0 5px 17px rgba(43, 67, 122, .035);
}
.kb-faq-list { display: flex; flex-direction: column; gap: 8px; }
.kb-faq-item {
  border: 1px solid #edf1f8;
  border-radius: 9px;
  background: #f8faff;
  overflow: hidden;
}
.kb-faq-q {
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: #21324e;
  padding: 10px 14px;
  list-style: none;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  transition: background .15s;
}
.kb-faq-q::before {
  content: "Q";
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 800;
  color: #4168dc;
  background: #eaf0ff;
  border-radius: 5px;
  padding: 1px 6px;
  min-width: 18px;
  text-align: center;
}
.kb-faq-q:hover { background: #eaf0ff; }
.kb-faq-item[open] .kb-faq-q { background: #eaf0ff; border-bottom: 1px solid #e1e7f2; }
.kb-faq-a {
  font-size: 13px;
  line-height: 1.7;
  color: #3a4a63;
  padding: 10px 14px 12px 38px;
  margin: 0;
}

/* ============ 难度视图切换 ============ */
.kb-level {
  display: grid;
  grid-template-columns: auto 1fr;
  align-items: stretch;
  gap: 10px;
  margin: -6px 0 18px;
}
.kb-level-seg {
  display: inline-flex;
  padding: 3px;
  border: 1px solid #dce5f3;
  border-radius: 10px;
  background: rgba(255, 255, 255, .9);
  box-shadow: 0 2px 8px rgba(54, 80, 137, .05);
}
.kb-level-btn {
  min-width: 82px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  border: none;
  background: transparent;
  color: #6b7a93;
  font-family: inherit;
  padding: 7px 11px;
  border-radius: 7px;
  cursor: pointer;
  transition: background .15s, color .15s, box-shadow .15s;
}
.kb-level-btn strong { font-size: 12.5px; line-height: 1.2; }
.kb-level-btn small { font-size: 9px; font-weight: 600; opacity: .66; }
.kb-level-btn:hover { color: #4168dc; }
.kb-level-btn.active {
  background: linear-gradient(125deg, #4168dc, #5278e4);
  color: #fff;
  box-shadow: 0 4px 11px rgba(65, 104, 220, .28);
}
.kb-level-hint {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  min-width: 0;
  padding: 7px 11px;
  border-left: 2px solid #d7e0f4;
  color: #77869d;
  font-size: 10.5px;
  line-height: 1.45;
}
.kb-level-hint strong { color: #52647e; font-size: 10px; }

/* ============ 专家深挖（deepDive） ============ */
.kb-deepdive {
  margin-bottom: 16px;
  padding: 16px 18px;
  border: 1px solid #c9d6f5;
  border-radius: 13px;
  background: linear-gradient(125deg, #f4f7ff, #eef2ff 60%, #f0f4ff);
  box-shadow: 0 6px 20px rgba(54, 80, 137, .07);
}
.kb-deepdive .kb-block-label { color: #304fae; }
.kb-deepdive-empty { background: #f7f8fb; border-style: dashed; box-shadow: none; }
.kb-deepdive-empty p { margin: 0; color: #6b7a93; font-size: 12.5px; line-height: 1.7; }
.kb-dd-item {
  margin-top: 12px;
  padding: 11px 13px;
  background: #fff;
  border-radius: 9px;
  border: 1px solid #e4e9f5;
}
.kb-dd-item:first-of-type { margin-top: 10px; }
.kb-dd-label {
  display: block;
  font-size: 11px;
  font-weight: 800;
  color: #304fae;
  letter-spacing: .04em;
  margin-bottom: 6px;
}
.kb-dd-item p {
  font-size: 13px;
  line-height: 1.75;
  color: #21324e;
  margin: 0;
}
.kb-dd-item p :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: #eef3ff;
  color: #3152b9;
  border-radius: 4px;
  padding: 1px 5px;
  font-size: .92em;
}
.kb-dd-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.kb-dd-list li {
  font-size: 13px;
  line-height: 1.7;
  color: #3a4a63;
  padding: 6px 10px 6px 22px;
  background: #f8faff;
  border-radius: 7px;
  position: relative;
}
.kb-dd-list li::before {
  content: "•";
  position: absolute;
  left: 9px;
  top: 5px;
  color: #4168dc;
  font-weight: 800;
}
.kb-source-links { display: flex; flex-direction: column; gap: 6px; }
.kb-source-links a {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 7px 9px;
  border-radius: 7px;
  background: #f7f9ff;
  color: #3152b9;
  font-size: 12px;
  text-decoration: none;
}
.kb-source-links a:hover { background: #edf2ff; text-decoration: underline; text-underline-offset: 3px; }

.kb-cmp {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  min-width: 480px;
}
.kb-cmp thead th {
  background: linear-gradient(145deg, #304fae, #5278e4 65%, #1aa5ad);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  padding: 10px 12px;
  text-align: left;
  letter-spacing: .02em;
}
.kb-cmp thead th:first-child { border-top-left-radius: 11px; }
.kb-cmp thead th:last-child { border-top-right-radius: 11px; }
.kb-cmp tbody td {
  font-size: 13px;
  line-height: 1.65;
  color: #3a4a63;
  padding: 11px 12px;
  border-top: 1px solid #eef1f8;
  vertical-align: top;
}
.kb-cmp tbody tr:nth-child(odd) td { background: #f8faff; }
.kb-cmp tbody tr:hover td { background: #eaf0ff; }
.kb-cmp tbody td :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: #eef3ff;
  color: #3152b9;
  border-radius: 4px;
  padding: 1px 5px;
  font-size: .92em;
}
.kb-cmp-dim {
  font-weight: 700;
  color: #21324e;
  white-space: nowrap;
}

/* ============ 相关原文（D2 概念级溯源）============ */
.kb-reldocs { margin-bottom: 16px; }
.kb-rd-hint { font-size: 13px; color: #94a0b4; padding: 6px 0; }
.kb-rd-list {
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.kb-rd-card {
  display: block;
  padding: 12px 14px;
  border: 1px solid #e1e7f2;
  border-radius: 11px;
  background: #fff;
  box-shadow: 0 4px 14px rgba(43, 67, 122, .035);
  text-decoration: none;
  color: inherit;
  transition: transform .15s, border-color .15s, box-shadow .15s;
}
.kb-rd-card:hover {
  transform: translateY(-1px);
  border-color: #bdcbed;
  box-shadow: 0 8px 20px rgba(49, 76, 142, .12);
}
.kb-rd-head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 4px;
}
.kb-rd-title {
  flex: 1;
  font-size: 13.5px;
  font-weight: 700;
  color: #21324e;
  line-height: 1.5;
}
.kb-rd-type {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  color: #4168dc;
  background: #eaf0ff;
  border-radius: 5px;
  padding: 2px 7px;
}
.kb-rd-meta {
  font-size: 11px;
  color: #94a0b4;
  display: flex;
  gap: 5px;
  margin-bottom: 6px;
}
.kb-rd-sep { color: #c8d2e3; }
.kb-rd-sum {
  font-size: 12.5px;
  line-height: 1.65;
  color: #52647e;
  margin: 0 0 8px;
}
.kb-rd-link {
  font-size: 12px;
  font-weight: 600;
  color: #4168dc;
}

/* 出站动作行 */
.kb-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 24px;
  padding: 14px 16px;
  border: 1px dashed #d4defb;
  border-radius: 13px;
  background: linear-gradient(125deg, #f7faff, #eef9fb);
}
.kb-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 16px;
  border: 1px solid #dce5f3;
  border-radius: 10px;
  background: #fff;
  color: #4168dc;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: transform .15s, box-shadow .15s, border-color .15s, background .15s;
}
.kb-action-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 14px rgba(65, 104, 220, .15);
  border-color: #4168dc;
}
.kb-action-btn:disabled { opacity: .45; cursor: not-allowed; }
.kb-action-btn.primary {
  background: linear-gradient(125deg, #4168dc, #5278e4);
  color: #fff;
  border-color: transparent;
}
.kb-action-btn.primary:hover:not(:disabled) {
  box-shadow: 0 8px 18px rgba(65, 104, 220, .3);
  border-color: transparent;
}
.kb-action-btn.accent {
  background: linear-gradient(125deg, #14a0b0, #1aa5ad);
  color: #fff;
  border-color: transparent;
}
.kb-action-btn.accent:hover:not(:disabled) {
  box-shadow: 0 8px 18px rgba(20, 160, 176, .3);
  border-color: transparent;
}

/* 底部导航 */
.kb-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 28px;
  padding-top: 18px;
  border-top: 1px solid #edf1f8;
}
.kb-nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 16px;
  border: 1px solid #dce5f3;
  border-radius: 10px;
  background: #fff;
  color: #4168dc;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: transform .15s, box-shadow .15s, border-color .15s;
}
.kb-nav-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 14px rgba(65, 104, 220, .15);
  border-color: #4168dc;
}
.kb-nav-btn:disabled { opacity: .4; cursor: not-allowed; }
.kb-nav-pos {
  font-size: 12px;
  color: #94a0b4;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* 兜底 */
.kb-fallback {
  text-align: center;
  padding: 60px 20px;
  color: #94a0b4;
}
.kb-fallback p { margin: 12px 0 18px; font-size: 14px; }

/* ============ ?kp 筛选 chip ============ */
.kb-kpfilter-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  margin-bottom: 10px;
  border: 1px solid #b7e3e6;
  border-radius: 9px;
  background: linear-gradient(125deg, #eaf9fb, #eef9fb);
  color: #0f7d8a;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: border-color .15s, background .15s;
}
.kb-kpfilter-chip:hover { border-color: #14a0b0; background: #e0f4f6; }
.kb-kpfilter-x { font-size: 13px; line-height: 1; color: #0f7d8a; }

/* ============ 章节进度 + 概念阅读标记 + 掌握度 chip ============ */
.kb-ch-prog {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
}
.kb-ch-prog-bar {
  width: 34px;
  height: 5px;
  border-radius: 4px;
  background: #e3e9f5;
  overflow: hidden;
}
.kb-ch-prog-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #4168dc, #1aa5ad);
  border-radius: 4px;
  transition: width .25s;
}
.kb-ch-prog-num {
  font-size: 10px;
  font-weight: 700;
  color: #94a0b4;
  font-variant-numeric: tabular-nums;
}

.kb-concept {
  display: flex;
  align-items: center;
  gap: 6px;
}
.kb-concept-mark {
  flex-shrink: 0;
  width: 14px;
  font-size: 13px;
  line-height: 1;
  color: #b6c0d2;
  text-align: center;
}
.kb-concept-mark.solid { color: #1aa5ad; font-weight: 800; }
.kb-concept.is-read .kb-concept-title { color: #7c8aa1; }
.kb-concept.is-understood .kb-concept-title { color: #0f7d8a; font-weight: 700; }
.kb-concept-title { flex: 1; overflow: hidden; text-overflow: ellipsis; }

.kb-mastery-chip {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 800;
  padding: 1px 5px;
  border-radius: 5px;
  font-variant-numeric: tabular-nums;
}
.kb-mastery-chip.low { color: #d64545; background: #fdeaea; }
.kb-mastery-chip.mid { color: #c77700; background: #fdf2e3; }
.kb-mastery-chip.good { color: #1a8a4a; background: #e6f6ec; }

/* ============ 概念正文状态条 ============ */
.kb-status-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}
.kb-rd-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 3px 9px;
  border-radius: 6px;
  letter-spacing: .04em;
}
.kb-rd-badge.read { color: #6b7a93; background: #eef1f8; }
.kb-rd-badge.understood { color: #0f7d8a; background: #e0f4f6; }
.kb-action-btn.small {
  padding: 5px 10px;
  font-size: 12px;
  border-radius: 8px;
}
.kb-mastery-mini {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}
.kb-mastery-mini-bar {
  width: 56px;
  height: 6px;
  border-radius: 4px;
  background: #e3e9f5;
  overflow: hidden;
}
.kb-mastery-mini-fill {
  display: block;
  height: 100%;
  border-radius: 4px;
}
.kb-mastery-mini.low .kb-mastery-mini-fill { background: #d64545; }
.kb-mastery-mini.mid .kb-mastery-mini-fill { background: #e89a1a; }
.kb-mastery-mini.good .kb-mastery-mini-fill { background: #1a8a4a; }
.kb-mastery-mini-num {
  font-size: 11px;
  font-weight: 700;
  color: #6b7a93;
  font-variant-numeric: tabular-nums;
}

/* ============ 本节自检 ============ */
.kb-selfcheck {
  margin-bottom: 16px;
  padding: 14px 16px;
  border: 1px solid #d4defb;
  border-radius: 13px;
  background: linear-gradient(125deg, #f7faff, #f3f9ff);
  box-shadow: 0 5px 17px rgba(43, 67, 122, .04);
}
.kb-sc-hint { font-size: 13px; color: #94a0b4; padding: 6px 0; }
.kb-sc-link { color: #4168dc; cursor: pointer; font-weight: 600; }
.kb-sc-body { display: flex; flex-direction: column; gap: 10px; }
.kb-sc-stem {
  font-size: 14px;
  line-height: 1.7;
  color: #21324e;
  font-weight: 600;
}
.kb-sc-options { display: flex; flex-direction: column; gap: 6px; }
.kb-sc-opt {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 11px;
  border: 1px solid #e1e7f2;
  border-radius: 9px;
  background: #fff;
  cursor: pointer;
  transition: border-color .15s, background .15s, transform .15s;
}
.kb-sc-opt:hover { border-color: #bdcbed; background: #f4f7ff; }
.kb-sc-opt.selected { border-color: #4168dc; background: #eaf0ff; }
.kb-sc-opt.show-correct { border-color: #1a8a4a; background: #e6f6ec; }
.kb-sc-opt.show-wrong { border-color: #d64545; background: #fdeaea; }
.kb-sc-opt input { margin-top: 3px; accent-color: #4168dc; }
.kb-sc-key {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 800;
  color: #4168dc;
  background: #eaf0ff;
  border-radius: 5px;
  padding: 1px 6px;
  min-width: 18px;
  text-align: center;
}
.kb-sc-text { font-size: 13px; line-height: 1.6; color: #3a4a63; }
.kb-sc-result {
  padding: 10px 12px;
  border-radius: 9px;
  border: 1px solid;
}
.kb-sc-result.correct { border-color: #bfe3c9; background: #f0fbf3; }
.kb-sc-result.wrong { border-color: #f0c9c9; background: #fdf0f0; }
.kb-sc-result-head {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  font-weight: 700;
}
.kb-sc-result.correct .kb-sc-verdict { color: #1a8a4a; }
.kb-sc-result.wrong .kb-sc-verdict { color: #d64545; }
.kb-sc-answer { color: #52647e; font-weight: 600; }
.kb-sc-analysis { font-size: 13px; line-height: 1.7; color: #3a4a63; margin-top: 6px; }
.kb-sc-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}
.kb-sc-actions .kb-action-btn { padding: 7px 13px; font-size: 12px; }
.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* ============ 移动端 ============ */
@media (max-width: 900px) {
  .kb-book { grid-template-columns: 1fr; }
  .kb-tree {
    position: fixed;
    top: 118px;
    left: 0;
    bottom: 0;
    width: 280px;
    height: calc(100dvh - 118px);
    z-index: 30;
    transform: translateX(-100%);
    transition: transform .26s cubic-bezier(.22, .61, .36, 1);
    box-shadow: 8px 0 30px rgba(47, 75, 140, .18);
  }
  .kb-tree.open { transform: translateX(0); }
  .kb-drawer-mask {
    position: fixed;
    inset: 118px 0 0 0;
    background: rgba(23, 40, 71, .35);
    z-index: 29;
    backdrop-filter: blur(2px);
  }
  .kb-tree-toggle { display: inline-flex; }
  .kb-reader { padding: 16px 16px 36px; }
  .kb-title { font-size: 22px; }
  .kpc-stages { grid-template-columns: 1fr; }
}
@media (max-width: 680px) {
  .kb-tree { width: 84vw; }
  .kb-level { grid-template-columns: 1fr; }
  .kb-level-seg { width: 100%; }
  .kb-level-btn { flex: 1; min-width: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .kb-ch, .kb-concept, .kpc-concept-link, .kb-chip, .kb-nav-btn, .kb-action-btn, .kb-tree { transition: none; }
}
</style>
