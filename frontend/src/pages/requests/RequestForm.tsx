import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../../api'
import { ApiError } from '../../api/client'
import type { BlockRequest, Department, RequestInput, Section, User, WorkType } from '../../api/types'
import { WORK_TYPES } from '../../api/types'
import { Field, Modal } from '../../components/ui'
import { isReviewer } from '../../lib/permissions'
import { istFromLocalInput, localInputFromIso } from '../../lib/time'

interface Props {
  mode: 'create' | 'edit'
  request?: BlockRequest
  user: User
  sections: Section[]
  departments: Department[]
  onSaved(request: BlockRequest): void
  onClose(): void
}

interface Form {
  department_code: string
  section_code: string
  work_type: WorkType
  duration_minutes: string
  earliest_date: string
  deadline_date: string
  priority: string
  needs_power_block: boolean
  description: string
  preferred_start: string
}

function initial(props: Props): Form {
  const r = props.request
  return {
    department_code: r?.department ?? props.user.department?.code ?? '',
    section_code: r?.section_code ?? props.sections[0]?.code ?? '',
    work_type: r?.work_type ?? 'track',
    duration_minutes: String(r?.duration_minutes ?? 120),
    earliest_date: r?.earliest_date ?? '',
    deadline_date: r?.deadline_date ?? '',
    priority: String(r?.priority ?? 2),
    needs_power_block: r?.needs_power_block ?? false,
    description: r?.description ?? '',
    preferred_start: localInputFromIso(r?.preferred_start ?? null),
  }
}

// The API reports the date-order rule against the whole request; show it under the deadline.
const FIELD_ALIASES: Record<string, string> = { '(whole request)': 'deadline_date' }
// Problem codes that belong to one field.
const CODE_FIELDS: Record<string, string> = {
  unknown_section: 'section_code',
  unknown_department: 'department_code',
}

export function RequestForm(props: Props) {
  const { mode, request, user, sections, departments, onSaved, onClose } = props
  const [form, setForm] = useState<Form>(() => initial(props))
  const [error, setError] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  const [local, setLocal] = useState<Record<string, string>>({})

  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => ({ ...f, [key]: value }))

  const fieldError = (name: string): string | undefined => {
    if (local[name]) return local[name]
    if (!error) return undefined
    const direct = error.fieldMessage(name)
    if (direct) return direct
    for (const [raw, alias] of Object.entries(FIELD_ALIASES)) {
      if (alias === name && error.fieldMessage(raw)) return error.fieldMessage(raw)
    }
    return CODE_FIELDS[error.title] === name ? error.detail : undefined
  }
  const handledFields = new Set(['department_code', 'section_code', 'work_type', 'duration_minutes', 'earliest_date', 'deadline_date', 'priority', 'description', 'preferred_start', ...Object.keys(FIELD_ALIASES)])
  const generalError =
    error &&
    (error.errors.length === 0 || error.errors.some((e) => !handledFields.has(e.field))) &&
    !CODE_FIELDS[error.title]
      ? error
      : null

  const payload = (): RequestInput => ({
    section_code: form.section_code,
    work_type: form.work_type,
    duration_minutes: Number(form.duration_minutes),
    earliest_date: form.earliest_date,
    deadline_date: form.deadline_date,
    priority: Number(form.priority),
    needs_power_block: form.needs_power_block,
    description: form.description.trim() || null,
    preferred_start: form.preferred_start ? istFromLocalInput(form.preferred_start) : null,
    ...(mode === 'create' && isReviewer(user) ? { department_code: form.department_code } : {}),
  })

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    // Empty required fields get a plain message here; every other rule is checked by the server.
    const missing: Record<string, string> = {}
    if (mode === 'create' && isReviewer(user) && !form.department_code) missing.department_code = 'Choose a department'
    if (!form.earliest_date) missing.earliest_date = 'Choose the earliest date'
    if (!form.deadline_date) missing.deadline_date = 'Choose the deadline'
    setLocal(missing)
    if (Object.keys(missing).length > 0) {
      setError(null)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const saved =
        mode === 'create'
          ? await api.createRequest(payload())
          : await api.updateRequest(request!.id, { ...payload(), version: request!.version })
      onSaved(saved)
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, 'error', String(e)))
      setBusy(false)
    }
  }

  return (
    <Modal title={mode === 'create' ? 'New block request' : `Edit request R${request!.id}`} onClose={onClose} wide>
      <form onSubmit={submit} noValidate>
        <div className="modal-body form-grid">
          {mode === 'create' && isReviewer(user) && (
            <Field label="Department" error={fieldError('department_code')}>
              <select value={form.department_code} onChange={(e) => set('department_code', e.target.value)} required>
                <option value="">Choose a department</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.code}>
                    {d.code} - {d.name}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <Field label="Section" error={fieldError('section_code')}>
            <select value={form.section_code} onChange={(e) => set('section_code', e.target.value)} required>
              {sections.map((s) => (
                <option key={s.id} value={s.code}>
                  {s.code} - {s.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Work type" error={fieldError('work_type')}>
            <select value={form.work_type} onChange={(e) => set('work_type', e.target.value as WorkType)}>
              {WORK_TYPES.map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Duration (minutes)" error={fieldError('duration_minutes')} hint="15 to 360">
            <input
              type="number"
              min={15}
              max={360}
              step={15}
              value={form.duration_minutes}
              onChange={(e) => set('duration_minutes', e.target.value)}
            />
          </Field>
          <Field label="Earliest date" error={fieldError('earliest_date')}>
            <input type="date" value={form.earliest_date} onChange={(e) => set('earliest_date', e.target.value)} />
          </Field>
          <Field label="Deadline" error={fieldError('deadline_date')}>
            <input type="date" value={form.deadline_date} onChange={(e) => set('deadline_date', e.target.value)} />
          </Field>
          <Field label="Priority" error={fieldError('priority')} hint="1 is lowest, 3 is highest">
            <select value={form.priority} onChange={(e) => set('priority', e.target.value)}>
              <option value="1">1 - low</option>
              <option value="2">2 - normal</option>
              <option value="3">3 - high</option>
            </select>
          </Field>
          <Field
            label="Preferred start (optional)"
            error={fieldError('preferred_start')}
            hint="Used only for the independent-planning baseline"
          >
            <input
              type="datetime-local"
              value={form.preferred_start}
              onChange={(e) => set('preferred_start', e.target.value)}
            />
          </Field>
          <label className="check field-wide">
            <input
              type="checkbox"
              checked={form.needs_power_block}
              onChange={(e) => set('needs_power_block', e.target.checked)}
            />
            Needs a power block (stored; not planned in this version)
          </label>
          <Field label="Description (optional)" error={fieldError('description')}>
            <textarea rows={2} value={form.description} onChange={(e) => set('description', e.target.value)} />
          </Field>
        </div>
        {generalError && (
          <div className="alert alert-error" role="alert">
            {generalError.status === 409 ? `${generalError.detail} Close this window and reload the list.` : generalError.status === 403 ? 'Your role is not allowed to do that.' : generalError.detail}
          </div>
        )}
        <footer className="modal-footer">
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Saving...' : mode === 'create' ? 'Create draft' : 'Save changes'}
          </button>
        </footer>
      </form>
    </Modal>
  )
}
