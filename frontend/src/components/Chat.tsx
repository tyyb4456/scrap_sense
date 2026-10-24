import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import {
  createThread,
  deleteThread,
  errorMessage,
  getThreadMessages,
  listThreads,
  sendMessage,
  type ChatThread,
} from '../lib/api'
import { useAccessToken } from '../lib/useAccessToken'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
}

const greeting: ChatMessage = {
  id: 'greeting',
  role: 'assistant',
  content:
    'Assalam-o-alaikum. Tell me about a scrap sale or ask what a material is worth.',
}

export function Chat() {
  const getToken = useAccessToken()
  const [threads, setThreads] = useState<ChatThread[]>([])
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  useEffect(() => {
    let cancelled = false

    async function loadThreadList() {
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
          setLoading(false)
        }
      }
    }

    void loadThreadList()

    return () => {
      cancelled = true
    }
  }, [getToken])

  useEffect(() => {
    const threadId = activeThreadId
    if (!threadId) {
      return
    }

    let cancelled = false

    async function loadHistory(id: string) {
      setLoading(true)
      try {
        const history = await getThreadMessages(await getToken(), id)
        if (cancelled) {
          return
        }
        setMessages(
          history.messages.map((message, index) => ({
            id: `${id}:${index}`,
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
          setLoading(false)
        }
      }
    }

    void loadHistory(threadId)

    return () => {
      cancelled = true
    }
  }, [activeThreadId, getToken])

  async function refreshThreads(token: string) {
    const threadList = await listThreads(token)
    setThreads(threadList)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const text = draft.trim()
    if (!text || sending) {
      return
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
    }

    setError(null)
    setSending(true)

    try {
      const token = await getToken()
      let threadId = activeThreadId

      if (!threadId) {
        const thread = await createThread(token)
        threadId = thread.id
        setThreads((current) => [
          thread,
          ...current.filter((item) => item.id !== thread.id),
        ])
        setMessages([userMessage])
      } else {
        setMessages((current) => [...current, userMessage])
      }

      setDraft('')
      const response = await sendMessage(token, text, threadId)
      setActiveThreadId(threadId)
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: 'assistant', content: response.reply },
      ])
      await refreshThreads(token)
    } catch (sendError) {
      setError(errorMessage(sendError))
    } finally {
      setSending(false)
    }
  }

  async function handleNewChat() {
    if (sending || loading) {
      return
    }

    setError(null)
    try {
      const token = await getToken()
      const thread = await createThread(token)
      setThreads((current) => [
        thread,
        ...current.filter((item) => item.id !== thread.id),
      ])
      setMessages([])
      setActiveThreadId(thread.id)
    } catch (createError) {
      setError(errorMessage(createError))
    }
  }

  async function handleDeleteThread() {
    if (!activeThreadId || sending || loading) {
      return
    }

    setError(null)
    try {
      const token = await getToken()
      await deleteThread(token, activeThreadId)
      const remaining = threads.filter((thread) => thread.id !== activeThreadId)
      setThreads(remaining)
      setMessages([])
      setActiveThreadId(remaining[0]?.id ?? null)
    } catch (deleteError) {
      setError(errorMessage(deleteError))
    }
  }

  function handleSelectThread(event: ChangeEvent<HTMLSelectElement>) {
    setActiveThreadId(event.target.value || null)
  }

  const visibleMessages = messages.length === 0 && !loading ? [greeting] : messages

  return (
    <section className="flex h-[calc(100svh-8.5rem)] min-h-[28rem] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2 sm:px-4">
        <label htmlFor="chat-thread" className="sr-only">
          Conversation
        </label>
        <select
          id="chat-thread"
          value={activeThreadId ?? ''}
          onChange={handleSelectThread}
          disabled={loading || sending || threads.length === 0}
          className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200 disabled:opacity-60"
        >
          {threads.length === 0 ? <option value="">New chat</option> : null}
          {threads.map((thread) => (
            <option key={thread.id} value={thread.id}>
              {thread.title}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={handleNewChat}
          disabled={sending || loading}
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          New chat
        </button>
        <button
          type="button"
          onClick={handleDeleteThread}
          disabled={!activeThreadId || sending || loading}
          className="rounded-lg border border-rose-200 bg-white px-3 py-2 text-sm font-medium text-rose-700 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Delete
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-6" aria-live="polite">
        {loading ? (
          <p className="text-sm text-slate-500">Loading conversation…</p>
        ) : null}

        {visibleMessages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <p
              className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                message.role === 'user'
                  ? 'rounded-br-sm bg-emerald-600 text-white'
                  : 'rounded-bl-sm bg-slate-100 text-slate-800'
              }`}
            >
              {message.content}
            </p>
          </div>
        ))}

        {sending ? (
          <div className="flex justify-start">
            <p className="rounded-2xl rounded-bl-sm bg-slate-100 px-4 py-3 text-sm text-slate-500">
              ScrapSense is thinking…
            </p>
          </div>
        ) : null}
        <div ref={endRef} />
      </div>

      {error ? (
        <p className="border-t border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </p>
      ) : null}

      <form
        onSubmit={handleSubmit}
        className="flex items-end gap-2 border-t border-slate-200 bg-white p-3 sm:p-4"
      >
        <label htmlFor="chat-message" className="sr-only">
          Message
        </label>
        <textarea
          id="chat-message"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              event.currentTarget.form?.requestSubmit()
            }
          }}
          rows={2}
          maxLength={4000}
          placeholder="Example: aaj maine 2 kilo plastic becha, 300 rupay mila"
          className="max-h-40 min-h-12 flex-1 resize-none rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200"
        />
        <button
          type="submit"
          disabled={sending || loading || draft.trim().length === 0}
          className="rounded-xl bg-emerald-600 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {sending ? 'Sending…' : 'Send'}
        </button>
      </form>
    </section>
  )
}
