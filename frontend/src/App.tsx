import { Show, SignInButton, UserButton } from '@clerk/react'
import { Chat } from './components/Chat'

function App() {
  return (
    <div className="min-h-svh bg-slate-100 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-4 py-4">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-600 text-lg font-bold text-white">
              S
            </span>
            <div>
              <p className="text-lg font-semibold leading-tight">ScrapSense</p>
              <p className="text-xs text-slate-500">Scrap market intelligence</p>
            </div>
          </div>
          <Show when="signed-in">
            <UserButton />
          </Show>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-8">
        <Show when="signed-out">
          <section className="mx-auto max-w-2xl rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm sm:p-12">
            <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">
              Picker chat
            </p>
            <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
              Know the price before you sell.
            </h1>
            <p className="mx-auto mt-4 max-w-xl text-slate-600">
              Sign in to talk to ScrapSense in plain language. Report a sale or ask what a
              material is worth, and keep your history across visits.
            </p>
            <SignInButton mode="modal">
              <button
                type="button"
                className="mt-8 rounded-lg bg-emerald-600 px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700"
              >
                Sign in to chat
              </button>
            </SignInButton>
          </section>
        </Show>

        <Show when="signed-in">
          <Chat />
        </Show>
      </main>
    </div>
  )
}

export default App
