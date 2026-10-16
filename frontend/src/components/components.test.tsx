import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import type { Plan, ScheduleBlock } from '../api/types'
import { ReviewActions } from '../pages/plans/PlanDetailPage'
import { Gantt } from './Gantt'
import { describeError } from '../lib/errors'
import { ConfirmDialog, ErrorMessage, StatusBadge } from './ui'

describe('error wording', () => {
  it('says plainly when the role is not allowed (403)', () => {
    const error = new ApiError(403, 'forbidden', "role 'viewer' may not do this")
    expect(describeError(error)).toBe('Your role is not allowed to do that.')
    render(<ErrorMessage error={error} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Your role is not allowed to do that.')
  })

  it('shows the server detail for other errors and the network message for status 0', () => {
    expect(describeError(new ApiError(409, 'version_conflict', 'Request is at version 3, not 2'))).toBe(
      'Request is at version 3, not 2',
    )
    expect(describeError(new ApiError(0, 'network_error', 'Cannot reach the server.'))).toBe('Cannot reach the server.')
    expect(describeError(new Error('boom'))).toBe('boom')
  })

  it('renders nothing without an error and offers a retry when asked', () => {
    const { container, rerender } = render(<ErrorMessage error={null} />)
    expect(container).toBeEmptyDOMElement()
    const retry = vi.fn()
    rerender(<ErrorMessage error={new ApiError(500, 'x', 'Server problem')} onRetry={retry} />)
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(retry).toHaveBeenCalled()
  })
})

describe('StatusBadge', () => {
  it('shows the status text', () => {
    render(<StatusBadge status="published" />)
    expect(screen.getByText('published')).toHaveClass('badge-good')
  })
})

describe('ConfirmDialog', () => {
  it('runs the action on confirm and shows its error without closing', async () => {
    const onConfirm = vi.fn().mockRejectedValue(new ApiError(409, 'stale_plan', 'Run a new plan.'))
    const onClose = vi.fn()
    render(
      <ConfirmDialog title="Approve plan #1?" confirmLabel="Approve" onConfirm={onConfirm} onClose={onClose}>
        <p>Details</p>
      </ConfirmDialog>,
    )
    expect(screen.getByRole('dialog', { name: 'Approve plan #1?' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Run a new plan.')
    expect(onClose).not.toHaveBeenCalled()
  })

  it('closes with Escape and with Cancel', () => {
    const onClose = vi.fn()
    render(
      <ConfirmDialog title="T" confirmLabel="Go" onConfirm={async () => {}} onClose={onClose}>
        x
      </ConfirmDialog>,
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})

const plan = (status: Plan['status']) => ({ id: 3, status }) as Plan

describe('review actions follow the role and the plan state', () => {
  const buttons = () => ({
    override: screen.getByRole('button', { name: /Override/ }),
    approve: screen.getByRole('button', { name: 'Approve' }),
    publish: screen.getByRole('button', { name: 'Publish' }),
  })
  const noop = () => {}

  it('lets a reviewer approve a succeeded plan, but not publish it yet', () => {
    render(<ReviewActions plan={plan('succeeded')} mayReview onOverride={noop} onApprove={noop} onPublish={noop} />)
    const b = buttons()
    expect(b.override).toBeEnabled()
    expect(b.approve).toBeEnabled()
    expect(b.publish).toBeDisabled()
  })

  it('lets a reviewer publish an approved plan, but not approve it again', () => {
    render(<ReviewActions plan={plan('approved')} mayReview onOverride={noop} onApprove={noop} onPublish={noop} />)
    const b = buttons()
    expect(b.approve).toBeDisabled()
    expect(b.publish).toBeEnabled()
    expect(b.override).toBeEnabled()
  })

  it('locks everything once published', () => {
    render(<ReviewActions plan={plan('published')} mayReview onOverride={noop} onApprove={noop} onPublish={noop} />)
    const b = buttons()
    expect([b.override, b.approve, b.publish].every((el) => (el as HTMLButtonElement).disabled)).toBe(true)
  })

  it('shows no buttons to someone who cannot review', () => {
    render(<ReviewActions plan={plan('succeeded')} mayReview={false} onOverride={noop} onApprove={noop} onPublish={noop} />)
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByText(/Only planners and administrators/)).toBeInTheDocument()
  })

  it('shows nothing for a plan that has no schedule', () => {
    const { container } = render(
      <ReviewActions plan={plan('running')} mayReview onOverride={noop} onApprove={noop} onPublish={noop} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('calls the handlers', () => {
    const onApprove = vi.fn()
    render(<ReviewActions plan={plan('succeeded')} mayReview onOverride={noop} onApprove={onApprove} onPublish={noop} />)
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(onApprove).toHaveBeenCalledTimes(1)
  })
})

const BLOCKS: ScheduleBlock[] = [
  {
    id: 11,
    section_code: 'A-B',
    start: '2026-10-20T03:30:00+05:30',
    end: '2026-10-20T06:30:00+05:30',
    trains_affected: 4,
    members: [
      { request: 'R5', request_id: 5, dept: 'SNT', start: '03:30', end: '05:30' },
      { request: 'R13', request_id: 13, dept: 'ENGG', start: '03:30', end: '06:30' },
    ],
  },
]

describe('Gantt', () => {
  const draw = () =>
    render(
      <MemoryRouter>
        <Gantt blocks={BLOCKS} horizonStart="2026-10-19T00:00:00+05:30" days={7} sections={['A-B', 'B-C']} title="Plan" />
      </MemoryRouter>,
    )

  it('draws one row per section, including sections without closures', () => {
    const { container } = draw()
    const labels = [...container.querySelectorAll('.row-label')].map((n) => n.textContent)
    expect(labels).toEqual(['A-B', 'B-C'])
    expect(container.querySelectorAll('.gantt-block')).toHaveLength(1)
  })

  it('colours member bars by department and draws one per request', () => {
    const { container } = draw()
    const fills = [...container.querySelectorAll('.gantt-block rect[fill]')].map((n) => n.getAttribute('fill'))
    expect(fills).toHaveLength(2)
    expect(new Set(fills).size).toBe(2)
  })

  it('shows the member requests when a bar is hovered', () => {
    const { container } = draw()
    expect(screen.queryByRole('tooltip')).toBeNull()
    fireEvent.mouseMove(container.querySelector('.gantt-block')!, { clientX: 10, clientY: 10 })
    const tooltip = screen.getByRole('tooltip')
    expect(within(tooltip).getByText(/R5/)).toBeInTheDocument()
    expect(within(tooltip).getByText(/R13/)).toBeInTheDocument()
    expect(tooltip).toHaveTextContent('A-B')
    expect(tooltip).toHaveTextContent('03:30-06:30')
    expect(tooltip).toHaveTextContent('4 trains affected')
    fireEvent.mouseLeave(container.querySelector('.gantt-block')!)
    expect(screen.queryByRole('tooltip')).toBeNull()
  })

  it('zooms to one day and hides blocks that fall on other days', () => {
    const { container } = draw()
    fireEvent.click(screen.getByRole('button', { name: 'Mon 19' }))
    expect(container.querySelectorAll('.gantt-block')).toHaveLength(0)
    fireEvent.click(screen.getByRole('button', { name: 'Tue 20' }))
    expect(container.querySelectorAll('.gantt-block')).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Whole plan' }))
    expect(container.querySelectorAll('.gantt-block')).toHaveLength(1)
  })

  it('offers a legend for the departments', () => {
    draw()
    const legend = screen.getByLabelText('Departments')
    expect(legend).toHaveTextContent('ENGG')
    expect(legend).toHaveTextContent('TRD')
    expect(legend).toHaveTextContent('SNT')
  })
})
