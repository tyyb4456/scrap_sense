const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
).replace(/\/$/, '')

export interface ChatResponse {
  user_id: string
  reply: string
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

  return (await response.json()) as T
}

export function sendMessage(token: string, message: string): Promise<ChatResponse> {
  return request<ChatResponse>('/chat', token, {
    method: 'POST',
    body: JSON.stringify({ message }),
  })
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong'
}
