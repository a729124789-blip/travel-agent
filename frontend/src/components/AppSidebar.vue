<template>
  <aside class="app-sidebar" :class="{ collapsed: collapsed }">
    <!-- Brand -->
    <div class="sidebar-brand">
      <div class="brand-logo">✈️</div>
      <div class="brand-info" v-if="!collapsed">
        <div class="brand-name">智能旅行助手</div>
        <div class="brand-sub">AI Travel Assistant</div>
      </div>
      <button class="collapse-btn" @click="$emit('toggle')" :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'" :title="collapsed ? '展开' : '收起'">
        <span class="collapse-icon">{{ collapsed ? '»' : '«' }}</span>
      </button>
    </div>

    <!-- New Chat -->
    <button class="new-chat-btn" @click="$emit('new-chat')" aria-label="新建对话">
      <span class="new-chat-icon">+</span>
      <span v-if="!collapsed">新建对话</span>
    </button>

    <!-- History -->
    <div class="sidebar-section">
      <div class="section-title" v-if="!collapsed">最近对话</div>
      <div class="conversation-list">
        <div
          v-for="conv in conversations"
          :key="conv.id"
          class="conversation-item"
          :class="{ active: conv.id === activeId }"
          @click="$emit('select', conv.id)"
          :title="conv.title"
        >
          <span class="conv-icon">📍</span>
          <div class="conv-info" v-if="!collapsed">
            <span class="conv-title">{{ conv.title }}</span>
            <span class="conv-date">{{ formatDate(conv.createdAt) }}</span>
          </div>
          <button
            class="conv-delete"
            v-if="!collapsed"
            @click.stop="$emit('delete', conv.id)"
            aria-label="删除对话"
            title="删除"
          >×</button>
        </div>
        <div v-if="conversations.length === 0 && !collapsed" class="conv-empty">
          暂无历史对话
        </div>
      </div>
    </div>

    <!-- Footer -->
    <div class="sidebar-footer">
      <button class="footer-btn" @click="$emit('open-history')" aria-label="历史记录" title="历史记录">
        <span class="footer-icon">🕘</span>
        <span v-if="!collapsed">历史记录</span>
      </button>
      <button class="footer-btn" @click="$emit('open-preferences')" aria-label="偏好管理" title="偏好管理">
        <span class="footer-icon">⚙️</span>
        <span v-if="!collapsed">偏好管理</span>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import dayjs from 'dayjs'

interface Conversation {
  id: string
  title: string
  destination: string
  createdAt: number
}

defineProps<{
  conversations: Conversation[]
  activeId: string | null
  collapsed?: boolean
}>()

defineEmits<{
  (e: 'new-chat'): void
  (e: 'select', id: string): void
  (e: 'delete', id: string): void
  (e: 'open-preferences'): void
  (e: 'open-history'): void
  (e: 'toggle'): void
}>()

function formatDate(ts: number) {
  const d = dayjs(ts)
  const now = dayjs()
  if (d.isSame(now, 'day')) return d.format('HH:mm')
  if (d.isSame(now, 'year')) return d.format('MM-DD')
  return d.format('YYYY-MM-DD')
}
</script>

<style scoped>
.app-sidebar {
  width: var(--sidebar-width);
  background: var(--sidebar-bg);
  border-right: 1px solid var(--sidebar-border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  padding: var(--space-4) var(--space-3);
  height: 100vh;
  position: relative;
  top: 0;
  transition: width var(--transition-normal);
}
.app-sidebar.collapsed {
  width: 64px;
  padding: var(--space-4) var(--space-2);
  align-items: center;
}
.app-sidebar.collapsed .sidebar-brand {
  flex-direction: column;
  justify-content: flex-start;
  gap: var(--space-2);
  width: 100%;
  padding-bottom: var(--space-3);
}
.app-sidebar.collapsed .collapse-btn {
  position: static;
  transform: none;
  margin-left: 0;
}

/* Brand */
.sidebar-brand {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-2) var(--space-4);
}
.brand-logo {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--color-primary), #7b6bbf);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 18px;
  flex-shrink: 0;
}
.brand-info { min-width: 0; }
.brand-name {
  font-size: var(--font-size-md);
  font-weight: 700;
  color: var(--color-text);
  white-space: nowrap;
}
.brand-sub {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: 1px;
}
.collapse-btn {
  margin-left: auto;
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--color-text-tertiary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  transition: background var(--transition-fast), color var(--transition-fast);
  flex-shrink: 0;
}
.collapse-btn:hover {
  background: var(--color-surface-hover);
  color: var(--color-text);
}
.app-sidebar.collapsed .collapse-btn {
  margin-left: 0;
}

/* New Chat */
.new-chat-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-3);
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition-fast), transform var(--transition-fast);
  margin-bottom: var(--space-5);
}
.new-chat-btn:hover { background: var(--color-primary-hover); }
.new-chat-btn:active { transform: scale(0.98); }
.new-chat-icon { font-size: 16px; font-weight: 700; line-height: 1; }

/* Section */
.sidebar-section {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.section-title {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 0 var(--space-2) var(--space-2);
}

/* Conversation List */
.conversation-list { display: flex; flex-direction: column; gap: 2px; }
.conversation-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--transition-fast);
  position: relative;
}
.conversation-item:hover { background: var(--color-surface-hover); }
.conversation-item.active {
  background: var(--color-primary-light);
}
.conversation-item.active .conv-title { color: var(--color-primary); font-weight: 600; }
.conv-icon { font-size: 14px; flex-shrink: 0; }
.conv-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}
.conv-title {
  font-size: var(--font-size-sm);
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-date {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: 1px;
}
.conv-delete {
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  font-size: 16px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  opacity: 0;
  transition: opacity var(--transition-fast), color var(--transition-fast);
  line-height: 1;
}
.conversation-item:hover .conv-delete { opacity: 1; }
.conv-delete:hover { color: var(--color-error); background: rgba(239, 68, 68, 0.08); }
.conv-empty {
  padding: var(--space-4) var(--space-2);
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  text-align: center;
}

/* Footer */
.sidebar-footer {
  padding-top: var(--space-3);
  border-top: 1px solid var(--sidebar-border);
  margin-top: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.footer-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.footer-btn:hover { background: var(--color-surface-hover); color: var(--color-text); }
.footer-icon { font-size: 15px; }
</style>
