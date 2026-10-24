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
    throw new Error(detail)
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

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong'
}
