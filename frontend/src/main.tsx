import { ClerkProvider } from '@clerk/react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { demoMode } from './lib/demoMode'

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {demoMode ? (
      <App />
    ) : publishableKey ? (
      <ClerkProvider publishableKey={publishableKey}>
        <App />
      </ClerkProvider>
    ) : (
      <main className="flex min-h-svh items-center justify-center bg-ground px-6">
        <div className="w-full max-w-md rounded-[10px] border border-line bg-surface p-6">
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted">Setup</p>
          <h1 className="mt-2 text-[22px] font-semibold tracking-[-0.02em] text-ink">
            ScrapSense needs a Clerk key
          </h1>
          <p className="mt-2 text-[13px] leading-6 text-muted">
            Add{' '}
            <code className="rounded-[4px] bg-raised px-1.5 py-0.5 font-mono text-[12px] text-ink">
              VITE_CLERK_PUBLISHABLE_KEY
            </code>{' '}
            to{' '}
            <code className="rounded-[4px] bg-raised px-1.5 py-0.5 font-mono text-[12px] text-ink">
              frontend/.env
            </code>{' '}
            and restart the dev server.
          </p>
        </div>
      </main>
    )}
  </StrictMode>,
)
