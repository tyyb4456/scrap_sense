import type { ChatThread } from '../../lib/api'

const clockFormat = new Intl.DateTimeFormat(undefined, {
  hour: 'numeric',
  minute: '2-digit',
})

const dayFormat = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: 'numeric',
})

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
}

export function relativeTime(iso: string, now = new Date()): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return ''
  }

  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60_000)

  if (minutes < 1) {
    return 'Just now'
  }
  if (minutes < 60) {
    return `${minutes} min ago`
  }

  const days = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000)
  if (days === 0) {
    return clockFormat.format(date)
  }
  if (days === 1) {
    return 'Yesterday'
  }
  if (days < 7) {
    return `${days} days ago`
  }
  return dayFormat.format(date)
}

export interface ThreadGroup {
  label: string
  threads: ChatThread[]
}

export function groupThreads(threads: ChatThread[], now = new Date()): ThreadGroup[] {
  const groups: ThreadGroup[] = [
    { label: 'Today', threads: [] },
    { label: 'Yesterday', threads: [] },
    { label: 'Earlier', threads: [] },
  ]

  const sorted = [...threads].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  )

  for (const thread of sorted) {
    const date = new Date(thread.updated_at)
    const days = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000)

    if (days <= 0) {
      groups[0].threads.push(thread)
    } else if (days === 1) {
      groups[1].threads.push(thread)
    } else {
      groups[2].threads.push(thread)
    }
  }

  return groups.filter((group) => group.threads.length > 0)
}
