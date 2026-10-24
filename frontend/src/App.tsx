import {
  ClerkLoaded,
  ClerkLoading,
  Show,
  SignInButton,
  UserButton,
} from '@clerk/react'
import { Chat } from './components/Chat'
import { ThemeToggle } from './components/ThemeToggle'
import { ArrowRightIcon, ShieldIcon, TagMark } from './components/chat/icons'
import { demoMode, landingMode } from './lib/demoMode'

const sampleRows = [
  { material: 'Plastic', detail: '2 kg · mixed bottles', paid: 'Rs 300' },
  { material: 'Kaghaz', detail: '5 kg · clean carton', paid: 'Rs 250' },
  { material: 'Iron', detail: '3 kg · light scrap', paid: 'Rs 285' },
]

function Wordmark() {
  return (
    <div className="flex items-center gap-2.5">
      <TagMark className="h-5 w-5 text-ink" />
      <span className="text-[15px] font-semibold tracking-[-0.01em] text-ink">ScrapSense</span>
    </div>
  )
}

function BootScreen() {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-4 bg-ground">
      <Wordmark />
      <p className="flex items-center gap-2 text-[13px] leading-4 text-muted">
        <span className="spinner h-3.5 w-3.5 rounded-full border-2 border-line border-t-ink" />
        Opening your ledger
      </p>
    </div>
  )
}

function SampleLedger() {
  return (
    <div className="clay-card">
      <div className="flex items-center justify-between gap-3 px-5 pb-1 pt-4">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
          <p className="text-[13px] font-medium text-ink">Example reports</p>
        </div>
        <p className="text-[13px] text-muted">Illustration only</p>
      </div>

      <ul className="space-y-2 px-3 py-3">
        {sampleRows.map((row) => (
          <li key={row.material} className="clay-row flex items-center gap-3 px-3.5 py-3">
            <div className="min-w-0 flex-1">
              <p className="text-[14px] font-medium leading-5 text-ink">{row.material}</p>
              <p className="mt-0.5 text-[13px] leading-4 text-muted">{row.detail}</p>
            </div>
            <p className="num shrink-0 font-mono text-[13px] leading-5 text-accent-text">{row.paid}</p>
          </li>
        ))}
      </ul>

      <div className="px-5 pb-5 pt-1">
        <p className="text-[13px] leading-5 text-muted">
          Reports are checked before they count toward a price reference. These rows are sample
          entries, not a quote.
        </p>
      </div>
    </div>
  )
}

function Landing() {
  return (
    <div className="flex min-h-svh flex-col bg-ground">
      <header className="mx-auto flex w-full max-w-[1120px] items-center justify-between px-6 py-5">
        <Wordmark />
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <SignInButton mode="modal">
            <button
              type="button"
              className="clay-button clay-button-secondary h-11 px-4 text-[13px] font-medium text-ink sm:h-9 sm:px-3.5"
            >
              Sign in
            </button>
          </SignInButton>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-[1120px] flex-1 items-center px-6 py-10 lg:py-16">
        <div className="grid w-full items-center gap-12 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16">
          <div>
            <p className="flex items-center gap-2 text-[13px] font-medium text-muted">
              <span className="h-px w-6 bg-control" aria-hidden="true" />
              Picker price ledger · Multan
            </p>

            <h1 className="mt-5 max-w-[15ch] text-[38px] font-semibold leading-[1.04] tracking-[-0.035em] text-ink sm:text-[48px] lg:text-[56px]">
              Know the price before you sell.
            </h1>

            <p className="mt-5 max-w-[44ch] text-[15px] leading-7 text-muted">
              Tell ScrapSense what you sold, in your own words. Your report is checked, then pooled
              with other pickers’ reports. The price reference comes from pickers, not dealers.
            </p>

            <SignInButton mode="modal">
              <button
                type="button"
                className="clay-button clay-button-primary group mt-8 flex h-11 items-center gap-2 px-4 text-[13px] font-medium text-on-solid"
              >
                Sign in to start a report
                <ArrowRightIcon className="cta-arrow h-4 w-4" />
              </button>
            </SignInButton>

            <p className="mt-5 flex max-w-[42ch] items-start gap-2 text-[13px] leading-5 text-muted">
              <ShieldIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              Reports are anonymous. Your name is never attached, and only pooled results are
              published.
            </p>

            <p className="mt-8 text-[13px] leading-4 text-faint">
              English interface · Roman Urdu welcome · Built for pickers, not dealers
            </p>
          </div>

          <div className="lg:pl-2">
            <SampleLedger />
          </div>
        </div>
      </main>
    </div>
  )
}

function App() {
  if (demoMode) {
    return <Chat demo />
  }

  if (landingMode) {
    return <Landing />
  }

  return (
    <>
      <ClerkLoading>
        <BootScreen />
      </ClerkLoading>
      <ClerkLoaded>
        <Show when="signed-in" fallback={<Landing />}>
          <Chat
            accountSlot={
              <UserButton appearance={{ elements: { avatarBox: 'h-7 w-7' } }} />
            }
          />
        </Show>
      </ClerkLoaded>
    </>
  )
}

export default App

