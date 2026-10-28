const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
).replace(/\/$/, '')

export interface ChatResponse {
  user_id: string
  thread_id: string
  reply: string
}

export interface ChatThread {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ThreadMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ThreadHistory {
  thread_id: string
  messages: ThreadMessage[]
}

export type PriceSource = 'local_reports' | 'city_reports' | 'seed_data' | 'unavailable'
export type PriceScope = 'area' | 'city' | 'national' | 'none'
export type PriceEvidenceQuality = 'high' | 'medium' | 'low' | 'none'

export interface PriceEstimate {
  material: string
  material_label: string
  location: string | null
  area: string | null
  currency: string
  unit: 'kg'
  estimated_price_per_kg: number | null
  source: PriceSource
  geographic_scope: PriceScope
  observation_count: number
  local_observation_count: number
  city_observation_count: number
  observed_min_price_per_kg: number | null
  observed_max_price_per_kg: number | null
  oldest_observation_at: string | null
  newest_observation_at: string | null
  freshness_days: number | null
  evidence_quality: PriceEvidenceQuality
  confidence: number
  seed_source: string | null
  seed_collected_at: string | null
  message: string
  limitations: string[]
  generated_at: string
}

export interface PriceEstimateQuery {
  material: string
  location?: string
  area?: string
}

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...init?.headers,
    },
  })

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const body: unknown = await response.json()
      if (
        typeof body === 'object' &&
        body !== null &&
        'detail' in body &&
        typeof body.detail === 'string'
      ) {
        detail = body.detail
      }
    } catch {
      // Keep the generic message when the response is not JSON.
    }
    throw new ApiError(detail, response.status)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export function sendMessage(
  token: string,
  message: string,
  threadId?: string,
): Promise<ChatResponse> {
  return request<ChatResponse>('/chat', token, {
    method: 'POST',
    body: JSON.stringify(threadId ? { message, thread_id: threadId } : { message }),
  })
}

export function listThreads(token: string): Promise<ChatThread[]> {
  return request<ChatThread[]>('/chat/threads', token)
}

export function createThread(token: string, title?: string): Promise<ChatThread> {
  return request<ChatThread>('/chat/threads', token, {
    method: 'POST',
    body: JSON.stringify(title ? { title } : {}),
  })
}

export function getThreadMessages(token: string, threadId: string): Promise<ThreadHistory> {
  return request<ThreadHistory>(
    `/chat/threads/${encodeURIComponent(threadId)}/messages`,
    token,
  )
}

export function deleteThread(token: string, threadId: string): Promise<void> {
  return request<void>(`/chat/threads/${encodeURIComponent(threadId)}`, token, {
    method: 'DELETE',
  })
}

export function getPriceEstimate(
  token: string,
  query: PriceEstimateQuery,
): Promise<PriceEstimate> {
  const params = new URLSearchParams({ material: query.material })
  if (query.location?.trim()) {
    params.set('location', query.location.trim())
  }
  if (query.area?.trim()) {
    params.set('area', query.area.trim())
  }

  return request<PriceEstimate>(`/prices/estimate?${params.toString()}`, token)
}

export type ReportStatus = 'accepted' | 'flagged' | 'rejected'
export type ReportReviewDecision = 'accepted' | 'rejected'

export interface ReportQueueItem {
  id: string
  material: string
  quantity_kg: number
  price_per_kg: number
  currency: string
  unit: 'kg'
  city: string | null
  area: string | null
  observed_at: string | null
  created_at: string
  status: ReportStatus
  is_anomalous: boolean
  anomaly_method: string
  anomaly_reason: string
  confidence: number | null
  reviewed_at: string | null
}

export interface ReportQueueResponse {
  items: ReportQueueItem[]
  page: number
  page_size: number
  total: number
  pages: number
  has_more: boolean
}

export interface ReportReviewResponse {
  id: string
  status: ReportReviewDecision
  is_anomalous: boolean
  reviewed_at: string
  reviewed_by: string
}

export interface ReportQueueQuery {
  status?: ReportStatus
  page?: number
  pageSize?: number
}

export function listReports(
  token: string,
  query: ReportQueueQuery = {},
): Promise<ReportQueueResponse> {
  const params = new URLSearchParams({
    status: query.status ?? 'flagged',
    page: String(query.page ?? 1),
    page_size: String(query.pageSize ?? 20),
  })
  return request<ReportQueueResponse>(`/reports?${params.toString()}`, token)
}

export function reviewReport(
  token: string,
  reportId: string,
  decision: ReportReviewDecision,
): Promise<ReportReviewResponse> {
  return request<ReportReviewResponse>(
    `/reports/${encodeURIComponent(reportId)}/review`,
    token,
    {
      method: 'PATCH',
      body: JSON.stringify({ status: decision }),
    },
  )
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong'
}
