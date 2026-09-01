import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { Describe, FieldMeta } from '@/hooks/useRecords'

const field = (over: Partial<FieldMeta>): FieldMeta => ({
	fieldname: 'x',
	label: 'X',
	fieldtype: 'Data',
	options: null,
	reqd: 0,
	read_only: false,
	hidden: 0,
	depends_on: null,
	mandatory_depends_on: null,
	default: null,
	description: null,
	permlevel: 0,
	precision: null,
	in_list_view: 1,
	...over,
})

/** The thirteen-step admission checklist, which is what made this unreadable. */
const CHECKLIST_COLUMNS: FieldMeta[] = [
	field({ fieldname: 'step_no', label: '#', fieldtype: 'Int', reqd: 1 }),
	field({ fieldname: 'step', label: 'Step', fieldtype: 'Select', options: 'A\nB', reqd: 1 }),
	field({
		fieldname: 'status',
		label: 'Status',
		fieldtype: 'Select',
		options: 'Approved\nVerified\nReviewed',
		reqd: 1,
		description:
			'Only statuses valid for this step are accepted; the server rejects the rest.',
	}),
	field({ fieldname: 'owner_role', label: 'Owner', read_only: true }),
	field({ fieldname: 'remarks', label: 'Remarks', fieldtype: 'Small Text' }),
]

const STEPS = [
	'Full Application Review',
	'Applicant Documents Review',
	'Reference 1 Review',
	'Reference 2 Review',
]

const meta: Describe = {
	doctype: 'Admission Application',
	label: 'Admission Application',
	fields: [
		field({ fieldname: 'full_name', label: 'Full name', reqd: 1 }),
		field({
			fieldname: 'checklist',
			label: 'Checklist',
			fieldtype: 'Table',
			options: 'Admission Checklist Item',
		}),
	],
	children: { checklist: CHECKLIST_COLUMNS },
	title_field: 'full_name',
	is_submittable: 0,
	autoname: null,
	list_fields: ['full_name'],
	can_create: true,
	can_write: true,
	can_delete: true,
}

const initial = {
	full_name: 'Grace Thangam',
	checklist: STEPS.map((step, index) => ({
		step_no: index + 1,
		step,
		status: 'Approved',
		owner_role: 'Admissions Officer',
		remarks: '',
	})),
}

async function renderForm(readOnly = false) {
	vi.resetModules()
	Object.assign(window, { user: 'a@x.com', roles: ['System Manager'], csrf_token: 't' })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: vi.fn(async () => []), frappePost: vi.fn() }
	})

	const { RecordForm } = await import('./RecordForm')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<RecordForm
				meta={readOnly ? { ...meta, can_write: false } : meta}
				name="APP-2026-00009"
				initial={initial}
				onSaved={() => {}}
			/>
		</QueryClientProvider>,
	)
}

beforeEach(() => vi.resetModules())
afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

describe('a child table in the record form', () => {
	it('names each column once, not once per row', async () => {
		// The complaint: four labels and a paragraph of help text repeated down
		// thirteen rows of the admission checklist.
		await renderForm()

		const headers = screen
			.getAllByRole('columnheader')
			.map((cell) => (cell.textContent ?? '').replace('*', '').trim())
			.filter(Boolean)

		expect(headers).toEqual(['#', 'Step', 'Status', 'Owner', 'Remarks'])
	})

	it('says the help text once, under the table', async () => {
		await renderForm()

		expect(
			screen.getAllByText(/only statuses valid for this step are accepted/i),
		).toHaveLength(1)
	})

	it('gives one row per record', async () => {
		await renderForm()

		const grid = screen.getByRole('table')
		// One header row plus one per checklist entry.
		expect(within(grid).getAllByRole('row')).toHaveLength(STEPS.length + 1)
	})

	it('keeps every row editable', async () => {
		await renderForm()

		const grid = screen.getByRole('table')
		// step and status are Selects, so two per row.
		expect(within(grid).getAllByRole('combobox')).toHaveLength(STEPS.length * 2)
	})

	it('renders a read-only column as text, not a disabled box', async () => {
		// A greyed input for something nobody can change looks broken.
		await renderForm()

		const grid = screen.getByRole('table')
		const owners = within(grid).getAllByText('Admissions Officer')
		expect(owners).toHaveLength(STEPS.length)
		for (const owner of owners) {
			expect(owner.tagName).not.toBe('INPUT')
		}
	})

	it('offers a way to add and remove rows', async () => {
		await renderForm()

		expect(screen.getByRole('button', { name: 'Row' })).toBeInTheDocument()
		expect(screen.getAllByRole('button', { name: /remove row/i })).toHaveLength(STEPS.length)
	})

	it('drops the add and remove controls when the record is read-only', async () => {
		await renderForm(true)

		expect(screen.queryByRole('button', { name: /remove row/i })).not.toBeInTheDocument()
		expect(screen.getByText(/read-only access/i)).toBeInTheDocument()
	})
})
