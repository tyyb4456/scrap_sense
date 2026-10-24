import type { ReactNode } from 'react'
import type { ChatThread } from '../../lib/api'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt?: string
}

export interface ChatViewProps {
  threads: ChatThread[]
  activeThreadId: string | null
  messages: ChatMessage[]
  loadingThreads: boolean
  loadingMessages: boolean
  sending: boolean
  error: string | null
  accountSlot?: ReactNode
  demo?: boolean
  onSend: (text: string) => void
  onRetry: () => void
  onDismissError: () => void
  onNewChat: () => void
  onSelectThread: (threadId: string) => void
  onDeleteThread: () => Promise<boolean>
  onRefreshThreads: () => void
}
