<template>
  <div class="history-panel">
    <!-- 面板头部 -->
    <div class="panel-header">
      <div class="panel-title-group">
        <h2 class="panel-title">{{ panelTitle }}</h2>
        <p class="panel-subtitle">{{ panelSubtitle }}</p>
      </div>
      <button class="panel-close" @click="$emit('close')" aria-label="关闭面板" title="关闭">×</button>
    </div>

    <!-- Tab 切换 -->
    <div class="panel-tabs">
      <button
        class="panel-tab"
        :class="{ active: activeTab === 'chats' }"
        @click="switchTab('chats')"
      >
        💬 对话历史
        <span v-if="chatHistory.length" class="tab-count">{{ chatHistory.length }}</span>
      </button>
      <button
        class="panel-tab"
        :class="{ active: activeTab === 'trips' }"
        @click="switchTab('trips')"
      >
        🧳 行程足迹
        <span v-if="tripHistory.length" class="tab-count">{{ tripHistory.length }}</span>
      </button>
      <button
        class="panel-tab"
        :class="{ active: activeTab === 'prefs' }"
        @click="switchTab('prefs')"
      >
        ⚙️ 偏好管理
      </button>
    </div>

    <!-- 加载中 / 错误 -->
    <div v-if="loading" class="panel-state">
      <span class="spinner"></span> 正在加载历史数据...
    </div>
    <div v-else-if="error" class="panel-state error">
      {{ error }}
      <button class="retry-btn" @click="loadData">重试</button>
    </div>

    <template v-else>
      <!-- ===== 对话历史 Tab ===== -->
      <div v-if="activeTab === 'chats'" class="tab-body">
        <!-- 统计摘要 -->
        <div class="stat-cards">
          <div class="stat-card">
            <div class="stat-num">{{ statistics.total_trips || 0 }}</div>
            <div class="stat-label">累计行程</div>
          </div>
          <div class="stat-card">
            <div class="stat-num">{{ statistics.total_messages || 0 }}</div>
            <div class="stat-label">累计消息</div>
          </div>
          <div class="stat-card">
            <div class="stat-num">{{ Object.keys(frequentDestinations).length || 0 }}</div>
            <div class="stat-label">去过城市</div>
          </div>
        </div>

        <!-- 常去目的地 -->
        <div v-if="Object.keys(frequentDestinations).length" class="freq-block">
          <div class="block-title">🌍 常去目的地</div>
          <div class="freq-tags">
            <span v-for="(cnt, city) in frequentDestinations" :key="city" class="freq-tag">
              {{ city }} <b>×{{ cnt }}</b>
            </span>
          </div>
        </div>

        <!-- 对话记录（分组展示） -->
        <div class="chat-timeline">
          <div v-if="!chatGroups.length" class="empty-hint">暂无对话记录</div>
          <div v-for="(group, i) in chatGroups" :key="i" class="chat-group">
            <!-- 用户消息（上） -->
            <div v-if="group.user" class="cg-item cg-user">
              <div class="cg-meta">
                <span class="tl-role user">你</span>
                <span class="tl-time">{{ formatTime(group.user.timestamp) }}</span>
              </div>
              <div class="tl-content" :title="group.user.content">{{ truncate(group.user.content, 160) }}</div>
            </div>

            <!-- 助手回复（下） -->
            <div v-if="group.assistant" class="cg-item cg-assistant">
              <div class="cg-meta">
                <span class="tl-role assistant">助手</span>
                <span class="tl-time">{{ formatTime(group.assistant.timestamp) }}</span>
              </div>
              <div class="tl-content" :title="group.assistant.content">{{ truncate(group.assistant.content, 200) }}</div>
            </div>

            <!-- 组操作：右下角删除 -->
            <div class="cg-actions">
              <button class="cg-delete" @click="removeChatGroup(group)" aria-label="删除这条对话记录" title="删除这条对话记录">🗑 删除</button>
            </div>
          </div>
        </div>
      </div>

      <!-- ===== 行程足迹 Tab ===== -->
      <div v-if="activeTab === 'trips'" class="tab-body">
        <div v-if="!tripHistory.length" class="empty-hint">暂无行程记录，快去规划一次旅行吧！</div>
        <div v-for="trip in tripHistory" :key="trip.trip_id" class="trip-card">
          <div class="trip-route">
            <span class="trip-origin">{{ trip.origin || '？' }}</span>
            <span class="trip-arrow">→</span>
            <span class="trip-dest">{{ trip.destination || '？' }}</span>
          </div>
          <div class="trip-info">
            <span class="trip-date">{{ trip.start_date || '' }}{{ trip.end_date && trip.end_date !== trip.start_date ? ' ~ ' + trip.end_date : '' }}</span>
            <span v-if="trip.duration" class="trip-days">{{ trip.duration }}</span>
          </div>
          <div v-if="trip.summary" class="trip-summary">{{ trip.summary }}</div>
          <div class="trip-tags">
            <span v-if="trip.transportation" class="trip-tag">🚄 {{ trip.transportation }}</span>
            <span v-if="trip.purpose" class="trip-tag">🎯 {{ trip.purpose }}</span>
          </div>
          <div class="trip-actions">
            <button class="trip-delete" @click="removeTrip(trip)" aria-label="删除这条行程" title="删除这条行程">🗑 删除</button>
          </div>
        </div>
      </div>

      <!-- ===== 偏好管理 Tab ===== -->
      <div v-if="activeTab === 'prefs'" class="tab-body">
        <div class="prefs-edit">
          <div v-if="!prefList.length" class="empty-hint">暂无保存的偏好</div>
          <div v-for="(item, i) in prefList" :key="item.type" class="pref-row">
            <div class="pref-left">
              <div class="pref-type">{{ prefTypeName(item.type) }}</div>
              <div class="pref-value">
                <input
                  v-model="prefList[i].valueText"
                  :placeholder="prefTypeHint(item.type)"
                  class="pref-input"
                />
              </div>
            </div>
            <div class="pref-actions">
              <button class="pref-save" @click="savePref(i)" aria-label="保存" title="保存">✓</button>
              <button class="pref-delete" @click="removePref(i)" aria-label="删除" title="删除">×</button>
            </div>
          </div>

          <!-- 新增偏好 -->
          <div class="pref-add">
            <select v-model="newPrefType" class="pref-type-select">
              <option value="">+ 选择偏好类型</option>
              <option v-for="t in prefTypes" :key="t.value" :value="t.value">{{ t.label }}</option>
            </select>
            <input v-model="newPrefValue" placeholder="偏好值" class="pref-add-input" />
            <button class="pref-add-btn" @click="addPref">添加</button>
          </div>

          <div class="prefs-hint">偏好保存在后端长期记忆中，规划新行程时会自动参考。</div>
          <transition name="fade">
            <div v-if="showSavedHint" class="saved-hint">✓ 偏好已保存</div>
          </transition>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import dayjs from 'dayjs'
import { fetchHistory, savePreference, deleteChatHistory, deleteTripHistory } from '../services/api'

const emit = defineEmits<{ (e: 'close'): void }>()
void emit

const activeTab = ref<'chats' | 'trips' | 'prefs'>('chats')
const loading = ref(false)
const error = ref('')

const chatHistory = ref<any[]>([])
const tripHistory = ref<any[]>([])
const preferences = ref<Record<string, any>>({})
const statistics = ref<Record<string, any>>({})

// 面板标题
const panelTitle = computed(() => {
  switch (activeTab.value) {
    case 'chats': return '历史对话'
    case 'trips': return '行程足迹'
    case 'prefs': return '偏好管理'
  }
})
const panelSubtitle = computed(() => {
  switch (activeTab.value) {
    case 'chats': return '查看你与助手的完整对话记录'
    case 'trips': return '过去规划的行程一览'
    case 'prefs': return '管理保存的旅行偏好'
  }
})

// 常去目的地
const frequentDestinations = computed(() => statistics.value.frequent_destinations || {})

// 对话时间线（按顺序配对成组：user 开组，随后的 assistant 归入该组；从新到旧）
interface ChatGroup {
  key: string
  user: any | null
  assistant: any | null
  timestamps: string[]
}
const chatGroups = computed<ChatGroup[]>(() => {
  const groups: ChatGroup[] = []
  let current: ChatGroup | null = null
  for (const msg of chatHistory.value) {
    const role = msg.role || ''
    const ts = msg.timestamp || ''
    if (role === 'user') {
      current = { key: ts || String(Date.now() + Math.random()), user: msg, assistant: null, timestamps: [ts] }
      groups.push(current)
    } else if (role === 'assistant') {
      // 助手消息归入上一个 user 组；若无 user 组则自成一列
      if (current && !current.assistant) {
        current.assistant = msg
        current.timestamps.push(ts)
      } else {
        current = { key: ts || String(Date.now() + Math.random()), user: null, assistant: msg, timestamps: [ts] }
        groups.push(current)
      }
    }
  }
  return groups.reverse() // 从新到旧
})

// 删除一组对话记录
async function removeChatGroup(group: ChatGroup) {
  try {
    await deleteChatHistory(group.timestamps)
    // 从本地移除该组消息（按 timestamp 移除）
    const tsSet = new Set(group.timestamps)
    chatHistory.value = chatHistory.value.filter((m) => !tsSet.has(m.timestamp))
    if (statistics.value.total_messages) {
      statistics.value.total_messages = Math.max(0, (statistics.value.total_messages || 0) - group.timestamps.length)
    }
  } catch (e: any) {
    error.value = '删除失败：' + (e?.message || '网络错误')
  }
}

// 删除一条行程足迹
async function removeTrip(trip: any) {
  try {
    await deleteTripHistory(trip.trip_id)
    tripHistory.value = tripHistory.value.filter((t) => t.trip_id !== trip.trip_id)
    if (statistics.value.total_trips) {
      statistics.value.total_trips = Math.max(0, (statistics.value.total_trips || 0) - 1)
    }
  } catch (e: any) {
    error.value = '删除失败：' + (e?.message || '网络错误')
  }
}

// ===== 偏好编辑 =====
const prefTypes = [
  { value: 'home_location', label: '常住地' },
  { value: 'hotel_brands', label: '酒店偏好' },
  { value: 'transportation_preference', label: '交通偏好' },
  { value: 'food_preference', label: '美食偏好' },
  { value: 'budget_level', label: '预算等级' },
  { value: 'meal_preference', label: '餐食偏好' },
  { value: 'airlines', label: '航空公司' },
  { value: 'seat_preference', label: '座位偏好' },
]
const prefList = reactive<any[]>([])
const newPrefType = ref('')
const newPrefValue = ref('')

const PREF_NAMES: Record<string, string> = {
  last_origin: '默认出发地', home_location: '常住地', hotel_brands: '酒店偏好',
  transportation_preference: '交通偏好', food_preference: '美食偏好', budget_level: '预算等级',
  meal_preference: '餐食偏好', airlines: '航空公司', seat_preference: '座位偏好',
}
function prefTypeName(t: string) { return PREF_NAMES[t] || t }
function prefTypeHint(t: string) {
  const hints: Record<string, string> = {
    hotel_brands: '如：汉庭、如家',
    transportation_preference: '如：高铁、飞机',
    food_preference: '如：杭帮菜、川菜',
    home_location: '如：南京',
    budget_level: '如：经济、舒适、豪华',
  }
  return hints[t] || '偏好值'
}

function valueToText(v: any): string {
  if (Array.isArray(v)) return v.join('、')
  return String(v ?? '')
}

function loadPrefList() {
  prefList.length = 0
  for (const [type, value] of Object.entries(preferences.value)) {
    prefList.push({ type, valueText: valueToText(value), original: value })
  }
}

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchHistory('default_user', 'default', 50)
    chatHistory.value = res.chat_history || []
    tripHistory.value = (res.trip_history || []).slice().reverse()
    preferences.value = res.preferences || {}
    statistics.value = res.statistics || {}
    loadPrefList()
  } catch (e: any) {
    error.value = '加载历史数据失败：' + (e?.message || '网络错误')
  } finally {
    loading.value = false
  }
}

function switchTab(tab: 'chats' | 'trips' | 'prefs') {
  activeTab.value = tab
}

async function removePref(i: number) {
  const item = prefList[i]
  // 后端删除偏好：置空即可（后端无删除接口，用空串覆盖）
  try {
    await savePreference(item.type, '', 'replace')
    prefList.splice(i, 1)
  } catch (e: any) {
    error.value = '删除失败：' + (e?.message || '网络错误')
  }
}

async function savePref(i: number) {
  const item = prefList[i]
  const value = item.valueText.trim()
  if (!value) {
    error.value = '偏好值不能为空'
    return
  }
  try {
    await savePreference(item.type, value, 'replace')
    item.original = value
    // 触发一次性提示
    showSavedHint.value = true
    setTimeout(() => { showSavedHint.value = false }, 1500)
  } catch (e: any) {
    error.value = '保存失败：' + (e?.message || '网络错误')
  }
}

const showSavedHint = ref(false)

async function addPref() {
  if (!newPrefType.value || !newPrefValue.value.trim()) return
  try {
    // 检查是否已存在 → 覆盖
    const exists = prefList.find((p) => p.type === newPrefType.value)
    if (exists) {
      await savePreference(newPrefType.value, newPrefValue.value.trim(), 'replace')
      exists.valueText = newPrefValue.value.trim()
    } else {
      await savePreference(newPrefType.value, newPrefValue.value.trim(), 'replace')
      prefList.push({ type: newPrefType.value, valueText: newPrefValue.value.trim(), original: null })
    }
    newPrefType.value = ''
    newPrefValue.value = ''
  } catch (e: any) {
    error.value = '保存失败：' + (e?.message || '网络错误')
  }
}

function formatTime(iso: string) {
  if (!iso) return ''
  return dayjs(iso).format('MM-DD HH:mm')
}
function truncate(s: string, n: number) {
  if (!s) return ''
  return s.length > n ? s.slice(0, n) + '…' : s
}

onMounted(loadData)
</script>

<style scoped>
.history-panel {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 420px;
  max-width: 92vw;
  background: var(--color-surface);
  border-left: 1px solid var(--color-border);
  box-shadow: -8px 0 24px rgba(0, 0, 0, 0.08);
  z-index: 200;
  display: flex;
  flex-direction: column;
  animation: slide-in 0.25s ease;
}
@keyframes slide-in {
  from { transform: translateX(40px); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: var(--space-5) var(--space-5) var(--space-3);
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}
.panel-title { margin: 0; font-size: var(--font-size-lg); font-weight: 700; }
.panel-subtitle { margin: 3px 0 0; font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.panel-close {
  background: none;
  border: none;
  font-size: 22px;
  color: var(--color-text-tertiary);
  cursor: pointer;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  line-height: 1;
}
.panel-close:hover { color: var(--color-text); background: var(--color-surface-hover); }

.panel-tabs {
  display: flex;
  gap: var(--space-1);
  padding: var(--space-3) var(--space-5);
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}
.panel-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: var(--space-2) var(--space-3);
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.panel-tab:hover { background: var(--color-surface-hover); }
.panel-tab.active { background: var(--color-primary-light); color: var(--color-primary); font-weight: 600; }
.tab-count {
  background: var(--color-primary);
  color: #fff;
  font-size: 10px;
  border-radius: 10px;
  padding: 0 6px;
  line-height: 16px;
}

.tab-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-4) var(--space-5);
}

.panel-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}
.panel-state.error { color: var(--color-error); flex-direction: column; }
.retry-btn {
  padding: var(--space-2) var(--space-4);
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
}
.spinner {
  width: 16px; height: 16px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.empty-hint {
  padding: var(--space-6);
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

/* 统计卡片 */
.stat-cards { display: flex; gap: var(--space-3); margin-bottom: var(--space-4); }
.stat-card {
  flex: 1;
  padding: var(--space-3);
  background: var(--color-primary-bg);
  border-radius: var(--radius-md);
  text-align: center;
}
.stat-num { font-size: 20px; font-weight: 700; color: var(--color-primary); }
.stat-label { font-size: var(--font-size-xs); color: var(--color-text-tertiary); margin-top: 2px; }

.freq-block { margin-bottom: var(--space-4); }
.block-title { font-size: var(--font-size-sm); font-weight: 600; margin-bottom: var(--space-2); }
.freq-tags { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.freq-tag {
  padding: 4px 12px;
  background: var(--color-surface-hover);
  border-radius: 14px;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}
.freq-tag b { color: var(--color-primary); }

/* 对话记录（分组） */
.chat-timeline { display: flex; flex-direction: column; gap: var(--space-3); }
.chat-group {
  position: relative;
  padding: var(--space-3);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}
.cg-item { margin-bottom: var(--space-3); }
.cg-item:last-child { margin-bottom: 0; }
.cg-item + .cg-item {
  border-top: 1px dashed var(--color-border);
  padding-top: var(--space-3);
}
.cg-meta { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-2); }
.tl-role {
  font-size: var(--font-size-xs);
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
}
.tl-role.user { background: var(--color-primary-light); color: var(--color-primary); }
.tl-role.assistant { background: var(--color-surface-hover); color: var(--color-text-secondary); }
.tl-time { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.tl-content {
  font-size: var(--font-size-sm);
  color: var(--color-text);
  line-height: var(--line-height-normal);
  white-space: pre-wrap;
  word-break: break-word;
}
.cg-actions { display: flex; justify-content: flex-end; margin-top: var(--space-2); }
.cg-delete {
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  cursor: pointer;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  transition: color var(--transition-fast), background var(--transition-fast);
}
.cg-delete:hover { color: var(--color-error); background: rgba(239, 68, 68, 0.08); }

/* 行程卡片 */
.trip-card {
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-3);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}
.trip-card:hover { border-color: var(--color-primary); box-shadow: var(--shadow-sm); }
.trip-route { display: flex; align-items: center; gap: var(--space-2); font-size: var(--font-size-md); font-weight: 700; }
.trip-arrow { color: var(--color-text-tertiary); }
.trip-dest { color: var(--color-primary); }
.trip-info { margin: var(--space-2) 0; font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.trip-summary { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-bottom: var(--space-2); }
.trip-tags { display: flex; gap: var(--space-2); flex-wrap: wrap; }
.trip-tag {
  font-size: var(--font-size-xs);
  padding: 3px 10px;
  background: var(--color-surface-hover);
  border-radius: 12px;
  color: var(--color-text-secondary);
}
.trip-actions { display: flex; justify-content: flex-end; margin-top: var(--space-2); }
.trip-delete {
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  cursor: pointer;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  transition: color var(--transition-fast), background var(--transition-fast);
}
.trip-delete:hover { color: var(--color-error); background: rgba(239, 68, 68, 0.08); }

/* 偏好编辑 */
.prefs-edit { display: flex; flex-direction: column; gap: var(--space-3); }
.pref-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
}
.pref-left { flex: 1; min-width: 0; }
.pref-type { font-size: var(--font-size-xs); font-weight: 600; color: var(--color-text-secondary); margin-bottom: 4px; }
.pref-input {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  font-family: var(--font-sans);
  box-sizing: border-box;
}
.pref-input:focus { border-color: var(--color-primary); outline: none; }
.pref-delete {
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  font-size: 16px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}
.pref-delete:hover { color: var(--color-error); background: rgba(239, 68, 68, 0.08); }

.pref-actions { display: flex; align-items: center; gap: 2px; flex-shrink: 0; }
.pref-save {
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}
.pref-save:hover { color: var(--color-success); background: rgba(82, 196, 26, 0.1); }

.saved-hint {
  padding: var(--space-2) var(--space-3);
  background: var(--color-success-bg, #f6ffed);
  border: 1px solid #b7eb8f;
  color: #389e0d;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  text-align: center;
}
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.pref-add {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
}
.pref-type-select, .pref-add-input {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  font-family: var(--font-sans);
  background: var(--color-surface);
}
.pref-type-select { width: 40%; }
.pref-add-input { flex: 1; min-width: 0; }
.pref-add-btn {
  padding: var(--space-2) var(--space-4);
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  flex-shrink: 0;
}
.pref-add-btn:hover { background: var(--color-primary-hover); }

.prefs-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: var(--space-2);
}

@media (max-width: 768px) {
  .history-panel { width: 100%; max-width: 100%; }
}
</style>
