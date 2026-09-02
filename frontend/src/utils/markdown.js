// 轻量 markdown 解析：仅支持 h1-h3 / blockquote / ul-list / 段落（以及 code/page/table 块）。
// 与 BookReader.vue 原内联实现完全等价，零依赖。

export function escapeHtml(text) {
  return String(text || '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]))
}

export function inlineHtml(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
}

export function parseMarkdown(markdown) {
  const lines = markdown.split('\n')
  const blocks = []
  let paragraph = []
  let list = []
  let code = []
  let inCode = false
  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ type: 'p', text: paragraph.join(' ') })
    paragraph = []
  }
  const flushList = () => {
    if (list.length) blocks.push({ type: 'list', items: [...list] })
    list = []
  }
  for (const raw of lines) {
    const line = raw.trim()
    if (line.startsWith('```')) {
      flushParagraph(); flushList()
      if (inCode) { blocks.push({ type: 'code', text: code.join('\n') }); code = [] }
      inCode = !inCode
      continue
    }
    if (inCode) { code.push(raw); continue }
    const page = line.match(/^<!--\s*page:\s*(\d+)\s*-->$/)
    if (page) { flushParagraph(); flushList(); blocks.push({ type: 'page', page: page[1] }); continue }
    const heading = line.match(/^(#{1,3})\s+(.+)$/)
    if (heading) { flushParagraph(); flushList(); blocks.push({ type: `h${heading[1].length}`, text: heading[2] }); continue }
    if (/^[-*+]\s+/.test(line)) { flushParagraph(); list.push(line.replace(/^[-*+]\s+/, '')); continue }
    if (line.startsWith('>')) { flushParagraph(); flushList(); blocks.push({ type: 'quote', text: line.slice(1).trim() }); continue }
    if (line.includes('|') && /^\|?.+\|.+/.test(line)) { flushParagraph(); flushList(); blocks.push({ type: 'table', text: line }); continue }
    if (!line) { flushParagraph(); flushList(); continue }
    paragraph.push(line)
  }
  flushParagraph(); flushList()
  return blocks
}
