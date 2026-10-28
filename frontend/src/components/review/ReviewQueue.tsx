import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import {
  ApiError,
  errorMessage,
  listReports,
  reviewReport,
  type ReportQueueItem,
  type ReportQueueResponse,
  type ReportReviewDecision,
} from '../../lib/api'
import { useAccessToken } from '../../lib/useAccessToken'
import { ThemeToggle } from '../ThemeToggle'
import {
  ArrowRightIcon,
  CheckIcon,
  CloseIcon,
  RetryIcon,
  ShieldIcon,
  TagMark,
} from '../chat/icons'

const PAGE_SIZE = 20

function materialLabel(value: string): string {
  return value
    .replace(/[-_]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatMoney(value: number, currency: string): string {
  const amount = new Intl.NumberFormat('en-PK', { maximumFractionDigits: 2 }).format(value)
  return currency === 'PKR' ? `Rs ${amount}` : `${currency} ${amount}`
}

function formatQuantity(value: number): string {
  return `${new Intl.NumberFormat('en-PK', { maximumFractionDigits: 3 }).format(value)} kg`
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return 'Not recorded'
  }
  const timestamp = new Date(value)
  if (Number.isNaN(timestamp.getTime())) {
    return 'Not recorded'
  }
  return new Intl.DateTimeFormat('en-PK', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(timestamp)
}

function locationLabel(report: ReportQueueItem): string {
  return [report.area, report.city].filter(Boolean).join(', ') || 'Not recorded'
}

function anomalyMethodLabel(method: string): string {
  const normalized = method.trim().toLowerCase()
  if (normalized === 'mad') {
    return 'Median/MAD statistical check'
  }
  if (normalized === 'validation') {
    return 'Intake validation'
  }
  return method
}

function isAccessError(error: Error | null): error is ApiError {
  return error instanceof ApiError && (error.status === 401 || error.status === 403)
}

interface ReviewQueueProps {
  accountSlot?: ReactNode
}

interface PendingDecision {
  report: ReportQueueItem
  decision: ReportReviewDecision
}

function Wordmark() {
  return (
    <div className="flex items-center gap-2.5">
      <TagMark className="h-5 w-5 text-ink" />
      <span className="text-[15px] font-semibold tracking-[-0.01em] text-ink">ScrapSense</span>
    </div>
  )
}

function QueueSkeleton() {
  return (
    <div className="space-y-3" aria-hidden="true">
      {[0, 1, 2].map((index) => (
        <div key={index} className="clay-card p-5">
          <div className="h-4 w-32 rounded-sm bg-active" />
          <div className="mt-3 h-3 w-52 rounded-sm bg-rule" />
          <div className="mt-2 h-3 w-40 rounded-sm bg-rule" />
          <div className="mt-5 h-10 w-full rounded-[14px] bg-active" />
        </div>
      ))}
    </div>
  )
}

function AccessPanel({ error }: { error: ApiError }) {
  const expired = error.status === 401
  return (
    <div className="clay-card mx-auto mt-10 max-w-[520px] p-6">
      <div className="flex items-center gap-2 text-negative">
        <ShieldIcon className="h-4 w-4" />
        <p className="text-[12px] font-medium uppercase tracking-[0.12em]">
          {expired ? 'Session expired' : 'Access restricted'}
        </p>
      </div>
      <h2 className="mt-3 text-[20px] font-semibold tracking-[-0.02em] text-ink">
        {expired ? 'Sign in again to review reports' : 'Reviewer access required'}
      </h2>
      <p className="mt-2 text-[13px] leading-6 text-muted">
        {expired
          ? 'Your Clerk session could not be verified. Sign in again and reopen the review queue.'
          : 'Your account is signed in, but it is not on the reviewer list. Ask an administrator to add your Clerk user ID to ADMIN_USER_IDS.'}
      </p>
      <a
        href="/"
        className="clay-button clay-button-secondary mt-5 inline-flex h-11 items-center gap-2 px-4 text-[13px] font-medium text-ink"
      >
        Back to reports
        <ArrowRightIcon className="h-4 w-4" />
      </a>
    </div>
  )
}

function ConfirmDialog({
  pending,
  deciding,
  error,
  onCancel,
  onConfirm,
}: {
  pending: PendingDecision
  deciding: boolean
  error: string | null
  onCancel: () => void
  onConfirm: () => void
}) {
  const cancelRef = useRef<HTMLButtonElement>(null)
  const titleId = useId()
  const descriptionId = useId()
  const approving = pending.decision === 'accepted'

  useEffect(() => {
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const timer = window.setTimeout(() => cancelRef.current?.focus(), 30)

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !deciding) {
        onCancel()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previous
      window.clearTimeout(timer)
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [deciding, onCancel])

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <button
        type="button"
        onClick={onCancel}
        disabled={deciding}
        aria-label="Cancel review decision"
        className="drawer-overlay absolute inset-0 bg-scrim"
      />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="clay-card dialog-panel relative w-full max-w-[440px] p-5"
      >
        <h2 id={titleId} className="text-[17px] font-semibold tracking-[-0.015em] text-ink">
          {approving ? 'Approve this report?' : 'Reject this report?'}
        </h2>
        <p id={descriptionId} className="mt-2 text-[13px] leading-5 text-muted">
          {approving
            ? 'Approval clears the anomaly flag and makes this report eligible for price estimates only if every other eligibility rule still passes.'
            : 'Rejection keeps this report for audit but permanently excludes it from price estimates.'}
        </p>

        <div className="clay-inset mt-4 space-y-1.5 px-3.5 py-3">
          <p className="text-[13px] font-medium text-ink">
            {materialLabel(pending.report.material)}
          </p>
          <p className="text-[12px] leading-5 text-muted">
            {formatMoney(pending.report.price_per_kg, pending.report.currency)} per kg
            {' · '}
            {formatQuantity(pending.report.quantity_kg)}
          </p>
          <p className="text-[12px] leading-5 text-muted">{locationLabel(pending.report)}</p>
        </div>

        {error ? (
          <p role="alert" className="mt-3 text-[12px] leading-5 text-negative">
            {error}
          </p>
        ) : null}

        <div className="mt-5 flex justify-end gap-2">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            disabled={deciding}
            className="clay-button clay-button-secondary h-11 px-4 text-[13px] font-medium text-ink sm:h-9 sm:px-3"
          >
            Keep pending
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={deciding}
            aria-busy={deciding || undefined}
            className={`clay-button h-11 px-4 text-[13px] font-medium sm:h-9 sm:px-3 ${
              approving
                ? 'clay-button-primary text-on-solid'
                : 'clay-button-danger text-on-negative'
            }`}
          >
            {deciding ? (
              <span className="flex items-center gap-2">
                <span className="spinner h-3.5 w-3.5 rounded-full border-2 border-on-solid/30 border-t-on-solid" />
                Saving…
              </span>
            ) : approving ? (
              'Approve report'
            ) : (
              'Reject report'
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

export function ReviewQueue({ accountSlot }: ReviewQueueProps) {
  const getToken = useAccessToken()
  const [page, setPage] = useState(1)
  const [data, setData] = useState<ReportQueueResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [pending, setPending] = useState<PendingDecision | null>(null)
  const [deciding, setDeciding] = useState(false)
  const [decisionError, setDecisionError] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    void (async () => {
      try {
        const token = await getToken()
        const response = await listReports(token, {
          status: 'flagged',
          page,
          pageSize: PAGE_SIZE,
        })
        if (!cancelled) {
          setData(response)
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError : new Error('Something went wrong'))
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [getToken, page, refreshKey])

  function openDecision(report: ReportQueueItem, decision: ReportReviewDecision) {
    setFeedback(null)
    setDecisionError(null)
    setPending({ report, decision })
  }

  function closeDecision() {
    if (deciding) {
      return
    }
    setPending(null)
    setDecisionError(null)
  }

  function reloadQueue() {
    setLoading(true)
    setError(null)
    setRefreshKey((current) => current + 1)
  }

  function changePage(nextPage: number) {
    setLoading(true)
    setError(null)
    setPage(nextPage)
  }

  async function confirmDecision() {
    if (!pending || deciding) {
      return
    }

    const { report, decision } = pending
    setDeciding(true)
    setDecisionError(null)
    setFeedback(null)

    try {
      const token = await getToken()
      await reviewReport(token, report.id, decision)
      setPending(null)
      setFeedback(
        decision === 'accepted'
          ? `Approved the ${materialLabel(report.material)} report. It is eligible only if every other rule still passes.`
          : `Rejected the ${materialLabel(report.material)} report. It will not influence price estimates.`,
      )

      setLoading(true)
      setError(null)
      if (data && data.items.length === 1 && page > 1) {
        setPage((current) => Math.max(1, current - 1))
      } else {
        setRefreshKey((current) => current + 1)
      }
    } catch (decisionFailure) {
      setDecisionError(errorMessage(decisionFailure))
    } finally {
      setDeciding(false)
    }
  }

  const accessError = isAccessError(error) ? error : null
  const total = data?.total ?? 0
  const pages = data?.pages ?? 0
  const items = data?.items ?? []

  return (
    <div className="min-h-svh bg-ground">
      <header className="mx-auto flex w-full max-w-[1120px] items-center justify-between gap-8 px-5 py-5 sm:px-6">
        <a href="/" aria-label="ScrapSense reports">
          <Wordmark />
        </a>
        <div className="flex items-center gap-2">
          <a
            href="/"
            className="clay-button clay-button-secondary hidden h-11 items-center gap-2 px-4 text-[13px] font-medium text-ink sm:inline-flex sm:h-9 sm:px-3.5"
          >
            Back to reports
            <ArrowRightIcon className="h-4 w-4" />
          </a>
          {accountSlot}
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1120px] px-5 pb-16 pt-2 sm:px-6 lg:pt-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="flex items-center gap-2 text-[12px] font-medium uppercase tracking-[0.12em] text-muted">
              <ShieldIcon className="h-3.5 w-3.5" />
              Human review
            </p>
            <h1 className="mt-2 text-[30px] font-semibold leading-[1.1] tracking-[-0.03em] text-ink sm:text-[36px]">
              Flagged reports
            </h1>
            <p className="mt-2 max-w-[58ch] text-[13px] leading-6 text-muted sm:text-[14px]">
              Statistical checks can flag a legitimate unusual sale. Approve only after reading the
              evidence. Rejected reports stay out of estimates permanently.
            </p>
          </div>
          <button
            type="button"
            onClick={reloadQueue}
            disabled={loading}
            className="clay-button clay-button-secondary flex h-11 items-center gap-2 px-4 text-[13px] font-medium text-ink sm:h-9"
          >
            <RetryIcon className="h-4 w-4" />
            Refresh
          </button>
        </div>

        <div className="mt-6 space-y-3">
          {feedback ? (
            <div
              role="status"
              className="clay-inset flex items-start gap-2 px-3.5 py-3 text-[12px] leading-5 text-ink"
            >
              <CheckIcon className="mt-0.5 h-4 w-4 shrink-0 text-accent-text" />
              <p className="min-w-0 flex-1">{feedback}</p>
              <button
                type="button"
                onClick={() => setFeedback(null)}
                aria-label="Dismiss confirmation"
                className="clay-icon-button flex h-8 w-8 shrink-0 items-center justify-center text-muted hover:text-ink"
              >
                <CloseIcon className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : null}

          {accessError ? (
            <AccessPanel error={accessError} />
          ) : error ? (
            <div role="alert" className="clay-card mx-auto mt-8 max-w-[560px] p-6">
              <h2 className="text-[18px] font-semibold tracking-[-0.015em] text-ink">
                The review queue could not be loaded
              </h2>
              <p className="mt-2 text-[13px] leading-6 text-muted">{errorMessage(error)}</p>
              <button
                type="button"
                onClick={reloadQueue}
                className="clay-button clay-button-primary mt-5 inline-flex h-11 items-center gap-2 px-4 text-[13px] font-medium text-on-solid"
              >
                <RetryIcon className="h-4 w-4" />
                Try again
              </button>
            </div>
          ) : loading && !data ? (
            <QueueSkeleton />
          ) : items.length === 0 ? (
            <div className="clay-card px-6 py-10 text-center">
              <div className="clay-icon-chip mx-auto flex h-10 w-10 items-center justify-center text-accent-text">
                <CheckIcon className="h-5 w-5" />
              </div>
              <h2 className="mt-4 text-[18px] font-semibold tracking-[-0.015em] text-ink">
                No reports waiting for review
              </h2>
              <p className="mx-auto mt-2 max-w-[44ch] text-[13px] leading-6 text-muted">
                Flagged reports will appear here in oldest-first order. Refresh to check again.
              </p>
            </div>
          ) : (
            <div className="space-y-3" aria-busy={loading || undefined}>
              {items.map((report) => (
                <article
                  key={report.id}
                  className="clay-card p-4 sm:p-5"
                  aria-labelledby={`report-${report.id}-title`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2
                          id={`report-${report.id}-title`}
                          className="text-[17px] font-semibold tracking-[-0.015em] text-ink"
                        >
                          {materialLabel(report.material)}
                        </h2>
                        <span className="clay-chip px-2.5 py-1 text-[11px] font-medium text-negative">
                          Flagged
                        </span>
                      </div>
                      <p className="mt-1 text-[12px] leading-5 text-muted">
                        {locationLabel(report)}
                        {' · '}
                        Reported {formatTimestamp(report.observed_at ?? report.created_at)}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-mono text-[18px] font-medium leading-6 text-accent-text">
                        {formatMoney(report.price_per_kg, report.currency)}
                        <span className="text-[12px] text-muted"> / kg</span>
                      </p>
                      <p className="mt-0.5 text-[12px] leading-5 text-muted">
                        {formatQuantity(report.quantity_kg)}
                      </p>
                    </div>
                  </div>

                  <div className="clay-inset mt-4 px-3.5 py-3">
                    <p className="text-[11px] font-medium uppercase tracking-[0.1em] text-muted">
                      {anomalyMethodLabel(report.anomaly_method)}
                    </p>
                    <p className="mt-1.5 text-[13px] leading-6 text-ink">
                      {report.anomaly_reason}
                    </p>
                    {report.confidence !== null ? (
                      <p className="mt-1 text-[11px] leading-5 text-muted">
                        Extraction confidence{' '}
                        {new Intl.NumberFormat('en-PK', {
                          style: 'percent',
                          maximumFractionDigits: 0,
                        }).format(report.confidence)}
                      </p>
                    ) : null}
                  </div>

                  <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                    <p className="text-[11px] leading-5 text-muted">
                      Submitted {formatTimestamp(report.created_at)}
                    </p>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => openDecision(report, 'rejected')}
                        disabled={deciding || loading}
                        aria-label={`Reject ${materialLabel(report.material)} report`}
                        className="clay-button clay-button-secondary flex h-11 items-center px-4 text-[13px] font-medium text-negative sm:h-9"
                      >
                        Reject
                      </button>
                      <button
                        type="button"
                        onClick={() => openDecision(report, 'accepted')}
                        disabled={deciding || loading}
                        aria-label={`Approve ${materialLabel(report.material)} report`}
                        className="clay-button clay-button-primary flex h-11 items-center gap-1.5 px-4 text-[13px] font-medium text-on-solid sm:h-9"
                      >
                        <CheckIcon className="h-3.5 w-3.5" />
                        Approve
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}

          {!accessError && !error && data ? (
            <nav
              aria-label="Review queue pages"
              className="flex flex-wrap items-center justify-between gap-3 pt-2"
            >
              <p className="text-[12px] leading-5 text-muted" aria-live="polite">
                {total} flagged {total === 1 ? 'report' : 'reports'}
                {pages > 0 ? ` · Page ${Math.min(page, pages)} of ${pages}` : ''}
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => changePage(Math.max(1, page - 1))}
                  disabled={loading || page <= 1}
                  className="clay-button clay-button-secondary h-11 px-4 text-[13px] font-medium text-ink sm:h-9"
                >
                  Previous
                </button>
                <button
                  type="button"
                  onClick={() => changePage(page + 1)}
                  disabled={loading || !data.has_more}
                  className="clay-button clay-button-secondary h-11 px-4 text-[13px] font-medium text-ink sm:h-9"
                >
                  Next
                </button>
              </div>
            </nav>
          ) : null}
        </div>
      </main>

      {pending ? (
        <ConfirmDialog
          pending={pending}
          deciding={deciding}
          error={decisionError}
          onCancel={closeDecision}
          onConfirm={() => void confirmDecision()}
        />
      ) : null}
    </div>
  )
}
