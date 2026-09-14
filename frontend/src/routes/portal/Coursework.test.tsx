import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import type { CourseworkResponse } from '@/types'

const REGISTRATION = 'REG-1'

const assignment = {
	name: 'CA-00001',
	title: 'Essay One',
	description: '<p>Write about Genesis.</p>',
	component: 'Assignment',
	points_possible: 20,
	grading_type: 'Points',
	submission_type: 'Text Entry',
	due_date: '2026-10-01 23:59:00',
	available_from: null,
	available_until: null,
	late_policy: 'Accept',
	late_penalty_pct_per_day: 0,
	allowed_attempts: 1,
}

function response(
	overrides: Partial<CourseworkResponse['rows'][0]> = {},
): CourseworkResponse {
	return {
		registration: {
			name: REGISTRATION,
			course_title: 'Systematic Theology I',
			course_offering: 'THST601-TERM-A',
			status: 'Active',
		},
		rows: [
			{
				assignment,
				submission: null,
				open: { open: true, reason: null },
				...overrides,
			},
		],
	}
}

async function renderWork(data: CourseworkResponse) {
	vi.resetModules()
	Object.assign(window, { user: 'student@x.com', roles: ['Student'], csrf_token: 't' })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: vi.fn(async () => data), frappePost: vi.fn() }
	})

	const { Coursework } = await import('./Coursework')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter initialEntries={[`/portal/courses/${REGISTRATION}/work`]}>
				<Routes>
					<Route path="/portal/courses/:name/work" element={<Coursework />} />
				</Routes>
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

describe('a student looking at their coursework', () => {
	it('lists each piece with when it is due and what it is worth', async () => {
		await renderWork(response())

		// Asserted on the row rather than by text: the points and the year both
		// contain "20", so a loose matcher finds two things and fails.
		const row = screen.getByRole('link', { name: /Essay One/ })
		expect(row).toHaveTextContent('Due 2026-10-01 23:59')
		expect(row).toHaveTextContent('20 points')
	})

	it('sends each piece to its own page rather than opening it here', async () => {
		// The instructions, the submission and the mark live on the piece's own
		// page. A form per row meant a dozen forms nobody asked for, and gave
		// the same work two places it could be handed in from.
		await renderWork(response())

		expect(screen.getByRole('link', { name: /Essay One/ })).toHaveAttribute(
			'href',
			`/portal/courses/${REGISTRATION}/work/CA-00001`,
		)
		expect(screen.queryByRole('button', { name: 'Hand in' })).toBeNull()
	})

	it('says at a glance what has happened to each piece', async () => {
		await renderWork(
			response({
				submission: {
					name: 'SUB-1',
					attempt: 1,
					status: 'Returned',
					submitted_on: '2026-09-30 12:00:00',
					late_days: 0,
					excused: 0,
					body: 'In the beginning',
					url: null,
					posted: 1,
					score: 17,
				},
			}),
		)

		expect(screen.getByText('17 / 20')).toBeInTheDocument()
	})

	it('shows the start of each brief under its row', async () => {
		await renderWork(response())

		const row = screen.getByRole('link', { name: /Essay One/ })
		expect(row).toHaveTextContent('Write about Genesis.')
		// Heard as the link's description, not as part of its name.
		expect(row).toHaveAccessibleDescription('Write about Genesis.')
		expect(row).not.toHaveAccessibleName(/Genesis/)
	})

	it('adds no line for a piece with no brief', async () => {
		await renderWork(response({ assignment: { ...assignment, description: null } }))

		const row = screen.getByRole('link', { name: /Essay One/ })
		expect(row).not.toHaveTextContent('Genesis')
		expect(row).not.toHaveAttribute('aria-describedby')
	})

	it('says when nothing is set yet', async () => {
		await renderWork({ ...response(), rows: [] })

		expect(screen.getByText('Nothing set yet')).toBeInTheDocument()
	})
})
