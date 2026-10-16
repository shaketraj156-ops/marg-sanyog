import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../../api'
import type { Plan } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { ConfirmDialog, ErrorMessage, Loading, StatusBadge, Tabs } from '../../components/ui'
import { useAsync, usePolling } from '../../hooks/useAsync'
import { canReviewPlans } from '../../lib/permissions'
import { fmtDate, fmtDateTime } from '../../lib/time'
import { CompareTab } from './CompareTab'
import { ConflictsTab } from './ConflictsTab'
import { ExplanationsTab } from './ExplanationsTab'
import { OverrideDialog } from './OverrideDialog'
import { ScheduleTab } from './ScheduleTab'
import { WhatIfTab } from './WhatIfTab'

type TabId = 'schedule' | 'compare' | 'conflicts' | 'explanations' | 'whatif'
const TABS: { id: TabId; label: string }[] = [
  { id: 'schedule', label: 'Schedule' },
  { id: 'compare', label: 'Compare' },
  { id: 'conflicts', label: 'Conflicts' },
  { id: 'explanations', label: 'Explanations' },
  { id: 'whatif', label: 'What-if' },
]
const ACTIVE = ['queued', 'running']
const READY = ['succeeded', 'approved', 'published']

type Dialog = 'approve' | 'publish' | 'override' | null

export function PlanDetailPage() {
  const planId = Number(useParams().id)
  const { user } = useAuth()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tab = (TABS.find((t) => t.id === params.get('tab'))?.id ?? 'schedule') as TabId
  const [dialog, setDialog] = useState<Dialog>(null)

  const plan = useAsync(() => api.plan(planId), [planId])
  const sections = useAsync(() => api.sections(), [])
  const status = plan.data?.status
  const ready = !!status && READY.includes(status)
  const schedule = useAsync(() => (ready ? api.schedule(planId) : Promise.resolve(null)), [planId, ready, status])

  usePolling(plan.reload, 2000, !!status && ACTIVE.includes(status))

  if (plan.loading && !plan.data) return <Loading label="Loading the plan" />
  if (plan.error && !plan.data) return <ErrorMessage error={plan.error} onRetry={plan.reload} />
  const p = plan.data
  if (!p) return null

  const mayReview = canReviewPlans(user)
  const sectionCodes = (sections.data ?? []).map((s) => s.code)
  const refreshed = () => {
    setDialog(null)
    plan.reload()
    schedule.reload()
  }

  return (
    <div className="stack">
      <div className="page-title">
        <div>
          <p className="crumbs">
            <Link to="/plans">Plans</Link> / #{p.id}
          </p>
          <h1>
            Plan #{p.id} <StatusBadge status={p.status} />
          </h1>
          <p className="muted">
            {fmtDate(p.horizon_start)} to {fmtDate(p.horizon_end)} · created {fmtDateTime(p.created_at)}
            {p.parent_id && (
              <>
                {' '}
                · override of <Link to={`/plans/${p.parent_id}`}>plan #{p.parent_id}</Link>
              </>
            )}
          </p>
        </div>
        <ReviewActions
          plan={p}
          mayReview={mayReview}
          onOverride={() => setDialog('override')}
          onApprove={() => setDialog('approve')}
          onPublish={() => setDialog('publish')}
        />
      </div>

      {ACTIVE.includes(p.status) && (
        <div className="card run-status" aria-live="polite">
          <span className="spinner" aria-hidden="true" /> The plan is {p.status}. It can take up to {p.time_limit_s}{' '}
          seconds. This page updates by itself.
        </div>
      )}
      {['failed', 'infeasible'].includes(p.status) && (
        <div className="alert alert-error" role="alert">
          This run did not produce a plan: {p.error ?? p.status}
        </div>
      )}
      {!ACTIVE.includes(p.status) && !ready && !['failed', 'infeasible'].includes(p.status) && (
        <div className="alert alert-warn">This plan is {p.status}; there is no schedule to show.</div>
      )}

      {ready && (
        <>
          <Tabs tabs={TABS} active={tab} onChange={(id) => setParams({ tab: id }, { replace: true })} />
          {schedule.loading && !schedule.data ? (
            <Loading label="Loading the schedule" />
          ) : schedule.error && !schedule.data ? (
            <ErrorMessage error={schedule.error} onRetry={schedule.reload} />
          ) : (
            schedule.data && (
              <div role="tabpanel">
                {tab === 'schedule' && <ScheduleTab plan={p} schedule={schedule.data} sections={sectionCodes} />}
                {tab === 'compare' && <CompareTab plan={p} schedule={schedule.data} sections={sectionCodes} />}
                {tab === 'conflicts' && <ConflictsTab plan={p} />}
                {tab === 'explanations' && <ExplanationsTab plan={p} />}
                {tab === 'whatif' && (
                  <WhatIfTab
                    plan={p}
                    schedule={schedule.data}
                    canReview={mayReview}
                    onOverridden={(child) => navigate(`/plans/${child.id}`)}
                  />
                )}
              </div>
            )
          )}
        </>
      )}

      {dialog === 'approve' && (
        <ConfirmDialog
          title={`Approve plan #${p.id}?`}
          confirmLabel="Approve"
          onClose={() => setDialog(null)}
          onConfirm={async () => {
            await api.approve(p.id)
            refreshed()
          }}
        >
          <p>
            The placed requests become <strong>scheduled</strong>. If any request was edited or cancelled after this
            plan was made, the server refuses and you need to run a new plan.
          </p>
          {p.deferred_request_ids.length > 0 && (
            <p className="muted">
              {p.deferred_request_ids.length} request(s) were not placed and stay submitted for a later plan.
            </p>
          )}
        </ConfirmDialog>
      )}
      {dialog === 'publish' && (
        <ConfirmDialog
          title={`Publish plan #${p.id}?`}
          confirmLabel="Publish"
          onClose={() => setDialog(null)}
          onConfirm={async () => {
            await api.publish(p.id)
            refreshed()
          }}
        >
          <p>
            The closures are put on the <Link to="/calendar">published calendar</Link> and the requests become{' '}
            <strong>published</strong>. If a published block already closes the same section at an overlapping time,
            nothing is published and you are told which block conflicts.
          </p>
        </ConfirmDialog>
      )}
      {dialog === 'override' && schedule.data && (
        <OverrideDialog
          plan={p}
          schedule={schedule.data}
          onClose={() => setDialog(null)}
          onDone={(child) => navigate(`/plans/${child.id}`)}
        />
      )}
    </div>
  )
}

export function ReviewActions({
  plan,
  mayReview,
  onOverride,
  onApprove,
  onPublish,
}: {
  plan: Plan
  mayReview: boolean
  onOverride(): void
  onApprove(): void
  onPublish(): void
}) {
  if (!['succeeded', 'approved', 'published'].includes(plan.status)) return null
  if (!mayReview) {
    return <p className="muted note-right">Only planners and administrators can override, approve or publish.</p>
  }
  return (
    <div className="button-row" role="group" aria-label="Review actions">
      <button type="button" className="btn" onClick={onOverride} disabled={plan.status === 'published'}>
        Override...
      </button>
      <button type="button" className="btn btn-primary" onClick={onApprove} disabled={plan.status !== 'succeeded'}>
        Approve
      </button>
      <button type="button" className="btn btn-primary" onClick={onPublish} disabled={plan.status !== 'approved'}>
        Publish
      </button>
    </div>
  )
}
