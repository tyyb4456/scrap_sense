import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import {
  errorMessage,
  getPriceEstimate,
  type PriceEstimate,
  type PriceEvidenceQuality,
  type PriceScope,
  type PriceSource,
} from '../../lib/api'
import { useAccessToken } from '../../lib/useAccessToken'
import { CloseIcon, TagMark } from './icons'

const materials = [
  'plastic',
  'paper',
  'iron',
  'copper',
  'aluminum',
  'brass',
  'glass',
  'textile',
]

const sourceMeta: Record<
  PriceSource,
  { label: string; detail: string; tone: 'good' | 'warn' | 'muted' }
> = {
  local_reports: {
    label: 'Neighbourhood reports',
    detail: 'Checked reports from your area',
    tone: 'good',
  },
  city_reports: {
    label: 'City reports',
    detail: 'Checked reports across the city',
    tone: 'good',
  },
  seed_data: {
    label: 'Seed reference',
    detail: 'From configured seed entries, not live reports',
    tone: 'warn',
  },
  unavailable: {
    label: 'Unavailable',
    detail: 'Not enough checked reports or seed data',
    tone: 'muted',
  },
}

const scopeLabels: Record<PriceScope, string> = {
  area: 'Neighbourhood',
  city: 'City',
  national: 'National',
  none: 'No scope',
}

const qualityLabels: Record<PriceEvidenceQuality, string> = {
  high: 'Strong evidence',
  medium: 'Moderate evidence',
  low: 'Thin evidence',
  none: 'No evidence',
}

function formatMoney(value: number, currency: string): string {
  const amount = new Intl.NumberFormat('en-PK', { maximumFractionDigits: 2 }).format(value)
  return currency === 'PKR' ? `Rs ${amount}` : `${currency} ${amount}`
}

function freshnessLabel(days: number | null, source: PriceSource): string {
  if (days === null) {
    return 'Not available'
  }
  const prefix = source === 'seed_data' ? 'Seed collected' : 'Newest report'
  if (days < 1) {
    return `${prefix} today`
  }
  if (days < 2) {
    return `${prefix} yesterday`
  }
  return `${prefix} ${Math.round(days)} days ago`
}

function sourceToneClass(tone: 'good' | 'warn' | 'muted'): string {
  if (tone === 'good') {
    return 'text-accent-text'
  }
  if (tone === 'warn') {
    return 'text-negative'
  }
  return 'text-muted'
}

interface PriceCheckProps {
  open: boolean
  onClose: () => void
}

export function PriceCheck({ open, onClose }: PriceCheckProps) {
  const getToken = useAccessToken()
  const materialListId = useId()
  const panelRef = useRef<HTMLDivElement>(null)

  const [material, setMaterial] = useState('plastic')
  const [location, setLocation] = useState('Multan')
  const [area, setArea] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<PriceEstimate | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const timer = window.setTimeout(() => panelRef.current?.focus(), 30)

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previous
      window.clearTimeout(timer)
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [open, onClose])

  function resetResult() {
    setResult(null)
    setError(null)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const requestedMaterial = material.trim()
    if (!requestedMaterial || loading) {
      return
    }
    if (area.trim() && !location.trim()) {
      setResult(null)
      setError('Enter a city before an area.')
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const token = await getToken()
      const estimate = await getPriceEstimate(token, {
        material: requestedMaterial,
        location,
        area,
      })
      setResult(estimate)
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  if (!open) {
    return null
  }

  const meta = result ? sourceMeta[result.source] : null
  const observedRange =
    result?.observed_min_price_per_kg != null && result.observed_max_price_per_kg != null
      ? `${formatMoney(result.observed_min_price_per_kg, result.currency)} – ${formatMoney(
          result.observed_max_price_per_kg,
          result.currency,
        )} / ${result.unit}`
      : 'Not available'
  const evidenceLabel = result?.source === 'seed_data' ? 'Seed entries' : 'Checked reports'
  const evidenceCount = result
    ? result.source === 'unavailable'
      ? result.city_observation_count
      : result.observation_count
    : 0

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center sm:items-center sm:p-4">
      <button
        type="button"
        onClick={onClose}
        aria-label="Close price check"
        className="drawer-overlay absolute inset-0 bg-scrim"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="price-check-title"
        tabIndex={-1}
        className="dialog-panel clay-card relative flex max-h-[92svh] w-full max-w-[540px] flex-col overflow-hidden rounded-b-none outline-none sm:rounded-b-[22px]"
      >
        <header className="flex shrink-0 items-start gap-3 px-5 pb-3 pt-5">
          <div className="clay-icon-chip flex h-8 w-8 shrink-0 items-center justify-center text-ink">
            <TagMark className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <h2
              id="price-check-title"
              className="text-[17px] font-semibold leading-6 tracking-[-0.015em] text-ink"
            >
              Check a price
            </h2>
            <p className="mt-0.5 text-[12px] leading-5 text-muted">
              Median of checked picker reports, with a labelled seed fallback.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close price check"
            className="clay-icon-button -mr-1 flex h-11 w-11 shrink-0 items-center justify-center text-muted hover:text-ink"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </header>

        <div className="chat-scroll min-h-0 overflow-y-auto px-5 pb-6">
          <form onSubmit={handleSubmit} className="space-y-3" aria-busy={loading}>
            <div>
              <label
                htmlFor="price-material"
                className="mb-1.5 block text-[12px] font-medium leading-4 text-ink"
              >
                Material
              </label>
              <input
                id="price-material"
                type="text"
                list={materialListId}
                value={material}
                onChange={(event) => {
                  setMaterial(event.target.value)
                  resetResult()
                }}
                autoComplete="off"
                maxLength={100}
                disabled={loading}
                placeholder="plastic, kaghaz, iron…"
                className="clay-input h-11 w-full px-3 text-[14px] text-ink placeholder:text-faint"
              />
              <datalist id={materialListId}>
                {materials.map((option) => (
                  <option value={option} key={option} />
                ))}
              </datalist>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="price-location"
                  className="mb-1.5 block text-[12px] font-medium leading-4 text-ink"
                >
                  City
                </label>
                <input
                  id="price-location"
                  type="text"
                  value={location}
                  onChange={(event) => {
                    setLocation(event.target.value)
                    resetResult()
                  }}
                  maxLength={100}
                  disabled={loading}
                  placeholder="Multan"
                  className="clay-input h-11 w-full px-3 text-[14px] text-ink placeholder:text-faint"
                />
              </div>
              <div>
                <label
                  htmlFor="price-area"
                  className="mb-1.5 block text-[12px] font-medium leading-4 text-ink"
                >
                  Area (optional)
                </label>
                <input
                  id="price-area"
                  type="text"
                  value={area}
                  onChange={(event) => {
                    setArea(event.target.value)
                    resetResult()
                  }}
                  maxLength={100}
                  disabled={loading}
                  placeholder="Neighbourhood"
                  className="clay-input h-11 w-full px-3 text-[14px] text-ink placeholder:text-faint"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || material.trim().length === 0}
              className="clay-button clay-button-primary flex h-11 w-full items-center justify-center gap-2 px-4 text-[13px] font-medium text-on-solid"
            >
              {loading ? (
                <>
                  <span className="spinner h-3.5 w-3.5 rounded-full border-2 border-on-solid/30 border-t-on-solid" />
                  Checking reports
                </>
              ) : (
                'Check price'
              )}
            </button>
          </form>

          {error ? (
            <div role="alert" className="clay-inset mt-4 flex items-start gap-2 px-3 py-2.5">
              <span
                className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-negative"
                aria-hidden="true"
              />
              <p className="text-[12px] leading-5 text-ink">{error}</p>
            </div>
          ) : null}

          {loading ? (
            <div className="clay-inset mt-4 px-4 py-5" role="status" aria-live="polite">
              <p className="text-[13px] font-medium text-ink">Reading checked reports…</p>
              <div className="mt-3 space-y-2" aria-hidden="true">
                <div className="h-3 w-28 rounded-sm bg-active" />
                <div className="h-8 w-40 rounded-sm bg-active" />
                <div className="h-3 w-full rounded-sm bg-active" />
              </div>
            </div>
          ) : null}

          {result && meta ? (
            <div className="clay-inset mt-4 px-4 py-4" aria-live="polite">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted">
                    {result.material_label} · {result.location ?? 'National'}
                  </p>
                  {result.estimated_price_per_kg !== null ? (
                    <p className="num mt-1 text-[28px] font-semibold leading-9 tracking-[-0.03em] text-ink">
                      {formatMoney(result.estimated_price_per_kg, result.currency)}
                      <span className="ml-1 text-[14px] font-normal tracking-normal text-muted">
                        / {result.unit}
                      </span>
                    </p>
                  ) : (
                    <p className="mt-1 text-[18px] font-semibold leading-7 tracking-[-0.02em] text-ink">
                      No trustworthy estimate yet
                    </p>
                  )}
                </div>
                <span className="clay-chip flex shrink-0 items-center gap-1.5 px-2.5 py-1 text-[10px] font-medium">
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      meta.tone === 'good'
                        ? 'bg-positive'
                        : meta.tone === 'warn'
                          ? 'bg-negative'
                          : 'bg-control'
                    }`}
                    aria-hidden="true"
                  />
                  <span className={sourceToneClass(meta.tone)}>{meta.label}</span>
                </span>
              </div>

              <p className="mt-2 text-[12px] leading-5 text-muted">{meta.detail}</p>
              <p className="mt-1 text-[12px] leading-5 text-muted">{result.message}</p>

              {result.source === 'seed_data' ? (
                <div className="mt-3 flex items-start gap-2 rounded-[12px] border border-line bg-active px-3 py-2">
                  <span
                    className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-negative"
                    aria-hidden="true"
                  />
                  <p className="text-[11px] leading-5 text-ink">
                    Seed reference, not live market data.
                    {result.seed_source ? ` Source: ${result.seed_source}.` : ''}
                  </p>
                </div>
              ) : null}

              <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-line pt-3 text-[11px] leading-5">
                <div>
                  <dt className="text-muted">{evidenceLabel}</dt>
                  <dd className="num font-medium text-ink">
                    {evidenceCount === 0
                      ? 'None yet'
                      : `${evidenceCount} found${result.source === 'unavailable' ? ', below threshold' : ''}`}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted">Scope</dt>
                  <dd className="font-medium text-ink">
                    {scopeLabels[result.geographic_scope]}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted">Observed range</dt>
                  <dd className="font-medium text-ink">{observedRange}</dd>
                </div>
                <div>
                  <dt className="text-muted">Freshness</dt>
                  <dd className="font-medium text-ink">
                    {freshnessLabel(result.freshness_days, result.source)}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted">Evidence quality</dt>
                  <dd className="font-medium text-ink">
                    {qualityLabels[result.evidence_quality]}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted">Source</dt>
                  <dd className="font-medium text-ink">
                    {result.source === 'seed_data' && result.seed_collected_at
                      ? `Seed · ${result.seed_collected_at}`
                      : meta.label}
                  </dd>
                </div>
              </dl>

              {result.limitations.length > 0 ? (
                <ul className="mt-3 space-y-1 border-t border-line pt-3">
                  {result.limitations.map((limitation) => (
                    <li
                      key={limitation}
                      className="flex items-start gap-1.5 text-[10px] leading-4 text-muted"
                    >
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-control" />
                      {limitation}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          <p className="mt-4 text-[10px] leading-4 text-muted">
            Estimates come from pooled picker reports. Dealer quotes are not used. A seed
            reference is reference data, not a live market price.
          </p>
        </div>
      </div>
    </div>
  )
}
