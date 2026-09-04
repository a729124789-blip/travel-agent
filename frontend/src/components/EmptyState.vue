<template>
  <div class="empty-state">
    <div class="empty-icon">✈️</div>
    <h2 class="empty-title">智能旅行助手</h2>
    <p class="empty-desc">
      告诉我你的目的地、旅行时间、预算和偏好，<br />我会帮你生成个性化旅行方案。
    </p>
    <div class="suggestions">
      <button
        v-for="(s, i) in suggestions"
        :key="i"
        class="suggestion-chip"
        @click="$emit('select', s)"
      >
        <span class="suggestion-icon">{{ s.icon }}</span>
        <span class="suggestion-text">{{ s.text }}</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Suggestion {
  icon: string
  text: string
}

withDefaults(
  defineProps<{
    suggestions?: Suggestion[]
  }>(),
  {
    suggestions: () => [
      { icon: '🏞️', text: '杭州 3 日游' },
      { icon: '🐼', text: '成都 5 日游' },
      { icon: '🌆', text: '香港 2 日游' },
      { icon: '🏯', text: '西安 4 日游' },
    ]
  }
)

defineEmits<{
  (e: 'select', suggestion: Suggestion): void
}>()
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--space-10) var(--space-6);
  flex: 1;
}
.empty-icon {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, var(--color-primary), #7b6bbf);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 26px;
  margin-bottom: var(--space-5);
  box-shadow: var(--shadow-md);
}
.empty-title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-xl);
  font-weight: 700;
  color: var(--color-text);
}
.empty-desc {
  margin: 0 0 var(--space-8);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: var(--line-height-relaxed);
}
.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  justify-content: center;
  max-width: 480px;
}
.suggestion-chip {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.suggestion-chip:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-primary-bg);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}
.suggestion-icon { font-size: 15px; }
.suggestion-text { white-space: nowrap; }
</style>
