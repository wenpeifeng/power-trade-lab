<template>
  <div class="reader-page" v-loading="loading">
    <header v-if="book" class="reader-header">
      <div class="header-copy">
        <router-link to="/learn/books"><ArrowLeft :size="14" /> 返回教材工坊</router-link>
        <span class="reader-kicker">CHAPTER LEARNING</span>
        <h1>{{ book.title }}</h1>
        <p>{{ book.chapter_count }} 个章节 · {{ Number(book.word_count || 0).toLocaleString('zh-CN') }} 字 · {{ book.parser_engine }}</p>
      </div>
      <div class="book-completion">
        <strong><span v-count="book.progress_pct">0</span>%</strong>
        <small>整本进度</small>
        <div><i :style="{ width: `${book.progress_pct}%` }"></i></div>
      </div>
    </header>

    <div v-if="book" class="reader-layout">
      <aside class="chapter-rail">
        <div class="rail-head"><span>课程目录</span><small>{{ completedCount }}/{{ chapters.length }} 已完成</small></div>
        <button
          v-for="chapter in chapters"
          :key="chapter.id"
          :class="{
            active: currentChapter?.id === chapter.id,
            complete: chapter.progress.status === 'completed',
          }"
          @click="selectChapter(chapter.id)"
        >
          <span class="chapter-order">
            <Check v-if="chapter.progress.status === 'completed'" :size="13" />
            <template v-else>{{ String(chapter.order).padStart(2, '0') }}</template>
          </span>
          <span class="chapter-label"><strong>{{ chapter.title }}</strong><small>{{ chapter.word_count }} 字</small></span>
          <ChevronRight :size="14" />
        </button>
      </aside>

      <main v-if="chapterData" class="chapter-canvas">
        <section class="chapter-intro">
          <div>
            <span>CHAPTER {{ String(chapterData.order).padStart(2, '0') }}</span>
            <h2>{{ chapterData.title }}</h2>
            <p v-if="chapterData.source_page_start">原书第 {{ chapterData.source_page_start }}{{ chapterData.source_page_end !== chapterData.source_page_start ? `—${chapterData.source_page_end}` : '' }} 页</p>
          </div>
          <div class="chapter-state" :class="progress.status">
            <CircleCheckBig v-if="progress.status === 'completed'" :size="19" />
            <BookOpen v-else :size="19" />
            <span><strong>{{ progressLabel }}</strong><small>章节进度 {{ progress.progress_pct }}%</small></span>
          </div>
        </section>

        <section class="chapter-briefing">
          <div class="briefing-head">
            <div class="section-title">
              <Sparkles :size="19" />
              <div><strong>本章学习导航</strong><small>先建立框架，再深入正文</small></div>
            </div>
            <div class="briefing-tabs" role="tablist" aria-label="章节学习导航">
              <button
                v-for="tab in briefingTabs"
                :key="tab.key"
                :class="{ active: briefingTab === tab.key }"
                role="tab"
                :aria-selected="briefingTab === tab.key"
                @click="briefingTab = tab.key"
              >
                <component :is="tab.icon" :size="16" />
                {{ tab.label }}
              </button>
            </div>
          </div>

          <Transition name="brief-panel" mode="out-in">
            <div v-if="briefingTab === 'overview'" key="overview" class="brief-panel overview-panel">
              <span class="brief-index">01</span>
              <div>
                <small>本章先看懂什么</small>
                <p>{{ chapterData.summary }}</p>
                <div class="key-points">
                  <span v-for="point in chapterData.key_points" :key="point">{{ point }}</span>
                </div>
              </div>
            </div>

            <div v-else-if="briefingTab === 'takeaways'" key="takeaways" class="brief-panel focus-panel">
              <span class="brief-index">{{ String(takeawayIndex + 1).padStart(2, '0') }}</span>
              <div class="focus-copy">
                <small>{{ currentTakeaway.title || '需要真正理解的结论' }}</small>
                <p>{{ currentTakeaway.explanation || '本章暂无核心知识点' }}</p>
                <button
                  v-if="currentTakeaway.evidence"
                  class="locate-evidence"
                  @click="scrollToEvidence(currentTakeaway.evidence)"
                >在正文中查看依据 ↓</button>
              </div>
              <div v-if="chapterData.knowledge_takeaways?.length > 1" class="brief-pager">
                <button
                  v-for="(_, index) in chapterData.knowledge_takeaways"
                  :key="index"
                  :class="{ active: takeawayIndex === index }"
                  :aria-label="`查看第 ${index + 1} 个核心知识点`"
                  @click="takeawayIndex = index"
                >{{ index + 1 }}</button>
              </div>
            </div>

            <div v-else key="quotes" class="brief-panel quote-panel">
              <Quote :size="26" />
              <div class="focus-copy">
                <small>可回到教材核对的原文依据</small>
                <blockquote>{{ chapterData.golden_sentences?.[quoteIndex] || '本章暂无原文精句' }}</blockquote>
                <button
                  v-if="chapterData.golden_sentences?.[quoteIndex]"
                  class="locate-evidence"
                  @click="scrollToEvidence(chapterData.golden_sentences[quoteIndex])"
                >定位到正文 ↓</button>
              </div>
              <div v-if="chapterData.golden_sentences?.length > 1" class="brief-pager">
                <button
                  v-for="(_, index) in chapterData.golden_sentences"
                  :key="index"
                  :class="{ active: quoteIndex === index }"
                  :aria-label="`查看第 ${index + 1} 条原文依据`"
                  @click="quoteIndex = index"
                >{{ index + 1 }}</button>
              </div>
            </div>
          </Transition>
        </section>

        <article class="markdown-article">
          <template v-for="(block, index) in markdownBlocks" :key="index">
            <h2 v-if="block.type === 'h1'" v-html="inlineHtml(block.text)"></h2>
            <h3 v-else-if="block.type === 'h2'" v-html="inlineHtml(block.text)"></h3>
            <h4 v-else-if="block.type === 'h3'" v-html="inlineHtml(block.text)"></h4>
            <blockquote v-else-if="block.type === 'quote'" v-html="inlineHtml(block.text)"></blockquote>
            <ul v-else-if="block.type === 'list'"><li v-for="item in block.items" :key="item" v-html="inlineHtml(item)"></li></ul>
            <pre v-else-if="block.type === 'code'"><code>{{ block.text }}</code></pre>
            <div v-else-if="block.type === 'table'" class="md-table"><pre>{{ block.text }}</pre></div>
            <div v-else-if="block.type === 'page'" class="page-anchor">原书第 {{ block.page }} 页</div>
            <div
              v-else-if="block.evidenceIndex >= 0"
              :id="`chapter-evidence-${block.evidenceIndex}`"
              class="evidence-paragraph"
              :class="{ pulse: activeEvidence === block.evidenceIndex }"
            >
              <span><Quote :size="13" /> 核心原文</span>
              <p v-html="inlineHtml(block.text)"></p>
            </div>
            <p v-else v-html="inlineHtml(block.text)"></p>
          </template>
        </article>

        <section class="chapter-notes">
          <div class="section-title"><NotebookPen :size="17" /><div><strong>我的章节笔记</strong><small>写下你自己的解释，比摘抄更有用</small></div></div>
          <el-input v-model="notes" type="textarea" :rows="4" placeholder="例如：日前市场解决什么问题？它和中长期合约如何衔接？" />
          <el-button :loading="savingNote" @click="saveNote">保存笔记</el-button>
        </section>

        <section class="chapter-check">
          <div class="check-head">
            <div class="section-title"><BrainCircuit :size="17" /><div><strong>章节理解检查</strong><small>一次专注一题，完成后查看依据</small></div></div>
            <div class="check-progress">
              <span>已答 {{ answeredCount }}/{{ chapterData.quiz.length }}</span>
              <div><i :style="{ width: `${chapterData.quiz.length ? answeredCount / chapterData.quiz.length * 100 : 0}%` }"></i></div>
            </div>
          </div>

          <div class="question-nav" aria-label="题目导航">
            <button
              v-for="(_, index) in chapterData.quiz"
              :key="index"
              :class="{
                active: quizIndex === index,
                answered: !!answers[index],
                correct: review?.items?.[index]?.is_correct,
                wrong: review?.items?.[index] && !review.items[index].is_correct,
              }"
              @click="quizIndex = index"
            >
              {{ index + 1 }}
            </button>
          </div>

          <Transition name="brief-panel" mode="out-in">
            <div v-if="currentQuizQuestion" :key="quizIndex" class="check-question">
              <span class="question-count">QUESTION {{ String(quizIndex + 1).padStart(2, '0') }}</span>
              <strong>{{ currentQuizQuestion.stem }}</strong>
            <div class="check-options">
              <button
                v-for="option in currentQuizQuestion.options"
                :key="option.key"
                :class="{
                  selected: answers[quizIndex] === option.key,
                  correct: currentReviewItem?.correct_answer === option.key,
                  wrong: currentReviewItem?.user_answer === option.key && !currentReviewItem?.is_correct,
                }"
                :disabled="!!review"
                @click="answers[quizIndex] = option.key"
              ><i>{{ option.key }}</i><span>{{ option.text }}</span></button>
            </div>
            <div v-if="currentReviewItem" class="answer-review" :class="{ correct: currentReviewItem.is_correct }">
              <strong>{{ currentReviewItem.is_correct ? '回答正确' : `正确答案：${currentReviewItem.correct_answer}` }}</strong>
              <p>{{ currentReviewItem.analysis }}</p>
            </div>
          </div>
          </Transition>

          <div class="check-actions">
            <el-button :disabled="quizIndex === 0" @click="quizIndex--">上一题</el-button>
            <span v-if="review">本次得分 <strong>{{ review.score }}</strong></span>
            <el-button
              v-if="quizIndex < chapterData.quiz.length - 1"
              type="primary"
              @click="quizIndex++"
            >下一题</el-button>
            <el-button v-else-if="review" type="primary" @click="resetCheck">重新检查</el-button>
            <el-button v-else type="primary" :disabled="answers.some(answer => !answer)" :loading="submitting" @click="submitCheck">提交全部答案</el-button>
          </div>
        </section>

        <section class="complete-panel">
          <div><Flag :size="18" /><span><strong>{{ progress.status === 'completed' ? '本章已经完成' : '确认完成本章' }}</strong><small>完成后仍可回来阅读、重做检查和修改笔记</small></span></div>
          <el-button v-if="progress.status !== 'completed'" type="success" @click="completeChapter">标记本章完成</el-button>
          <el-button v-else-if="nextChapter" type="primary" @click="selectChapter(nextChapter.id)">进入下一章 →</el-button>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { bookApi } from '../../api'
import { parseMarkdown, inlineHtml } from '../../utils/markdown'
import {
  ArrowLeft, Check, ChevronRight, CircleCheckBig, BookOpen, Sparkles,
  NotebookPen, BrainCircuit, Flag, Target, Quote,
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const savingNote = ref(false)
const submitting = ref(false)
const book = ref(null)
const chapters = ref([])
const chapterData = ref(null)
const progress = ref({ status: 'not_started', progress_pct: 0, notes: '' })
const notes = ref('')
const answers = ref([])
const review = ref(null)
const briefingTab = ref('overview')
const takeawayIndex = ref(0)
const quoteIndex = ref(0)
const quizIndex = ref(0)
const activeEvidence = ref(-1)

const briefingTabs = [
  { key: 'overview', label: '章节概览', icon: BookOpen },
  { key: 'takeaways', label: '核心知识', icon: Target },
  { key: 'quotes', label: '原文依据', icon: Quote },
]

const currentChapter = computed(() => chapters.value.find(item => item.id === chapterData.value?.id))
const completedCount = computed(() => chapters.value.filter(item => item.progress.status === 'completed').length)
const answeredCount = computed(() => answers.value.filter(Boolean).length)
const currentQuizQuestion = computed(() => chapterData.value?.quiz?.[quizIndex.value] || null)
const currentReviewItem = computed(() => review.value?.items?.[quizIndex.value] || null)
const currentTakeaway = computed(() => {
  const item = chapterData.value?.knowledge_takeaways?.[takeawayIndex.value]
  if (item && typeof item === 'object') {
    return {
      title: item.title || `核心结论 ${takeawayIndex.value + 1}`,
      explanation: item.explanation || '',
      evidence: item.evidence || '',
    }
  }
  return {
    title: `核心结论 ${takeawayIndex.value + 1}`,
    explanation: typeof item === 'string' ? item : '',
    evidence: '',
  }
})
const evidenceSources = computed(() => {
  const values = [
    ...(chapterData.value?.golden_sentences || []),
    ...(chapterData.value?.knowledge_takeaways || []).map(item => (
      typeof item === 'object' ? item.evidence : ''
    )),
  ].filter(Boolean)
  return [...new Set(values)]
})
const nextChapter = computed(() => {
  const index = chapters.value.findIndex(item => item.id === chapterData.value?.id)
  return index >= 0 ? chapters.value[index + 1] : null
})
const progressLabel = computed(() => ({
  not_started: '尚未开始', in_progress: '学习中', completed: '已完成',
}[progress.value.status] || '学习中'))

const markdownBlocks = computed(() => annotateEvidence(
  parseMarkdown(chapterData.value?.markdown_content || ''),
  evidenceSources.value,
))

const loadBook = async () => {
  loading.value = true
  try {
    const data = await bookApi.detail(route.params.bookId)
    book.value = data.book
    chapters.value = data.chapters
    if (book.value.parser_status !== 'ready') {
      ElMessage.warning('教材尚未完成解析或未通过行业准入')
      router.replace('/learn/books')
      return
    }
    const requested = Number(route.query.chapter)
    const first = chapters.value.find(item => item.id === requested)
      || chapters.value.find(item => item.id === book.value.current_chapter_id)
      || chapters.value[0]
    if (first) await loadChapter(first.id)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

const loadChapter = async (chapterId) => {
  const data = await bookApi.chapter(route.params.bookId, chapterId)
  book.value = data.book
  chapterData.value = data.chapter
  progress.value = data.progress
  notes.value = data.progress.notes || ''
  review.value = data.progress.quiz_attempts?.at(-1) || null
  answers.value = review.value?.items?.length
    ? data.chapter.quiz.map((_, index) => review.value.items[index]?.user_answer || '')
    : data.chapter.quiz.map(() => '')
  briefingTab.value = 'overview'
  takeawayIndex.value = 0
  quoteIndex.value = 0
  quizIndex.value = 0
  activeEvidence.value = -1
  if (progress.value.status === 'not_started') {
    const result = await bookApi.updateProgress(book.value.id, chapterId, { action: 'start', progress_pct: 15 })
    progress.value = result.progress
  }
}
const selectChapter = async (id) => {
  await router.replace({ query: { ...route.query, chapter: id } })
  await loadChapter(id)
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
const saveNote = async () => {
  savingNote.value = true
  try {
    const result = await bookApi.updateProgress(book.value.id, chapterData.value.id, { action: 'note', notes: notes.value })
    progress.value = result.progress
    ElMessage.success('章节笔记已保存')
  } catch (e) { ElMessage.error(e.message) } finally { savingNote.value = false }
}
const submitCheck = async () => {
  submitting.value = true
  try {
    const result = await bookApi.updateProgress(book.value.id, chapterData.value.id, { action: 'quiz', answers: answers.value })
    review.value = result.review
    progress.value = result.progress
  } catch (e) { ElMessage.error(e.message) } finally { submitting.value = false }
}
const resetCheck = () => {
  answers.value = chapterData.value.quiz.map(() => '')
  review.value = null
  quizIndex.value = 0
}
const scrollToEvidence = (text) => {
  const target = normalizeEvidence(text)
  let index = evidenceSources.value.findIndex(item => {
    const source = normalizeEvidence(item)
    return source.includes(target.slice(0, 36)) || target.includes(source.slice(0, 36))
  })
  if (index < 0) index = 0
  activeEvidence.value = index
  document.getElementById(`chapter-evidence-${index}`)?.scrollIntoView({
    behavior: 'smooth',
    block: 'center',
  })
  window.setTimeout(() => {
    if (activeEvidence.value === index) activeEvidence.value = -1
  }, 2200)
}
const completeChapter = async () => {
  try {
    const result = await bookApi.updateProgress(book.value.id, chapterData.value.id, { action: 'complete' })
    progress.value = result.progress
    book.value.progress_pct = result.book_progress_pct
    const item = chapters.value.find(chapter => chapter.id === chapterData.value.id)
    if (item) item.progress = result.progress
    ElMessage.success('本章已完成')
  } catch (e) { ElMessage.error(e.message) }
}

const normalizeEvidence = (value) => String(value || '')
  .replace(/[^0-9A-Za-z\u4e00-\u9fff]/g, '')

function annotateEvidence(blocks, sources) {
  const normalizedSources = sources.map(normalizeEvidence)
  return blocks.map(block => {
    if (block.type !== 'p' && block.type !== 'quote') {
      return { ...block, evidenceIndex: -1 }
    }
    const text = normalizeEvidence(block.text)
    const evidenceIndex = normalizedSources.findIndex(source => {
      const probe = source.slice(0, Math.min(42, source.length))
      return probe.length >= 16 && (text.includes(probe) || source.includes(text.slice(0, 42)))
    })
    return { ...block, evidenceIndex }
  })
}

onMounted(loadBook)
</script>

<style scoped>
.reader-page{color:var(--text-primary)}.reader-header{min-height:190px;padding:31px 37px;display:flex;align-items:center;justify-content:space-between;gap:30px;border:1px solid #cfe4e8;border-radius:22px;color:#203847;background:radial-gradient(circle at 87% 23%,rgba(44,155,173,.11),transparent 30%),linear-gradient(120deg,#fff,#f3f9fa 57%,#eaf5f7);box-shadow:0 18px 43px rgba(20,91,111,.09);position:relative;overflow:hidden}.reader-header::after{content:"";position:absolute;width:330px;height:330px;border:1px solid rgba(35,127,145,.08);border-radius:50%;right:-95px;top:-180px;box-shadow:0 0 0 42px rgba(35,127,145,.025),0 0 0 86px rgba(35,127,145,.018)}.header-copy,.book-completion{position:relative;z-index:1}.header-copy>a{display:inline-flex;align-items:center;gap:5px;color:#5d7b87;text-decoration:none;font-size:10px}.reader-kicker{display:block;margin-top:16px;font-size:9px;letter-spacing:.15em;font-weight:850;color:#287f91}.header-copy h1{font-size:27px;margin:5px 0 7px;letter-spacing:-.03em}.header-copy p{font-size:10px;color:#778b94}.book-completion{width:160px}.book-completion strong{font-size:27px;color:#257f91}.book-completion small{display:block;color:#758991;font-size:10px;margin:2px 0 10px}.book-completion>div{height:4px;border-radius:3px;background:#dbeaec;overflow:hidden}.book-completion i{display:block;height:100%;background:linear-gradient(90deg,#2c93a5,#74cdbf);transition:width 1s}
.reader-layout{display:grid;grid-template-columns:260px 1fr;gap:16px;margin-top:16px;align-items:start}.chapter-rail{position:sticky;top:84px;max-height:calc(100vh - 105px);overflow:auto;padding:14px;border:1px solid #dfe9eb;border-radius:17px;background:rgba(255,255,255,.88);box-shadow:0 9px 25px rgba(24,77,90,.05)}.rail-head{display:flex;justify-content:space-between;padding:5px 6px 13px;border-bottom:1px solid #edf0f4}.rail-head span{font-size:12px;font-weight:750}.rail-head small{font-size:9px;color:#9298a7}.chapter-rail>button{width:100%;display:flex;align-items:center;gap:9px;padding:11px 8px;border:0;border-radius:10px;background:transparent;text-align:left;color:#626b7f;cursor:pointer;transition:.2s}.chapter-rail>button:hover{background:#f0f8f8}.chapter-rail>button.active{color:#21778a;background:#e8f6f7}.chapter-rail>button.complete .chapter-order{color:#fff;background:#12a17b}.chapter-order{width:28px;height:28px;border-radius:9px;display:grid;place-items:center;flex:none;background:#f0f2f6;color:#9096a5;font:750 9px/1 ui-monospace}.chapter-label{display:flex;flex-direction:column;min-width:0;flex:1}.chapter-label strong{font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.chapter-label small{font-size:8px;color:#a0a5b3;margin-top:2px}.chapter-rail>button>svg{color:#a8adba}
.chapter-canvas{min-width:0}.chapter-intro,.learning-lens,.chapter-insights,.markdown-article,.chapter-notes,.chapter-check,.complete-panel{border:1px solid #e5e7ef;border-radius:17px;background:#fff;box-shadow:0 8px 24px rgba(31,41,90,.045)}.chapter-intro{padding:26px 29px;display:flex;justify-content:space-between;align-items:center}.chapter-intro>div>span{font:800 9px/1 ui-monospace;color:#5b65d8;letter-spacing:.1em}.chapter-intro h2{font-size:24px;margin:7px 0 5px}.chapter-intro p{font-size:9px;color:#9ba1ae}.chapter-state{display:flex;align-items:center;gap:9px;padding:10px 12px;border-radius:11px;color:#5360d3;background:#eef0ff}.chapter-state.completed{color:#087f61;background:#e8f8f2}.chapter-state span{display:flex;flex-direction:column}.chapter-state strong{font-size:11px}.chapter-state small{font-size:8px;opacity:.72}.learning-lens{margin-top:11px;padding:18px 21px;display:flex;align-items:center;justify-content:space-between;gap:18px;background:linear-gradient(135deg,#f7f8ff,#fff)}.summary-block{display:flex;gap:10px;align-items:flex-start}.summary-block>svg{color:#5d67dc;flex:none}.summary-block span{display:flex;flex-direction:column}.summary-block strong{font-size:11px}.summary-block p{font-size:11px;line-height:1.6;color:#737b8f;margin-top:3px}.key-points{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}.key-points span{padding:4px 8px;border-radius:8px;color:#5360d1;background:#ebeeff;font-size:9px;white-space:nowrap}.chapter-insights{display:grid;grid-template-columns:1.06fr .94fr;gap:0;margin-top:11px;overflow:hidden}.insight-track{padding:22px 24px;position:relative}.insight-track+ .insight-track{border-left:1px solid #e8eaf2}.insight-title{display:flex;align-items:center;gap:9px;margin-bottom:14px;color:#5964d8}.insight-title span{display:flex;flex-direction:column}.insight-title strong{font-size:12px;color:#2a334e}.insight-title small{font-size:8px;color:#969cac;margin-top:2px}.insight-track ol{display:flex;flex-direction:column;gap:9px;list-style:none;margin:0;padding:0}.insight-track li{display:grid;grid-template-columns:28px 1fr;gap:10px;align-items:start}.insight-track li i{height:25px;border-radius:8px;display:grid;place-items:center;font:800 8px/1 ui-monospace;color:#5964d8;background:#edf0ff}.insight-track li span{font-size:10px;line-height:1.65;color:#60697d}.quotes{background:linear-gradient(145deg,#fbfcff,#f6fbfb)}.quotes blockquote{margin:0 0 9px;padding:9px 11px;border-left:2px solid #4aa9ae;border-radius:0 8px 8px 0;background:rgba(255,255,255,.76);font-size:10px;line-height:1.65;color:#667385}.quotes blockquote:last-child{margin-bottom:0}
.markdown-article{margin-top:11px;padding:38px 48px;line-height:1.85}.markdown-article h2{font-size:23px;margin:12px 0 20px;padding-bottom:12px;border-bottom:1px solid #e9ebf1}.markdown-article h3{font-size:19px;margin:34px 0 12px;color:#263054}.markdown-article h4{font-size:15px;margin:25px 0 8px;color:#39425f}.markdown-article p{font-size:13px;color:#4f586c;margin:0 0 13px}.markdown-article :deep(code){padding:2px 5px;border-radius:5px;color:#505bd1;background:#eef0ff}.markdown-article :deep(a){color:#4f5bd1}.markdown-article blockquote{margin:17px 0;padding:13px 16px;border-left:3px solid #6872df;background:#f5f6ff;color:#626b80;font-size:12px}.markdown-article ul{padding-left:20px;margin:12px 0}.markdown-article li{font-size:13px;color:#535c70;margin:5px 0}.markdown-article pre{max-width:100%;overflow:auto;padding:14px;border-radius:10px;background:#171d34;color:#d8ddf5;font-size:11px}.md-table{overflow:auto;margin:8px 0}.md-table pre{white-space:pre;background:#f7f8fb;color:#515a6d}.page-anchor{display:flex;align-items:center;gap:8px;margin:28px 0 13px;color:#a0a5b3;font-size:9px}.page-anchor::before,.page-anchor::after{content:"";height:1px;background:#eceef3;flex:1}
.chapter-notes,.chapter-check{margin-top:11px;padding:23px}.section-title{display:flex;align-items:center;gap:9px;margin-bottom:14px;color:#5761d6}.section-title>div{display:flex;flex-direction:column}.section-title strong{font-size:13px;color:#29324d}.section-title small{font-size:9px;color:#9298a8;margin-top:2px}.chapter-notes :deep(.el-textarea__inner){border-radius:11px;box-shadow:0 0 0 1px #e4e7ef inset}.chapter-notes>.el-button{margin-top:9px}.check-question{padding:18px 0;border-top:1px solid #edf0f4}.check-question>strong{display:block;font-size:12px;line-height:1.55;margin-bottom:11px}.check-options{display:grid;grid-template-columns:1fr 1fr;gap:7px}.check-options button{display:flex;gap:8px;align-items:center;text-align:left;padding:9px 11px;border:1px solid #e4e7ee;border-radius:10px;background:#fff;color:#5b6477;cursor:pointer;font-size:10px}.check-options button.selected{border-color:#7983e6;background:#f0f2ff}.check-options button.correct{border-color:#75cdb4;background:#edfaf6}.check-options button.wrong{border-color:#e59891;background:#fff1f0}.check-options i{width:22px;height:22px;border-radius:7px;display:grid;place-items:center;font-style:normal;background:#f0f2f5;font-weight:750}.answer-review{margin-top:8px;padding:9px 11px;border-radius:9px;background:#fff2f1;color:#ca5951}.answer-review.correct{background:#ebf9f4;color:#07805f}.answer-review strong{font-size:10px}.answer-review p{font-size:9px;margin-top:2px;color:#727b8c}.check-actions{display:flex;align-items:center;justify-content:flex-end;gap:9px;margin-top:13px}.check-actions>span{font-size:10px;color:#7c8496}.check-actions>span strong{font-size:16px;color:#5661d5}.complete-panel{margin-top:11px;padding:19px 23px;display:flex;align-items:center;justify-content:space-between}.complete-panel>div{display:flex;align-items:center;gap:10px;color:#159875}.complete-panel span{display:flex;flex-direction:column}.complete-panel strong{font-size:12px;color:#2e3752}.complete-panel small{font-size:9px;color:#9399a8;margin-top:2px}

/* 阅读器可读性层：教材页面以长时间阅读为主，不沿用数据看板的小字号密度。 */
.reader-layout{
  grid-template-columns:clamp(290px,18vw,336px) minmax(0,1fr);
  gap:24px;
  margin-top:24px;
}
.chapter-rail{
  top:92px;
  max-height:calc(100vh - 116px);
  padding:18px 14px;
  border-radius:20px;
}
.rail-head{padding:7px 9px 16px}
.rail-head span{font-size:15px}
.rail-head small{font-size:12px}
.chapter-rail>button{
  gap:12px;
  min-height:68px;
  padding:13px 11px;
  margin-top:4px;
  border:1px solid transparent;
  border-radius:14px;
}
.chapter-rail>button:hover{
  border-color:#d8ecef;
  background:#f2f9fa;
  transform:translateX(2px);
}
.chapter-rail>button.active{
  border-color:#b8dfe5;
  box-shadow:0 8px 20px rgba(36,126,145,.09);
}
.chapter-order{
  width:36px;
  height:36px;
  border-radius:11px;
  font-size:11px;
}
.chapter-label strong{font-size:14px;line-height:1.4}
.chapter-label small{font-size:11px;margin-top:4px}
.chapter-rail>button>svg{width:18px;height:18px}

.chapter-intro,.learning-lens,.chapter-insights,.markdown-article,.chapter-notes,.chapter-check,.complete-panel{
  border-radius:20px;
}
.chapter-intro{padding:32px 36px}
.chapter-intro>div>span{font-size:11px}
.chapter-intro h2{max-width:920px;font-size:30px;line-height:1.32;margin:10px 0 8px}
.chapter-intro p{font-size:12px}
.chapter-state{gap:11px;padding:13px 16px;border-radius:13px}
.chapter-state strong{font-size:14px}
.chapter-state small{font-size:11px;margin-top:3px}

.learning-lens{margin-top:16px;padding:24px 28px;gap:24px}
.summary-block{gap:13px}
.summary-block>svg{width:21px;height:21px}
.summary-block strong{font-size:15px}
.summary-block p{max-width:920px;font-size:15px;line-height:1.85;margin-top:7px}
.key-points{gap:8px}
.key-points span{padding:7px 11px;border-radius:10px;font-size:12px}

.chapter-insights{margin-top:16px}
.insight-track{padding:28px 30px}
.insight-title{gap:11px;margin-bottom:20px}
.insight-title>svg{width:21px;height:21px}
.insight-title strong{font-size:16px}
.insight-title small{font-size:11px;margin-top:4px}
.insight-track ol{gap:14px}
.insight-track li{grid-template-columns:34px 1fr;gap:13px}
.insight-track li i{height:31px;border-radius:9px;font-size:10px}
.insight-track li span{font-size:14px;line-height:1.8}
.quotes blockquote{
  margin-bottom:13px;
  padding:13px 15px;
  border-left-width:3px;
  font-size:14px;
  line-height:1.8;
}

.markdown-article{margin-top:16px;padding:46px clamp(36px,5vw,76px);line-height:1.95}
.markdown-article h2{font-size:29px;line-height:1.4;margin:15px 0 26px;padding-bottom:17px}
.markdown-article h3{font-size:23px;line-height:1.45;margin:42px 0 17px}
.markdown-article h4{font-size:19px;line-height:1.5;margin:30px 0 12px}
.markdown-article p{font-size:16.5px;line-height:1.95;color:#465268;margin-bottom:19px}
.markdown-article blockquote{margin:22px 0;padding:17px 21px;font-size:15px;line-height:1.85}
.markdown-article ul{padding-left:25px;margin:18px 0}
.markdown-article li{font-size:16px;line-height:1.85;margin:8px 0}
.markdown-article pre{padding:18px;border-radius:13px;font-size:14px;line-height:1.7}
.page-anchor{margin:34px 0 17px;font-size:11px}

.chapter-notes,.chapter-check{margin-top:16px;padding:30px 34px}
.section-title{gap:11px;margin-bottom:20px}
.section-title>svg{width:21px;height:21px}
.section-title strong{font-size:17px}
.section-title small{font-size:12px;margin-top:4px}
.chapter-notes :deep(.el-textarea__inner){
  min-height:138px!important;
  padding:16px 18px;
  border-radius:14px;
  font-size:15px;
  line-height:1.75;
}
.chapter-notes>.el-button{height:40px;margin-top:12px;padding:0 20px;font-size:14px}
.check-question{padding:27px 0}
.check-question>strong{font-size:17px;line-height:1.65;margin-bottom:17px}
.check-options{gap:12px}
.check-options button{
  min-height:68px;
  align-items:flex-start;
  gap:12px;
  padding:15px 17px;
  border-radius:14px;
  font-size:14.5px;
  line-height:1.65;
  transition:border-color .18s,background .18s,box-shadow .18s,transform .18s;
}
.check-options button:not(:disabled):hover{
  border-color:#aab1f0;
  background:#f7f8ff;
  box-shadow:0 8px 20px rgba(67,77,166,.08);
  transform:translateY(-1px);
}
.check-options i{
  width:30px;
  height:30px;
  border-radius:9px;
  flex:none;
  font-size:13px;
}
.answer-review{margin-top:13px;padding:14px 17px;border-radius:12px}
.answer-review strong{font-size:14px}
.answer-review p{font-size:13px;line-height:1.7;margin-top:5px}
.check-actions{gap:12px;margin-top:19px}
.check-actions>span{font-size:13px}
.check-actions>span strong{font-size:20px}
.check-actions :deep(.el-button){height:44px;padding:0 24px;font-size:15px}

.complete-panel{margin-top:16px;padding:24px 30px}
.complete-panel>div{gap:13px}
.complete-panel strong{font-size:16px}
.complete-panel small{font-size:12px;margin-top:4px}
.complete-panel :deep(.el-button){height:44px;padding:0 24px;font-size:15px}

.chapter-briefing{
  margin-top:16px;
  padding:26px 28px 28px;
  border:1px solid #dfe5f1;
  border-radius:20px;
  background:linear-gradient(145deg,#fff 30%,#f8faff);
  box-shadow:0 12px 30px rgba(31,41,90,.055);
  overflow:hidden;
}
.briefing-head{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:24px;
  padding-bottom:20px;
  border-bottom:1px solid #e9edf5;
}
.briefing-head .section-title{margin-bottom:0}
.briefing-tabs{
  display:flex;
  align-items:center;
  gap:5px;
  padding:5px;
  border:1px solid #e2e6f0;
  border-radius:14px;
  background:#f2f4f8;
}
.briefing-tabs button{
  display:flex;
  align-items:center;
  gap:7px;
  min-height:39px;
  padding:0 14px;
  border:0;
  border-radius:10px;
  color:#697388;
  background:transparent;
  font-size:13px;
  font-weight:700;
  cursor:pointer;
  transition:color .18s,background .18s,box-shadow .18s,transform .18s;
}
.briefing-tabs button:hover{color:#4f5bd1;transform:translateY(-1px)}
.briefing-tabs button.active{
  color:#fff;
  background:linear-gradient(135deg,#5864df,#717bf0);
  box-shadow:0 7px 16px rgba(83,95,212,.23);
}
.brief-panel{
  min-height:210px;
  display:grid;
  align-items:center;
  position:relative;
  margin-top:22px;
  padding:28px 30px;
  border:1px solid #e4e8f3;
  border-radius:17px;
  background:#fff;
}
.overview-panel{grid-template-columns:66px 1fr;gap:22px}
.brief-index{
  width:58px;
  height:58px;
  display:grid;
  place-items:center;
  align-self:start;
  border-radius:18px;
  color:#5662d7;
  background:#eef0ff;
  font:850 16px/1 ui-monospace;
}
.brief-panel small{
  display:block;
  margin-bottom:9px;
  color:#727cef;
  font-size:12px;
  font-weight:800;
  letter-spacing:.05em;
}
.brief-panel p{
  max-width:980px;
  margin:0;
  color:#3f4a61;
  font-size:14.5px;
  line-height:1.8;
}
.brief-panel .key-points{justify-content:flex-start;margin-top:19px}
.focus-panel{
  grid-template-columns:66px minmax(0,1fr) auto;
  gap:22px;
  background:
    radial-gradient(circle at 90% 15%,rgba(101,113,231,.10),transparent 28%),
    #fff;
}
.focus-copy p{max-width:900px;font-size:16px;line-height:1.8;color:#303b55}
.quote-panel{
  grid-template-columns:52px minmax(0,1fr) auto;
  gap:18px;
  border-color:#d7ecea;
  background:
    radial-gradient(circle at 8% 10%,rgba(43,159,153,.10),transparent 28%),
    linear-gradient(145deg,#fbfffe,#f5fbfb);
}
.quote-panel>svg{align-self:start;color:#299a99}
.quote-panel small{color:#278d8b}
.quote-panel blockquote{
  max-width:980px;
  margin:0;
  color:#354a55;
  font-size:17px;
  font-weight:560;
  line-height:1.9;
}
.locate-evidence{
  display:inline-flex;
  align-items:center;
  margin-top:17px;
  padding:0 0 4px;
  border:0;
  border-bottom:1px solid currentColor;
  color:#5965d8;
  background:transparent;
  font-size:12px;
  font-weight:750;
  cursor:pointer;
  opacity:.86;
  transition:opacity .18s,transform .18s;
}
.quote-panel .locate-evidence{color:#278d8b}
.locate-evidence:hover{opacity:1;transform:translateY(1px)}
.brief-pager{
  align-self:end;
  display:flex;
  gap:7px;
}
.brief-pager button{
  width:32px;
  height:32px;
  border:1px solid #dfe4ef;
  border-radius:10px;
  color:#8991a4;
  background:#fff;
  font-size:12px;
  font-weight:800;
  cursor:pointer;
  transition:.18s;
}
.brief-pager button:hover{border-color:#818be5;color:#5662d7}
.brief-pager button.active{
  border-color:#5d69df;
  color:#fff;
  background:#5d69df;
  box-shadow:0 6px 13px rgba(83,95,212,.2);
}
.brief-panel-enter-active,.brief-panel-leave-active{transition:opacity .18s,transform .18s}
.brief-panel-enter-from{opacity:0;transform:translateX(12px)}
.brief-panel-leave-to{opacity:0;transform:translateX(-8px)}

.chapter-check{
  background:
    radial-gradient(circle at 94% 6%,rgba(94,105,225,.075),transparent 22%),
    #fff;
}
.check-head{
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:24px;
}
.check-head .section-title{margin-bottom:0}
.check-progress{width:190px;flex:none}
.check-progress>span{
  display:block;
  margin-bottom:8px;
  color:#6e778c;
  font-size:12px;
  text-align:right;
}
.check-progress>div{height:6px;border-radius:99px;background:#e9ecf4;overflow:hidden}
.check-progress i{
  display:block;
  height:100%;
  border-radius:inherit;
  background:linear-gradient(90deg,#5965df,#42b7aa);
  transition:width .3s ease;
}
.question-nav{
  display:flex;
  gap:9px;
  margin-top:23px;
  padding-top:20px;
  border-top:1px solid #e9edf4;
}
.question-nav button{
  width:38px;
  height:38px;
  border:1px solid #dfe3ed;
  border-radius:12px;
  color:#7e879b;
  background:#fff;
  font-size:13px;
  font-weight:800;
  cursor:pointer;
  transition:.18s;
}
.question-nav button:hover{border-color:#8993e8;color:#5964d8}
.question-nav button.answered{color:#5360d3;background:#eef0ff}
.question-nav button.active{
  border-color:#5964d8;
  color:#fff;
  background:#5964d8;
  box-shadow:0 7px 16px rgba(83,95,212,.23);
}
.question-nav button.correct{border-color:#36a985;color:#087b5e;background:#e8f8f2}
.question-nav button.wrong{border-color:#df7b73;color:#bd514a;background:#fff0ef}
.question-nav button.active.correct{color:#fff;background:#159875}
.question-nav button.active.wrong{color:#fff;background:#d9655e}
.chapter-check .check-question{
  min-height:390px;
  margin-top:18px;
  padding:27px 29px 30px;
  border:1px solid #e3e7f1;
  border-radius:17px;
  background:rgba(255,255,255,.82);
}
.question-count{
  display:block;
  margin-bottom:10px;
  color:#6974e6;
  font:850 11px/1 ui-monospace;
  letter-spacing:.09em;
}
.chapter-check .check-question>strong{
  max-width:1060px;
  font-size:18px;
  line-height:1.65;
}
.chapter-check .check-options{margin-top:19px}
.chapter-check .check-actions{
  justify-content:space-between;
  min-height:44px;
}
.chapter-check .check-actions>span{margin-left:auto}

.evidence-paragraph{
  position:relative;
  margin:25px -18px;
  padding:25px 28px 7px;
  border:1px solid #d4e9e7;
  border-left:4px solid #31a19a;
  border-radius:4px 15px 15px 4px;
  background:linear-gradient(105deg,#f3fbfa,#fbfefd 72%);
  box-shadow:0 8px 24px rgba(34,131,126,.07);
  scroll-margin-top:110px;
}
.evidence-paragraph>span{
  display:inline-flex;
  align-items:center;
  gap:5px;
  margin-bottom:10px;
  color:#248d88;
  font-size:11px;
  font-weight:850;
  letter-spacing:.06em;
}
.evidence-paragraph p{color:#344c56}
.evidence-paragraph.pulse{animation:evidence-pulse 1.05s ease-in-out 2}
@keyframes evidence-pulse{
  50%{
    border-color:#38aaa4;
    background:#e9f8f6;
    box-shadow:0 0 0 6px rgba(49,161,154,.10),0 12px 30px rgba(34,131,126,.12);
  }
}

@media(max-width:900px){
  .reader-layout{grid-template-columns:1fr}
  .chapter-rail{position:static;max-height:280px}
  .learning-lens{align-items:flex-start;flex-direction:column}
  .key-points{justify-content:flex-start}
  .briefing-head{align-items:flex-start;flex-direction:column}
  .briefing-tabs{width:100%}
  .briefing-tabs button{flex:1;justify-content:center}
}
@media(max-width:700px){
  .chapter-insights{grid-template-columns:1fr}
  .insight-track+.insight-track{border-left:0;border-top:1px solid #e8eaf2}
  .focus-panel,.quote-panel{grid-template-columns:52px 1fr}
  .brief-pager{grid-column:2;justify-self:start;margin-top:4px}
  .check-head{flex-direction:column}
  .check-progress{width:100%}
  .check-progress>span{text-align:left}
}
@media(max-width:620px){
  .reader-header{padding:25px 21px}
  .book-completion{display:none}
  .chapter-intro{align-items:flex-start;flex-direction:column;gap:14px}
  .markdown-article{padding:26px 21px}
  .check-options{grid-template-columns:1fr}
  .complete-panel{align-items:flex-start;flex-direction:column;gap:14px}
  .chapter-briefing,.chapter-notes,.chapter-check{padding:22px 18px}
  .briefing-tabs{display:grid;grid-template-columns:1fr 1fr 1fr}
  .briefing-tabs button{padding:0 7px;font-size:12px}
  .overview-panel,.focus-panel,.quote-panel{grid-template-columns:1fr;padding:23px 20px}
  .brief-index{width:46px;height:46px}
  .brief-pager{grid-column:1}
  .chapter-check .check-question{min-height:0;padding:23px 18px}
}
@media(prefers-reduced-motion:reduce){
  .book-completion i,.chapter-rail>button,.brief-panel-enter-active,.brief-panel-leave-active{transition:none}
  .evidence-paragraph.pulse{animation:none}
}
</style>
