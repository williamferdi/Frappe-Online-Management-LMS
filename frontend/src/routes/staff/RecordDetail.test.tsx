import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import type { Describe, FieldMeta } from '@/hooks/useRecords'

const field = (overrides: Partial<FieldMeta> & { fieldname: string }): FieldMeta => ({
	label: overrides.fieldname,
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
	in_list_view: 0,
	...overrides,
})

const promotion: Describe = {
	doctype: 'Level Promotion',
	label: 'Level Promotion',
	fields: [
		field({ fieldname: 'program_enrollment', label: 'Program Enrollment', fieldtype: 'Data' }),
		field({ fieldname: 'from_level', label: 'From Level', fieldtype: 'Data' }),
		field({ fieldname: 'to_level', label: 'To Level', fieldtype: 'Data' }),
		field({ fieldname: 'remarks', label: 'Remarks', fieldtype: 'Data', default: 'ask' }),
	],
	children: {},
	title_field: 'name',
	is_submittable: 0,
	autoname: null,
	list_fields: [],
	can_create: true,
	can_write: true,
	can_delete: true,
}

async function renderNew(search: string) {
	const get = vi.fn(async (method: string) => {
		if (method.endsWith('records.describe')) return promotion
		throw new Error(`unexpected call: ${method}`)
	})

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: get, frappePost: vi.fn() }
	})

	const { RecordDetail } = await import('./RecordDetail')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter initialEntries={[`/staff/data/Level Promotion/new${search}`]}>
				<Routes>
					<Route path="/staff/data/:doctype/:name" element={<RecordDetail />} />
				</Routes>
			</MemoryRouter>
		</QueryClientProvider>,
	)

	await waitFor(() =>
		expect(screen.getByRole('heading', { name: /New Level Promotion/ })).toBeInTheDocument(),
	)
}

beforeEach(() => vi.resetModules())
afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

describe('a new record seeded from the link that opened it', () => {
	it('fills the fields named in the query string', async () => {
		// This is what makes "Change level" on a student worth clicking: the
		// form already knows whose enrolment it is and where the level starts.
		await renderNew('?program_enrollment=ENR-0007&from_level=1')

		expect(screen.getByLabelText(/Program Enrollment/)).toHaveValue('ENR-0007')
		expect(screen.getByLabelText(/From Level/)).toHaveValue('1')
		expect(screen.getByLabelText(/To Level/)).toHaveValue('')
	})

	it('still applies the DocType own defaults', async () => {
		await renderNew('?program_enrollment=ENR-0007')

		expect(screen.getByLabelText(/Program Enrollment/)).toHaveValue('ENR-0007')
		expect(screen.getByLabelText(/Remarks/)).toHaveValue('ask')
	})

	it('ignores a parameter the DocType has no field for', async () => {
		// A crafted URL cannot introduce a field. The server decides what is
		// writable regardless, but the form should not invent one either.
		await renderNew('?program_enrollment=ENR-0007&current_level=9&docstatus=1')

		expect(screen.getByLabelText(/Program Enrollment/)).toHaveValue('ENR-0007')
		expect(screen.queryByLabelText(/current_level/)).toBeNull()
		expect(screen.queryByLabelText(/docstatus/)).toBeNull()
	})
})
