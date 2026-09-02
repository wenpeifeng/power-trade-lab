<template>
  <div class="kb-glossary">
    <!-- ============ 顶部：搜索 + 分类筛选 + 排序 ============ -->
    <section class="gl-toolbar">
      <div class="gl-search">
        <Search :size="16" class="gl-search-ic" />
        <el-input
          v-model="q"
          placeholder="搜索术语 / 英文缩写 / 大白话释义…"
          size="large"
          clearable
          class="gl-search-input"
        />
      </div>
      <div class="gl-sort">
        <button
          v-for="m in SORT_MODES" :key="m.key"
          class="gl-sort-btn"
          :class="{ active: sort === m.key }"
          @click="sort = m.key"
        >{{ m.label }}</button>
      </div>
      <div class="gl-chips">
        <button
          class="gl-chip"
          :class="{ active: cat === '' }"
          @click="cat = ''"
        >全部 <span class="gl-chip-num">{{ GLOSSARY.length }}</span></button>
        <button
          v-for="c in CATEGORIES" :key="c"
          class="gl-chip"
          :class="{ active: cat === c }"
          @click="cat = c"
        >{{ c }}<span class="gl-chip-num">{{ catCount(c) }}</span></button>
      </div>
    </section>

    <div class="gl-meta">
      <span v-if="filtered.length === GLOSSARY.length">共 {{ GLOSSARY.length }} 条术语</span>
      <span v-else>命中 <strong>{{ filtered.length }}</strong> / {{ GLOSSARY.length }} 条</span>
      <span v-if="filtered.length" class="gl-page-meta">第 {{ pageStart }}–{{ pageEnd }} 条</span>
      <span class="gl-meta-hint" v-if="q || cat">小白看「大白话」，点开「精确释义」看专家校准</span>
    </div>

    <!-- ============ 列表 ============ -->
    <div class="gl-list">
      <article
        v-for="t in pagedTerms" :key="t.term"
        class="gl-card"
      >
        <div class="gl-card-head">
          <div class="gl-term">
            <span class="gl-term-zh">{{ t.term }}</span>
            <span v-if="t.en" class="gl-term-en">{{ t.en }}</span>
          </div>
          <span class="gl-cat-tag" :class="catClass(t.category)">{{ t.category }}</span>
        </div>

        <p class="gl-plain">
          <span class="gl-plain-label">大白话</span>{{ t.plain }}
        </p>

        <details class="gl-precise">
          <summary class="gl-precise-sum">
            <ChevronRight :size="13" class="gl-precise-chev" />
            <span>精确释义（专家校准）</span>
          </summary>
          <p class="gl-precise-body">{{ t.precise }}</p>
        </details>

        <div v-if="t.conceptCode" class="gl-link">
          <a class="gl-concept-link" @click="openConcept(t.conceptCode)">
            查看完整概念 <ArrowRight :size="12" />
          </a>
        </div>
      </article>

      <div v-if="!filtered.length" class="gl-empty">
        <Inbox :size="38" />
        <p>没有找到「{{ q || cat }}」相关术语</p>
        <button class="gl-reset" @click="reset">重置筛选</button>
      </div>
    </div>

    <footer v-if="filtered.length > PAGE_SIZE" class="gl-pagination" aria-label="术语表分页">
      <el-pagination
        v-model:current-page="page"
        background
        layout="prev, pager, next"
        :page-size="PAGE_SIZE"
        :total="filtered.length"
        :pager-count="7"
        @current-change="scrollToTop"
      />
    </footer>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { Search, ChevronRight, ArrowRight, Inbox } from 'lucide-vue-next'
import { GLOSSARY, CATEGORIES } from '../../knowledge/glossary'

const router = useRouter()

const q = ref('')
const cat = ref('')
const sort = ref('cat')   // 'cat' | 'alpha'
const page = ref(1)
const PAGE_SIZE = 18

const SORT_MODES = [
  { key: 'cat', label: '按分类' },
  { key: 'alpha', label: '按拼音' },
]

// 分类计数（静态，不随筛选变化）
function catCount(c) {
  return GLOSSARY.filter(t => t.category === c).length
}

// 过滤：term / en / plain / precise 命中
const filtered = computed(() => {
  const kw = q.value.trim().toLowerCase()
  let arr = GLOSSARY.filter(t => {
    if (cat.value && t.category !== cat.value) return false
    if (!kw) return true
    return (
      (t.term && t.term.toLowerCase().includes(kw)) ||
      (t.en && t.en.toLowerCase().includes(kw)) ||
      (t.plain && t.plain.toLowerCase().includes(kw)) ||
      (t.precise && t.precise.toLowerCase().includes(kw))
    )
  })
  // 排序
  if (sort.value === 'alpha') {
    arr = [...arr].sort((a, b) => a.term.localeCompare(b.term, 'zh-Hans-CN'))
  } else {
    // 按分类顺序，同类内按拼音
    const order = CATEGORIES
    arr = [...arr].sort((x, y) => {
      const cx = order.indexOf(x.category)
      const cy = order.indexOf(y.category)
      if (cx !== cy) return cx - cy
      return x.term.localeCompare(y.term, 'zh-Hans-CN')
    })
  }
  return arr
})

const pagedTerms = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE
  return filtered.value.slice(start, start + PAGE_SIZE)
})
const pageStart = computed(() => filtered.value.length ? (page.value - 1) * PAGE_SIZE + 1 : 0)
const pageEnd = computed(() => Math.min(page.value * PAGE_SIZE, filtered.value.length))

watch([q, cat, sort], () => { page.value = 1 })

function scrollToTop() {
  nextTick(() => {
    document.querySelector('.kb-body')?.scrollTo({ top: 0, behavior: 'smooth' })
  })
}

function reset() {
  q.value = ''
  cat.value = ''
}

// 分类 tag 配色（cobalt/teal 系微调）
function catClass(c) {
  const map = {
    市场品种: 'c-variety',
    主体: 'c-entity',
    辅助服务: 'c-anc',
    电价结算: 'c-price',
    绿色权益: 'c-green',
    容量与输电: 'c-cap',
    新兴: 'c-new',
    金融: 'c-fin',
    监管: 'c-reg',
    基础: 'c-base',
  }
  return map[c] || ''
}

function openConcept(code) {
  router.push({ path: '/knowledge', query: { tab: 'book', c: code } })
}
</script>

<style scoped>
.kb-glossary {
  padding: 22px max(24px, calc((100vw - 1440px) / 2)) 48px;
  max-width: 1440px;
  margin: 0 auto;
}

/* ============ 顶部工具条 ============ */
.gl-toolbar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 14px;
}
.gl-search {
  position: relative;
  display: flex;
  align-items: center;
}
.gl-search-ic {
  position: absolute;
  left: 16px;
  color: #94a0b4;
  z-index: 2;
  pointer-events: none;
}
.gl-search-input {
  width: 100%;
  max-width: 560px;
}
.gl-search-input :deep(.el-input__wrapper) {
  min-height: 46px;
  border-radius: 13px;
  padding-left: 42px;
  background: rgba(255, 255, 255, .92);
  box-shadow: 0 0 0 1px #dce5f2, 0 8px 22px rgba(54, 80, 137, .07);
}
.gl-search-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 2px rgba(65, 104, 220, .35);
}
.gl-search-input :deep(.el-input__inner) {
  font-size: 14px;
}

.gl-sort {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}
.gl-sort-btn {
  border: 1px solid #dce5f3;
  background: rgba(255, 255, 255, .8);
  color: #6b7a93;
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
  padding: 5px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all .15s;
}
.gl-sort-btn:hover { color: #4168dc; border-color: #4168dc; }
.gl-sort-btn.active {
  color: #fff;
  background: linear-gradient(125deg, #4168dc, #5278e4);
  border-color: transparent;
  box-shadow: 0 4px 11px rgba(65, 104, 220, .25);
}

.gl-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}
.gl-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid #e0e6f0;
  background: rgba(255, 255, 255, .85);
  color: #50617c;
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
  padding: 6px 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: transform .16s, border-color .16s, color .16s, background .16s, box-shadow .16s;
}
.gl-chip:hover {
  border-color: #4168dc;
  color: #4168dc;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(65, 104, 220, .1);
}
.gl-chip.active {
  color: #fff;
  background: linear-gradient(125deg, #4168dc, #5278e4 60%, #1aa5ad);
  border-color: transparent;
  box-shadow: 0 7px 16px rgba(57, 89, 198, .22);
}
.gl-chip-num {
  font-size: 10px;
  font-weight: 700;
  background: rgba(65, 104, 220, .12);
  color: #4168dc;
  border-radius: 5px;
  padding: 1px 5px;
  min-width: 14px;
  text-align: center;
}
.gl-chip.active .gl-chip-num {
  background: rgba(255, 255, 255, .25);
  color: #fff;
}

.gl-meta {
  font-size: 12px;
  color: #94a0b4;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.gl-meta strong { color: #4168dc; font-weight: 700; }
.gl-meta-hint { color: #b6c0d2; }
.gl-page-meta {
  margin-left: auto;
  color: #6f7f98;
  font-variant-numeric: tabular-nums;
}

/* ============ 卡片列表 ============ */
.gl-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 12px;
}
.gl-card {
  border: 1px solid #e1e7f2;
  border-radius: 13px;
  padding: 14px 16px;
  background: #fff;
  box-shadow: 0 5px 17px rgba(43, 67, 122, .035);
  display: flex;
  flex-direction: column;
  gap: 9px;
  transition: transform .18s, box-shadow .18s, border-color .18s;
}
.gl-card:hover {
  transform: translateY(-2px);
  border-color: #c5d0f5;
  box-shadow: 0 12px 28px rgba(49, 76, 142, .1);
}

.gl-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.gl-term {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}
.gl-term-zh {
  font-size: 16px;
  font-weight: 800;
  color: #172847;
  letter-spacing: -.01em;
}
.gl-term-en {
  font-size: 11px;
  font-weight: 700;
  color: #4168dc;
  background: #eaf0ff;
  border-radius: 5px;
  padding: 1px 7px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: .02em;
  white-space: nowrap;
}
.gl-cat-tag {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 6px;
  letter-spacing: .03em;
}
.gl-cat-tag.c-variety { color: #4168dc; background: #eaf0ff; }
.gl-cat-tag.c-entity { color: #3152b9; background: #e6ecff; }
.gl-cat-tag.c-anc { color: #1aa5ad; background: #e3f7f8; }
.gl-cat-tag.c-price { color: #9a6a00; background: #fdf3d6; }
.gl-cat-tag.c-green { color: #2a9d4a; background: #e6f7ea; }
.gl-cat-tag.c-cap { color: #7a4dd6; background: #f0e9ff; }
.gl-cat-tag.c-new { color: #d6456f; background: #ffe9f0; }
.gl-cat-tag.c-fin { color: #c2701a; background: #fcefe0; }
.gl-cat-tag.c-reg { color: #c94545; background: #fde8e8; }
.gl-cat-tag.c-base { color: #52647e; background: #eef1f6; }

.gl-plain {
  font-size: 13.5px;
  line-height: 1.7;
  color: #21324e;
  margin: 0;
}
.gl-plain-label {
  display: inline-block;
  font-size: 10px;
  font-weight: 800;
  color: #1aa5ad;
  background: #e3f7f8;
  border-radius: 5px;
  padding: 1px 6px;
  margin-right: 7px;
  vertical-align: 2px;
  letter-spacing: .04em;
}

.gl-precise {
  border-top: 1px dashed #e3e8f0;
  padding-top: 8px;
  margin-top: 2px;
}
.gl-precise-sum {
  list-style: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  font-weight: 700;
  color: #6b7a93;
  user-select: none;
  transition: color .15s;
}
.gl-precise-sum::-webkit-details-marker { display: none; }
.gl-precise-sum:hover { color: #4168dc; }
.gl-precise-chev {
  transition: transform .18s ease;
  color: #94a0b4;
}
.gl-precise[open] .gl-precise-chev { transform: rotate(90deg); color: #4168dc; }
.gl-precise[open] .gl-precise-sum { color: #4168dc; }
.gl-precise-body {
  font-size: 12.5px;
  line-height: 1.78;
  color: #3a4a63;
  margin: 8px 0 0;
  padding: 10px 12px;
  background: linear-gradient(125deg, #f7faff, #eef9fb);
  border: 1px solid #d4defb;
  border-radius: 9px;
}

.gl-link {
  margin-top: 2px;
}
.gl-concept-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  font-weight: 700;
  color: #4168dc;
  cursor: pointer;
  text-decoration: none;
  transition: gap .15s, color .15s;
}
.gl-concept-link:hover { color: #3152b9; gap: 7px; }

.gl-empty {
  grid-column: 1 / -1;
  text-align: center;
  color: #94a0b4;
  padding: 50px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.gl-empty p { margin: 0; font-size: 13px; }
.gl-reset {
  border: 1px solid #dce5f3;
  background: #fff;
  color: #4168dc;
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
  padding: 6px 14px;
  border-radius: 9px;
  cursor: pointer;
  transition: all .15s;
}
.gl-reset:hover { background: #eaf0ff; transform: translateY(-1px); }

.gl-pagination {
  display: flex;
  justify-content: center;
  padding: 28px 0 4px;
}
.gl-pagination :deep(.el-pager li),
.gl-pagination :deep(.btn-prev),
.gl-pagination :deep(.btn-next) {
  border: 1px solid #dce5f3;
  background: #fff;
  color: #63738d;
}
.gl-pagination :deep(.el-pager li.is-active) {
  border-color: #4168dc;
  background: #4168dc;
  color: #fff;
}

@media (max-width: 620px) {
  .kb-glossary { padding: 14px 14px 32px; }
  .gl-list { grid-template-columns: 1fr; }
  .gl-term-zh { font-size: 15px; }
}
</style>
