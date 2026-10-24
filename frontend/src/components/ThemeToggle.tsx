import { toggleTheme, useTheme } from '../lib/theme'
import { MoonIcon, SunIcon } from './chat/icons'

export function ThemeToggle({ className = '' }: { className?: string }) {
  const theme = useTheme()
  const dark = theme === 'dark'

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      className={`clay-icon-button theme-toggle flex h-11 w-11 shrink-0 items-center justify-center text-muted hover:text-ink lg:h-9 lg:w-9 ${className}`}
    >
      <span className="theme-toggle-glyph" data-active={dark}>
        <SunIcon className="h-4 w-4" />
      </span>
      <span className="theme-toggle-glyph" data-active={!dark}>
        <MoonIcon className="h-4 w-4" />
      </span>
    </button>
  )
}
