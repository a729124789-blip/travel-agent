<template>
  <div class="app-layout">
    <!-- 侧边栏 -->
    <AppSidebar
      :conversations="conversations"
      :active-id="activeConversationId"
      :collapsed="sidebarCollapsed"
      @new-chat="newConversation"
      @select="loadConversation"
      @delete="deleteConversation"
      @open-preferences="showPrefsModal = true"
      @open-history="openHistoryPanel"
      @toggle="sidebarCollapsed = !sidebarCollapsed"
    />

    <!-- 主工作区 -->
    <main class="workspace">
      <ChatHeader />

      <!-- 聊天滚动区 -->
      <div ref="chatArea" class="chat-scroll">
        <div class="chat-content">
          <!-- 空状态 -->
          <EmptyState v-if="isEmpty" @select="handleSuggestion" />

          <template v-else>
            <!-- 消息列表 -->
            <div
              v-for="(msg, idx) in messages"
              :key="idx"
              class="msg-enter"
              :class="msg.role === 'user' ? 'user-msg' : 'ai-msg'"
            >
              <!-- AI 消息 -->
              <template v-if="msg.role === 'assistant'">
                <div class="ai-label">
                  <span class="ai-icon">🤖</span>
                  <span class="ai-name">智能旅行助手</span>
                  <span class="msg-time">{{ formatTime(msg.timestamp) }}</span>
                </div>
                <template v-for="(seg, segIdx) in buildMessageSegments(msg)" :key="'seg' + segIdx">
                  <!-- 天气横幅 -->
                  <div v-if="seg.type === 'weather'" class="weather-banner">
                    <span class="weather-icon">
                      {{ seg.weather.dayweather?.includes('雨') ? '🌧️' : seg.weather.dayweather?.includes('晴') ? '☀️' : seg.weather.dayweather?.includes('云') ? '⛅' : '🌤️' }}
                    </span>
                    <span class="weather-info">
                      天气：{{ seg.weather.dayweather || '' }}/{{ seg.weather.nightweather || '' }} ·
                      {{ seg.weather.daytemp || '?' }}°C ~ {{ seg.weather.nighttemp || '?' }}°C
                      <template v-if="seg.weather.wind"> · {{ seg.weather.wind }}风</template>
                    </span>
                  </div>
                  <!-- 文本段（含 POI 触发词） -->
                  <div
                    v-if="seg.type === 'text'"
                    class="ai-content markdown-body"
                    v-html="seg.html"
                    @mouseover="onPoiOver($event, seg.pois)"
                    @mouseleave="onPoiOut"
                    @click="onPoiClick($event, seg.pois)"
                  ></div>
                  <!-- 景点推荐栏（晚上与住宿之间，含行程内景点+热门补充） -->
                  <div v-else-if="seg.type === 'poi'" class="card-group">
                    <div class="card-group-title">📍 景点推荐</div>
                    <div class="poi-grid">
                      <div v-for="(p, pIdx) in seg.pois" :key="'p' + pIdx" class="poi-card">
                        <div class="poi-card-photo">
                          <img
                            v-if="p.photo"
                            :src="p.photo"
                            :alt="p.poi_name || p.name"
                            loading="lazy"
                            @error="(e:any) => (e.target.style.display = 'none')"
                          />
                          <div v-else class="poi-photo-placeholder">📍</div>
                        </div>
                        <div class="poi-card-body">
                          <div class="poi-card-name">{{ p.poi_name || p.name }}</div>
                          <div class="poi-card-meta">
                            <span v-if="p.rating" class="poi-card-rating">⭐ {{ p.rating }}</span>
                            <span v-if="p.level" class="poi-card-level">{{ p.level }}</span>
                          </div>
                          <div v-if="p.address" class="poi-card-addr">📍 {{ p.address }}</div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <!-- 12306 真实车次卡片段 -->
                  <div v-else-if="seg.type === 'train'" class="card-group">
                    <div class="card-group-title">🚄 可选车次（12306 实时余票）</div>
                    <div class="train-grid">
                      <div v-for="(tr, tIdx) in seg.trains" :key="'t' + tIdx" class="train-card">
                        <div class="train-head">
                          <span class="train-no">{{ tr.train_no }}</span>
                          <span class="train-time">{{ tr.dep_time || '' }} → {{ tr.arr_time || '' }}</span>
                          <span v-if="tr.duration" class="train-duration">历时 {{ tr.duration }}</span>
                        </div>
                        <div v-if="tr.seats?.length" class="train-seats">
                          <span v-for="(s, sIdx) in tr.seats" :key="'s' + sIdx" class="train-seat">
                            {{ s.type }}<b>{{ s.price ? s.price + '元' : '' }}</b>
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                  <!-- 真实酒店推荐卡片段 -->
                  <div v-else-if="seg.type === 'hotel'" class="card-group">
                    <div class="card-group-title">🏨 真实酒店推荐（RollingGo 实时数据）</div>
                    <div class="hotel-grid">
                      <div v-for="(h, hIdx) in seg.hotels" :key="'h' + hIdx" class="hotel-card">
                        <div class="hotel-head">
                          <span class="hotel-name">{{ h.name }}</span>
                          <span v-if="h.starRating" class="hotel-star">{{ '★'.repeat(Math.min(h.starRating, 5)) }}</span>
                        </div>
                        <div class="hotel-meta">
                          <span class="hotel-price">¥{{ h.lowestPrice }}/晚</span>
                          <span v-if="h.priceTier" class="hotel-tier">{{ h.priceTier }}</span>
                        </div>
                        <div v-if="h.address" class="hotel-addr">📍 {{ h.address }}</div>
                        <div v-if="h.tags?.length" class="hotel-tags">
                          <span v-for="(tg, tgIdx) in h.tags.slice(0, 5)" :key="'tg' + tgIdx" class="hotel-tag">{{ tg }}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </template>
                <div class="ai-actions">
                  <button class="action-btn" @click="copyMessage(msg.text)" aria-label="复制">
                    <span>📋</span> 复制
                  </button>
                  <button class="action-btn" @click="regenerateLast" aria-label="重新生成">
                    <span>🔄</span> 重新生成
                  </button>
                </div>
              </template>
              <!-- 用户消息 -->
              <div v-else class="user-msg-wrap">
                <div class="user-bubble">{{ msg.text }}</div>
                <div class="user-time">{{ formatTime(msg.timestamp) }}</div>
              </div>
            </div>

            <!-- AI 思考中 -->
            <div v-if="analyzing" class="ai-msg msg-enter">
              <div class="ai-label">
                <span class="ai-icon">🤖</span>
                <span class="ai-name">智能旅行助手</span>
              </div>
              <div class="ai-content thinking">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="thinking-text">{{ thinkingText }}</span>
              </div>
              <!-- 深度思考过程实时展示（glm 深度思考模型） -->
              <div v-if="reasoningText" class="reasoning-box">
                <div class="reasoning-label">🤔 模型思考中（实时）</div>
                <div class="reasoning-content" ref="reasoningBox">{{ reasoningText }}</div>
              </div>
            </div>

            <!-- 行程确认表单 -->
            <div v-if="showForm" class="ai-msg msg-enter">
              <div class="ai-label">
                <span class="ai-icon">🤖</span>
                <span class="ai-name">智能旅行助手</span>
              </div>
              <div class="ai-content">
                <div class="form-hint">已根据你的描述自动提取以下信息，请确认或补充必要信息：</div>
                <div class="itinerary-card">
                  <div class="form-grid">
                    <div class="field">
                      <label>出发城市</label>
                      <input v-model="formFields.departure_city" placeholder="例如：上海" />
                    </div>
                    <div class="field">
                      <label>目的地城市</label>
                      <input v-model="formFields.city" placeholder="例如：杭州" />
                    </div>
                    <div class="field">
                      <label>开始日期</label>
                      <a-date-picker
                        v-model:value="formFields.start_date"
                        value-format="YYYY-MM-DD"
                        format="YYYY年MM月DD日"
                        placeholder="请选择日期"
                        style="width: 100%"
                      />
                    </div>
                    <div class="field">
                      <label>旅行天数</label>
                      <a-input-number
                        v-model:value="formFields.travel_days"
                        :min="1"
                        :max="30"
                        style="width: 100%"
                      />
                    </div>
                  </div>

                  <div class="form-grid form-grid-half">
                    <div class="field">
                      <label>交通方式</label>
                      <a-select v-model:value="formFields.transportation" style="width: 100%">
                        <a-select-option value="公共交通">🚇 公共交通</a-select-option>
                        <a-select-option value="自驾">🚗 自驾</a-select-option>
                        <a-select-option value="飞机">✈️ 飞机</a-select-option>
                        <a-select-option value="高铁">🚄 高铁</a-select-option>
                        <a-select-option value="火车">🚆 火车</a-select-option>
                      </a-select>
                    </div>
                    <div class="field">
                      <label>住宿偏好</label>
                      <a-select v-model:value="formFields.accommodation" style="width: 100%">
                        <a-select-option value="经济型酒店">💰 经济型酒店</a-select-option>
                        <a-select-option value="舒适型酒店">🏨 舒适型酒店</a-select-option>
                        <a-select-option value="豪华酒店">🌟 豪华酒店</a-select-option>
                        <a-select-option value="民宿">🏠 民宿</a-select-option>
                        <a-select-option value="青旅">🎒 青旅</a-select-option>
                      </a-select>
                    </div>
                  </div>

                  <div class="field">
                    <label>旅行偏好</label>
                    <div class="preference-tags">
                      <a-checkbox-group v-model:value="formFields.preferences" class="custom-checkbox-group">
                        <a-checkbox
                          v-for="pref in preferenceOptions"
                          :key="pref.value"
                          :value="pref.value"
                          class="preference-tag"
                        >{{ pref.icon }} {{ pref.label }}</a-checkbox>
                      </a-checkbox-group>
                    </div>
                  </div>

                  <div class="field field-spaced">
                    <label>额外要求</label>
                    <textarea
                      v-model="formFields.free_text"
                      rows="2"
                      placeholder="例如：预算、想去的景点、特殊需求..."
                    ></textarea>
                  </div>

                  <div class="end-date-hint">行程结束日期：<b>{{ computedEndDate }}</b></div>

                  <div class="form-actions">
                    <button class="btn-primary" @click="confirmAndGenerate">确认并生成行程</button>
                    <button class="btn-secondary" @click="resetForm">重新填写</button>
                  </div>
                </div>
              </div>
            </div>

            <!-- 生成中 -->
            <div v-if="generating" class="ai-msg msg-enter">
              <div class="ai-label">
                <span class="ai-icon">🤖</span>
                <span class="ai-name">智能旅行助手</span>
              </div>
              <div class="ai-content thinking">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="thinking-text">{{ thinkingText }}</span>
              </div>
            </div>

            <!-- 生成结果 -->
            <div v-if="result && !generating" class="ai-msg msg-enter">
              <div class="ai-label">
                <span class="ai-icon">🤖</span>
                <span class="ai-name">智能旅行助手</span>
              </div>
              <div class="ai-content result-content">
                <h3 class="result-title">📍 {{ result.city }}行程规划</h3>
                <p class="result-meta"><b>日期：</b>{{ result.start_date }} 至 {{ result.end_date }}</p>
                <div v-for="day in result.days" :key="day.day_index" class="day-plan">
                  <h4>Day {{ day.day_index }}（{{ day.date }}）</h4>
                  <p>{{ day.description }}</p>
                  <p v-if="day.attractions?.length"><b>景点：</b>{{ day.attractions.map(a => a.name).join('、') }}</p>
                  <p v-if="day.meals?.length"><b>餐饮：</b>{{ day.meals.map(m => m.name).join('、') }}</p>
                  <p v-if="day.hotel"><b>住宿：</b>{{ day.hotel.name }}（{{ day.hotel.price_range }}）</p>
                </div>
                <div v-if="result.weather_info?.length" class="result-section">
                  <h4>🌤️ 天气</h4>
                  <p v-for="w in result.weather_info" :key="w.date">
                    {{ w.date }}：{{ w.day_weather }}，{{ w.day_temp }}°C ~ {{ w.night_temp }}°C
                  </p>
                </div>
                <div v-if="result.budget" class="result-section">
                  <h4>💰 预算估算</h4>
                  <p>景点：{{ result.budget.total_attractions }}元</p>
                  <p>住宿：{{ result.budget.total_hotels }}元</p>
                  <p>餐饮：{{ result.budget.total_meals }}元</p>
                  <p>交通：{{ result.budget.total_transportation }}元</p>
                  <p class="budget-total"><b>总计：{{ result.budget.total }}元</b></p>
                </div>
                <p v-if="result.overall_suggestions" class="result-suggestions">
                  <b>💡 建议：</b>{{ result.overall_suggestions }}
                </p>
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- 输入区 -->
      <ChatComposer
        ref="composerRef"
        v-model="composerText"
        :disabled="analyzing || generating"
        @send="handleSend"
      />
    </main>

    <!-- 偏好管理弹窗 -->
    <PreferencesModal
      :visible="showPrefsModal"
      :prefs="prefs"
      @close="showPrefsModal = false"
      @save="handleSavePrefs"
    />

    <!-- 历史记录 / 行程足迹 / 偏好管理 完整面板 -->
    <HistoryPanel v-if="showHistoryPanel" @close="showHistoryPanel = false" />

    <!-- POI 触发式卡片（点击/悬停景点名弹出） -->
    <Teleport to="body">
      <div
        v-if="poiPop.show && poiPop.poi"
        class="poi-popover"
        :style="{ left: poiPop.x + 'px', top: poiPop.y + 'px' }"
        @click.stop
      >
        <div class="poi-pop-photo" v-if="poiPop.poi.type !== 'hotel'">
          <img
            v-if="poiPop.poi.photo"
            :src="poiPop.poi.photo"
            :alt="poiPop.poi.poi_name || poiPop.poi.name"
            loading="lazy"
            @error="(e:any) => (e.target.style.display = 'none')"
          />
          <div v-else class="poi-photo-placeholder">📍</div>
        </div>
        <div class="poi-pop-body">
          <div class="poi-pop-name">{{ poiPop.poi.poi_name || poiPop.poi.name }}</div>
          <!-- 酒店类型：星级 + 价格 + 设施标签 -->
          <template v-if="poiPop.poi.type === 'hotel'">
            <div class="poi-pop-meta">
              <span v-if="poiPop.poi.star" class="poi-pop-rating">{{ '★'.repeat(Math.min(poiPop.poi.star, 5)) }}</span>
              <span v-if="poiPop.poi.price" class="poi-pop-price">¥{{ poiPop.poi.price }}/晚</span>
            </div>
            <div v-if="poiPop.poi.tags?.length" class="poi-pop-tags">
              <span v-for="(tg, tgIdx) in poiPop.poi.tags.slice(0, 5)" :key="'tg' + tgIdx" class="poi-pop-tag">{{ tg }}</span>
            </div>
          </template>
          <!-- 景点类型：评分 + 等级 + 营业时间 -->
          <template v-else>
            <div class="poi-pop-meta">
              <span v-if="poiPop.poi.rating" class="poi-pop-rating">⭐ {{ poiPop.poi.rating }}</span>
              <span v-if="poiPop.poi.level" class="poi-pop-level">{{ poiPop.poi.level }}</span>
            </div>
            <div v-if="poiPop.poi.open_time" class="poi-pop-open">🕐 {{ poiPop.poi.open_time }}</div>
          </template>
          <div v-if="poiPop.poi.address" class="poi-pop-addr">📍 {{ poiPop.poi.address }}</div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import dayjs, { type Dayjs } from 'dayjs'
import { message } from 'ant-design-vue'
import { marked } from 'marked'
import AppSidebar from '../components/AppSidebar.vue'
import ChatHeader from '../components/ChatHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import ChatComposer from '../components/ChatComposer.vue'
import PreferencesModal from '../components/PreferencesModal.vue'
import HistoryPanel from '../components/HistoryPanel.vue'
import { generateTripPlan, fetchPreferences, savePreference, streamChat, dayPlanStream } from '../services/api'
import { analyzeIntent, type ItineraryFields } from '../services/intent'
import type { TripFormData, TripPlan } from '../types'

// ===== 类型 =====
interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  timestamp: number
  /** 高德补充的景点/餐厅真实信息（图片/评分/经纬度等），仅 assistant 消息可选 */
  pois?: Array<{
    name: string
    poi_name?: string
    address?: string
    photo?: string
    location?: string
    rating?: string
    open_time?: string
    level?: string
  }>
  /** 12306 真实车次信息（当天跨城移动时） */
  trains?: Array<{
    train_no: string
    dep_time?: string
    arr_time?: string
    duration?: string
    seats?: Array<{ type: string; price?: string; info?: string }>
  }>
  /** 当天天气（高德实时预报） */
  weather?: {
    city?: string
    date?: string
    dayweather?: string
    nightweather?: string
    daytemp?: string
    nighttemp?: string
    wind?: string
  }
  /** 真实酒店推荐（RollingGo） */
  hotels?: Array<{
    hotelId?: number
    name?: string
    starRating?: number
    lowestPrice?: number
    address?: string
    priceTier?: string
    tags?: string[]
    amenities?: string[]
  }>
}
interface Conversation {
  id: string
  title: string
  destination: string
  createdAt: number
  messages: ChatMessage[]
  formFields: any
  showForm: boolean
  result: TripPlan | null
  /** 该对话的逐天行程状态（切回对话后用于继续"下一天"） */
  dayPlan?: {
    totalDays: number
    currentDay: number
    daysText: string[]
    poiNamesByDay: string[][]
    formData: TripFormData | null
  } | null
}
interface UserPreferences {
  departure_city: string
  transportation: string
  accommodation: string
  preferences: string[]
  budget: string
  companions: string
}

// ===== 常量 =====
const preferenceOptions = [
  { value: '历史文化', label: '历史文化', icon: '🏛️' },
  { value: '自然风光', label: '自然风光', icon: '🏞️' },
  { value: '美食', label: '美食', icon: '🍜' },
  { value: '购物', label: '购物', icon: '🛍️' },
  { value: '艺术', label: '艺术', icon: '🎨' },
  { value: '休闲', label: '休闲', icon: '☕' },
]

const STORAGE_KEYS = {
  conversations: 'travel_assistant_conversations',
  preferences: 'travel_assistant_preferences',
}

// ===== 偏好 =====
const prefs = reactive<UserPreferences>({
  departure_city: '',
  transportation: '',
  accommodation: '',
  preferences: [],
  budget: '',
  companions: '',
})

// ===== 表单 =====
const defaultFields = () => ({
  departure_city: prefs.departure_city || '',
  city: '',
  start_date: null as Dayjs | null,
  travel_days: 1,
  transportation: prefs.transportation || '公共交通',
  accommodation: prefs.accommodation || '经济型酒店',
  preferences: [...prefs.preferences] as string[],
  free_text: '',
})

const formFields = reactive(defaultFields())

// ===== 状态 =====
const chatArea = ref<HTMLElement | null>(null)
const composerRef = ref<any>(null)
const composerText = ref('')
const messages = ref<ChatMessage[]>([])
const analyzing = ref(false)
const generating = ref(false)
const thinkingText = ref('正在分析你的需求...')
const reasoningText = ref('') // 深度思考模型（glm）的思考过程实时展示
const reasoningBox = ref<HTMLElement | null>(null)
const showForm = ref(false)
const result = ref<TripPlan | null>(null)

// ===== 会话代际令牌：切换/新建会话时递增，使旧会话进行中的异步生成失效 =====
const sessionEpoch = ref(0)
let activeAbortController: AbortController | null = null

// ===== 逐天行程规划状态（方案A：一次生成一天，用户满意再继续） =====
const dayPlanMode = ref(false) // 是否处于逐天推进模式
const dayPlanFeedback = ref('') // 用户对当前天的修改意见（待传给后端）
const dayPlanState = reactive({
  totalDays: 1,
  currentDay: 0, // 已生成的最后一天（0 = 未开始）
  daysText: [] as string[], // 已生成各天的 Markdown 文本（按天序）
  poiNamesByDay: [] as string[][], // 每天展示过的景点/餐厅名（跨天去重用，按天记录）
  formData: null as TripFormData | null, // 本次行程的表单数据
})

// ===== 进行中的逐天生成状态（对话级隔离：切换对话不打断后台生成，切回可恢复"思考中"显示） =====
interface ActiveDayGen {
  convId: string // 所属对话 id
  epoch: number
  abort: AbortController | null
  thinking: string
  reasoning: string
  streamed: string
  msgPushed: boolean
  assistantMsg: ChatMessage | null // 正在流式生成的 AI 消息（独立对象，避免切走后污染其他对话的 messages）
  dayPlanMode: boolean
  totalDays: number
  currentDay: number
  daysText: string[]
  poiNamesByDay: string[][]
  formData: TripFormData | null
  feedback: string
  done: boolean
}
const activeDayGen = ref<ActiveDayGen | null>(null)

/** 切换会话时调用：递增令牌 + 中断进行中的流式请求 */
function bumpSession() {
  sessionEpoch.value += 1
  if (activeAbortController) {
    activeAbortController.abort()
    activeAbortController = null
  }
  if (activeDayGen.value) activeDayGen.value.done = true // 标记结束，避免被 restore 恢复
  activeDayGen.value = null
  analyzing.value = false
  generating.value = false
  thinkingText.value = '正在分析你的需求...'
  reasoningText.value = '' // 清空上一会话的深度思考过程，避免残留
  dayPlanMode.value = false // 切换会话退出逐天模式
}

/** 将进行中的生成结果持久化到指定对话（用于生成期间已切到别的对话的场景） */
function persistGenToConversation(gen: ActiveDayGen, extra: ChatMessage[] = []) {
  const idx = conversations.value.findIndex((c) => c.id === gen.convId)
  if (idx < 0) return
  const conv = conversations.value[idx]
  const list = [...conv.messages]
  if (gen.assistantMsg && !list.some((m) => m === gen.assistantMsg)) list.push(gen.assistantMsg)
  for (const m of extra) list.push(m)
  conversations.value[idx] = { ...conv, messages: list }
  persistConversations()
}

/** 切回对话时恢复该对话进行中的生成显示（思考/流式正文） */
function restoreActiveGen(id: string) {
  const gen = activeDayGen.value
  if (!gen || gen.done || gen.convId !== id) {
    analyzing.value = false
    generating.value = false
    reasoningText.value = ''
    return
  }
  analyzing.value = true
  generating.value = false
  thinkingText.value = gen.thinking
  reasoningText.value = gen.reasoning
  if (gen.assistantMsg && !messages.value.some((m) => m === gen.assistantMsg)) {
    messages.value.push(gen.assistantMsg)
  }
  dayPlanMode.value = gen.dayPlanMode
  dayPlanState.totalDays = gen.totalDays
  dayPlanState.currentDay = gen.currentDay
  dayPlanState.daysText = [...gen.daysText]
  dayPlanState.poiNamesByDay = gen.poiNamesByDay.map((a) => [...a])
  dayPlanState.formData = gen.formData
  dayPlanFeedback.value = gen.feedback
  nextTick(scrollToBottom)
}

/** 开始新生成前，中断属于其他对话的进行中生成（避免后台残留 + 状态串台） */
function abortStaleGen(): boolean {
  if (activeDayGen.value && activeDayGen.value.convId !== activeConversationId.value) {
    bumpSession()
    return true
  }
  return false
}

// ===== 侧边栏 =====
const conversations = ref<Conversation[]>([])
const activeConversationId = ref<string | null>(null)
const showPrefsModal = ref(false)
const sidebarCollapsed = ref(false)
const showHistoryPanel = ref(false)

// 打开历史记录面板（同时刷新后端数据）
function openHistoryPanel() {
  showHistoryPanel.value = true
}

// ===== Markdown =====
marked.setOptions({ gfm: true, breaks: true })
function renderMarkdown(text: string): string {
  try {
    return marked.parse(text) as string
  } catch {
    return text
  }
}

/**
 * 把 AI 消息拆成"文本段 + 卡片段"交错的渲染序列：
 *  - 正文按段落拆分
 *  - 景点/餐厅不单独成栏：文本中出现的景点名被注入为可触发词（hover/点击弹出卡片）
 *  - train 卡片插入到含交通/车次关键词的正文段落后；无匹配则追加到末尾
 *  - hotel 卡片插入到含住宿/酒店关键词的正文段落后；无匹配则追加到末尾
 */
function buildMessageSegments(msg: ChatMessage): Array<
  | { type: 'text'; html: string; pois: NonNullable<ChatMessage['pois']> }
  | { type: 'poi'; pois: NonNullable<ChatMessage['pois']> }
  | { type: 'train'; trains: NonNullable<ChatMessage['trains']> }
  | { type: 'weather'; weather: NonNullable<ChatMessage['weather']> }
  | { type: 'hotel'; hotels: NonNullable<ChatMessage['hotels']> }
> {
  const text = msg.text || ''
  const pois = msg.pois || []
  const trains = msg.trains || []
  const hotels = msg.hotels || []
  const weather = msg.weather
  const segments: Array<any> = []

  // 合并触发词列表：景点/餐厅 + 酒店名（酒店标记为 type='hotel'，popover 显示酒店信息）
  const segPois: NonNullable<ChatMessage['pois']> & any[] = [
    ...pois.map((p) => ({ ...p, type: 'attraction' })),
    ...hotels.map((h) => ({
      type: 'hotel',
      name: h.name,
      poi_name: h.name,
      address: h.address,
      price: h.lowestPrice,
      priceTier: h.priceTier,
      star: h.starRating,
      tags: h.tags || [],
      amenities: h.amenities || [],
    })),
  ]

  // 天气横幅：当天整体信息，置顶展示
  if (weather) segments.push({ type: 'weather', weather })

  // 触发词跨段落共享去重集合（同一实体全文只高亮一次）
  const sharedUsedNames = new Set<string>()

  // 无卡片：整段返回
  if (!trains.length && !hotels.length) {
    const html = segPois.length ? injectPoiTriggers(renderMarkdown(text), segPois, sharedUsedNames) : renderMarkdown(text)
    if (text.trim()) segments.push({ type: 'text', html, pois: segPois })
    return segments
  }

  // 按段落拆分（\n\n 或至少两个换行），保留段落顺序
  const paras = text.split(/\n{2,}/).filter((p) => p.trim())
  if (!paras.length && text.trim()) paras.push(text)

  // train 卡片：找含交通关键词的正文段（跳过标题/主题等短段）；无则放末尾
  const trainKw = ['火车', '高铁', '车次', '动车', '乘坐', '乘车', '抵达', '到达', '交通', '车票', '列车']
  let trainParaIdx = -1
  for (let i = 0; i < paras.length; i++) {
    if (paras[i].length >= 40 && trainKw.some((kw) => paras[i].includes(kw))) { trainParaIdx = i; break }
  }
  const trainEmitted = { done: false }

  const pushTrain = () => {
    if (!trainEmitted.done && trains.length) {
      trainEmitted.done = true
      segments.push({ type: 'train', trains })
    }
  }

  // hotel 卡片：精确匹配"🏨 住宿"小节标题段，在其后插入；避免误匹配"前往住宿酒店"等正文段
  let hotelParaIdx = -1
  for (let i = 0; i < paras.length; i++) {
    const p0 = paras[i].trim()
    if (/^#{1,4}\s*(?:🏨\s*)?住宿/.test(p0) || /^#{1,4}\s*住宿/.test(p0)) { hotelParaIdx = i; break }
  }
  // 兜底：未找到"住宿"标题段时，找含"推荐入住/住宿"的长正文段
  if (hotelParaIdx === -1) {
    for (let i = 0; i < paras.length; i++) {
      if (paras[i].length >= 40 && (paras[i].includes('推荐入住') || paras[i].includes('住宿'))) { hotelParaIdx = i; break }
    }
  }
  const hotelEmitted = { done: false }
  const pushHotel = () => {
    if (!hotelEmitted.done && hotels.length) {
      hotelEmitted.done = true
      segments.push({ type: 'hotel', hotels })
    }
  }
  // 景点介绍栏是否已插入（放在"住宿"段之前 = 晚上与住宿之间）
  // 只放景点类 POI（category==='attraction'）；餐厅/酒店/购物只作为正文触发词，不占景点栏
  const isFoodOrHotel = (p: any) => {
    const c = (p.category || '').trim()
    if (c === 'attraction') return false
    if (c === 'food' || c === 'hotel' || c === 'shopping' || c === 'other') return true
    // 旧数据无 category：按名称启发式判断
    const n = p.poi_name || p.name || ''
    if (/酒店|宾馆|民宿|客栈|旅店|招待所/.test(n)) return true
    if (/(店|馆|楼|庄|铺|食堂|食府|酒楼|餐厅|小吃|生煎|馒头|咖啡|甜品|茶)(?!园)/.test(n)) return true
    return false
  }
  const attractionPois = pois.filter((p) => !isFoodOrHotel(p))
  const poiEmitted = { done: false }
  const pushPoi = () => {
    if (!poiEmitted.done && attractionPois.length) {
      poiEmitted.done = true
      segments.push({ type: 'poi', pois: attractionPois })
    }
  }

  paras.forEach((para, i) => {
    // 在"住宿"段之前插入景点介绍栏（若当天有景点 POI）
    if (i === hotelParaIdx) pushPoi()
    const html = segPois.length ? injectPoiTriggers(renderMarkdown(para), segPois, sharedUsedNames) : renderMarkdown(para)
    if (para.trim()) segments.push({ type: 'text', html, pois: segPois })
    // 在交通正文段后插入车次卡片
    if (i === trainParaIdx) pushTrain()
    // 在住宿正文段后插入酒店卡片
    if (i === hotelParaIdx) pushHotel()
  })
  // 收尾：未插入的 train / hotel / 景点栏
  pushPoi()
  pushTrain()
  pushHotel()

  return segments
}

/** 把文本 HTML 中出现的景点/餐厅/酒店名替换为可触发的高亮词（占位符法避免嵌套替换） */
function injectPoiTriggers(html: string, pois: any[], sharedUsedNames?: Set<string>): string {
  // 统一全角括号为半角（正文 markdown 常用全角"（）"，后端 POI 名常用半角"()"，避免匹配失败）
  let out = html.replace(/（/g, '(').replace(/）/g, ')')
  const placeholders: Array<[string, string]> = []
  // 候选名：poi_name 与 name 都参与匹配（正文可能用简称/标准名任一写法），
  // 每个名称再附加"括号前核心名"（如"南京大牌档(夫子庙平江府店)"→"南京大牌档"，"蒋有锅贴(老门东店)"→"蒋有锅贴"），
  // 供正文用简称/无括号写法时回退匹配；核心名过短（<3字）不参与，避免误匹配。
  const candidates: Array<{ i: number; names: string[] }> = pois
    .map((p, i) => {
      const names: string[] = []
      const pushName = (n: string) => {
        const s = (n || '').trim()
        if (!s || names.includes(s)) return
        names.push(s)
      }
      for (const n of [p.poi_name, p.name]) pushName(n)
      // 核心名（括号前部分）作为回退候选，长度≥3
      for (const n of [...names]) {
        const m = n.match(/^(.+?)[(（]/)
        if (m) {
          const core = m[1].trim()
          if (core.length >= 3 && !names.includes(core)) names.push(core)
        }
      }
      return { i, names }
    })
    .filter((c) => c.names.length)
  // 按"候选名最长优先"排序，避免短名（如"布丁酒店"）先吃掉长名的一部分；同名时酒店类型优先（popover 显示价格）
  candidates.sort((a, b) => {
    const la = Math.max(...a.names.map((n) => n.length))
    const lb = Math.max(...b.names.map((n) => n.length))
    if (lb !== la) return lb - la
    const ah = pois[a.i].type === 'hotel' ? 1 : 0
    const bh = pois[b.i].type === 'hotel' ? 1 : 0
    return bh - ah
  })
  const usedNames = sharedUsedNames || new Set<string>()
  for (const { i, names } of candidates) {
    // 同一 poi 的多个候选名：只替换第一次出现（一个触发词即可，避免正文重复高亮）
    const ph = `__POI_${i}__`
    const sortedNames = [...names].sort((a, b) => b.length - a.length)
    let matched: string | null = null
    for (const nm of sortedNames) {
      if (usedNames.has(nm)) continue // 该名称已被其他 poi 高亮过（如重复的"外滩"），不再重复
      if (out.includes(nm)) {
        matched = nm
        break
      }
    }
    if (matched === null) continue
    out = out.replace(matched, ph) // 仅替换第一个匹配
    usedNames.add(matched)
    placeholders.push([
      ph,
      `<span class="poi-trigger" data-poi="${i}">${matched}</span>`,
    ])
  }
  for (const [ph, span] of placeholders) {
    out = out.split(ph).join(span)
  }
  return out
}

// ===== POI 触发式卡片（popover） =====
const poiPop = ref<{
  show: boolean
  poi: any
  x: number
  y: number
  pinned: boolean
}>({ show: false, poi: null, x: 0, y: 0, pinned: false })

/** 悬停触发词：显示卡片（若未固定） */
function onPoiOver(e: MouseEvent, pois: any[]) {
  const el = (e.target as HTMLElement).closest('.poi-trigger') as HTMLElement | null
  if (!el) return
  const idx = Number(el.dataset.poi)
  const poi = pois[idx]
  if (!poi) return
  const r = el.getBoundingClientRect()
  poiPop.value = {
    show: true,
    poi,
    x: Math.min(r.left, window.innerWidth - 280),
    y: r.bottom + 6,
    pinned: poiPop.value.pinned,
  }
}

/** 移出触发词：未固定则隐藏 */
function onPoiOut() {
  if (!poiPop.value.pinned) poiPop.value.show = false
}

/** 点击触发词：固定/取消固定 */
function onPoiClick(e: MouseEvent, pois: any[]) {
  // 点击卡片内部不处理
  if ((e.target as HTMLElement).closest('.poi-popover')) return
  const el = (e.target as HTMLElement).closest('.poi-trigger') as HTMLElement | null
  if (!el) return
  const idx = Number(el.dataset.poi)
  const poi = pois[idx]
  if (!poi) return
  if (poiPop.value.pinned && poiPop.value.poi === poi) {
    poiPop.value.pinned = false
    poiPop.value.show = false
  } else {
    const r = el.getBoundingClientRect()
    poiPop.value = { show: true, poi, x: Math.min(r.left, window.innerWidth - 280), y: r.bottom + 6, pinned: true }
  }
}

/** 点击页面其他位置：取消固定 */
function onDocClick(e: MouseEvent) {
  if (!poiPop.value.pinned) return
  const t = e.target as HTMLElement
  if (!t.closest('.poi-trigger') && !t.closest('.poi-popover')) {
    poiPop.value.pinned = false
    poiPop.value.show = false
  }
}

onMounted(() => {
  document.addEventListener('click', onDocClick)
})
onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
})
function formatTime(ts?: number): string {
  if (!ts) return ''
  return dayjs(ts).format('HH:mm')
}

// ===== 计算 =====
const isEmpty = computed(() => messages.value.length === 0 && !showForm.value && !result.value)

const computedEndDate = computed(() => {
  if (formFields.start_date && formFields.travel_days > 0) {
    return dayjs(formFields.start_date).add(formFields.travel_days - 1, 'day').format('YYYY年MM月DD日')
  }
  return '待定（请先选择出发日期）'
})

// ===== localStorage =====
function loadFromStorage() {
  try {
    const convs = localStorage.getItem(STORAGE_KEYS.conversations)
    if (convs) conversations.value = JSON.parse(convs)
    const p = localStorage.getItem(STORAGE_KEYS.preferences)
    if (p) Object.assign(prefs, JSON.parse(p))
  } catch (e) {
    console.warn('load storage failed', e)
  }
}

function persistConversations() {
  try {
    localStorage.setItem(STORAGE_KEYS.conversations, JSON.stringify(conversations.value))
  } catch (e) { /* ignore */ }
}

function persistPreferences() {
  try {
    localStorage.setItem(STORAGE_KEYS.preferences, JSON.stringify(prefs))
  } catch (e) { /* ignore */ }
}

// ===== 生命周期 =====
onMounted(async () => {
  loadFromStorage()
  // 尝试从后端加载长期偏好
  try {
    const backendPrefs = await fetchPreferences()
    if (backendPrefs && Object.keys(backendPrefs).length) {
      applyBackendPrefs(backendPrefs)
      persistPreferences()
    }
  } catch (e) {
    console.warn('后端偏好加载失败（使用本地）:', e)
  }
})

// 后端偏好 → 前端表单默认值
function applyBackendPrefs(bp: Record<string, any>) {
  const map: Record<string, string> = {
    home_location: 'departure_city',
    last_origin: 'departure_city',
    transportation_preference: 'transportation',
    hotel_brands: 'accommodation',
    budget_level: 'budget',
  }
  for (const [bk, fk] of Object.entries(map)) {
    const v = bp[bk]
    if (v && !(prefs as any)[fk]) {
      if (Array.isArray(v)) {
        ;(prefs as any)[fk] = v.join('、')
      } else {
        ;(prefs as any)[fk] = String(v)
      }
    }
  }
  // 美食/偏好标签 → preferences
  if (bp.food_preference) {
    const food = Array.isArray(bp.food_preference) ? bp.food_preference : [bp.food_preference]
    const known = preferenceOptions.map((o) => o.value)
    food.forEach((f: string) => {
      if (known.includes(f) && !prefs.preferences.includes(f)) prefs.preferences.push(f)
    })
  }
  // 补全表单默认值
  Object.assign(formFields, defaultFields())
}

// ===== 对话操作 =====
function newConversation() {
  bumpSession() // 中断旧会话进行中的生成，避免污染新会话
  activeConversationId.value = null
  messages.value = []
  showForm.value = false
  result.value = false as any
  result.value = null
  Object.assign(formFields, defaultFields())
  composerText.value = ''
  composerRef.value?.clear()
  message.success('已开始新对话')
}

function saveCurrentConversation() {
  const title = formFields.city ? `${formFields.city} ${formFields.travel_days}日游` : '未命名行程'
  const savedFields = JSON.parse(JSON.stringify(formFields))
  if (formFields.start_date) {
    savedFields.start_date = dayjs(formFields.start_date).format('YYYY-MM-DD')
  }
  // 随会话持久化逐天状态（切回后可继续"下一天"）
  const hasDayPlan = dayPlanMode.value && dayPlanState.formData
  const convDayPlan = hasDayPlan
    ? {
        totalDays: dayPlanState.totalDays,
        currentDay: dayPlanState.currentDay,
        daysText: [...dayPlanState.daysText],
        poiNamesByDay: dayPlanState.poiNamesByDay.map((a) => [...a]),
        formData: dayPlanState.formData,
      }
    : null
  const conv: Conversation = {
    id: activeConversationId.value || `conv_${Date.now()}`,
    title,
    destination: formFields.city,
    createdAt: Date.now(),
    messages: JSON.parse(JSON.stringify(messages.value)),
    formFields: savedFields,
    showForm: showForm.value,
    result: result.value ? JSON.parse(JSON.stringify(result.value)) : null,
    dayPlan: convDayPlan,
  }
  const idx = conversations.value.findIndex((c) => c.id === conv.id)
  if (idx >= 0) {
    conversations.value[idx] = conv
  } else {
    conversations.value.unshift(conv)
  }
  activeConversationId.value = conv.id
  if (conversations.value.length > 50) {
    conversations.value = conversations.value.slice(0, 50)
  }
  persistConversations()
}

function loadConversation(id: string) {
  const conv = conversations.value.find((c) => c.id === id)
  if (!conv) return
  // 切换前把当前对话的逐天状态落盘（若正处逐天模式）
  saveCurrentDayPlanToActiveConv()
  // 若没有任何"逐天后台生成"在跑（仅普通对话生成），切走即中断，避免结果串到目标对话；
  // 若有逐天后台生成（某对话正在生成行程），则保留后台继续，切回时由 restoreActiveGen 恢复显示
  if (!activeDayGen.value) bumpSession()
  activeConversationId.value = id
  messages.value = JSON.parse(JSON.stringify(conv.messages))
  const loadedFields = JSON.parse(JSON.stringify(conv.formFields))
  if (loadedFields.start_date && typeof loadedFields.start_date === 'string') {
    loadedFields.start_date = dayjs(loadedFields.start_date)
  }
  Object.assign(formFields, loadedFields)
  showForm.value = conv.showForm
  result.value = conv.result
  // 恢复该对话的逐天状态
  if (conv.dayPlan) {
    dayPlanMode.value = conv.dayPlan.currentDay > 0
    dayPlanState.totalDays = conv.dayPlan.totalDays
    dayPlanState.currentDay = conv.dayPlan.currentDay
    dayPlanState.daysText = [...conv.dayPlan.daysText]
    dayPlanState.poiNamesByDay = conv.dayPlan.poiNamesByDay.map((a) => [...a])
    dayPlanState.formData = conv.dayPlan.formData
  } else {
    dayPlanMode.value = false
    dayPlanState.totalDays = 1
    dayPlanState.currentDay = 0
    dayPlanState.daysText = []
    dayPlanState.poiNamesByDay = []
    dayPlanState.formData = null
  }
  dayPlanFeedback.value = ''
  // 若该对话有进行中的生成，恢复"思考中"显示（不打断后台生成）
  restoreActiveGen(id)
  nextTick(scrollToBottom)
}

/** 切换对话前，把当前对话的逐天状态持久化到 conv.dayPlan */
function saveCurrentDayPlanToActiveConv() {
  if (!activeConversationId.value) return
  const idx = conversations.value.findIndex((c) => c.id === activeConversationId.value)
  if (idx < 0) return
  const conv = conversations.value[idx]
  const hasDayPlan = dayPlanMode.value && dayPlanState.formData
  const dp = hasDayPlan
    ? {
        totalDays: dayPlanState.totalDays,
        currentDay: dayPlanState.currentDay,
        daysText: [...dayPlanState.daysText],
        poiNamesByDay: dayPlanState.poiNamesByDay.map((a) => [...a]),
        formData: dayPlanState.formData,
      }
    : null
  if (JSON.stringify(conv.dayPlan || null) !== JSON.stringify(dp)) {
    conversations.value[idx] = { ...conv, dayPlan: dp }
    persistConversations()
  }
}

function deleteConversation(id: string) {
  conversations.value = conversations.value.filter((c) => c.id !== id)
  persistConversations()
  if (activeConversationId.value === id) {
    newConversation()
  }
}

// ===== 偏好 =====
function handleSavePrefs(newPrefs: UserPreferences) {
  Object.assign(prefs, newPrefs)
  persistPreferences()
  // 同步到后端长期记忆（fire-and-forget，不阻塞 UI）
  try {
    if (newPrefs.departure_city) savePreference('home_location', newPrefs.departure_city, 'replace')
    if (newPrefs.transportation) savePreference('transportation_preference', newPrefs.transportation, 'replace')
    if (newPrefs.accommodation) savePreference('hotel_brands', newPrefs.accommodation, 'replace')
    if (newPrefs.budget) savePreference('budget_level', newPrefs.budget, 'replace')
    newPrefs.preferences.forEach((p, i) => {
      savePreference('food_preference', p, i === 0 ? 'replace' : 'append')
    })
  } catch (e) {
    console.warn('偏好同步后端失败:', e)
  }
  // 应用到当前表单（作为默认值，不覆盖用户已填内容）
  if (prefs.departure_city && !formFields.departure_city) {
    formFields.departure_city = prefs.departure_city
  }
  if (prefs.transportation) formFields.transportation = prefs.transportation
  if (prefs.accommodation) formFields.accommodation = prefs.accommodation
  if (prefs.preferences.length) formFields.preferences = [...prefs.preferences]
  showPrefsModal.value = false
  message.success('偏好已保存')
}

// ===== Suggestion =====
function handleSuggestion(s: { icon: string; text: string }) {
  composerText.value = s.text
  nextTick(() => composerRef.value?.focus())
}

// ===== 发送 =====
async function handleSend(text: string) {
  if (!text || analyzing.value || generating.value) return
  abortStaleGen() // 若其他对话有进行中的生成，先中断（epoch 会变化）
  const myEpoch = sessionEpoch.value // 捕获当前会话代际
  // 若本函数运行时发生了会话切换，直接放弃执行
  if (sessionEpoch.value !== myEpoch) return

  const ac = new AbortController()
  activeAbortController = ac

  messages.value.push({ role: 'user', text, timestamp: Date.now() })
  analyzing.value = true
  showForm.value = false
  result.value = null
  nextTick(scrollToBottom)

  // ===== 逐天模式：输入作为"继续/修改意见"，不重新走意图识别 =====
  if (dayPlanMode.value) {
    await handleDayPlanFeedback(text, myEpoch, ac)
    return
  }

  let intentResult
  try {
    intentResult = await analyzeIntent(text)
  } catch (e: any) {
    if (sessionEpoch.value !== myEpoch) return // 已切换会话
    messages.value.push({
      role: 'assistant',
      text: '抱歉，意图识别服务暂时不可用，请稍后重试。',
      timestamp: Date.now(),
    })
    analyzing.value = false
    nextTick(scrollToBottom)
    return
  }

  // 意图识别返回前可能已切换会话
  if (sessionEpoch.value !== myEpoch) return

  if (intentResult.intent === 'itinerary_planning') {
    applyExtracted(intentResult.fields)
    let reply = `我识别到你想去「${formFields.city || '？'}」`
    if (formFields.start_date) {
      const dateStr = dayjs(formFields.start_date).format('YYYY年MM月DD日')
      reply += `，出发日期 ${dateStr}`
    }
    if (formFields.travel_days) reply += `，共 ${formFields.travel_days} 天`
    reply += '。已自动填好下面的表单，请确认；如还有遗漏，请补充后生成。'

    messages.value.push({ role: 'assistant', text: reply, timestamp: Date.now() })
    showForm.value = true
    // 保存表单态会话，切走再切回时可继续编辑表单
    saveCurrentConversation()
  } else {
    // 非行程意图：直接走完整对话（信息查询 / 记忆查询 / 偏好等）— SSE 流式
    thinkingText.value = '正在分析你的需求...'
    let streamed = ''
    let msgPushed = false
    try {
      await streamChat(
        '/api/chat/message/stream',
        { user_input: text, user_id: 'default_user', session_id: 'default' },
        {
          onProgress: (msg) => {
            if (sessionEpoch.value !== myEpoch) return
            thinkingText.value = msg
          },
          onDelta: (delta) => {
            if (sessionEpoch.value !== myEpoch) return // 已切换会话，丢弃
            if (!msgPushed) {
              messages.value.push({ role: 'assistant', text: '', timestamp: Date.now() })
              msgPushed = true
            }
            streamed += delta
            const last = messages.value[messages.value.length - 1]
            if (last?.role === 'assistant') last.text = streamed
            nextTick(scrollToBottom)
          },
        },
        ac.signal
      )
      if (sessionEpoch.value !== myEpoch) return
      // 兜底：无 delta 时给默认文案
      if (!msgPushed) {
        messages.value.push({ role: 'assistant', text: streamed || '（未返回可显示的内容）', timestamp: Date.now() })
      } else if (!streamed) {
        const last = messages.value[messages.value.length - 1]
        if (last?.role === 'assistant') last.text = '（未返回可显示的内容）'
      }
    } catch (e: any) {
      if (sessionEpoch.value !== myEpoch) return // 切换会话导致的 abort 不报错
      if (!msgPushed) {
        messages.value.push({
          role: 'assistant',
          text: '抱歉，AI 服务暂时不可用，请稍后重试。',
          timestamp: Date.now(),
        })
      }
    }
  }

  analyzing.value = false
  nextTick(scrollToBottom)
}

function applyExtracted(fields: ItineraryFields) {
  formFields.departure_city = fields.departure_city || prefs.departure_city || ''
  formFields.city = fields.city
  formFields.start_date = fields.start_date ? dayjs(fields.start_date) : dayjs()
  if (fields.travel_days) formFields.travel_days = fields.travel_days
  // 交通方式归一化（去掉后端返回的"（建议）"等后缀）
  const transMap: Record<string, string> = {
    '高铁（建议）': '高铁', '动车（建议）': '高铁', '火车（建议）': '火车', '飞机（建议）': '飞机',
    '公共交通（建议）': '公共交通', '自驾（建议）': '自驾',
  }
  const trans = fields.transportation || ''
  formFields.transportation = transMap[trans] || trans.replace(/（.*?）|\(.*?\)/g, '') || prefs.transportation || formFields.transportation
  formFields.accommodation = fields.accommodation || prefs.accommodation || formFields.accommodation
  if (fields.preferences.length) formFields.preferences = fields.preferences
  formFields.free_text = fields.free_text
}

function resetForm() {
  showForm.value = false
  Object.assign(formFields, defaultFields())
}

async function confirmAndGenerate() {
  const missing: string[] = []
  if (!formFields.city) missing.push('目的地城市')
  if (!formFields.start_date) missing.push('开始日期')
  if (missing.length) {
    message.warning(`请补充必要信息：${missing.join('、')}`)
    return
  }
  abortStaleGen() // 若其他对话有进行中的生成，先中断（epoch 会变化）
  const myEpoch = sessionEpoch.value // 捕获当前会话代际
  if (sessionEpoch.value !== myEpoch) return

  const ac = new AbortController()
  activeAbortController = ac

  const start = dayjs(formFields.start_date).format('YYYY-MM-DD')
  const end = dayjs(formFields.start_date).add(formFields.travel_days - 1, 'day').format('YYYY-MM-DD')

  const requestData: TripFormData = {
    departure_city: formFields.departure_city,
    city: formFields.city,
    start_date: start,
    end_date: end,
    travel_days: formFields.travel_days,
    transportation: formFields.transportation,
    accommodation: formFields.accommodation,
    preferences: formFields.preferences,
    free_text_input: formFields.free_text,
  }

  generating.value = true
  result.value = null
  showForm.value = false
  // 先关闭表单再保存会话，避免把 showForm=true 存进历史（否则切回时会重新弹表单）
  saveCurrentConversation()
  nextTick(scrollToBottom)

  try {
    // ===== 逐天生成模式：生成第 1 天，然后询问用户是否满意 =====
    await startDayPlan(requestData, myEpoch, ac)
  } catch (e: any) {
    if (sessionEpoch.value !== myEpoch) return // 切换会话导致的 abort，不处理
    message.error('生成失败：' + (e?.message || '网络错误'))
    // 回退本地 mock，保证演示可用
    try {
      const res = await generateTripPlan(requestData)
      if (res.success && (res.data as any)?.final_response) {
        messages.value.push({ role: 'assistant', text: (res.data as any).final_response, timestamp: Date.now() })
      } else {
        message.error(res.message || '生成失败，请重试')
      }
    } catch (e2: any) {
      message.error('生成失败：' + (e2?.message || '网络错误'))
    }
  } finally {
    if (sessionEpoch.value === myEpoch) {
      generating.value = false
      // 生成完成后再次保存，确保完整行程消息被持久化（否则切回时只显示确认阶段的快照）
      saveCurrentConversation()
      nextTick(scrollToBottom)
    }
  }
}

// ===== 逐天行程生成 =====

/** 初始化逐天模式并生成第 1 天 */
async function startDayPlan(formData: TripFormData, myEpoch: number, ac: AbortController) {
  // 初始化逐天状态
  dayPlanMode.value = true
  dayPlanState.formData = { ...formData }
  dayPlanState.totalDays = formData.travel_days || 1
  dayPlanState.currentDay = 0
  dayPlanState.daysText = []
  dayPlanState.poiNamesByDay = []

  // 先推一条说明消息（可选）
  messages.value.push({
    role: 'assistant',
    text: `好的，我来为你逐天规划**${formData.city}**的 ${dayPlanState.totalDays} 天行程。\n\n我会先规划第 1 天，你满意后回复「继续」，我再规划下一天；不满意可以直接告诉我哪里想调整。`,
    timestamp: Date.now(),
  })
  saveCurrentConversation()
  nextTick(scrollToBottom)

  await generateOneDay(1, myEpoch, ac)
}

/** 生成指定一天（currentDay 从1开始），并将"是否满意"引导合并到当天消息末尾 */
async function generateOneDay(day: number, myEpoch: number, ac: AbortController) {
  if (sessionEpoch.value !== myEpoch) return
  if (!dayPlanState.formData) return
  const convId = activeConversationId.value || ''
  // 初始化该对话的进行中生成状态（独立对象：切走后后台仍继续写它，不污染其他对话的 messages）
  const gen: ActiveDayGen = {
    convId,
    epoch: myEpoch,
    abort: ac,
    thinking: `正在为你规划第 ${day} 天行程...`,
    reasoning: '',
    streamed: '',
    msgPushed: false,
    assistantMsg: null,
    dayPlanMode: true,
    totalDays: dayPlanState.totalDays,
    currentDay: dayPlanState.currentDay,
    daysText: [...dayPlanState.daysText],
    poiNamesByDay: dayPlanState.poiNamesByDay.map((a) => [...a]),
    formData: dayPlanState.formData,
    feedback: dayPlanFeedback.value || '',
    done: false,
  }
  activeDayGen.value = gen
  const isCurrent = () => gen.convId === (activeConversationId.value || '')
  const syncDay = () => {
    dayPlanState.totalDays = gen.totalDays
    dayPlanState.currentDay = gen.currentDay
    dayPlanState.daysText = gen.daysText
    dayPlanState.poiNamesByDay = gen.poiNamesByDay
    dayPlanState.formData = gen.formData
    dayPlanFeedback.value = gen.feedback
  }

  // 逐天模式统一用 analyzing 表示思考状态；关闭 generating，避免出现两个"正在思考"
  if (isCurrent()) {
    generating.value = false
    analyzing.value = true
    thinkingText.value = gen.thinking
    reasoningText.value = '' // 清空上一次的思考过程
  }

  try {
    await dayPlanStream(
      gen.formData!,
      {
        current_day: day,
        previous_days: gen.daysText,
        // 传给后端的 = 前 day-1 天的全部名字（当天自身不参与过滤，避免重生成时丢卡片）
        used_poi_names: gen.poiNamesByDay.slice(0, day - 1).flat(),
        feedback: gen.feedback || '',
      },
      {
        onProgress: (msg) => {
          if (sessionEpoch.value !== myEpoch) return
          gen.thinking = msg
          if (isCurrent()) thinkingText.value = msg
        },
        onReasoning: (delta) => {
          if (sessionEpoch.value !== myEpoch) return
          gen.reasoning += delta
          if (isCurrent()) {
            reasoningText.value = gen.reasoning.slice(-4000)
            nextTick(scrollReasoningBox)
          }
        },
        onDelta: (delta) => {
          if (sessionEpoch.value !== myEpoch) return
          gen.streamed += delta
          if (!gen.msgPushed) {
            gen.assistantMsg = { role: 'assistant', text: '', timestamp: Date.now() }
            gen.msgPushed = true
            if (isCurrent()) messages.value.push(gen.assistantMsg)
          }
          if (gen.assistantMsg) gen.assistantMsg.text = gen.streamed
          if (isCurrent()) nextTick(scrollToBottom)
        },
        onPoi: (pois) => {
          if (sessionEpoch.value !== myEpoch) return
          if (pois && pois.length && gen.assistantMsg) {
            gen.assistantMsg.pois = pois
            // 按天记录展示过的 POI 名（供下一天去重）；同一天内已出现的跳过
            const dayNames = gen.poiNamesByDay[day - 1] || []
            for (const p of pois) {
              const pn = (p.poi_name || p.name || '').trim()
              if (pn && !dayNames.includes(pn)) dayNames.push(pn)
            }
            gen.poiNamesByDay[day - 1] = dayNames
            if (isCurrent()) nextTick(scrollToBottom)
          }
        },
        onTrain: (trains) => {
          if (sessionEpoch.value !== myEpoch) return
          if (trains && trains.length && gen.assistantMsg) {
            gen.assistantMsg.trains = trains
            if (isCurrent()) nextTick(scrollToBottom)
          }
        },
        onWeather: (weather) => {
          if (sessionEpoch.value !== myEpoch) return
          if (weather && gen.assistantMsg) {
            gen.assistantMsg.weather = weather
            if (isCurrent()) nextTick(scrollToBottom)
          }
        },
        onHotel: (hotels) => {
          if (sessionEpoch.value !== myEpoch) return
          if (hotels && hotels.length && gen.assistantMsg) {
            gen.assistantMsg.hotels = hotels
            if (isCurrent()) nextTick(scrollToBottom)
          }
        },
      },
      ac.signal
    )
    if (sessionEpoch.value !== myEpoch) return

    // 记录当天文本
    if (gen.streamed) {
      gen.daysText[day - 1] = gen.streamed
      gen.currentDay = day
    }
    gen.feedback = ''
    syncDay()

    // 判断是否还有下一天
    if (day >= gen.totalDays) {
      // 全部生成完成
      const doneMsg: ChatMessage = {
        role: 'assistant',
        text: `\n\n✅ **${gen.totalDays} 天行程已全部规划完成！**\n\n你可以随时告诉我调整某一天，或者有其他需要（预订提醒、费用明细等）也可以问我。`,
        timestamp: Date.now(),
      }
      gen.done = true
      dayPlanMode.value = false
      if (isCurrent()) {
        messages.value.push(doneMsg)
        syncDay()
        saveCurrentConversation()
      } else {
        persistGenToConversation(gen, [doneMsg])
      }
      if (activeDayGen.value === gen) activeDayGen.value = null
    } else {
      // 引导继续：合并到当天消息末尾（不另起一条消息，避免出现重复"正在思考"图标）
      if (gen.assistantMsg) {
        gen.assistantMsg.text += `\n\n---\n📌 第 ${day} 天行程如上，**你满意吗？**\n\n回复「**继续**」我规划第 ${day + 1} 天；不满意可以直接告诉我哪里想调整（如"第1天想去迪士尼"）。`
      }
      if (isCurrent()) saveCurrentConversation()
      else persistGenToConversation(gen, [])
      if (activeDayGen.value === gen) activeDayGen.value = null // 当天流式结束
    }
    if (isCurrent()) nextTick(scrollToBottom)
  } catch (e: any) {
    if (sessionEpoch.value !== myEpoch) return
    if (!gen.msgPushed) {
      const errMsg: ChatMessage = {
        role: 'assistant',
        text: `第 ${day} 天行程生成失败，请稍后重试。`,
        timestamp: Date.now(),
      }
      gen.assistantMsg = errMsg
      gen.msgPushed = true
      if (isCurrent()) messages.value.push(errMsg)
      else persistGenToConversation(gen, [])
    }
    gen.feedback = ''
    gen.done = true
    if (activeDayGen.value === gen) activeDayGen.value = null
  } finally {
    if (sessionEpoch.value === myEpoch && isCurrent()) {
      analyzing.value = false
      reasoningText.value = '' // 生成结束（完成/失败）统一清空思考过程
    }
  }
}

/** 逐天模式下处理用户反馈（继续 / 修改意见） */
async function handleDayPlanFeedback(text: string, myEpoch: number, ac: AbortController) {
  // 判断是否"继续"类表达
  const continueRe = /^(继续|可以|满意|没问题|好的|好|ok|嗯|行|可以了|不错|okay|fine|go on)\s*[！!。.]*$/i
  if (continueRe.test(text.trim())) {
    if (dayPlanState.currentDay >= dayPlanState.totalDays) {
      // 已全部完成，退出逐天模式
      dayPlanMode.value = false
      analyzing.value = false
      messages.value.push({
        role: 'assistant',
        text: '好的，行程已经全部规划完成啦！有其他需要随时找我。',
        timestamp: Date.now(),
      })
      saveCurrentConversation()
      nextTick(scrollToBottom)
      return
    }
    // 继续生成下一天
    await generateOneDay(dayPlanState.currentDay + 1, myEpoch, ac)
    return
  }

  // 否则视为修改意见：重新生成当前天（feedback 传给后端）
  if (dayPlanState.currentDay >= 1) {
    dayPlanFeedback.value = text
    // 重生成前清掉当天的旧文本与POI记录，避免当作"前面几天"传给后端
    const cur = dayPlanState.currentDay
    dayPlanState.daysText[cur - 1] = ''
    if (dayPlanState.poiNamesByDay[cur - 1]) dayPlanState.poiNamesByDay[cur - 1] = []
    // 移除最后一条 AI 消息（当前天的旧版本），重新生成
    const lastMsg = messages.value[messages.value.length - 1]
    if (lastMsg?.role === 'assistant') messages.value.pop()
    messages.value.push({
      role: 'assistant',
      text: `好的，我根据你的意见「${text}」重新调整第 ${cur} 天：`,
      timestamp: Date.now(),
    })
    await generateOneDay(cur, myEpoch, ac)
  } else {
    analyzing.value = false
  }
}

function scrollToBottom() {
  if (chatArea.value) {
    chatArea.value.scrollTo({ top: chatArea.value.scrollHeight, behavior: 'smooth' })
  }
}

/** 思考过程面板自动滚动到底部，保持显示最新思考内容 */
function scrollReasoningBox() {
  const el = reasoningBox.value
  if (el) el.scrollTop = el.scrollHeight
}

function copyMessage(text: string) {
  navigator.clipboard.writeText(text).then(() => {
    message.success('已复制到剪贴板')
  }).catch(() => {
    message.error('复制失败')
  })
}

function regenerateLast() {
  if (analyzing.value || generating.value) return // 生成中不允许重新生成
  const lastUserMsg = [...messages.value].reverse().find(m => m.role === 'user')
  if (lastUserMsg) {
    // 移除最后一条 AI 回复（如果存在）
    const lastMsg = messages.value[messages.value.length - 1]
    if (lastMsg?.role === 'assistant') {
      messages.value.pop()
    }
    handleSend(lastUserMsg.text)
  }
}

watch(messages, () => nextTick(scrollToBottom), { deep: true })
watch(generating, (val) => { if (val) nextTick(scrollToBottom) })
</script>

<style scoped>
/* ===== 布局 ===== */
.app-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.workspace {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
  height: 100vh;
}

/* ===== 聊天滚动区 ===== */
.chat-scroll {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.chat-content {
  max-width: var(--chat-max-width);
  margin: 0 auto;
  padding: var(--space-6) var(--space-6) var(--space-4);
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

/* ===== AI 消息 ===== */
.ai-msg {
  display: flex;
  flex-direction: column;
  margin-bottom: var(--space-6);
  max-width: 100%;
}
.ai-label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}
.ai-icon {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: linear-gradient(135deg, var(--color-primary), #7b6bbf);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}
.ai-name {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
}
.ai-content {
  font-size: var(--font-size-md);
  line-height: var(--line-height-relaxed);
  color: var(--color-text);
  padding-left: 32px;
}

/* 思考中 */
.ai-content.thinking {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}
.typing-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-text-tertiary);
  animation: typing-bounce 1.4s infinite;
}
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
.thinking-text { margin-left: var(--space-1); }

/* 深度思考过程实时展示 */
.reasoning-box {
  margin: var(--space-2) 0 var(--space-1) 32px;
  max-width: 560px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-muted, #f8f9fb);
  overflow: hidden;
}
.reasoning-label {
  padding: 6px 12px;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  border-bottom: 1px dashed var(--color-border);
  background: rgba(123, 107, 191, 0.06);
}
.reasoning-content {
  max-height: 180px;
  overflow-y: auto;
  padding: 8px 12px;
  font-size: var(--font-size-xs);
  line-height: 1.6;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

/* ===== 用户消息 ===== */
.user-msg {
  display: flex;
  justify-content: flex-end;
  margin-bottom: var(--space-6);
}
.user-msg-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  width: 100%;
  max-width: 100%;
}
.user-bubble {
  max-width: 70%;
  padding: var(--space-3) var(--space-4);
  background: var(--color-primary-light);
  color: var(--color-text);
  border-radius: var(--radius-md);
  border-bottom-right-radius: 4px;
  font-size: var(--font-size-md);
  line-height: var(--line-height-normal);
  word-break: break-word;
}
.user-time {
  text-align: right;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: var(--space-1);
  padding-right: var(--space-1);
}

/* 消息时间戳 */
.msg-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-left: var(--space-2);
  font-weight: 400;
}

/* AI 消息操作栏 */
.ai-actions {
  display: flex;
  gap: var(--space-2);
  padding-left: 32px;
  margin-top: var(--space-2);
}

/* 高德景点/餐厅卡片 */
.card-group {
  padding-left: 32px;
  margin-top: 12px;
  margin-bottom: 4px;
}
/* 天气横幅 */
.weather-banner {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 6px 0 10px 32px;
  padding: 6px 14px;
  background: linear-gradient(135deg, rgba(139, 200, 234, 0.12), rgba(139, 200, 234, 0.05));
  border: 1px solid rgba(139, 200, 234, 0.35);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  color: var(--color-text);
}
.weather-icon {
  font-size: 18px;
  line-height: 1;
}
.weather-info {
  color: var(--color-text);
  font-weight: 500;
}
.card-group-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 10px;
  letter-spacing: 0.3px;
}
.card-group-title::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--color-border);
  margin-left: 6px;
}
/* POI 触发词 / popover / 景点卡片样式统一在下方非 scoped 全局块（v-html 注入内容无 data-v） */
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all var(--transition-fast);
}
/* 12306 真实车次卡片 */
.train-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 10px;
  margin-top: 8px;
}
.train-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  padding: 10px 12px;
  min-width: 0;
}
.train-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.train-no {
  font-weight: 700;
  font-size: var(--font-size-md);
  color: var(--color-primary);
  background: var(--color-primary-light, rgba(99, 102, 241, 0.1));
  padding: 1px 8px;
  border-radius: var(--radius-sm);
}
.train-time {
  font-size: var(--font-size-xs);
  color: var(--color-text);
  font-weight: 500;
}
.train-duration {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}
.train-seats {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.train-seat {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  background: var(--color-bg-muted, #f4f4f6);
  border-radius: var(--radius-sm);
  padding: 2px 8px;
}
.train-seat b {
  color: #d48806;
  font-weight: 600;
  margin-left: 4px;
}
/* 真实酒店推荐卡片（默认2行×3个） */
.hotel-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-top: 8px;
}
@media (max-width: 900px) {
  .hotel-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 480px) {
  .hotel-grid {
    grid-template-columns: 1fr;
  }
}
.hotel-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  padding: 10px 12px;
  min-width: 0;
}
.hotel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.hotel-name {
  font-weight: 600;
  font-size: var(--font-size-md);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hotel-star {
  color: #faad14;
  font-size: var(--font-size-xs);
  letter-spacing: 1px;
}
.hotel-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
.hotel-price {
  font-weight: 700;
  font-size: var(--font-size-md);
  color: var(--color-primary);
}
.hotel-tier {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  background: var(--color-bg-muted, #f4f4f6);
  padding: 1px 8px;
  border-radius: var(--radius-sm);
}
.hotel-addr {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-top: 6px;
}
.hotel-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.hotel-tag {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  background: var(--color-bg-muted, #f4f4f6);
  padding: 1px 8px;
  border-radius: var(--radius-sm);
}
.action-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-primary-light);
}

/* Markdown 排版 */
.markdown-body {
  font-size: var(--font-size-md);
  line-height: var(--line-height-relaxed);
  color: var(--color-text);
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  font-weight: 600;
  margin: var(--space-4) 0 var(--space-2);
  color: var(--color-text);
}
.markdown-body :deep(h1) { font-size: 1.4em; }
.markdown-body :deep(h2) { font-size: 1.25em; }
.markdown-body :deep(h3) { font-size: 1.1em; }
.markdown-body :deep(h4) { font-size: 1em; }
.markdown-body :deep(p) {
  margin: 0 0 var(--space-3);
}
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0 0 var(--space-3);
  padding-left: var(--space-5);
}
.markdown-body :deep(li) {
  margin-bottom: var(--space-1);
  line-height: var(--line-height-relaxed);
}
.markdown-body :deep(strong) {
  font-weight: 600;
  color: var(--color-text);
}
.markdown-body :deep(a) {
  color: var(--color-primary);
  text-decoration: none;
}
.markdown-body :deep(a:hover) {
  text-decoration: underline;
}
.markdown-body :deep(code) {
  background: var(--color-surface-hover);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-size: 0.9em;
  font-family: 'SF Mono', Consolas, monospace;
}
.markdown-body :deep(pre) {
  background: var(--color-surface-hover);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  overflow-x: auto;
  margin: 0 0 var(--space-3);
}
.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--color-primary);
  padding-left: var(--space-3);
  margin: 0 0 var(--space-3);
  color: var(--color-text-secondary);
}
.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--color-border);
  margin: var(--space-4) 0;
}
.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-sm);
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--color-border);
  padding: var(--space-2) var(--space-3);
  text-align: left;
}
.markdown-body :deep(th) {
  background: var(--color-surface-hover);
  font-weight: 600;
}

/* ===== 行程表单卡片 ===== */
.form-hint {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-3);
}
.itinerary-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  box-shadow: var(--shadow-sm);
}
.form-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}
.form-grid .field {
  flex: 1 1 180px;
  min-width: 0;
  margin-bottom: var(--space-3);
}
.form-grid-half .field { flex: 1 1 45%; }
.field-spaced { margin-top: var(--space-4); }

.field label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: var(--space-2);
}
.field input[type='text'],
.field input:not([type]),
.field textarea {
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
.field textarea:focus { border-color: var(--color-primary); }
.field textarea { resize: vertical; }

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

.end-date-hint {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin: var(--space-3) 0 var(--space-4);
}
.end-date-hint b { color: var(--color-primary); }

.form-actions {
  display: flex;
  gap: var(--space-3);
}
.btn-primary {
  flex: 1;
  padding: var(--space-3) var(--space-5);
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
  padding: var(--space-3) var(--space-5);
  background: var(--color-surface-hover);
  color: var(--color-text-secondary);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: background var(--transition-fast);
}
.btn-secondary:hover { background: var(--color-surface-active); }

/* ===== 结果 ===== */
.result-content h3 {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-lg);
  font-weight: 700;
}
.result-meta {
  margin: 0 0 var(--space-4);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}
.day-plan {
  padding: var(--space-3) var(--space-4);
  background: var(--color-primary-bg);
  border-radius: var(--radius-md);
  margin: var(--space-3) 0;
}
.day-plan h4 {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--color-primary);
}
.day-plan p { margin: 3px 0; font-size: var(--font-size-sm); }
.result-section { margin-top: var(--space-4); }
.result-section h4 {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--color-text);
}
.result-section p { margin: 3px 0; font-size: var(--font-size-sm); }
.budget-total {
  margin-top: var(--space-2) !important;
  padding-top: var(--space-2);
  border-top: 1px solid var(--color-border);
}
.result-suggestions {
  margin-top: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: #fef9e7;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
}

/* ===== 响应式 ===== */
@media (max-width: 768px) {
  .chat-content { padding: var(--space-4) var(--space-4) var(--space-3); }
  .user-bubble { max-width: 80%; }
}

@media (max-width: 640px) {
  .app-layout { flex-direction: column; }
  .ai-content { padding-left: 0; }
  .form-actions { flex-direction: column; }
}
</style>

<!-- 非 scoped 全局样式：POI 触发词/卡片由 v-html 动态注入，不携带 data-v 属性，必须用全局选择器 -->
<style>
/* POI 触发词（嵌入正文的可点击景点/餐厅/酒店名）——仅靠颜色+底色区分，无边框无图标 */
.poi-trigger {
  position: relative;
  display: inline-block;
  color: var(--color-primary);
  font-weight: 600;
  background: var(--color-primary-light, rgba(99, 102, 241, 0.1));
  cursor: pointer;
  padding: 0 5px;
  margin: 0 1px;
  border-radius: 5px;
  transition: all var(--transition-fast);
  white-space: nowrap;
}
.poi-trigger:hover {
  background: var(--color-primary-light, rgba(99, 102, 241, 0.22));
}
.poi-trigger:active {
  transform: scale(0.97);
}
/* POI 触发式卡片（popover） */
.poi-popover {
  position: fixed;
  z-index: 3000;
  width: 260px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  overflow: hidden;
  animation: popIn var(--transition-fast);
}
@keyframes popIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}
.poi-pop-photo {
  width: 100%;
  height: 120px;
  background: var(--color-bg-muted, #f4f4f6);
  display: flex;
  align-items: center;
  justify-content: center;
}
.poi-pop-photo img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.poi-pop-body {
  padding: 10px 12px;
}
.poi-pop-name {
  font-weight: 600;
  font-size: var(--font-size-md);
  color: var(--color-text);
}
.poi-pop-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}
.poi-pop-rating {
  font-size: var(--font-size-xs);
  color: #d48806;
  font-weight: 600;
}
.poi-pop-price {
  font-size: var(--font-size-sm);
  color: var(--color-primary);
  font-weight: 600;
}
.poi-pop-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}
.poi-pop-tag {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  background: var(--color-bg-muted, #f4f4f6);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
}
.poi-pop-level {
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  background: var(--color-primary-light, rgba(99, 102, 241, 0.1));
  padding: 0 6px;
  border-radius: var(--radius-sm);
}
.poi-pop-addr,
.poi-pop-open {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-top: 4px;
  line-height: 1.5;
}
/* 景点介绍栏卡片（晚上与住宿之间，默认2行×4个） */
.poi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-top: 8px;
}
@media (max-width: 900px) {
  .poi-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 480px) {
  .poi-grid {
    grid-template-columns: 1fr;
  }
}
.poi-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--color-surface);
  transition: box-shadow var(--transition-fast);
}
.poi-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}
.poi-card-photo {
  width: 100%;
  height: 110px;
  background: var(--color-bg-muted, #f4f4f6);
  display: flex;
  align-items: center;
  justify-content: center;
}
.poi-card-photo img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.poi-photo-placeholder {
  font-size: 28px;
  opacity: 0.4;
}
.poi-card-body {
  padding: 8px 10px 10px;
}
.poi-card-name {
  font-weight: 600;
  font-size: var(--font-size-sm);
  color: var(--color-text);
  line-height: 1.4;
}
.poi-card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}
.poi-card-rating {
  font-size: var(--font-size-xs);
  color: #d48806;
  font-weight: 600;
}
.poi-card-level {
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  background: var(--color-primary-light, rgba(99, 102, 241, 0.1));
  padding: 0 6px;
  border-radius: var(--radius-sm);
}
.poi-card-addr {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-top: 4px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
