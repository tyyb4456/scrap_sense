import { useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'scrapsense-theme'
const listeners = new Set<() => void>()

function readStored(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

function systemTheme(): Theme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function initialTheme(): Theme {
  const fromDocument = document.documentElement.dataset.theme
  if (fromDocument === 'light' || fromDocument === 'dark') {
    return fromDocument
  }
  return readStored() ?? systemTheme()
}

function applyTheme(next: Theme) {
  const root = document.documentElement
  root.dataset.theme = next
  root.style.colorScheme = next
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', next === 'dark' ? '#161512' : '#ECE7DD')
}

function emit() {
  for (const listener of listeners) {
    listener()
  }
}

let current: Theme = initialTheme()
applyTheme(current)

export function setTheme(next: Theme) {
  if (next === current) {
    return
  }
  current = next
  try {
    localStorage.setItem(STORAGE_KEY, next)
  } catch {
    // Storage can be unavailable in private modes; the session still switches.
  }
  applyTheme(next)
  emit()
}

export function toggleTheme() {
  setTheme(current === 'dark' ? 'light' : 'dark')
}

export function useTheme(): Theme {
  return useSyncExternalStore(
    (onStoreChange) => {
      listeners.add(onStoreChange)
      return () => {
        listeners.delete(onStoreChange)
      }
    },
    () => current,
    () => 'light',
  )
}

if (typeof window !== 'undefined' && window.matchMedia) {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (event) => {
    if (readStored()) {
      return
    }
    current = event.matches ? 'dark' : 'light'
    applyTheme(current)
    emit()
  })
}
