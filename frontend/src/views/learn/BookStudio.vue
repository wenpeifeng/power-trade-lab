<template>
  <div class="book-studio" v-loading="loading">
    <section class="studio-hero">
      <div class="hero-copy">
        <span class="eyebrow"><LibraryBig :size="14" /> PERSONAL COURSE FOUNDRY</span>
        <h1>把一本行业书，变成<br><em>会带你学的课程</em></h1>
        <p>上传 PDF 或 Word。系统使用 MinerU 转成结构化 Markdown，先判断是否属于电力行业，再生成章节、重点、练习和进度。</p>
        <div class="engine-state" :class="{ online: mineru.available }">
          <span class="engine-dot"></span>
          <strong>{{ mineru.available ? 'MinerU 解析引擎在线' : 'MinerU 尚未连接' }}</strong>
          <small>{{ mineru.message }}</small>
        </div>
      </div>
      <div class="transform-visual" aria-label="文件到课程的转换流程">
        <div class="paper source-paper"><FileType2 :size="28" /><span>PDF / DOCX</span><i>原始资产</i></div>
        <div class="transform-beam"><span></span><span></span><span></span></div>
        <div class="paper course-paper">
          <BookOpenCheck :size="28" /><span>章节课程</span><i>可学习资产</i>
          <b v-for="n in 3" :key="n"></b>
        </div>
        <span class="mineru-badge">MinerU → MD</span>
      </div>
    </section>

    <section class="ingest-panel">
      <div class="panel-copy">
        <span class="section-kicker">IMPORT A BOOK</span>
        <h2>导入你的第一本电力教材</h2>
        <p>原文件与 Markdown 会作为个人资产保留。只有通过行业相关性检测，才会生成学习路径。</p>
        <div class="pipeline">
          <span><i>1</i>版面解析</span><b></b>
          <span><i>2</i>行业检测</span><b></b>
          <span><i>3</i>章节重建</span><b></b>
          <span><i>4</i>练习生成</span>
        </div>
      </div>
      <div class="upload-side">
        <el-input v-model="bookTitle" placeholder="教材名称（不填则使用文件名）" clearable />
        <el-upload
          drag
          :show-file-list="false"
          :before-upload="uploadBook"
          accept=".pdf,.doc,.docx"
          :disabled="uploading"
        >
          <div class="upload-content">
            <span class="upload-icon"><UploadCloud :size="28" /></span>
            <strong>{{ uploading ? '正在上传…' : '拖入教材，或点击选择文件' }}</strong>
            <small>PDF / DOC / DOCX · 最大 300MB</small>
          </div>
        </el-upload>
        <p v-if="!mineru.available" class="fallback-note">
          <Info :size="13" /> 当前 PDF 会使用全文降级解析；扫描 PDF 和 Word 需要连接 MinerU。
        </p>
      </div>
    </section>

    <section class="library-section">
      <div class="section-heading">
        <div><span class="section-kicker">MY BOOK ASSETS</span><h2>我的教材库</h2></div>
        <div class="library-stats">
          <span><strong v-count="summary.ready">0</strong>可学习</span>
          <span><strong v-count="summary.processing">0</strong>解析中</span>
          <span><strong v-count="summary.rejected">0</strong>未通过</span>
          <button @click="loadAll"><RefreshCw :size="14" /> 刷新</button>
        </div>
      </div>

      <div v-if="!books.length" class="empty-library">
        <span><BookDashed :size="34" /></span>
        <h3>教材库还是空的</h3>
        <p>建议从《电力市场基础》《电力交易员培训教材》或省级交易规则汇编开始。</p>
      </div>

      <div v-else class="book-grid">
        <article v-for="book in books" :key="book.id" class="book-card" :class="book.parser_status">
          <div class="book-spine"><span>{{ fileLabel(book.file_type) }}</span></div>
          <div class="book-content">
            <div class="book-top">
              <span class="status-pill" :class="book.parser_status">
                <LoaderCircle v-if="book.parser_status === 'processing'" :size="12" />
                <CheckCircle2 v-else-if="book.parser_status === 'ready'" :size="12" />
                <ShieldX v-else-if="book.parser_status === 'rejected'" :size="12" />
                <CircleAlert v-else :size="12" />
                {{ statusLabel(book.parser_status) }}
              </span>
              <div class="book-actions">
                <button
                  v-if="mineru.available && book.parser_status !== 'processing'"
                  class="reparse-book"
                  :class="{ recommended: book.parser_engine === 'pdfplumber-fulltext' }"
                  :disabled="reprocessingId === book.id"
                  :title="book.parser_engine === 'pdfplumber-fulltext' ? '当前是降级解析，建议用 MinerU 修复乱码' : '使用 MinerU 重新生成课程'"
                  @click="reprocessBook(book)"
                >
                  <RefreshCw :size="14" :class="{ spinning: reprocessingId === book.id }" />
                  <span>{{ book.parser_engine === 'pdfplumber-fulltext' ? '修复解析' : '重新解析' }}</span>
                </button>
                <button v-if="book.markdown_ready" class="download-book" title="下载 Markdown" @click="downloadMarkdown(book)">
                  <Download :size="15" />
                </button>
              </div>
            </div>
            <h3>{{ book.title }}</h3>
            <p>{{ book.parser_message }}</p>
            <div v-if="book.parser_engine === 'pdfplumber-fulltext'" class="quality-warning">
              <CircleAlert :size="13" />
              当前为字符流降级结果，可能出现乱码、错序和伪章节，请点击“修复解析”
            </div>

            <template v-if="book.parser_status === 'ready'">
              <div class="book-metrics">
                <span><strong v-count="book.chapter_count">0</strong>章节</span>
                <span><strong>{{ formatWords(book.word_count) }}</strong>字</span>
                <span><strong>{{ Math.round((book.industry_relevance || 0) * 100) }}%</strong>行业相关</span>
              </div>
              <div class="book-progress"><i :style="{ width: `${book.progress_pct}%` }"></i></div>
              <div class="card-foot">
                <small>已完成 {{ book.progress_pct }}%</small>
                <button class="open-book" @click="$router.push(`/learn/books/${book.id}`)">
                  {{ book.progress_pct ? '继续学习' : '打开课程' }} <ArrowRight :size="14" />
                </button>
              </div>
            </template>
            <div v-else-if="book.parser_status === 'processing'" class="processing-line">
              <i></i><span>后台正在解析，完成后会自动出现在课程目录中</span>
            </div>
            <div v-else class="relevance-box">
              <strong>准入说明</strong><span>{{ book.relevance_reason || '没有识别到足够的电力行业内容' }}</span>
            </div>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { bookApi } from '../../api'
import {
  LibraryBig, FileType2, BookOpenCheck, UploadCloud, Info, RefreshCw,
  BookDashed, LoaderCircle, CheckCircle2, ShieldX, CircleAlert,
  Download, ArrowRight,
} from 'lucide-vue-next'

const loading = ref(false)
const uploading = ref(false)
const reprocessingId = ref(null)
const bookTitle = ref('')
const mineru = ref({ available: false, message: '正在检测解析引擎…' })
const books = ref([])
const summary = ref({ ready: 0, processing: 0, rejected: 0 })
const MAX_BOOK_SIZE = 300 * 1024 * 1024
let pollTimer = null

const statusLabel = (status) => ({
  processing: '解析中', ready: '可学习', rejected: '行业检测未通过', failed: '解析失败',
}[status] || status)
const fileLabel = (type) => String(type || '').toUpperCase()
const formatWords = (value) => Number(value || 0).toLocaleString('zh-CN')

const loadAll = async (quiet = false) => {
  if (!quiet) loading.value = true
  try {
    const [status, list] = await Promise.all([bookApi.mineruStatus(), bookApi.list()])
    mineru.value = status
    books.value = list.items
    summary.value = list
    if (list.processing && !pollTimer) {
      pollTimer = setInterval(() => loadAll(true), 4000)
    } else if (!list.processing && pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

const uploadBook = async (file) => {
  if (file.size > MAX_BOOK_SIZE) {
    ElMessage.error('教材文件不能超过 300MB')
    return false
  }
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', file)
    if (bookTitle.value.trim()) formData.append('title', bookTitle.value.trim())
    const result = await bookApi.upload(formData)
    if (result.dedup) ElMessage.info('这本教材已经在你的教材库中')
    else ElMessage.success('教材已入库，正在后台解析并生成章节')
    bookTitle.value = ''
    await loadAll(true)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    uploading.value = false
  }
  return false
}

const downloadMarkdown = async (book) => {
  try {
    const blob = await bookApi.downloadMarkdown(book.id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${book.title}.md`
    link.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

const reprocessBook = async (book) => {
  try {
    await ElMessageBox.confirm(
      `将使用 MinerU 重新解析《${book.title}》，成功后会替换现有章节，并重置这本书的章节进度、笔记和测验记录。`,
      '修复教材解析',
      {
        confirmButtonText: '开始重新解析',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    reprocessingId.value = book.id
    await bookApi.reprocess(book.id)
    ElMessage.success('已进入 MinerU 解析队列，完成后会自动刷新')
    await loadAll(true)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || '重新解析失败')
  } finally {
    reprocessingId.value = null
  }
}

onMounted(loadAll)
onUnmounted(() => pollTimer && clearInterval(pollTimer))
</script>

<style scoped>
.book-studio{color:var(--text-primary)}.studio-hero{min-height:330px;display:grid;grid-template-columns:1.08fr .92fr;gap:40px;align-items:center;padding:46px 52px;border:1px solid #cfe4e8;border-radius:26px;color:#203847;background:radial-gradient(circle at 83% 24%,rgba(44,155,173,.11),transparent 30%),linear-gradient(120deg,#fff,#f3f9fa 57%,#eaf5f7);box-shadow:0 20px 46px rgba(20,91,111,.1);position:relative;overflow:hidden}.studio-hero::after{content:"";position:absolute;inset:0;background-image:linear-gradient(rgba(35,127,145,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(35,127,145,.045) 1px,transparent 1px);background-size:32px 32px;mask-image:linear-gradient(90deg,transparent,#000)}.hero-copy,.transform-visual{position:relative;z-index:1}.eyebrow,.section-kicker{display:inline-flex;align-items:center;gap:7px;color:#287f91;font-size:10px;letter-spacing:.15em;font-weight:850}.hero-copy h1{margin:12px 0 13px;font-size:37px;line-height:1.18;letter-spacing:-.04em}.hero-copy h1 em{font-style:normal;color:#23899b}.hero-copy>p{max-width:620px;color:#687c87;font-size:13px;line-height:1.8}.engine-state{margin-top:24px;display:grid;grid-template-columns:auto auto 1fr;align-items:center;gap:8px 9px;width:fit-content;padding:10px 13px;border:1px solid #d2e4e7;border-radius:11px;background:rgba(255,255,255,.76)}.engine-state strong{font-size:11px}.engine-state small{font-size:10px;color:#84949c}.engine-dot{width:8px;height:8px;border-radius:50%;background:#f6a94d;box-shadow:0 0 0 5px rgba(246,169,77,.1)}.engine-state.online .engine-dot{background:#34ae8e;box-shadow:0 0 0 5px rgba(52,174,142,.1)}
.transform-visual{height:220px}.paper{position:absolute;width:145px;height:180px;border:1px solid #d8e7e9;border-radius:9px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;background:rgba(255,255,255,.96);color:#28485a;box-shadow:0 18px 38px rgba(28,86,101,.15)}.paper span{font-size:13px;font-weight:800}.paper i{font-size:9px;font-style:normal;color:#8699a2}.source-paper{left:12px;top:17px;transform:rotate(-5deg)}.course-paper{right:8px;top:8px;transform:rotate(5deg);background:#fff}.course-paper b{width:78px;height:3px;border-radius:2px;background:#dbe8ea}.course-paper b:nth-of-type(2){width:58px}.transform-beam{position:absolute;left:155px;right:145px;top:102px;height:2px;background:linear-gradient(90deg,rgba(44,155,173,.14),#2c9bad,rgba(44,155,173,.14));box-shadow:0 0 14px rgba(44,155,173,.32)}.transform-beam span{position:absolute;width:7px;height:7px;border-radius:50%;top:-3px;background:#2c9bad;animation:beamMove 2.4s linear infinite}.transform-beam span:nth-child(2){animation-delay:.8s}.transform-beam span:nth-child(3){animation-delay:1.6s}.mineru-badge{position:absolute;left:50%;top:65px;transform:translateX(-50%);font:750 10px/1 ui-monospace;color:#287f91;white-space:nowrap}
.ingest-panel{margin:18px 0 44px;padding:26px 30px;display:grid;grid-template-columns:1fr 1fr;gap:36px;align-items:center;border:1px solid #dce9eb;border-radius:19px;background:rgba(255,255,255,.88);box-shadow:0 10px 28px rgba(22,91,108,.06)}.section-kicker{color:#237f91}.panel-copy h2,.section-heading h2{font-size:22px;margin:6px 0 8px;letter-spacing:-.025em}.panel-copy>p{font-size:12px;line-height:1.7;color:#7e8698;max-width:520px}.pipeline{margin-top:22px;display:flex;align-items:center;gap:7px}.pipeline span{display:flex;align-items:center;gap:5px;color:#646d82;font-size:10px;white-space:nowrap}.pipeline i{width:20px;height:20px;border-radius:7px;display:grid;place-items:center;font-style:normal;color:#237f91;background:#e9f7f8;font-weight:800}.pipeline b{flex:1;height:1px;background:#d9e8ea}.upload-side{display:flex;flex-direction:column;gap:9px}.upload-side :deep(.el-input__wrapper){border-radius:10px}.upload-side :deep(.el-upload-dragger){padding:18px;border-radius:13px;background:#f5fbfb;border:1px dashed #9bc9cf}.upload-side :deep(.el-upload-dragger:hover){border-color:#2c96a7;background:#eefafa}.upload-content{display:flex;align-items:center;justify-content:center;gap:12px}.upload-content strong{font-size:12px}.upload-content small{font-size:9px;color:#959bab}.upload-icon{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;color:#237f91;background:#e5f6f7}.fallback-note{display:flex;align-items:center;gap:5px;color:#c07626;font-size:10px}
.section-heading{display:flex;justify-content:space-between;align-items:end;margin-bottom:17px}.library-stats{display:flex;align-items:center;gap:18px}.library-stats span{font-size:10px;color:#9298a8}.library-stats strong{font-size:15px;color:#374160;margin-right:3px}.library-stats button{display:flex;align-items:center;gap:5px;border:0;background:transparent;color:#247f91;cursor:pointer;font-size:11px}.book-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.book-card{min-height:290px;display:grid;grid-template-columns:12px 1fr;border:1px solid #e1e9eb;border-radius:18px;background:#fff;overflow:hidden;box-shadow:0 8px 24px rgba(31,66,78,.05);transition:transform .25s,box-shadow .25s,border-color .25s}.book-card:hover{transform:translateY(-4px);border-color:#9fcbd0;box-shadow:0 16px 34px rgba(32,104,118,.11)}.book-spine{background:linear-gradient(180deg,#21778c,#49aebb);position:relative}.book-spine span{position:absolute;top:17px;left:-12px;transform:rotate(-90deg);font:800 8px/1 ui-monospace;color:rgba(255,255,255,.75)}.book-card.rejected .book-spine,.book-card.failed .book-spine{background:linear-gradient(#a6aab6,#777d8c)}.book-content{padding:21px 22px;display:flex;flex-direction:column}.book-top{display:flex;justify-content:space-between;gap:12px}.book-actions{display:flex;align-items:center;gap:6px}.book-actions button{height:30px;border:0;border-radius:9px;color:#287f90;background:#eff7f8;cursor:pointer;transition:transform .2s,background .2s,box-shadow .2s}.book-actions button:hover{transform:translateY(-2px);background:#e3f3f5;box-shadow:0 5px 13px rgba(35,127,145,.12)}.book-actions button:disabled{cursor:wait;opacity:.65}.download-book{width:30px;display:grid;place-items:center}.reparse-book{display:flex;align-items:center;gap:5px;padding:0 9px;font-size:9px;font-weight:750}.reparse-book.recommended{color:#fff;background:linear-gradient(135deg,#248a9c,#36aeba);box-shadow:0 6px 14px rgba(36,138,156,.18)}.reparse-book.recommended:hover{background:linear-gradient(135deg,#207f91,#2c9eac)}.reparse-book .spinning{animation:spin 1s linear infinite}.status-pill{display:inline-flex;align-items:center;gap:5px;width:fit-content;padding:4px 8px;border-radius:9px;font-size:9px;font-weight:750;color:#247b8d;background:#e9f6f7}.status-pill.processing svg{animation:spin 1.3s linear infinite}.status-pill.ready{color:#078763;background:#e8f8f2}.status-pill.rejected,.status-pill.failed{color:#b86737;background:#fff1e9}.book-content h3{font-size:17px;margin:13px 0 7px}.book-content>p{font-size:11px;color:#858c9d;line-height:1.6;min-height:36px}.quality-warning{display:flex;align-items:flex-start;gap:6px;margin-top:2px;padding:8px 10px;border-radius:9px;color:#a46324;background:#fff7e8;font-size:9px;line-height:1.5}.quality-warning svg{flex:none;margin-top:1px}.book-metrics{display:flex;gap:23px;margin:16px 0}.book-metrics span{display:flex;flex-direction:column;color:#9ba1af;font-size:9px}.book-metrics strong{font-size:15px;color:#39425e}.book-progress{height:4px;border-radius:3px;background:#edf0f5;overflow:hidden}.book-progress i{display:block;height:100%;background:linear-gradient(90deg,#27869a,#69d2c5);transition:width 1s}.card-foot{margin-top:auto;padding-top:13px;display:flex;justify-content:space-between;align-items:center}.card-foot small{font-size:9px;color:#999fac}.open-book{display:flex;align-items:center;gap:5px;border:0;background:transparent;color:#237f91;font-size:11px;font-weight:700;cursor:pointer}.processing-line{margin-top:auto;padding-top:18px;display:flex;align-items:center;gap:8px;color:#8b92a3;font-size:10px}.processing-line i{width:44px;height:3px;border-radius:2px;background:linear-gradient(90deg,#247f91,#78d7cd,#247f91);background-size:200%;animation:flow 1.5s linear infinite}.relevance-box{margin-top:auto;padding:11px;border-radius:10px;background:#f7f8fa;display:flex;flex-direction:column;gap:4px}.relevance-box strong{font-size:10px}.relevance-box span{font-size:10px;line-height:1.5;color:#858c9c}.empty-library{text-align:center;padding:65px;border:1px dashed #d9dce7;border-radius:18px;background:rgba(255,255,255,.55)}.empty-library>span{width:58px;height:58px;border-radius:18px;display:grid;place-items:center;margin:0 auto 12px;color:#247f91;background:#e8f6f7}.empty-library h3{font-size:15px;margin-bottom:5px}.empty-library p{font-size:11px;color:#9298a8}
@keyframes beamMove{from{left:0;opacity:0}15%{opacity:1}85%{opacity:1}to{left:100%;opacity:0}}@keyframes spin{to{transform:rotate(360deg)}}@keyframes flow{to{background-position:-200%}}@media(max-width:900px){.studio-hero,.ingest-panel{grid-template-columns:1fr}.transform-visual{max-width:460px;width:100%;margin:auto}.book-grid{grid-template-columns:1fr}.pipeline{flex-wrap:wrap}.pipeline b{min-width:18px}}@media(max-width:620px){.studio-hero{padding:30px 22px}.hero-copy h1{font-size:30px}.transform-visual{display:none}.ingest-panel{padding:20px}.upload-content{flex-direction:column}.section-heading{align-items:flex-start;flex-direction:column;gap:10px}.library-stats{width:100%;justify-content:space-between;gap:8px}}@media(prefers-reduced-motion:reduce){.transform-beam span,.processing-line i,.status-pill.processing svg{animation:none}.book-card{transition:none}}
</style>
