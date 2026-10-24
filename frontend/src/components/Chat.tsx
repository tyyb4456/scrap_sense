import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  deleteThread,
  errorMessage,
  getThreadMessages,
  listThreads,
  sendMessage,
  type ChatThread,
} from '../lib/api'
import { useAccessToken } from '../lib/useAccessToken'
import { ChatView } from './chat/ChatView'
import type { ChatMessage } from './chat/types'

interface ChatProps {
  accountSlot?: ReactNode
  demo?: boolean
}

function minutesAgo(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString()
}

const demoThreads: ChatThread[] = [
  {
    id: 'demo-plastic',
    title: '2 kilo plastic · Rs 300',
    created_at: minutesAgo(52),
    updated_at: minutesAgo(12),
  },
  {
    id: 'demo-iron',
    title: 'Iron rate before selling',
    created_at: minutesAgo(190),
    updated_at: minutesAgo(96),
  },
  {
    id: 'demo-paper',
    title: 'Kaghaz sale · 5 kilo',
    created_at: minutesAgo(1_520),
    updated_at: minutesAgo(1_470),
  },
  {
    id: 'demo-copper',
    title: 'Copper wire weight check',
    created_at: minutesAgo(4_380),
    updated_at: minutesAgo(4_320),
  },
]

const demoHistory: Record<string, ChatMessage[]> = {
  'demo-plastic': [
    {
      id: 'demo-plastic-1',
      role: 'user',
      content: 'Aaj maine 2 kilo plastic becha, 300 rupay milay.',
    },
    {
      id: 'demo-plastic-2',
      role: 'assistant',
      content:
        'Noted: 2 kilo plastic for Rs 300. That works out to Rs 150 per kilo. I’ve sent it for checking. There isn’t enough verified data yet for a Multan plastic range, so I won’t invent one.',
    },
    {
      id: 'demo-plastic-3',
      role: 'user',
      content: 'Thekedar ne wazan 1.8 kilo bataya.',
    },
    {
      id: 'demo-plastic-4',
      role: 'assistant',
      content:
        'That is a 200 gram gap from the weight you reported. I’ve flagged the report for review instead of counting it. If you can, keep your own weight and the dealer’s weight separate next time.',
    },
  ],
  'demo-iron': [
    {
      id: 'demo-iron-1',
      role: 'user',
      content: 'What is iron worth this week in Multan?',
    },
    {
      id: 'demo-iron-2',
      role: 'assistant',
      content:
        'I don’t have a verified iron price for this week yet. No checked picker reports have come in, so I’d rather say that than guess. I can keep your question on file and show a range once the reports are validated.',
    },
    {
      id: 'demo-iron-3',
      role: 'user',
      content: 'The dealer said Rs 95 per kilo.',
    },
    {
      id: 'demo-iron-4',
      role: 'assistant',
      content:
        'That is a dealer quote, not a checked picker report. I’ve noted it separately. It won’t be used as a price reference on its own.',
    },
  ],
  'demo-paper': [
    {
      id: 'demo-paper-1',
      role: 'user',
      content: 'Kal 5 kilo kaghaz becha, 250 rupay milay.',
    },
    {
      id: 'demo-paper-2',
      role: 'assistant',
      content:
        'Recorded as a paper report: 5 kilo for Rs 250. I’ll check the weight and payment before it counts toward the reference. There is no verified paper range for Multan yet, so I can’t quote a price.',
    },
  ],
  'demo-copper': [
    {
      id: 'demo-copper-1',
      role: 'user',
      content: 'Copper wire ka wazan kaise check karun?',
    },
    {
      id: 'demo-copper-2',
      role: 'assistant',
      content:
        'Weigh it on a kitchen scale if you can, and note the dealer’s weight too. Send both numbers here. I won’t quote a copper price until there are checked reports to support it.',
    },
  ],
}

function titleFromText(text: string): string {
  const clean = text.replace(/\s+/g, ' ').trim()
  if (clean.length <= 46) {
    return clean
  }
  return `${clean.slice(0, 46).trimEnd()}…`
}

function demoReply(text: string): string {
  const value = text.toLowerCase()

  if (/(plastic|bottle|pet|polythene)/.test(value)) {
    return 'Noted. I’ll check the weight and the amount before this counts toward the plastic reference. There is not enough verified data for a Multan plastic range yet, so I won’t guess one.'
  }
  if (/(iron|loha|sariya|steel)/.test(value)) {
    return 'I don’t have a verified iron price for this week yet. No checked reports have come in for Multan, so I’d rather say that than invent a number. I can keep your question on file.'
  }
  if (/(paper|kaghaz|kagaz|carton|cardboard)/.test(value)) {
    return 'Recorded as a paper report. I’ll verify the weight and payment first. Right now there is no checked paper reference for Multan, so I can’t quote a price.'
  }
  if (/(copper|tamba|tambe|wire)/.test(value)) {
    return 'Noted as copper wire. I’ll check the report before it affects any reference. I don’t have a verified copper range yet, so no number from me until the data is there.'
  }

  return 'Samajh gaya. I’ve noted the report. I’ll check the material, the weight, and what you were paid before it affects any price. Is there a weight or amount you want to add?'
}

function LiveChat({ accountSlot }: { accountSlot?: ReactNode }) {
  const getToken = useAccessToken()
  const [threads, setThreads] = useState<ChatThread[]>([])
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loadingThreads, setLoadingThreads] = useState(true)
  const [loadingMessages, setLoadingMessages] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const pendingRef = useRef<{ text: string; threadId: string | null } | null>(null)
  const suppressHistoryRef = useRef<string | null>(null)
  const sendingRef = useRef(false)
  const activeThreadRef = useRef<string | null>(null)

  useEffect(() => {
    activeThreadRef.current = activeThreadId
  }, [activeThreadId])

  useEffect(() => {
    let cancelled = false
    setLoadingThreads(true)

    void (async () => {
      try {
        const threadList = await listThreads(await getToken())
        if (cancelled) {
          return
        }
        setThreads(threadList)
        setActiveThreadId((current) => current ?? threadList[0]?.id ?? null)
      } catch (loadError) {
        if (!cancelled) {
          setError(errorMessage(loadError))
        }
      } finally {
        if (!cancelled) {
          setLoadingThreads(false)
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [getToken])

  useEffect(() => {
    const threadId = activeThreadId
    if (!threadId) {
      setMessages([])
      setLoadingMessages(false)
      return
    }

    if (suppressHistoryRef.current === threadId) {
      suppressHistoryRef.current = null
      setLoadingMessages(false)
      return
    }

    let cancelled = false
    setLoadingMessages(true)

    void (async () => {
      try {
        const history = await getThreadMessages(await getToken(), threadId)
        if (cancelled) {
          return
        }
        setMessages(
          history.messages.map((message, index) => ({
            id: `${threadId}:${index}`,
            role: message.role,
            content: message.content,
          })),
        )
      } catch (loadError) {
        if (!cancelled) {
          setError(errorMessage(loadError))
        }
      } finally {
        if (!cancelled) {
          setLoadingMessages(false)
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [activeThreadId, getToken, reloadKey])

  async function refreshThreads(token: string) {
    try {
      const threadList = await listThreads(token)
      setThreads(threadList)
    } catch {
      // The reply already succeeded; keep the current thread list.
    }
  }

  async function deliver(text: string, threadId: string | null, appendUser: boolean) {
    if (sendingRef.current) {
      return
    }

    sendingRef.current = true
    setSending(true)
    setError(null)

    if (appendUser) {
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: 'user', content: text },
      ])
    }

    const startedThreadId = threadId
    let target = threadId

    try {
      const token = await getToken()
      const response = await sendMessage(token, text, target ?? undefined)
      const stillHere = activeThreadRef.current === startedThreadId

      if (!target) {
        target = response.thread_id
        const now = new Date().toISOString()
        const placeholder: ChatThread = {
          id: target,
          title: titleFromText(text),
          created_at: now,
          updated_at: now,
        }
        setThreads((current) => [
          placeholder,
          ...current.filter((thread) => thread.id !== target),
        ])
        if (stillHere) {
          suppressHistoryRef.current = target
          setActiveThreadId(target)
        }
      }

      if (stillHere) {
        setMessages((current) => [
          ...current,
          { id: crypto.randomUUID(), role: 'assistant', content: response.reply },
        ])
      }
      pendingRef.current = null
      await refreshThreads(token)
    } catch (sendError) {
      pendingRef.current = { text, threadId: target }
      setError(errorMessage(sendError))
    } finally {
      sendingRef.current = false
      setSending(false)
    }
  }

  function handleSend(text: string) {
    if (sendingRef.current) {
      return
    }
    void deliver(text, activeThreadId, true)
  }

  function handleNewChat() {
    if (sendingRef.current) {
      return
    }
    setError(null)
    pendingRef.current = null
    setActiveThreadId(null)
    setMessages([])
    setLoadingMessages(false)
  }

  function handleSelectThread(threadId: string) {
    setError(null)
    pendingRef.current = null
    setActiveThreadId(threadId)
  }

  async function handleDeleteThread(): Promise<boolean> {
    const threadId = activeThreadId
    if (!threadId || sendingRef.current) {
      return false
    }

    setError(null)
    pendingRef.current = null

    try {
      const token = await getToken()
      await deleteThread(token, threadId)
      const remaining = threads.filter((thread) => thread.id !== threadId)
      setThreads(remaining)
      setMessages([])
      setActiveThreadId(remaining[0]?.id ?? null)
      return true
    } catch (deleteError) {
      setError(errorMessage(deleteError))
      return false
    }
  }

  function handleRetry() {
    if (sendingRef.current) {
      return
    }

    const pending = pendingRef.current
    if (pending) {
      void deliver(pending.text, pending.threadId, false)
      return
    }

    setError(null)
    setReloadKey((current) => current + 1)
  }

  function handleDismissError() {
    setError(null)
    pendingRef.current = null
  }

  function handleRefreshThreads() {
    void (async () => {
      try {
        const token = await getToken()
        setThreads(await listThreads(token))
        setReloadKey((current) => current + 1)
      } catch (refreshError) {
        setError(errorMessage(refreshError))
      }
    })()
  }

  return (
    <ChatView
      threads={threads}
      activeThreadId={activeThreadId}
      messages={messages}
      loadingThreads={loadingThreads}
      loadingMessages={loadingMessages}
      sending={sending}
      error={error}
      accountSlot={accountSlot}
      onSend={handleSend}
      onRetry={handleRetry}
      onDismissError={handleDismissError}
      onNewChat={handleNewChat}
      onSelectThread={handleSelectThread}
      onDeleteThread={handleDeleteThread}
      onRefreshThreads={handleRefreshThreads}
    />
  )
}

function DemoChat({ accountSlot }: { accountSlot?: ReactNode }) {
  const [threads, setThreads] = useState<ChatThread[]>(demoThreads)
  const [activeThreadId, setActiveThreadId] = useState<string | null>(
    demoThreads[0]?.id ?? null,
  )
  const [messagesByThread, setMessagesByThread] =
    useState<Record<string, ChatMessage[]>>(demoHistory)
  const [sending, setSending] = useState(false)

  const sendingRef = useRef(false)
  const timerRef = useRef<number | null>(null)

  const messages = activeThreadId ? (messagesByThread[activeThreadId] ?? []) : []

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        window.clearTimeout(timerRef.current)
      }
    }
  }, [])

  function handleSend(text: string) {
    if (sendingRef.current) {
      return
    }

    sendingRef.current = true
    setSending(true)

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
    }

    let target = activeThreadId

    if (!target) {
      const newId = `demo-${Date.now()}`
      const now = new Date().toISOString()
      target = newId
      setThreads((current) => [
        {
          id: newId,
          title: titleFromText(text),
          created_at: now,
          updated_at: now,
        },
        ...current,
      ])
      setActiveThreadId(newId)
      setMessagesByThread((current) => ({ ...current, [newId]: [userMessage] }))
    } else {
      const id = target
      setMessagesByThread((current) => ({
        ...current,
        [id]: [...(current[id] ?? []), userMessage],
      }))
    }

    const threadId = target
    setThreads((current) =>
      current.map((thread) =>
        thread.id === threadId ? { ...thread, updated_at: new Date().toISOString() } : thread,
      ),
    )

    timerRef.current = window.setTimeout(() => {
      const reply: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: demoReply(text),
      }
      setMessagesByThread((current) => ({
        ...current,
        [threadId]: [...(current[threadId] ?? []), reply],
      }))
      setThreads((current) =>
        current.map((thread) =>
          thread.id === threadId ? { ...thread, updated_at: new Date().toISOString() } : thread,
        ),
      )
      sendingRef.current = false
      setSending(false)
    }, 950)
  }

  function handleNewChat() {
    if (sendingRef.current) {
      return
    }
    setActiveThreadId(null)
  }

  function handleSelectThread(threadId: string) {
    setActiveThreadId(threadId)
  }

  async function handleDeleteThread(): Promise<boolean> {
    const threadId = activeThreadId
    if (!threadId || sendingRef.current) {
      return false
    }

    const remaining = threads.filter((thread) => thread.id !== threadId)
    setThreads(remaining)
    setMessagesByThread((current) => {
      const next = { ...current }
      delete next[threadId]
      return next
    })
    setActiveThreadId(remaining[0]?.id ?? null)
    return true
  }

  return (
    <ChatView
      threads={threads}
      activeThreadId={activeThreadId}
      messages={messages}
      loadingThreads={false}
      loadingMessages={false}
      sending={sending}
      error={null}
      accountSlot={accountSlot}
      demo
      onSend={handleSend}
      onRetry={() => undefined}
      onDismissError={() => undefined}
      onNewChat={handleNewChat}
      onSelectThread={handleSelectThread}
      onDeleteThread={handleDeleteThread}
      onRefreshThreads={() => undefined}
    />
  )
}

export function Chat({ accountSlot, demo = false }: ChatProps) {
  if (demo) {
    return <DemoChat accountSlot={accountSlot} />
  }
  return <LiveChat accountSlot={accountSlot} />
}
