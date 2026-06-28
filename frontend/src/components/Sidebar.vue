<template>
  <aside class="sidebar">
    <div class="sidebar-header" @click="$emit('select-type', null)">
      <div class="logo-icon">🎓</div>
      <div class="logo-text">
        <h2>考研英语二 AI 助手</h2>
        <div class="subtitle">智能辅导系统</div>
      </div>
    </div>

    <nav class="sidebar-nav">
      <div class="nav-section-title">题型选择</div>

      <button
        v-for="item in questionTypes"
        :key="item.id"
        class="nav-item"
        :class="{ active: currentType === item.id }"
        @click="$emit('select-type', item.id)"
      >
        <span class="nav-item-icon">{{ item.icon }}</span>
        <div class="nav-item-content">
          <span class="nav-item-name">{{ item.name }}</span>
          <span class="nav-item-desc">{{ item.description }}</span>
        </div>
        <span class="nav-item-score">{{ item.score }}</span>
      </button>
    </nav>

    <div class="sidebar-footer">
      <button
        class="btn-clear"
        :disabled="currentType === null"
        @click="$emit('clear-chat')"
      >
        清空当前对话
      </button>
    </div>
  </aside>
</template>

<script setup>
defineProps({
  currentType: { type: String, default: null },
})

defineEmits(['select-type', 'clear-chat'])

const questionTypes = [
  { id: 'free',       icon: '💬', name: '自由对话',  description: '不限定题型，随意提问' },
  { id: 'cloze',      icon: '📝', name: '完形填空',  description: 'Use of English',         score: '10分' },
  { id: 'reading_a',  icon: '📖', name: '阅读理解A', description: '传统阅读 - 4篇',         score: '40分' },
  { id: 'reading_b',  icon: '🔗', name: '阅读理解B', description: '多项对应 / 小标题',      score: '10分' },
  { id: 'translation',icon: '🌐', name: '翻译',      description: '短文英译汉',             score: '15分' },
  { id: 'writing_a',  icon: '✉️', name: '小作文',    description: '应用文写作',             score: '10分' },
  { id: 'writing_b',  icon: '🖼️', name: '大作文',    description: '图表作文',               score: '15分' },
]
</script>

<style scoped>
.sidebar {
  width: 260px;
  min-width: 260px;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border);
  box-shadow: var(--shadow);
  z-index: 10;
}

.sidebar-header {
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.15s;
}
.sidebar-header:hover {
  background: var(--bg);
}

.logo-icon {
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, var(--primary), var(--primary-light));
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: #fff;
}

.logo-text h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}
.subtitle {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

.sidebar-nav {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
}

.nav-section-title {
  padding: 8px 20px 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.nav-item {
  width: calc(100% - 16px);
  margin: 2px 8px;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
  color: var(--text);
}
.nav-item:hover {
  background: var(--primary-bg);
}
.nav-item.active {
  background: var(--primary-bg);
  color: var(--primary);
}

.nav-item-icon {
  font-size: 18px;
  width: 28px;
  text-align: center;
  flex-shrink: 0;
}

.nav-item-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.nav-item-name {
  font-size: 13px;
  font-weight: 600;
}
.nav-item-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}
.nav-item.active .nav-item-desc {
  color: var(--primary);
}

.nav-item-score {
  font-size: 11px;
  color: var(--success);
  background: #ecfdf5;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
  flex-shrink: 0;
}

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid var(--border);
}

.btn-clear {
  width: 100%;
  padding: 10px;
  border: 1px solid var(--danger);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--danger);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-clear:hover:not(:disabled) {
  background: #fef2f2;
}
.btn-clear:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  border-color: var(--border);
  color: var(--text-muted);
}
</style>
