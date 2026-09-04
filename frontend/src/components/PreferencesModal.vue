<template>
  <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-header">
        <h3>⚙️ 偏好管理</h3>
        <button class="modal-close" @click="$emit('close')" aria-label="关闭">×</button>
      </div>
      <div class="modal-body">
        <div class="prefs-grid">
          <div class="field">
            <label>默认出发城市</label>
            <input v-model="local.departure_city" placeholder="例如：上海" />
          </div>
          <div class="field">
            <label>默认交通方式</label>
            <select v-model="local.transportation">
              <option value="">不设置</option>
              <option value="公共交通">公共交通</option>
              <option value="自驾">自驾</option>
              <option value="飞机">飞机</option>
              <option value="高铁">高铁</option>
              <option value="火车">火车</option>
            </select>
          </div>
          <div class="field">
            <label>默认住宿偏好</label>
            <select v-model="local.accommodation">
              <option value="">不设置</option>
              <option value="经济型酒店">经济型酒店</option>
              <option value="舒适型酒店">舒适型酒店</option>
              <option value="豪华酒店">豪华酒店</option>
              <option value="民宿">民宿</option>
              <option value="青旅">青旅</option>
            </select>
          </div>
          <div class="field">
            <label>预算区间</label>
            <input v-model="local.budget" placeholder="例如：5000以内" />
          </div>
          <div class="field">
            <label>同行人</label>
            <input v-model="local.companions" placeholder="例如：带爸妈、情侣" />
          </div>
        </div>
        <div class="field">
          <label>旅行偏好</label>
          <div class="preference-tags">
            <a-checkbox-group v-model:value="local.preferences" class="custom-checkbox-group">
              <a-checkbox
                v-for="pref in preferenceOptions"
                :key="pref.value"
                :value="pref.value"
                class="preference-tag"
              >{{ pref.icon }} {{ pref.label }}</a-checkbox>
            </a-checkbox-group>
          </div>
        </div>
        <p class="prefs-hint">保存后，新建对话时这些偏好会自动填入行程表单。</p>
      </div>
      <div class="modal-actions">
        <button class="btn-secondary" @click="$emit('close')">取消</button>
        <button class="btn-primary" @click="handleSave">保存偏好</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'

interface UserPreferences {
  departure_city: string
  transportation: string
  accommodation: string
  preferences: string[]
  budget: string
  companions: string
}

const props = defineProps<{
  visible: boolean
  prefs: UserPreferences
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'save', prefs: UserPreferences): void
}>()

const preferenceOptions = [
  { value: '历史文化', label: '历史文化', icon: '🏛️' },
  { value: '自然风光', label: '自然风光', icon: '🏞️' },
  { value: '美食', label: '美食', icon: '🍜' },
  { value: '购物', label: '购物', icon: '🛍️' },
  { value: '艺术', label: '艺术', icon: '🎨' },
  { value: '休闲', label: '休闲', icon: '☕' },
]

const local = reactive<UserPreferences>({
  departure_city: '',
  transportation: '',
  accommodation: '',
  preferences: [],
  budget: '',
  companions: '',
})

watch(
  () => props.visible,
  (val) => {
    if (val) {
      Object.assign(local, props.prefs)
    }
  }
)

function handleSave() {
  emit('save', { ...local, preferences: [...local.preferences] })
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(2px);
}
.modal {
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  width: 90%;
  max-width: 520px;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: var(--shadow-lg);
  animation: modal-in 0.2s ease;
}
@keyframes modal-in {
  from { opacity: 0; transform: translateY(12px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-5) var(--space-6) var(--space-3);
}
.modal-header h3 { margin: 0; font-size: var(--font-size-lg); font-weight: 700; }
.modal-close {
  background: none;
  border: none;
  font-size: 22px;
  cursor: pointer;
  color: var(--color-text-tertiary);
  line-height: 1;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: color var(--transition-fast), background var(--transition-fast);
}
.modal-close:hover { color: var(--color-text); background: var(--color-surface-hover); }
.modal-body { padding: 0 var(--space-6) var(--space-4); }
.prefs-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.prefs-grid .field { flex: 1 1 45%; min-width: 0; margin-bottom: 0; }
.field { margin-bottom: var(--space-4); }
.field label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: var(--space-2);
}
.field input,
.field select {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-base);
  font-family: var(--font-sans);
  outline: none;
  transition: border-color var(--transition-fast);
  box-sizing: border-box;
}
.field input:focus,
.field select:focus { border-color: var(--color-primary); }
.preference-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.custom-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  width: 100%;
}
.preference-tag {
  margin: 0 !important;
  padding: 6px 14px !important;
  border: 1px solid var(--color-border) !important;
  border-radius: 20px !important;
  transition: all var(--transition-fast) !important;
  background: var(--color-surface) !important;
  font-size: var(--font-size-sm) !important;
  display: inline-flex !important;
  align-items: center !important;
}
.preference-tag:hover {
  border-color: var(--color-primary) !important;
  background: var(--color-primary-light) !important;
}
.preference-tag.ant-checkbox-wrapper-checked {
  border-color: var(--color-primary) !important;
  background: var(--color-primary) !important;
  color: #fff !important;
}
.prefs-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin: var(--space-4) 0 0;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-6) var(--space-5);
}
.btn-primary {
  padding: var(--space-2) var(--space-5);
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition-fast);
}
.btn-primary:hover { background: var(--color-primary-hover); }
.btn-secondary {
  padding: var(--space-2) var(--space-5);
  background: var(--color-surface-hover);
  color: var(--color-text-secondary);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: background var(--transition-fast);
}
.btn-secondary:hover { background: var(--color-surface-active); }
</style>
