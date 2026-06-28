import { marked } from 'marked'

/**
 * 将 Markdown 字符串渲染为 HTML（基于 marked GFM 规范）
 */
export function renderMarkdown(content) {
  if (!content) return ''
  return marked.parse(content, {
    gfm: true,
    breaks: true,
  })
}
