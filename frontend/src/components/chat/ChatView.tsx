import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
  type RefObject,
} from 'react'
import type { ChatThread } from '../../lib/api'
import { ThemeToggle } from '../ThemeToggle'
import { groupThreads, relativeTime } from './format'
import {
  ArrowDownIcon,
  ArrowRightIcon,
  CheckIcon,
  CloseIcon,
  CopyIcon,
  MenuIcon,
  PlusIcon,
  RetryIcon,
  SearchIcon,
  SendIcon,
  ShieldIcon,
  TagMark,
  TrashIcon,
} from './icons'
import { MarkdownMessage } from './MarkdownMessage'
import { MessageText } from './MessageText'
import { PriceCheck } from './PriceCheck'
import type { ChatMessage, ChatViewProps } from './types'

const prompts = [
  {
    example: '2 kilo plastic, Rs 300 mila',
    label: 'Report a sale in Roman Urdu',
  },
  {
    example: 'What is iron worth this week?',
    label: 'Check a material before you sell',
  },
  {
    example: 'Aaj 5 kilo kaghaz becha',
    label: 'Report a paper sale',
  },
]

interface SidebarContentProps {
  threads: ChatThread[]
  activeThreadId: string | null
  loading: boolean
  search: string
  accountSlot?: ReactNode
  demo?: boolean
  busy?: boolean
  showClose?: boolean
  closeButtonRef?: RefObject<HTMLButtonElement | null>
  onSearch: (value: string) => void
  onNewChat: () => void
  onSelectThread: (threadId: string) => void
  onClose?: () => void
}

function SidebarContent({
  threads,
  activeThreadId,
  loading,
  search,
  accountSlot,
  demo,
  busy,
  showClose,
  closeButtonRef,
  onSearch,
  onNewChat,
  onSelectThread,
  onClose,
}: SidebarContentProps) {
  const searchId = useId()
  const query = search.trim().toLowerCase()
  const filtered = query
    ? threads.filter((thread) => thread.title.toLowerCase().includes(query))
    : threads
  const groups = groupThreads(filtered)

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-start gap-2.5 px-4 pb-3 pt-4">
        <TagMark className="mt-0.5 h-5 w-5 shrink-0 text-ink" />
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-semibold leading-5 tracking-[-0.01em]">ScrapSense</p>
          <p className="mt-0.5 truncate text-[11px] leading-4 text-muted">
            Multan · picker price ledger
          </p>
        </div>
        {showClose ? (
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="Close conversations"
            className="clay-icon-button -mr-1 flex h-11 w-11 shrink-0 items-center justify-center text-muted hover:text-ink"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        ) : null}
      </div>

      <div className="px-3">
        <button
          type="button"
          onClick={onNewChat}
          disabled={busy}
          className="clay-button clay-button-primary group flex h-11 w-full items-center justify-between px-3.5 text-[13px] font-medium text-on-solid lg:h-10 lg:px-3"
        >
          <span className="flex items-center gap-2">
            <PlusIcon className="h-4 w-4" />
            <span>New report</span>
          </span>
          <span className="hidden font-mono text-[10px] text-on-solid-muted sm:inline">Ctrl K</span>
        </button>
      </div>

      <div className="px-3 pt-3">
        <label htmlFor={searchId} className="sr-only">
          Search reports
        </label>
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
          <input
            id={searchId}
            type="search"
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="Search reports"
            className="clay-input h-12 w-full pl-9 pr-12 text-[12px] text-ink placeholder:text-faint lg:h-9 lg:pr-8"
          />
          {search ? (
            <button
              type="button"
              onClick={() => onSearch('')}
              aria-label="Clear search"
              className="search-clear absolute right-0.5 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full text-muted lg:right-1 lg:h-7 lg:w-7"
            >
              <CloseIcon className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </div>
      </div>

      <nav
        aria-label="Conversations"
        aria-busy={loading}
        className="chat-scroll mt-3 min-h-0 flex-1 overflow-y-auto px-2 pb-4"
      >
        {loading ? (
          <ThreadSkeleton />
        ) : groups.length > 0 ? (
          groups.map((group) => (
            <div key={group.label} className="mb-4 last:mb-0">
              <p className="px-2.5 pb-1.5 text-[11px] leading-4 text-muted">{group.label}</p>
              <ul className="space-y-0.5">
                {group.threads.map((thread) => {
                  const active = thread.id === activeThreadId
                  return (
                    <li key={thread.id}>
                      <button
                        type="button"
                        onClick={() => onSelectThread(thread.id)}
                        disabled={busy}
                        aria-current={active ? 'true' : undefined}
                        className={`clay-row flex w-full flex-col gap-0.5 px-2.5 py-2 text-left ${
                          active ? 'clay-row-active' : ''
                        }`}
                      >
                        <span className="truncate text-[13px] font-medium leading-5 text-ink">
                          {thread.title}
                        </span>
                        <span className="text-[11px] leading-4 text-muted">
                          {relativeTime(thread.updated_at)}
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))
        ) : (
          <ThreadEmpty
            search={search}
            busy={busy}
            onClear={() => onSearch('')}
            onNewChat={onNewChat}
          />
        )}
      </nav>

      <div className="px-3 py-3">
        <div className="clay-surface flex items-center gap-2.5 px-3 py-2.5">
          {accountSlot ?? (
            <div className="clay-icon-chip flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-medium text-accent-text">
              S
            </div>
          )}
          <div className="min-w-0 flex-1">
            <p className="truncate text-[12px] font-medium leading-4">
              {demo ? 'Demo picker' : 'Picker account'}
            </p>
            <p className="truncate text-[11px] leading-4 text-muted">Reports are anonymous</p>
          </div>
          <ThemeToggle className="-mr-1" />
        </div>
        {!demo ? (
          <a
            href="/review"
            aria-label="Open reviewer queue"
            className="clay-row mt-2 flex min-h-11 items-center gap-2 px-3 py-2 text-[12px] font-medium text-ink"
          >
            <ShieldIcon className="h-3.5 w-3.5 shrink-0 text-muted" />
            <span className="min-w-0 flex-1 truncate">Review queue</span>
            <ArrowRightIcon className="h-3.5 w-3.5 shrink-0 text-muted" />
          </a>
        ) : null}
      </div>
    </div>
  )
}

function ThreadSkeleton() {
  return (
    <div aria-hidden="true" className="space-y-1 px-1">
      {[0, 1, 2, 3].map((index) => (
        <div key={index} className="rounded-[6px] px-2.5 py-2">
          <div className="h-3 w-[72%] rounded-sm bg-active" />
          <div className="mt-2 h-2 w-16 rounded-sm bg-rule" />
        </div>
      ))}
    </div>
  )
}

function ThreadEmpty({
  search,
  busy,
  onClear,
  onNewChat,
}: {
  search: string
  busy?: boolean
  onClear: () => void
  onNewChat: () => void
}) {
  if (search.trim()) {
    return (
      <div className="px-2.5 py-6">
        <p className="text-[13px] font-medium leading-5 text-ink">
          No reports match “{search.trim()}”.
        </p>
        <button
          type="button"
          onClick={onClear}
          className="mt-1 inline-flex min-h-11 items-center text-[12px] font-medium leading-4 text-ink underline decoration-control underline-offset-2 transition-colors hover:decoration-ink"
        >
          Clear search
        </button>
      </div>
    )
  }

  return (
    <div className="px-2.5 py-6">
      <p className="text-[13px] font-medium leading-5 text-ink">No reports yet</p>
      <p className="mt-1 text-[12px] leading-5 text-muted">
        Your saved conversations will appear here.
      </p>
      <button
        type="button"
        onClick={onNewChat}
        disabled={busy}
        className="group mt-3 flex min-h-11 items-center gap-1.5 text-[12px] font-medium leading-4 text-ink underline decoration-control underline-offset-2 transition-colors hover:decoration-ink disabled:cursor-not-allowed disabled:opacity-50"
      >
        Start a report
        <ArrowRightIcon className="cta-arrow h-3.5 w-3.5" />
      </button>
    </div>
  )
}

function EmptyState({
  disabled,
  onPrompt,
  onOpenPriceCheck,
}: {
  disabled: boolean
  onPrompt: (text: string) => void
  onOpenPriceCheck?: () => void
}) {
  return (
    <div className="pt-6 sm:pt-10 lg:pt-[7vh]">
      <h2 className="text-[26px] font-semibold leading-[1.1] tracking-[-0.03em] text-ink sm:text-[30px]">
        Assalam-o-alaikum.
      </h2>
      <p className="mt-3 max-w-[46ch] text-[14px] leading-6 text-muted sm:text-[15px]">
        Tell me what you sold: the material, the weight, and what you were paid. I’ll check it
        before it counts toward the price reference.
      </p>

      <div className="mt-8">
        <p className="text-[12px] font-medium leading-4 text-muted">Start with what you sold</p>
        <div className="mt-2 space-y-2">
          {prompts.map((prompt) => (
            <button
              key={prompt.example}
              type="button"
              disabled={disabled}
              onClick={() => onPrompt(prompt.example)}
              className="clay-row group flex w-full items-center gap-3 px-3 py-3 text-left"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-medium leading-5 text-ink">
                  <MessageText text={prompt.example} tone="assistant" />
                </span>
                <span className="mt-0.5 block text-[11px] leading-4 text-muted">
                  {prompt.label}
                </span>
              </span>
              <ArrowRightIcon className="cta-arrow h-4 w-4 shrink-0 text-muted" />
            </button>
          ))}
        </div>

        {onOpenPriceCheck ? (
          <button
            type="button"
            onClick={onOpenPriceCheck}
            className="clay-row group mt-2 flex w-full items-center gap-3 px-3 py-3 text-left"
          >
            <span className="clay-icon-chip flex h-8 w-8 shrink-0 items-center justify-center text-accent-text">
              <TagMark className="h-4 w-4" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[13px] font-medium leading-5 text-ink">
                Check a price before you sell
              </span>
              <span className="mt-0.5 block text-[11px] leading-4 text-muted">
                See the evidence, scope, and freshness behind the number.
              </span>
            </span>
            <ArrowRightIcon className="cta-arrow h-4 w-4 shrink-0 text-muted" />
          </button>
        ) : null}
      </div>

      <p className="mt-6 flex max-w-[48ch] items-start gap-2 text-[11px] leading-5 text-muted">
        <ShieldIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        Reports are checked before they affect a price. Your name is never attached.
      </p>
    </div>
  )
}

function MessageSkeleton() {
  return (
    <div className="py-4" role="status">
      <span className="sr-only">Loading conversation</span>
      <div aria-hidden="true" className="space-y-6">
        <div className="flex gap-3">
          <div className="clay-icon-chip mt-0.5 h-7 w-7 shrink-0" />
          <div className="flex-1 space-y-2 pt-1">
            <div className="h-2.5 w-20 rounded-[8px] bg-active" />
            <div className="h-3 w-[86%] rounded-[8px] bg-active" />
            <div className="h-3 w-[62%] rounded-[8px] bg-active" />
          </div>
        </div>
        <div className="flex justify-end">
          <div className="h-12 w-[54%] rounded-[22px] bg-active" />
        </div>
        <div className="flex gap-3">
          <div className="clay-icon-chip mt-0.5 h-7 w-7 shrink-0" />
          <div className="flex-1 space-y-2 pt-1">
            <div className="h-2.5 w-20 rounded-[8px] bg-active" />
            <div className="h-3 w-[74%] rounded-[8px] bg-active" />
            <div className="h-3 w-[48%] rounded-[8px] bg-active" />
          </div>
        </div>
      </div>
    </div>
  )
}

function AssistantMessage({
  message,
  copied,
  onCopy,
}: {
  message: ChatMessage
  copied: boolean
  onCopy: (message: ChatMessage) => void
}) {
  return (
    <article className="group flex gap-3 py-3">
      <div className="clay-icon-chip mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center text-ink">
        <TagMark className="h-3.5 w-3.5" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-medium leading-4 text-muted">ScrapSense</p>
        <div className="clay-bubble-assistant mt-1.5 max-w-[62ch] px-4 py-3 text-[14px] leading-6 text-ink sm:text-[15px] sm:leading-7">
          <MarkdownMessage text={message.content} tone="assistant" />
        </div>
        <div className="mt-1.5 flex items-center gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100">
          <button
            type="button"
            onClick={() => onCopy(message)}
            aria-label={copied ? 'Copied' : 'Copy message'}
            className="clay-icon-button flex h-11 items-center gap-1.5 px-3 text-[11px] font-medium text-muted hover:text-ink sm:h-7 sm:px-2"
          >
            {copied ? <CheckIcon className="h-3.5 w-3.5" /> : <CopyIcon className="h-3.5 w-3.5" />}
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      </div>
    </article>
  )
}

function UserMessage({ message }: { message: ChatMessage }) {
  return (
    <div className="flex justify-end py-2">
      <div className="max-w-[86%] sm:max-w-[78%]">
        <div className="clay-bubble-user px-3.5 py-2.5 text-[14px] leading-6 text-ink sm:px-4 sm:py-3">
          <MarkdownMessage text={message.content} tone="user" />
        </div>
      </div>
    </div>
  )
}

function Thinking() {
  return (
    <div className="flex gap-3 py-3" role="status">
      <div className="clay-icon-chip mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center text-ink">
        <TagMark className="h-3.5 w-3.5" />
      </div>
      <div className="clay-chip flex items-center gap-2 px-3 py-1.5">
        <span className="text-[11px] font-medium leading-4 text-muted">Reading your message</span>
        <span className="flex items-end gap-1" aria-hidden="true">
          <span className="typing-dot h-1 w-1 rounded-full bg-ink" />
          <span className="typing-dot h-1 w-1 rounded-full bg-ink" />
          <span className="typing-dot h-1 w-1 rounded-full bg-ink" />
        </span>
      </div>
    </div>
  )
}

function ErrorBanner({
  message,
  onRetry,
  onDismiss,
}: {
  message: string
  onRetry: () => void
  onDismiss: () => void
}) {
  return (
    <div
      role="alert"
      className="clay-inset mb-2 flex items-center gap-2 px-3 py-2"
    >
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-negative" aria-hidden="true" />
      <p className="min-w-0 flex-1 text-[12px] leading-4 text-ink">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="flex min-h-11 shrink-0 items-center gap-1 text-[12px] font-medium leading-4 text-ink underline decoration-control underline-offset-2 transition-colors hover:decoration-ink sm:min-h-0"
      >
        Retry
        <RetryIcon className="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss error"
        className="clay-icon-button flex h-11 w-11 shrink-0 items-center justify-center text-muted hover:text-ink sm:h-6 sm:w-6"
      >
        <CloseIcon className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

export function ChatView({
  threads,
  activeThreadId,
  messages,
  loadingThreads,
  loadingMessages,
  sending,
  error,
  accountSlot,
  demo,
  onSend,
  onRetry,
  onDismissError,
  onNewChat,
  onSelectThread,
  onDeleteThread,
  onRefreshThreads,
}: ChatViewProps) {
  const [draft, setDraft] = useState('')
  const [search, setSearch] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [showJump, setShowJump] = useState(false)
  const [priceOpen, setPriceOpen] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const drawerRef = useRef<HTMLDivElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const atBottomRef = useRef(true)
  const lastCountRef = useRef(0)
  const copyTimerRef = useRef<number | null>(null)

  const activeThread = threads.find((thread) => thread.id === activeThreadId) ?? null
  const hasMessages = messages.length > 0
  const title = activeThread?.title ?? 'New report'
  const subline = demo
    ? 'Demo workspace · sample reports only'
    : activeThread
      ? 'Saved to your history'
      : 'Tell me what you sold, or ask about a material.'

  useEffect(() => {
    const element = textareaRef.current
    if (!element) {
      return
    }
    element.style.height = '0px'
    element.style.height = `${Math.min(element.scrollHeight, 160)}px`
  }, [draft])

  useEffect(() => {
    if (loadingMessages) {
      return
    }
    const element = scrollRef.current
    if (!element) {
      return
    }
    if (lastCountRef.current === 0) {
      element.scrollTop = element.scrollHeight
    } else if (atBottomRef.current) {
      element.scrollTo({ top: element.scrollHeight, behavior: 'smooth' })
    }
    lastCountRef.current = messages.length
  }, [messages, loadingMessages, sending])

  useEffect(() => {
    lastCountRef.current = 0
    atBottomRef.current = true
    setShowJump(false)
    setDrawerOpen(false)
  }, [activeThreadId])

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setDrawerOpen(false)
        onNewChat()
        return
      }

      if (event.key === 'Escape') {
        if (confirmOpen) {
          setConfirmOpen(false)
        } else if (drawerOpen) {
          setDrawerOpen(false)
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [confirmOpen, drawerOpen, onNewChat])

  useEffect(() => {
    if (!drawerOpen) {
      return
    }
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const timer = window.setTimeout(() => drawerRef.current?.focus(), 30)
    return () => {
      document.body.style.overflow = previous
      window.clearTimeout(timer)
    }
  }, [drawerOpen])

  useEffect(() => {
    if (!confirmOpen) {
      return
    }
    const timer = window.setTimeout(() => cancelRef.current?.focus(), 30)
    return () => window.clearTimeout(timer)
  }, [confirmOpen])

  useEffect(() => {
    return () => {
      if (copyTimerRef.current) {
        window.clearTimeout(copyTimerRef.current)
      }
    }
  }, [])

  function scrollToBottom() {
    atBottomRef.current = true
    setShowJump(false)
    const element = scrollRef.current
    if (element) {
      element.scrollTo({ top: element.scrollHeight, behavior: 'smooth' })
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const text = draft.trim()
    if (!text || sending || loadingMessages) {
      return
    }
    setDraft('')
    onSend(text)
    requestAnimationFrame(scrollToBottom)
  }

  function handlePrompt(text: string) {
    if (sending || loadingMessages) {
      return
    }
    onSend(text)
    requestAnimationFrame(scrollToBottom)
  }

  function handleNewChat() {
    setDrawerOpen(false)
    setDraft('')
    onNewChat()
    window.setTimeout(() => textareaRef.current?.focus(), 30)
  }

  function handleSelectThread(threadId: string) {
    setDrawerOpen(false)
    onSelectThread(threadId)
  }

  function handleScroll() {
    const element = scrollRef.current
    if (!element) {
      return
    }
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight
    const atBottom = distance < 48
    atBottomRef.current = atBottom
    setShowJump(distance > 160)
  }

  async function handleCopy(message: ChatMessage) {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopiedId(message.id)
      if (copyTimerRef.current) {
        window.clearTimeout(copyTimerRef.current)
      }
      copyTimerRef.current = window.setTimeout(() => setCopiedId(null), 1600)
    } catch {
      setCopiedId(null)
    }
  }

  async function handleDelete() {
    setDeleting(true)
    try {
      const deleted = await onDeleteThread()
      if (deleted) {
        setConfirmOpen(false)
      }
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="flex h-svh overflow-hidden bg-surface">
      <aside className="hidden h-full w-[264px] shrink-0 bg-ground lg:block">
        <SidebarContent
          threads={threads}
          activeThreadId={activeThreadId}
          loading={loadingThreads}
          search={search}
          accountSlot={accountSlot}
          demo={demo}
          busy={sending}
          onSearch={setSearch}
          onNewChat={handleNewChat}
          onSelectThread={handleSelectThread}
        />
      </aside>

      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-1.5 px-2.5 lg:hidden">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open conversations"
            className="clay-icon-button flex h-11 w-11 items-center justify-center text-ink"
          >
            <MenuIcon className="h-5 w-5" />
          </button>
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <TagMark className="h-[18px] w-[18px] shrink-0 text-ink" />
            <span className="truncate text-[13px] font-semibold tracking-[-0.01em]">ScrapSense</span>
          </div>
          <ThemeToggle />
          <button
            type="button"
            onClick={handleNewChat}
            disabled={sending}
            aria-label="New report"
            className="clay-icon-button flex h-11 w-11 items-center justify-center text-ink"
          >
            <PlusIcon className="h-5 w-5" />
          </button>
        </header>

        <div className="shrink-0 px-5 pb-3 pt-4 lg:px-8 lg:pb-4 lg:pt-5">
          <div className="mx-auto flex w-full max-w-[760px] items-start gap-3">
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-[18px] font-semibold leading-6 tracking-[-0.015em] lg:text-[20px]">
                {title}
              </h1>
              <p className="mt-1 truncate text-[12px] leading-4 text-muted">{subline}</p>
            </div>
            {!demo ? (
              <button
                type="button"
                onClick={() => setPriceOpen(true)}
                disabled={sending}
                aria-label="Check a scrap price"
                className="clay-button clay-button-secondary flex h-11 shrink-0 items-center gap-1.5 px-3 text-[12px] font-medium text-ink lg:h-9"
              >
                <TagMark className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Check price</span>
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => setConfirmOpen(true)}
              disabled={!activeThreadId || sending || loadingMessages}
              aria-label="Delete conversation"
              title="Delete conversation"
              className="clay-icon-button flex h-11 w-11 shrink-0 items-center justify-center text-muted hover:text-ink lg:h-9 lg:w-9"
            >
              <TrashIcon className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="relative min-h-0 flex-1">
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            className="chat-scroll h-full overflow-y-auto overscroll-contain px-5 lg:px-8"
            aria-live="polite"
            aria-busy={loadingMessages || sending}
          >
            <div className="mx-auto w-full max-w-[760px] pb-6">
              {loadingMessages ? (
                <MessageSkeleton />
              ) : hasMessages ? (
                <div className="py-2">
                  {messages.map((message) =>
                    message.role === 'assistant' ? (
                      <AssistantMessage
                        key={message.id}
                        message={message}
                        copied={copiedId === message.id}
                        onCopy={handleCopy}
                      />
                    ) : (
                      <UserMessage key={message.id} message={message} />
                    ),
                  )}
                  {sending ? <Thinking /> : null}
                </div>
              ) : (
                <EmptyState
                  disabled={sending}
                  onPrompt={handlePrompt}
                  onOpenPriceCheck={demo ? undefined : () => setPriceOpen(true)}
                />
              )}
              <div ref={endRef} className="h-1" />
            </div>
          </div>

          {showJump ? (
            <button
              type="button"
              onClick={scrollToBottom}
              aria-label="Jump to the latest message"
              className="clay-chip absolute bottom-3 left-1/2 flex h-11 -translate-x-1/2 items-center gap-1.5 px-4 text-[11px] font-medium text-ink sm:h-8 sm:px-3"
            >
              <ArrowDownIcon className="h-3.5 w-3.5" />
              Latest
            </button>
          ) : null}
        </div>

        <div className="safe-bottom shrink-0 bg-surface px-5 pt-3 lg:px-8 lg:pt-4">
          <div className="mx-auto w-full max-w-[760px]">
            {error ? (
              <ErrorBanner message={error} onRetry={onRetry} onDismiss={onDismissError} />
            ) : null}

            <form onSubmit={handleSubmit}>
              <div className="clay-composer">
                <label htmlFor="chat-message" className="sr-only">
                  Message
                </label>
                <textarea
                  id="chat-message"
                  ref={textareaRef}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault()
                      event.currentTarget.form?.requestSubmit()
                    }
                  }}
                  rows={1}
                  maxLength={4000}
                  placeholder="Tell me what you sold, or ask about a material…"
                  className="block max-h-40 min-h-12 w-full resize-none bg-transparent px-4 pb-1 pt-3 text-[16px] leading-6 text-ink outline-none placeholder:text-faint sm:text-[14px]"
                />
                <div className="flex items-center justify-between gap-3 px-3 pb-2.5">
                  <p className="hidden text-[11px] leading-4 text-muted sm:block">
                    Enter to send
                    <span className="mx-1.5 text-control">·</span>
                    Shift + Enter for a new line
                  </p>
                  <div className="ml-auto flex items-center gap-2">
                    {draft.length > 3600 ? (
                      <span className="num font-mono text-[10px] leading-4 text-muted">
                        {draft.length}/4000
                      </span>
                    ) : null}
                    <button
                      type="submit"
                      disabled={sending || loadingMessages || draft.trim().length === 0}
                      data-loading={sending ? 'true' : undefined}
                      aria-busy={sending || undefined}
                      aria-label={sending ? 'Sending' : 'Send message'}
                      className="clay-icon-button clay-icon-button-accent flex h-11 w-11 items-center justify-center rounded-full text-on-solid sm:h-9 sm:w-9"
                    >
                      {sending ? (
                        <span className="spinner h-4 w-4 rounded-full border-2 border-on-solid/30 border-t-on-solid" />
                      ) : (
                        <SendIcon className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </form>

            <div className="mt-2 flex items-center justify-between gap-3 sm:hidden">
              <p className="flex items-center gap-1.5 text-[11px] leading-4 text-muted">
                <ShieldIcon className="h-3.5 w-3.5" />
                Reports are anonymous
              </p>
              {error ? (
                <button
                  type="button"
                  onClick={onRefreshThreads}
                  className="text-[11px] font-medium leading-4 text-muted transition-colors hover:text-ink"
                >
                  Refresh history
                </button>
              ) : null}
            </div>
          </div>
        </div>
      </main>

      {!demo ? (
        <PriceCheck open={priceOpen} onClose={() => setPriceOpen(false)} />
      ) : null}

      {drawerOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            onClick={() => setDrawerOpen(false)}
            aria-label="Close conversations"
            className="drawer-overlay absolute inset-0 bg-scrim"
          />
          <div
            ref={drawerRef}
            role="dialog"
            aria-modal="true"
            aria-label="Conversations"
            tabIndex={-1}
            className="drawer-panel relative flex h-full w-[88%] max-w-[320px] flex-col bg-ground shadow-drawer outline-none"
          >
            <SidebarContent
              threads={threads}
              activeThreadId={activeThreadId}
              loading={loadingThreads}
              search={search}
              accountSlot={accountSlot}
              demo={demo}
              busy={sending}
              showClose
              closeButtonRef={closeButtonRef}
              onSearch={setSearch}
              onNewChat={handleNewChat}
              onSelectThread={handleSelectThread}
              onClose={() => setDrawerOpen(false)}
            />
          </div>
        </div>
      ) : null}

      {confirmOpen ? (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <button
            type="button"
            onClick={() => setConfirmOpen(false)}
            aria-label="Cancel delete"
            className="drawer-overlay absolute inset-0 bg-scrim"
          />
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-title"
            aria-describedby="delete-copy"
            className="clay-card dialog-panel relative w-full max-w-[400px] p-5"
          >
            <h2
              id="delete-title"
              className="text-[16px] font-semibold tracking-[-0.01em] text-ink"
            >
              Delete this report?
            </h2>
            <p id="delete-copy" className="mt-2 text-[13px] leading-5 text-muted">
              This removes the conversation from your history. Reports you already submitted stay
              in the price pool.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                ref={cancelRef}
                type="button"
                onClick={() => setConfirmOpen(false)}
                className="clay-button clay-button-secondary h-11 px-4 text-[13px] font-medium text-ink sm:h-9 sm:px-3"
              >
                Keep it
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting}
                className="clay-button clay-button-danger h-11 px-4 text-[13px] font-medium text-on-negative sm:h-9 sm:px-3"
              >
                {deleting ? 'Deleting…' : 'Delete report'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
