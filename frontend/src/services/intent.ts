/**
 * 意图识别与关键信息提取
 *
 * 优先调用后端 LangGraph 的 /api/chat/intent 进行真实语义识别（意图、关键实体、补全偏好）；
 * 若后端不可用，则回退到本地关键词启发式解析，保证前端交互仍可演示。
 * 返回结构统一为 IntentResult，Home.vue 无需感知后端是否在线。
 */
import dayjs from 'dayjs'
import { intentAnalysis } from './api'

export interface ItineraryFields {
  departure_city: string
  city: string
  start_date: string // YYYY-MM-DD
  end_date: string // YYYY-MM-DD（由 start_date + travel_days 推算）
  travel_days: number
  transportation: string
  accommodation: string
  preferences: string[]
  free_text: string
}

export interface IntentResult {
  intent: 'itinerary_planning' | 'unknown'
  fields: ItineraryFields
  missing: string[]
  raw?: any // 后端返回的原始结构
  backend: boolean // 是否来自后端
}

// 常见城市表（启发式匹配用）
const CITIES = [
  '北京', '上海', '广州', '深圳', '杭州', '成都', '重庆', '西安', '南京', '武汉',
  '长沙', '苏州', '厦门', '青岛', '大连', '天津', '三亚', '昆明', '桂林', '丽江',
  '大理', '香港', '澳门', '哈尔滨', '沈阳', '济南', '郑州', '合肥', '南昌', '福州',
  '贵阳', '南宁', '兰州', '西宁', '拉萨', '乌鲁木齐', '呼和浩特', '银川', '海口', '珠海'
]

const TRANSPORT_RULES: Array<[string, string]> = [
  ['自驾', '自驾'], ['开车', '自驾'],
  ['高铁', '公共交通'], ['动车', '公共交通'], ['火车', '公共交通'],
  ['飞机', '公共交通'], ['航班', '公共交通'],
  ['公交', '公共交通'], ['地铁', '公共交通'], ['公共交通', '公共交通'],
  ['步行', '步行'], ['走路', '步行']
]

const ACCOMMODATION_RULES: Array<[string, string]> = [
  ['豪华', '豪华酒店'], ['五星', '豪华酒店'], ['四星', '舒适型酒店'],
  ['舒适', '舒适型酒店'], ['经济', '经济型酒店'], ['连锁', '经济型酒店'],
  ['民宿', '民宿'], ['客栈', '民宿']
]

const PREFERENCE_TAGS = ['历史文化', '自然风光', '美食', '购物', '艺术', '休闲']

// 中文数字解析（支持 一~三十，含"两"）
const CN_DIGITS: Record<string, number> = {
  '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
  '六': 6, '七': 7, '八': 8, '九': 9,
}
function parseChineseNumber(s: string): number {
  if (/^\d+$/.test(s)) return parseInt(s, 10)
  if (s === '十') return 10
  if (s.startsWith('十')) return 10 + (CN_DIGITS[s[1]] || 0)
  if (s.endsWith('十') && s.length === 1) return 10
  if (s.endsWith('十')) return (CN_DIGITS[s[0]] || 0) * 10
  if (s.includes('十')) {
    const [tens, ones] = s.split('十')
    return (CN_DIGITS[tens] || 0) * 10 + (CN_DIGITS[ones] || 0)
  }
  return CN_DIGITS[s] || 0
}

/**
 * 口语化天数解析：覆盖阿拉伯/中文数字 + 天/日/晚/夜 + 周/星期/礼拜
 * 示例：2天、两天、3日、五日、两晚、三夜、2天1夜、三天两夜、
 *       一周、两周、一个星期、两个星期、一个礼拜
 * 返回 0 表示未识别
 */
function parseDurationDays(text: string): number {
  // 0) 排除"周末/下周末/这周末"（这些是日期指示，不是天数）
  if (/周末/.test(text)) {
    // 仍可能同时有"两天周末"这类？罕见，先直接排除纯周末表达
  }

  // 1) 明确数量 + 周/星期/礼拜："两周"、"2周"、"两个星期"、"一个礼拜"
  const numWeek = text.match(/(\d{1,2}|[一二两三四五六七八九十]{1,2})\s*个?\s*(?:周|星期|礼拜)(?!末)/)
  if (numWeek) {
    const n = parseChineseNumber(numWeek[1])
    if (n > 0 && n <= 8) return n * 7
  }

  // 2) 天/日："2天"、"两天"、"3日"、"三天"、"2天1夜"、"三天两夜"
  const day = text.match(/(\d{1,2}|[一二两三四五六七八九十]{1,3})\s*[天日]/)
  if (day) {
    const n = parseChineseNumber(day[1])
    if (n > 0 && n <= 30) return n
  }

  // 3) 晚/夜："两晚"、"3晚"、"一晚"、"两夜"
  const night = text.match(/(\d{1,2}|[一二两三四五六七八九十]{1,2})\s*[晚夜]/)
  if (night) {
    const n = parseChineseNumber(night[1])
    if (n > 0 && n <= 30) return n
  }

  return 0
}

// 星期 → 数字（0=周日, 1=周一...）
const WEEKDAY_MAP: Record<string, number> = {
  一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 日: 0, 天: 0,
}

/**
 * 口语化开始日期解析：覆盖相对日期、方位+周几、月日、月份、节假日
 * 示例：今天/明天/后天/大后天、下周三/这周六/本周一/周三/下个星期三、
 *       3月5日/3月5号/3.5/3/5、下个月5号/这个月5号、3月、国庆/五一/元旦
 * 返回 '' 表示未识别（调用方默认今天）
 */
function parseStartDate(text: string): string {
  const now = dayjs()
  const fmt = (d: dayjs.Dayjs) => d.format('YYYY-MM-DD')
  const nextYearIfPast = (d: dayjs.Dayjs) => (d.isBefore(now, 'day') ? d.add(1, 'year') : d)

  // 1) 具体月日："3月5日"、"3月5号"、"3月5"、"3.5"、"3/5"
  //    边界保护：前后不能紧跟数字，避免把"100-130"里的"00-13"误当作月日
  let m = text.match(/(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?(?!\d)/)
  if (!m) m = text.match(/(?<!\d)(\d{1,2})[./-](\d{1,2})(?!\d)\s*[日号]?/)
  if (m) {
    const d = dayjs(`${now.year()}-${m[1]}-${m[2]}`)
    if (d.isValid()) return fmt(nextYearIfPast(d))
  }

  // 2) 仅月份："3月"、"三月份"（默认1号）
  m = text.match(/(\d{1,2}|[一二两三四五六七八九十]{1,2})\s*月/)
  if (m) {
    const mon = /^\d+$/.test(m[1]) ? parseInt(m[1], 10) : parseChineseNumber(m[1])
    if (mon >= 1 && mon <= 12) {
      const d = dayjs(`${now.year()}-${String(mon).padStart(2, '0')}-01`)
      return fmt(nextYearIfPast(d))
    }
  }

  // 3) 节假日（公历固定日）
  const holiday: Record<string, [number, number]> = {
    元旦: [1, 1], 春节: [1, 1], 劳动节: [5, 1], 五一: [5, 1], 国庆: [10, 1], 十一: [10, 1],
    圣诞: [12, 25], 平安夜: [12, 24], 七夕: [8, 1],
  }
  for (const [kw, [mon, d]] of Object.entries(holiday)) {
    if (text.includes(kw)) {
      const dt = dayjs(`${now.year()}-${String(mon).padStart(2, '0')}-${String(d).padStart(2, '0')}`)
      return fmt(nextYearIfPast(dt))
    }
  }

  // 4) 相对日
  if (text.includes('大后天')) return fmt(now.add(3, 'day'))
  if (text.includes('后天')) return fmt(now.add(2, 'day'))
  if (text.includes('明天')) return fmt(now.add(1, 'day'))
  if (text.includes('今天')) return fmt(now)

  // 5) 方位 + 周几："下周三"、"这周六"、"本周一"、"周三"、"下个星期三"、"上个星期五"
  const wd = text.match(/(下|这|本|上个?)?\s*(?:周|星期|礼拜)\s*([一二三四五六日天])/)
  if (wd) {
    const target = WEEKDAY_MAP[wd[2]]
    const dir = wd[1] || ''
    let d: dayjs.Dayjs
    if (dir.includes('下')) {
      d = now.day(target).add(7, 'day') // 本周 target + 7 = 下周 target
    } else if (dir.includes('上')) {
      d = now.day(target).subtract(7, 'day')
    } else {
      d = now.day(target)
      if (d.isBefore(now, 'day')) d = d.add(7, 'day') // 本周已过则顺延下周
    }
    return fmt(d)
  }

  // 5.5) 裸周（未带具体星期几）："下周"、"这周"、"本周" → 默认对应周周一
  //      排除"下周末/本周末/这周末"（走第6分支），且"周"后不带星期几
  if (!/周末/.test(text)) {
    const bareWeek = text.match(/(下|这|本|上个?)\s*个?\s*(?:周|星期|礼拜)(?!\s*[一二三四五六日天])/)
    if (bareWeek) {
      const dir = bareWeek[1]
      if (dir.includes('下')) return fmt(now.day(1).add(7, 'day')) // 下周周一
      if (dir.includes('上')) return fmt(now.day(1).subtract(7, 'day')) // 上周周一
      return fmt(now.day(1).isBefore(now, 'day') ? now.day(1).add(7, 'day') : now.day(1)) // 本周周一（已过则下周）
    }
  }

  // 6) 周末："本周末/这周末/下周末/周末"（默认周六）
  if (text.includes('下周末')) {
    return fmt(now.day(6).add(7, 'day'))
  }
  if (/本周末|这周末|周末/.test(text)) {
    const d = now.day(6)
    return fmt(d.isBefore(now, 'day') ? d.add(7, 'day') : d)
  }

  return ''
}

export function parseItineraryIntent(text: string): IntentResult {
  const fields: ItineraryFields = {
    departure_city: '',
    city: '',
    start_date: '',
    end_date: '',
    travel_days: 1,
    transportation: '',
    accommodation: '',
    preferences: [],
    free_text: ''
  }

  const now = dayjs()

  // 0. 出发城市："从上海去杭州" / "上海到杭州"
  let depCity = ''
  const depMatch = text.match(/从([\u4e00-\u9fa5]{2,6}?)(?:去|到|往|飞|出发)/)
  if (depMatch && CITIES.includes(depMatch[1])) {
    depCity = depMatch[1]
  } else {
    // 无"从"字的路线表达："上海到杭州"
    const routeMatch = text.match(/([\u4e00-\u9fa5]{2,4})(?:到|去|往|飞)([\u4e00-\u9fa5]{2,4})/)
    if (routeMatch && CITIES.includes(routeMatch[1]) && CITIES.includes(routeMatch[2])) {
      depCity = routeMatch[1]
    }
  }
  fields.departure_city = depCity

  // 1. 目的地城市（若已识别出发城市，则跳过出发城市取下一个）
  const foundCity = CITIES.find((c) => text.includes(c) && c !== depCity)
  if (foundCity) fields.city = foundCity

  // 2. 开始日期：口语化解析（相对日期/周几/月日/节假日等），未识别时默认今天
  fields.start_date = parseStartDate(text) || now.format('YYYY-MM-DD')

  // 3. 旅行天数：口语化解析（天/日/晚/夜/周/星期/礼拜），默认 1
  const days = parseDurationDays(text)
  if (days > 0) fields.travel_days = days

  // 4. 结束日期：按 start + days - 1 推算
  if (fields.start_date && fields.travel_days > 0) {
    fields.end_date = dayjs(fields.start_date).add(fields.travel_days - 1, 'day').format('YYYY-MM-DD')
  }

  // 5. 交通
  for (const [kw, val] of TRANSPORT_RULES) {
    if (text.includes(kw)) {
      fields.transportation = val
      break
    }
  }

  // 6. 住宿
  for (const [kw, val] of ACCOMMODATION_RULES) {
    if (text.includes(kw)) {
      fields.accommodation = val
      break
    }
  }

  // 7. 偏好
  fields.preferences = PREFERENCE_TAGS.filter((t) => text.includes(t))

  // 8. 额外要求（预算、同行人、具体诉求等）
  const extra: string[] = []
  // 预算区间："便宜点100-130左右"、"预算200-300元"、"100-130元/晚" → 预算XX-XX元
  const budgetRange = text.match(/(\d{2,4})\s*(?:-|~|～|到|至)\s*(\d{2,4})/)
  if (budgetRange) {
    extra.push(`预算${budgetRange[1]}-${budgetRange[2]}元`)
  } else {
    // 预算单值："预算200元"、"便宜点150" → 预算XX元
    const budgetSingle = text.match(/(?:预算|大概|大约|约|便宜点|控制在|不超过|低于|希望|想)\s*(\d{2,4})\s*(?:元|左右)?/)
    if (budgetSingle) extra.push(`预算${budgetSingle[1]}元`)
  }

  // 同行人："带爸妈去" → "带爸妈同行"
  const dai = text.match(/(?:带|带着)([\u4e00-\u9fa5]{1,8})/)
  if (dai) {
    const who = dai[1].replace(/[去到往].*$/, '').trim()
    if (who) extra.push(`带${who}同行`)
  }

  // 具体诉求："想去看升旗 / 不要爬山 / 希望住市中心" 等
  const needs = text.match(/(?:想|希望|要求|建议|不要|别|记得)[^，。；,!！?？\n]{1,24}/g)
  if (needs) {
    needs.forEach((s) => {
      const clean = s.replace(/[去往到]/g, '').trim()
      // 过滤掉只是复述目的地/城市的片段（如"想去杭州"）
      if (fields.city && clean.includes(fields.city)) return
      if (clean.length >= 2) extra.push(clean)
    })
  }

  fields.free_text = Array.from(new Set(extra)).join('；')

  // 意图判定（TODO 后端语义识别）：识别到目的地即视为行程规划
  const intent: IntentResult['intent'] = fields.city ? 'itinerary_planning' : 'unknown'

  // 必填项检查
  const missing: string[] = []
  if (!fields.city) missing.push('目的地')
  if (!fields.start_date) missing.push('出发日期')

  return { intent, fields, missing, backend: false }
}

/**
 * 将后端 key_entities 转换为前端表单字段
 */
function mapBackendEntities(entities: Record<string, any>): ItineraryFields {
  const fields: ItineraryFields = {
    departure_city: entities.origin || entities.departure_city || '',
    city: entities.destination || entities.city || '',
    start_date: '',
    end_date: '',
    travel_days: 0, // 0 表示未设置（后端没返回天数），避免与"真1天"混淆
    transportation: entities.transportation || '',
    accommodation: entities.accommodation || entities.hotel_brand || '',
    preferences: [],
    free_text: '',
  }

  // 日期
  if (entities.start_date) {
    fields.start_date = String(entities.start_date)
  } else if (entities.start_month || entities.month) {
    // 只有月份：默认当月1号
    const y = dayjs().year()
    const m = entities.start_month || entities.month
    fields.start_date = dayjs(`${y}-${String(m).padStart(2, '0')}-01`).format('YYYY-MM-DD')
  }
  if (entities.end_date) {
    fields.end_date = String(entities.end_date)
  }

  // 天数
  const days = entities.duration_days || entities.days || entities.travel_days
  if (days) fields.travel_days = Number(days)

  // 结束日期：若无则按 start + days - 1 推算
  if (!fields.end_date && fields.start_date && fields.travel_days > 0) {
    fields.end_date = dayjs(fields.start_date).add(fields.travel_days - 1, 'day').format('YYYY-MM-DD')
  }

  // 额外信息（预算等）
  const extras: string[] = []
  if (entities.budget) {
    if (typeof entities.budget === 'object' && entities.budget !== null) {
      const b = entities.budget
      const bparts: string[] = []
      const trainRaw = b.train_price ?? b.train_fare ?? b.transport_price ?? b.traffic_price
      const hotelRaw = b.hotel_price ?? b.hotel_price_per_night ?? b.hotel
      const stripYuan = (v: unknown) => String(v).replace(/[元块¥￥]/g, '').trim()
      if (trainRaw != null && String(trainRaw).trim() !== '') bparts.push(`火车票约${stripYuan(trainRaw)}元`)
      if (hotelRaw != null && String(hotelRaw).trim() !== '') bparts.push(`酒店${stripYuan(hotelRaw)}元/晚`)
      if (bparts.length) extras.push(bparts.join('，'))
    } else {
      extras.push(`预算${String(entities.budget).replace(/[元块¥￥]/g, '')}元`)
    }
  }
  if (entities.trip_purpose && entities.trip_purpose !== '旅游') extras.push(`目的：${entities.trip_purpose}`)
  if (entities.other) extras.push(String(entities.other))
  fields.free_text = extras.filter(Boolean).join('；')

  return fields
}

/**
 * 优先调用后端 /api/chat/intent 进行语义意图识别，
 * 失败时回退本地启发式解析。
 */
export async function analyzeIntent(text: string): Promise<IntentResult> {
  // 先走后端
  try {
    const res = await intentAnalysis(text)
    const hasPlanning = (res.intents || []).some((i) => i.type === 'itinerary_planning')
    const fields = mapBackendEntities(res.key_entities || {})
    const local = parseItineraryIntent(text) // 本地解析，用于补全缺失字段

    // 工具函数：后端实体优先，缺失字段用本地解析补全
    const mergeWithLocal = (base: ItineraryFields, localFields: ItineraryFields): ItineraryFields => {
      const merged: ItineraryFields = { ...localFields }
      if (base.city) merged.city = base.city
      if (base.departure_city) merged.departure_city = base.departure_city

      // 日期合并策略：
      // 后端已内置日期预处理器（"下周五/明天/X天后"→具体日期），返回的日期可靠，后端优先；
      // 本地解析仅在后端未返回日期时兜底，避免本地把"100-130"等误解析成月日覆盖正确日期。
      const todayStr = dayjs().format('YYYY-MM-DD')
      const localDate = parseStartDate(text) // 本地识别的日期（'' 表示未识别）
      if (base.start_date) {
        merged.start_date = base.start_date
      } else if (localDate && localDate !== todayStr) {
        merged.start_date = localDate
      }

      if (base.end_date) merged.end_date = base.end_date
      if (base.travel_days > 0) merged.travel_days = base.travel_days
      if (base.transportation) merged.transportation = base.transportation
      if (base.accommodation) merged.accommodation = base.accommodation
      if (base.preferences.length) merged.preferences = base.preferences
      if (base.free_text) merged.free_text = base.free_text
      return merged
    }

    if (!hasPlanning) {
      // 双保险：后端未识别为行程，但本地启发式能提取出目的地时，仍按行程处理
      // 防止"杭州3日游"这类明确行程被误判为信息查询
      if (local.intent === 'itinerary_planning') {
        const merged = mergeWithLocal(fields, local.fields)
        return { intent: 'itinerary_planning', fields: merged, missing: [], raw: res, backend: true }
      }
      return {
        intent: 'unknown',
        fields,
        missing: [],
        raw: res,
        backend: true,
      }
    }

    // 后端识别为行程，但实体可能提取不全（LLM 偶发），用本地解析补全缺失字段
    const merged = mergeWithLocal(fields, local.fields)
    const missing: string[] = []
    if (!merged.city) missing.push('目的地')
    if (!merged.start_date) missing.push('出发日期')

    return { intent: 'itinerary_planning', fields: merged, missing, raw: res, backend: true }
  } catch (e) {
    console.warn('后端意图识别不可用，回退本地解析:', e)
  }

  // 回退本地
  return parseItineraryIntent(text)
}
