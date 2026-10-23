import { ClerkProvider } from '@clerk/react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {publishableKey ? (
      <ClerkProvider publishableKey={publishableKey}>
        <App />
      </ClerkProvider>
    ) : (
      <main className="mx-auto max-w-xl p-8">
        <h1 className="text-2xl font-bold text-slate-900">ScrapSense setup required</h1>
        <p className="mt-3 text-slate-600">
          Set <code className="rounded bg-slate-200 px-1.5 py-0.5">VITE_CLERK_PUBLISHABLE_KEY</code>{' '}
          in <code className="rounded bg-slate-200 px-1.5 py-0.5">frontend/.env</code> to enable
          sign-in.
        </p>
      </main>
    )}
  </StrictMode>,
)
