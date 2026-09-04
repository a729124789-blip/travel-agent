import axios from 'axios'
import type { TripFormData, TripPlanResponse } from '@/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 180000, // 3分钟超时（LLM 生成较慢）
  headers: {
    'Content-Type': 'application/json; charset=utf-8'
  }
})

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    console.log('发送请求:', config.method?.toUpperCase(), config.url)
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    console.log('收到响应:', response.status, response.config.url)
    return response
  },
  (error) => {
    console.error('响应错误:', error.response?.status, error.message)
    return Promise.reject(error)
  }
)

// ============================================================
// 后端正式 API 对接（LangGraph 后端）
// ============================================================

export interface ChatIntentResponse {
  intents: Array<{ type: string; confidence: number; description?: string }>
  key_entities: Record<string, any>
  rewritten_query: string
  agent_schedule: Array<{ agent_name: string; priority: number; reason?: string }>
}

export interface ChatMessageResponse {
  final_response: string
  intents: Array<{ type: string; confidence: number }>
  event_info: Record<string, any>
  itinerary: Record<string, any>
  preference_updates: Array<{ type: string; value: string; action: string }>
  info_query_result: Record<string, any>
  rag_result: Record<string, any>
  memory_result: Record<string, any>
  key_entities: Record<string, any>
  rewritten_query: string
  agent_schedule: Array<{ agent_name: string; priority: number }>
  errors: string[]
}

export interface ChatHistoryResponse {
  chat_history: Array<{ role: string; content: string; timestamp: string; session_id?: string }>
  trip_history: Array<Record<string, any>>
  preferences: Record<string, any>
  statistics: Record<string, any>
}

/**
 * 表单直通行程规划（结构化字段，跳过 intent 二次识别）
 */
export async function formPlan(
  formData: TripFormData,
  user_id = 'default_user',
  session_id = 'default'
): Promise<ChatMessageResponse> {
  try {
    const response = await apiClient.post<ChatMessageResponse>('/api/chat/form-plan', {
      ...formData,
      user_id,
      session_id,
    })
    return response.data
  } catch (error: any) {
    console.error('行程规划失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '行程规划失败')
  }
}

/**
 * 意图识别（表单预填充）
 * @param user_input 用户输入
 * @param user_id 用户ID
 * @param session_id 会话ID
 */
export async function intentAnalysis(
  user_input: string,
  user_id = 'default_user',
  session_id = 'default'
): Promise<ChatIntentResponse> {
  try {
    const response = await apiClient.post<ChatIntentResponse>('/api/chat/intent', {
      user_input,
      user_id,
      session_id,
    })
    return response.data
  } catch (error: any) {
    console.error('意图识别失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '意图识别失败')
  }
}

/**
 * 通用对话（走完整 LangGraph 流程）
 */
export async function sendChatMessage(
  user_input: string,
  user_id = 'default_user',
  session_id = 'default'
): Promise<ChatMessageResponse> {
  try {
    const response = await apiClient.post<ChatMessageResponse>('/api/chat/message', {
      user_input,
      user_id,
      session_id,
    })
    return response.data
  } catch (error: any) {
    console.error('对话请求失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '对话请求失败')
  }
}

/**
 * SSE 流式对话：通用对话 + 表单行程规划
 * @param path 后端流式端点路径（/api/chat/message/stream 或 /api/chat/form-plan/stream）
 * @param body 请求体
 * @param callbacks onProgress / onDelta / onDone / onError
 * @returns 完整回复文本
 */
export async function streamChat(
  path: string,
  body: Record<string, any>,
  callbacks: {
    onProgress?: (msg: string) => void
    onReasoning?: (text: string) => void
    onDelta?: (text: string) => void
    onDone?: () => void
    onError?: (msg: string) => void
    onMeta?: (meta: { day?: number; total_days?: number; [k: string]: any }) => void
    onPoi?: (pois: any[]) => void
    onTrain?: (trains: any[]) => void
    onWeather?: (weather: any) => void
    onHotel?: (hotels: any[]) => void
  } = {},
  signal?: AbortSignal
): Promise<string> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify(body),
    signal,
  })

  if (!response.ok || !response.body) {
    const errMsg = `请求失败（${response.status}）`
    callbacks.onError?.(errMsg)
    throw new Error(errMsg)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let full = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // 解析 SSE 事件：以 \n\n 分隔
      let sepIndex
      while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
        const event = buffer.slice(0, sepIndex)
        buffer = buffer.slice(sepIndex + 2)
        if (!event.startsWith('data:')) continue
        const dataStr = event.slice(5).trim()
        if (!dataStr) continue

        let data: any
        try {
          data = JSON.parse(dataStr)
        } catch {
          continue
        }

        if (data.type === 'progress') {
          callbacks.onProgress?.(data.message || '')
        } else if (data.type === 'reasoning') {
          callbacks.onReasoning?.(data.content || '')
        } else if (data.type === 'meta') {
          callbacks.onMeta?.(data)
        } else if (data.type === 'delta') {
          full += data.content || ''
          callbacks.onDelta?.(data.content || '')
        } else if (data.type === 'poi') {
          callbacks.onPoi?.(data.pois || [])
        } else if (data.type === 'train') {
          callbacks.onTrain?.(data.trains || [])
        } else if (data.type === 'weather') {
          callbacks.onWeather?.(data.weather || null)
        } else if (data.type === 'hotel') {
          callbacks.onHotel?.(data.hotels || [])
        } else if (data.type === 'done') {
          callbacks.onDone?.()
        } else if (data.type === 'error') {
          callbacks.onError?.(data.message || '流式响应出错')
          throw new Error(data.message || '流式响应出错')
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
  return full
}

/**
 * 逐天行程规划（SSE 流式）：一次生成一天
 * @param formData 表单字段
 * @param dayMeta { current_day, previous_days, feedback }
 */
export async function dayPlanStream(
  formData: TripFormData,
  dayMeta: { current_day: number; previous_days: string[]; feedback?: string; used_poi_names?: string[] },
  callbacks: Parameters<typeof streamChat>[2] = {},
  signal?: AbortSignal
): Promise<string> {
  return streamChat(
    '/api/chat/day-plan/stream',
    { ...formData, ...dayMeta, user_id: 'default_user', session_id: 'default' },
    callbacks,
    signal
  )
}

/**
 * 获取历史会话
 */
export async function fetchHistory(
  user_id = 'default_user',
  session_id = 'default',
  limit = 20
): Promise<ChatHistoryResponse> {
  try {
    const response = await apiClient.get<ChatHistoryResponse>('/api/chat/history', {
      params: { user_id, session_id, limit },
    })
    return response.data
  } catch (error: any) {
    console.error('获取历史失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '获取历史失败')
  }
}

/**
 * 删除一组对话记录（按 timestamp）
 */
export async function deleteChatHistory(
  timestamps: string[],
  user_id = 'default_user',
  session_id = 'default'
): Promise<{ ok: boolean; removed: number }> {
  try {
    const response = await apiClient.post('/api/chat/history/delete-chat', { user_id, session_id, timestamps })
    return response.data
  } catch (error: any) {
    console.error('删除对话记录失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '删除对话记录失败')
  }
}

/**
 * 删除单条行程足迹（按 trip_id）
 */
export async function deleteTripHistory(
  trip_id: string,
  user_id = 'default_user',
  session_id = 'default'
): Promise<{ ok: boolean }> {
  try {
    const response = await apiClient.post('/api/chat/history/delete-trip', { user_id, session_id, trip_id })
    return response.data
  } catch (error: any) {
    console.error('删除行程足迹失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '删除行程足迹失败')
  }
}

/**
 * 读取偏好
 */
export async function fetchPreferences(
  user_id = 'default_user',
  session_id = 'default'
): Promise<Record<string, any>> {
  try {
    const response = await apiClient.get('/api/chat/preferences', {
      params: { user_id, session_id },
    })
    return response.data?.preferences || {}
  } catch (error: any) {
    console.error('读取偏好失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '读取偏好失败')
  }
}

/**
 * 保存偏好
 */
export async function savePreference(
  pref_type: string,
  value: string,
  action = 'replace',
  user_id = 'default_user',
  session_id = 'default'
): Promise<Record<string, any>> {
  try {
    const response = await apiClient.post(
      '/api/chat/preferences',
      { pref_type, value, action },
      { params: { user_id, session_id } }
    )
    return response.data?.preferences || {}
  } catch (error: any) {
    console.error('保存偏好失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '保存偏好失败')
  }
}

// ============================================================
// 兼容旧接口（行程规划）
// ============================================================
export async function generateTripPlan(formData: TripFormData): Promise<TripPlanResponse> {
  try {
    // 组装自然语言请求，交给后端多智能体处理
    const parts: string[] = []
    if (formData.departure_city) parts.push(`从${formData.departure_city}出发`)
    if (formData.city) parts.push(`去${formData.city}`)
    if (formData.start_date) parts.push(`${formData.start_date}开始`)
    if (formData.travel_days) parts.push(`玩${formData.travel_days}天`)
    if (formData.transportation) parts.push(`坐${formData.transportation}`)
    if (formData.accommodation) parts.push(`住${formData.accommodation}`)
    if (formData.preferences?.length) parts.push(`偏好${formData.preferences.join('、')}`)
    if (formData.free_text_input) parts.push(formData.free_text_input)
    const user_input = parts.join('，')

    const data = await sendChatMessage(user_input)
    return {
      success: true,
      message: '生成成功',
      data: { final_response: data.final_response } as any,
    }
  } catch (error: any) {
    return {
      success: false,
      message: error?.message || '生成失败',
    }
  }
}

/**
 * 健康检查
 */
export async function healthCheck(): Promise<any> {
  try {
    const response = await apiClient.get('/health')
    return response.data
  } catch (error: any) {
    console.error('健康检查失败:', error)
    throw new Error(error.message || '健康检查失败')
  }
}

export default apiClient
