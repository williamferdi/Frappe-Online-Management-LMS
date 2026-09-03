import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import type { PipelineResponse } from '@/types'

const pipeline: PipelineResponse = {
	rows: [
		{
			name: 'APP-2026-00014',
			full_name: 'Beula Patricia',
			photo: '/private/files/APP-2026-00014-photo.jpeg',
			email: 'beula@example.invalid',
			mobile: '+91 90000 00001',
			program: 'MDIV',
			intake_term: 'Term 1 2026',
			entry_level: '1',
			workflow_state: 'Admitted',
			application_fee_paid: 1,
			qualifying_exam_score: 80,
			student: null,
			creation: '2026-06-13 09:00:00',
			modified: '2026-09-01 13:00:00',
			progress: { done: 9, total: 13, percent: 69 },
		},
		{
			name: 'APP-2026-00013',
			full_name: 'Gandham Vijay Kumar',
			photo: null,
			email: 'vijay@example.invalid',
			mobile: null,
			program: 'MDIV',
			intake_term: null,
			entry_level: null,
			workflow_state: 'In Review',
			application_fee_paid: 0,
			qualifying_exam_score: null,
			student: null,
			creation: '2026-06-14 09:00:00',
			modified: '2026-09-01 13:00:00',
			progress: { done: 2, total: 13, percent: 15 },
		},
	],
	states: ['Draft', 'In Review', 'Admitted'],
	programs: ['MDIV'],
	filters: { state: null, program: null, search: null },
	truncated: false,
}

async function renderList() {
	vi.resetModules()
	Object.assign(window, { user: 'admin@x.com', roles: ['System Manager'], csrf_token: 't' })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: vi.fn(async () => pipeline), frappePost: vi.fn() }
	})

	const { Admissions } = await import('./Admissions')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter initialEntries={['/staff/admissions']}>
				<Admissions />
			</MemoryRouter>
		</QueryClientProvider>,
	)

	await waitFor(() => expect(document.querySelector('[data-slot="skeleton"]')).toBeNull())
}

beforeEach(() => vi.resetModules())
afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

describe('the admissions pipeline', () => {
	it('shows the candidate photograph in the row', async () => {
		// The complaint this answers: the row rendered a name and nothing else.
		await renderList()

		const row = screen.getByText('Beula Patricia').closest('tr') as HTMLElement
		const image = within(row).getByRole('presentation', { hidden: true })
		expect(image).toHaveAttribute('src', '/private/files/APP-2026-00014-photo.jpeg')
	})

	it('falls back to initials for a candidate with no photograph', async () => {
		await renderList()

		const row = screen.getByText('Gandham Vijay Kumar').closest('tr') as HTMLElement
		expect(within(row).queryByRole('presentation', { hidden: true })).toBeNull()
		expect(within(row).getByText('GV')).toBeInTheDocument()
	})
})
