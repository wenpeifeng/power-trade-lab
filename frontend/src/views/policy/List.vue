<template>
  <div class="policy-list" v-loading="loading">
    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="cat-tabs">
        <span class="cat-tab" :class="{ active: filter.category === '' }" @click="setCategory('')">
          全部 <i v-if="unreadByCat['']">({{ unreadByCat[''] }})</i>
        </span>
        <span
          v-for="c in categories"
          :key="c.category"
          class="cat-tab"
          :class="[c.category, { active: filter.category === c.category }]"
          @click="setCategory(c.category)"
        >
          {{ catLabel(c.category) }} <i>({{ c.count }})</i>
        </span>
      </div>
      <div class="filter-right">
        <div class="filter-control">
          <span class="filter-label"><MapPinned :size="12" /> 地域</span>
          <el-select
            v-model="filter.province" class="policy-select" popper-class="policy-filter-popper"
            placeholder="全国范围" clearable size="small" @change="load"
          >
            <el-option v-for="p in provinces" :key="p.province" :label="p.province" :value="p.province" />
          </el-select>
        </div>
        <div class="filter-control">
          <span class="filter-label"><CalendarDays :size="12" /> 时效</span>
          <el-select
            v-model="filter.days" class="policy-select" popper-class="policy-filter-popper"
            placeholder="不限时间" clearable size="small" @change="load"
          >
            <el-option :value="7" label="近 7 天" />
            <el-option :value="30" label="近 30 天" />
            <el-option :value="90" label="近 3 个月" />
          </el-select>
        </div>
        <el-button class="read-all" size="small" @click="markAllRead">全部标为已读</el-button>
      </div>
    </div>
    <div class="sort-rule">
      按发布日期倒序；同日按“紧急事项 → 国家政策 → 交易规则 → 出清结果 → 市场公告”排列
    </div>

    <!-- 新闻流时间线 -->
    <div class="news-timeline">
      <div
        v-for="item in list"
        :key="item.id"
        class="news-row"
        :class="{ unread: !item.is_read }"
        @click="openDetail(item)"
      >
        <div class="news-dot-col">
          <span class="news-dot" :class="`p${item.priority}`">●</span>
        </div>
        <div class="news-body">
          <div class="news-row1">
            <span class="news-cat-tag" :class="item.category">{{ catLabel(item.category) }}</span>
            <span
              v-if="item.importance_level !== 'normal'"
              class="importance-tag"
              :class="item.importance_level"
              :title="(item.importance_reasons || []).join('、')"
            >{{ item.importance_label }}</span>
            <span v-if="item.province" class="news-prov">{{ item.province }}</span>
            <span class="news-title">{{ item.title }}</span>
            <span v-if="item.doc_number" class="news-docnum">{{ item.doc_number }}</span>
          </div>
          <div class="news-row2">
            <span class="news-summary" v-if="item.ai_summary"><Bot :size="13" /> {{ item.ai_summary }}</span>
            <span class="news-summary" v-else-if="item.content">{{ item.content }}</span>
          </div>
          <div class="news-row3">
            <span class="news-date" :class="{ unverified: item.publish_date_status !== 'verified' }">
              {{ item.publish_date || '日期待核验' }}
            </span>
            <span v-if="item.attachments?.length" class="news-attach"><Paperclip :size="12" /> {{ item.attachments.length }}个附件</span>
            <span class="news-source">来源: {{ item.source }}</span>
            <a
              v-if="item.source_url"
              class="news-source-link"
              :href="item.source_url"
              target="_blank"
              rel="noopener noreferrer"
              @click.stop
            ><ExternalLink :size="12" /> 查看原文</a>
            <span v-else class="news-source-missing">暂无原文链接</span>
          </div>
        </div>
      </div>
      <div v-if="!list.length && !loading" class="empty">暂无政策公告</div>
    </div>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" size="480px" :title="current?.title" direction="rtl">
      <div v-if="current" class="detail-content">
        <div class="detail-meta">
          <el-tag size="small">{{ catLabel(current.category) }}</el-tag>
          <el-tag
            v-if="current.importance_level !== 'normal'"
            size="small"
            :type="current.importance_level === 'urgent' ? 'danger' : 'warning'"
          >{{ current.importance_label }}</el-tag>
          <span v-if="current.doc_number">{{ current.doc_number }}</span>
          <span :class="{ 'date-unverified': current.publish_date_status !== 'verified' }">
            {{ current.publish_date || '日期待核验' }}
          </span>
          <span v-if="current.province">{{ current.province }}</span>
          <a
            v-if="current.source_url"
            class="detail-source-link"
            :href="current.source_url"
            target="_blank"
            rel="noopener noreferrer"
          ><ExternalLink :size="13" /> 查看原文</a>
          <span v-else class="news-source-missing">暂无原文链接</span>
        </div>
        <div v-if="current.ai_summary" class="detail-section">
          <h4><Bot :size="15" /> AI 解读</h4>
          <p>{{ current.ai_summary }}</p>
        </div>
        <div v-if="current.ai_analysis" class="detail-section">
          <h4><ChartBar :size="15" /> 对交易的影响</h4>
          <p>{{ current.ai_analysis }}</p>
        </div>
        <div class="detail-section">
          <h4><FileText :size="15" /> 正文摘要</h4>
          <p>{{ current.content }}</p>
        </div>
        <div v-if="current.attachments?.length" class="detail-section">
          <h4><Paperclip :size="15" /> 附件</h4>
          <div v-for="a in current.attachments" :key="a.id" class="attach-item">
            <a :href="a.file_url" target="_blank">{{ a.filename }}</a>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Bot, Paperclip, ChartBar, FileText, ExternalLink, MapPinned, CalendarDays } from 'lucide-vue-next'
import { policyApi } from '../../api'

const loading = ref(false)
const list = ref([])
const categories = ref([])
const provinces = ref([])
const unreadByCat = ref({})
const filter = reactive({ category: '', province: '', days: null })
const detailVisible = ref(false)
const current = ref(null)

const catLabel = (c) => ({
  national: '国家政策', market: '市场公告', clearing: '出清结果', regulation: '交易规则',
}[c] || c)

const load = async () => {
  loading.value = true
  try {
    const params = {
      page: 1, page_size: 50,
      category: filter.category || undefined,
      province: filter.province || undefined,
      days: filter.days || undefined,
    }
    const data = await policyApi.list(params)
    list.value = data.items
    // 统计未读
    const byCat = { '': data.items.filter((i) => !i.is_read).length }
    list.value.forEach((i) => {
      if (!i.is_read) byCat[i.category] = (byCat[i.category] || 0) + 1
    })
    unreadByCat.value = byCat
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

const loadFilters = async () => {
  try {
    const [cats, provs] = await Promise.all([policyApi.categories(), policyApi.provinces()])
    categories.value = cats
    provinces.value = provs
  } catch (e) { console.error(e) }
}

const setCategory = (c) => {
  filter.category = c
  load()
}

const openDetail = async (item) => {
  try {
    current.value = await policyApi.detail(item.id)
    detailVisible.value = true
    item.is_read = true
    load()
  } catch (e) { ElMessage.error(e.message) }
}

const markAllRead = async () => {
  try {
    await policyApi.markAllRead()
    ElMessage.success('已全部标记为已读')
    load()
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(() => {
  load()
  loadFilters()
})
</script>

<style scoped>
.filter-bar {
  display: flex; justify-content: space-between; align-items: center;
  flex-wrap: wrap; gap: 12px;
  margin-bottom: 20px;padding:12px;
  border:1px solid #dfe6f3;border-radius:14px;background:rgba(255,255,255,.9);
  box-shadow:0 9px 24px rgba(46,70,128,.065);
}
.cat-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
.cat-tab {
  padding: 6px 14px; border-radius: 16px; cursor: pointer;
  font-size: 13px; color: var(--text-secondary);
  background: var(--bg-card); border: 1px solid var(--border-color);
  transition: all 0.15s;
}
.cat-tab:hover { color: var(--accent); border-color: var(--accent); }
.cat-tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.cat-tab i { font-style: normal; font-size: 11px; opacity: 0.8; }
.cat-tab.national{color:#345dcc;border-color:#cbd9ff;background:#f2f5ff}
.cat-tab.regulation{color:#7a3da6;border-color:#e2cdf2;background:#faf3ff}
.cat-tab.clearing{color:#ad6512;border-color:#efd7ad;background:#fff9eb}
.cat-tab.market{color:#087c82;border-color:#bfe4e2;background:#edfafa}
.cat-tab.national.active{color:#fff;border-color:#4168dc;background:#4168dc}
.cat-tab.regulation.active{color:#fff;border-color:#8b35b5;background:#8b35b5}
.cat-tab.clearing.active{color:#fff;border-color:#e49a22;background:#e49a22}
.cat-tab.market.active{color:#fff;border-color:#0d9aa2;background:#0d9aa2}
.filter-right { display: flex; gap: 8px; align-items: stretch; }
.filter-control{
  min-width:144px;padding:6px 9px 6px 11px;display:flex;align-items:center;gap:8px;
  border:1px solid #dce5f4;border-radius:11px;background:#f8faff;
  transition:border-color .2s,background .2s,box-shadow .2s;
}
.filter-control:hover,.filter-control:focus-within{
  border-color:#7694e9;background:#fff;box-shadow:0 6px 16px rgba(65,104,220,.1);
}
.filter-label{
  display:inline-flex;align-items:center;gap:4px;color:#8794aa;
  font-size:10px;font-weight:750;white-space:nowrap;
}
.policy-select{width:88px}
.policy-select :deep(.el-select__wrapper){
  min-height:25px;padding:0;background:transparent;border:0;border-radius:0;
  box-shadow:none!important;
}
.policy-select :deep(.el-select__placeholder),.policy-select :deep(.el-select__selected-item){
  color:#3e4b63;font-size:12px;font-weight:700;
}
.read-all{
  height:auto!important;padding-inline:13px!important;border-radius:11px!important;
  color:#4168dc!important;border-color:#d9e2fb!important;background:#f2f5ff!important;
  font-weight:750!important;
}
.read-all:hover{color:#fff!important;border-color:#4168dc!important;background:#4168dc!important}
.sort-rule {
  margin: -8px 0 10px; color: var(--text-tertiary); font-size: 11px; line-height: 1.5;
}

.news-timeline {
  display:flex;flex-direction:column;padding:8px 14px;
  border:1px solid #dfe6f3;border-radius:16px;background:rgba(255,255,255,.93);
  box-shadow:0 13px 32px rgba(46,70,128,.07);
}
.news-row {
  display: flex; gap: 14px; padding: 16px 8px;
  border-bottom: 1px solid var(--border-light);
  cursor: pointer; transition: background .2s,transform .2s,box-shadow .2s;
  border-left: 3px solid transparent;
}
.news-row:hover { background:var(--bg-hover);border-left-color:var(--accent);transform:translateX(4px);box-shadow:0 8px 18px rgba(49,76,142,.06) }
.news-row.unread { background:#f4f7ff }
.news-dot-col { padding-top: 4px; }
.news-dot { font-size: 8px; color: var(--text-tertiary); }
.news-dot.p2 { color: var(--accent-red); }
.news-dot.p1 { color: var(--accent-orange); }
.news-row.unread .news-dot { color: var(--accent); }
.news-body { flex: 1; min-width: 0; }
.news-row1 { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
.news-cat-tag {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  background: var(--accent-soft); color: var(--accent);
  border:1px solid transparent;white-space: nowrap;font-weight:700;
}
.news-cat-tag.national{color:#fff;background:#4168dc;border-color:#4168dc;box-shadow:0 4px 10px rgba(65,104,220,.18)}
.news-cat-tag.regulation{color:#fff;background:#8b35b5;border-color:#8b35b5;box-shadow:0 4px 10px rgba(139,53,181,.18)}
.news-cat-tag.clearing{color:#fff;background:#e49a22;border-color:#e49a22;box-shadow:0 4px 10px rgba(228,154,34,.18)}
.news-cat-tag.market{color:#fff;background:#0d9aa2;border-color:#0d9aa2;box-shadow:0 4px 10px rgba(13,154,162,.18)}
.importance-tag {
  padding: 2px 7px; border-radius: 4px; font-size: 10px; font-weight: 700; white-space: nowrap;
}
.importance-tag.important { color: #b45309; background: #fff7df; border: 1px solid #f5d487; }
.importance-tag.urgent { color: #c24132; background: #fff0ed; border: 1px solid #f3b7ad; }
.news-prov { font-size: 12px; color: var(--text-secondary); white-space: nowrap; }
.news-title { font-size: 14px; color: var(--text-primary); font-weight: 500; }
.news-docnum { font-size: 12px; color: var(--text-tertiary); }
.news-row2 { margin-bottom: 6px; }
.news-summary { font-size: 13px; color: var(--text-secondary); line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.news-row3 { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; font-size: 12px; color: var(--text-tertiary); }
.news-date.unverified, .date-unverified { color: #b7791f; }
.news-attach { display: inline-flex; align-items: center; gap: 3px; }
.news-source-link, .detail-source-link {
  display: inline-flex; align-items: center; gap: 4px;
  padding:3px 8px;border-radius:7px;color:var(--accent);text-decoration:none;font-weight:650;
  background:var(--accent-soft);transition:color .18s,background .18s,transform .18s;
}
.news-source-link:hover, .detail-source-link:hover { color:#fff;background:var(--accent);text-decoration:none;transform:translateY(-1px) }
.news-source-missing { color: var(--text-tertiary); opacity: 0.72; }
.empty { text-align: center; padding: 60px; color: var(--text-tertiary); }

.detail-content { padding: 0 8px; }
.detail-meta { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 20px;
  font-size: 13px; color: var(--text-secondary); }
.detail-section { margin-bottom: 20px; }
.detail-section h4 { font-size: 14px; color: var(--accent); margin-bottom: 8px; display: inline-flex; align-items: center; gap: 5px; }
.detail-section p { font-size: 13px; line-height: 1.8; color: var(--text-primary); }
.attach-item a { color: var(--accent); font-size: 13px; display: block; margin-bottom: 6px; }

:global(.policy-filter-popper.el-popper){
  padding:6px;border:1px solid #dce5f4;border-radius:12px;
  box-shadow:0 16px 36px rgba(37,57,105,.15);
}
:global(.policy-filter-popper .el-select-dropdown__item){
  margin:2px 0;border-radius:8px;color:#536076;font-size:12px;font-weight:650;
}
:global(.policy-filter-popper .el-select-dropdown__item.is-selected){
  color:#365dcc;background:#edf2ff;
}
@media(max-width:780px){
  .filter-right{width:100%;flex-wrap:wrap}
  .filter-control{flex:1}
}
</style>
