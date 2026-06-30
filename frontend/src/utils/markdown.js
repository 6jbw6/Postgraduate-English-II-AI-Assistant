import { marked } from 'marked'

/**
 * 将 Markdown 字符串渲染为 HTML（基于 marked GFM 规范）
 */
export function renderMarkdown(content) {
  if (!content) return ''
  // breaks=true 让模型输出中的普通换行按用户预期展示。
  return marked.parse(content, {
    gfm: true,
    breaks: true,
  })
}
