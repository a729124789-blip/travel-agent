<template>
  <header class="chat-header">
    <div class="header-left">
      <div class="header-title-group">
        <h1 class="header-title">{{ title }}</h1>
        <p class="header-subtitle">{{ subtitle }}</p>
      </div>
    </div>
    <div class="header-right">
      <div class="ai-status">
        <span class="status-dot"></span>
        <span class="status-text">{{ status }}</span>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string
    subtitle?: string
    status?: string
  }>(),
  {
    title: '智能旅行助手',
    subtitle: '智能规划你的下一次旅行',
    status: '准备为你规划行程'
  }
)
</script>

<style scoped>
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-6);
  border-bottom: 1px solid var(--color-border-light);
  background: var(--color-surface);
  flex-shrink: 0;
}
.header-left { display: flex; align-items: center; gap: var(--space-3); }
.header-title-group { min-width: 0; }
.header-title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--color-text);
  line-height: var(--line-height-tight);
}
.header-subtitle {
  margin: 2px 0 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}
.header-right { display: flex; align-items: center; gap: var(--space-3); }
.ai-status {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-primary-bg);
  border-radius: var(--radius-sm);
}
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-success);
  animation: pulse 2s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.status-text {
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  font-weight: 500;
}

@media (max-width: 640px) {
  .chat-header { padding: var(--space-3) var(--space-4); }
  .header-subtitle { display: none; }
}
</style>
