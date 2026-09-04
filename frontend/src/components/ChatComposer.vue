<template>
  <div class="composer-wrapper">
    <div class="composer" :class="{ focused: isFocused, disabled: disabled }">
      <textarea
        ref="textareaRef"
        v-model="text"
        class="composer-input"
        :placeholder="placeholder"
        :disabled="disabled"
        rows="1"
        @input="autoResize"
        @keydown="handleKeydown"
        @focus="isFocused = true"
        @blur="isFocused = false"
        aria-label="旅行计划输入框"
      ></textarea>
      <button
        class="send-btn"
        :disabled="!text.trim() || disabled"
        @click="send"
        aria-label="发送消息"
      >
        <span v-if="disabled" class="send-loading"></span>
        <template v-else>
          <span class="send-icon">↑</span>
          <span class="send-text">发送</span>
        </template>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    disabled?: boolean
    placeholder?: string
    modelValue?: string
  }>(),
  {
    disabled: false,
    placeholder: '告诉我你的旅行计划...',
    modelValue: ''
  }
)

const emit = defineEmits<{
  (e: 'send', text: string): void
  (e: 'update:modelValue', text: string): void
}>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const text = ref(props.modelValue)
const isFocused = ref(false)

watch(
  () => props.modelValue,
  (val) => {
    text.value = val
  }
)

watch(text, (val) => {
  emit('update:modelValue', val)
})

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  const maxHeight = 160 // ~5 lines
  el.style.height = Math.min(el.scrollHeight, maxHeight) + 'px'
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

function send() {
  const content = text.value.trim()
  if (!content || props.disabled) return
  emit('send', content)
  text.value = ''
  emit('update:modelValue', '')
  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
      textareaRef.value.focus()
    }
  })
}

defineExpose({
  focus: () => textareaRef.value?.focus(),
  clear: () => {
    text.value = ''
    emit('update:modelValue', '')
    if (textareaRef.value) textareaRef.value.style.height = 'auto'
  }
})
</script>

<style scoped>
.composer-wrapper {
  padding: var(--space-3) var(--space-6) var(--space-4);
  background: var(--color-surface);
  border-top: 1px solid var(--color-border-light);
  flex-shrink: 0;
}
.composer {
  max-width: var(--chat-max-width);
  margin: 0 auto;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
  display: flex;
  align-items: flex-end;
  gap: var(--space-3);
  padding: var(--space-3);
}
.composer.focused {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(91, 106, 191, 0.1);
}
.composer.disabled {
  opacity: 0.6;
}
.composer-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  resize: none;
  padding: var(--space-2) var(--space-1);
  font-size: var(--font-size-base);
  font-family: var(--font-sans);
  line-height: var(--line-height-normal);
  color: var(--color-text);
  background: transparent;
  max-height: 160px;
  overflow-y: auto;
}
.composer-input::placeholder {
  color: var(--color-text-placeholder);
}
.send-btn {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-4);
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  flex-shrink: 0;
  align-self: flex-end;
  transition: background var(--transition-fast), opacity var(--transition-fast);
}
.send-btn:hover:not(:disabled) { background: var(--color-primary-hover); }
.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.send-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  font-size: 12px;
  font-weight: 700;
}
.send-loading {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 640px) {
  .composer-wrapper { padding: var(--space-2) var(--space-3) var(--space-3); }
  .send-text { display: none; }
}
</style>
