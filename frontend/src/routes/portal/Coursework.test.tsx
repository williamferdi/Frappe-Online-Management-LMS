import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

function response(overrides: Partial<CourseworkResponse['rows'][0]> = {}): CourseworkResponse {
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

const post = vi.fn(async (_path: string, _args?: Record<string, unknown>) => ({}))

async function renderWork(data: CourseworkResponse, at = '') {
	vi.resetModules()
	Object.assign(window, { user: 'student@x.com', roles: ['Student'], csrf_token: 't' })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: vi.fn(async () => data), frappePost: post }
	})

	const { Coursework } = await import('./Coursework')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter initialEntries={[`/portal/courses/${REGISTRATION}/work${at}`]}>
				<Routes>
					<Route path="/portal/courses/:name/work" element={<Coursework />} />
				</Routes>
			</MemoryRouter>
		</QueryClientProvider>,
	)

	await waitFor(() => expect(document.querySelector('[data-slot="skeleton"]')).toBeNull())
}

beforeEach(() => {
	vi.resetModules()
	post.mockClear()
})
afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

describe('a student looking at their coursework', () => {
	it('says when it is due, what it is worth and how it goes in', async () => {
		// Three facts read separately: somebody checking a deadline is not
		// reading about the submission type on the way past.
		await renderWork(response())

		expect(screen.getByText('Due')).toBeInTheDocument()
		expect(screen.getByText('Points')).toBeInTheDocument()
		expect(screen.getByText('Submitting')).toBeInTheDocument()
		// The field spells it "Text Entry"; a student is handing in a text box.
		expect(screen.getByText('a text box')).toBeInTheDocument()
	})

	it('opens the assignment it was sent to, not just the list holding it', async () => {
		// The player's "Hand it in" used to land on the whole list, leaving
		// somebody to find again the assignment they had just clicked.
		const data = response()
		const asked = data.rows[0].assignment.name

		await renderWork(data, `?assignment=${asked}`)

		expect(await screen.findByLabelText('Your answer')).toBeInTheDocument()
	})

	it('hands work in', async () => {
		await renderWork(response())

		await userEvent.click(screen.getByRole('button', { name: 'Hand in' }))
		await userEvent.type(screen.getByLabelText('Your answer'), 'In the beginning')
		await userEvent.click(screen.getByRole('button', { name: /Hand in/ }))

		await waitFor(() => expect(post).toHaveBeenCalled())
		const [path, args] = post.mock.calls[0]
		expect(path).toBe('sibbcs.api.coursework.submit')
		expect(args).toMatchObject({
			course_registration: REGISTRATION,
			assignment: 'CA-00001',
		})
	})

	it('says work is in but not yet marked', async () => {
		// The score is absent from the payload, not hidden here -- so there is
		// nothing for the page to leak.
		await renderWork(
			response({
				submission: {
					name: 'SUB-1',
					attempt: 1,
					status: 'Submitted',
					submitted_on: '2026-09-30 12:00:00',
					late_days: 0,
					excused: 0,
					body: 'In the beginning',
					url: null,
					posted: 0,
				},
			}),
		)

		expect(screen.getByText('Handed in')).toBeInTheDocument()
		expect(screen.getByText(/Not marked yet/)).toBeInTheDocument()
		expect(screen.queryByText(/\/ 20/)).toBeNull()
	})

	it('shows the mark and the feedback once they are posted', async () => {
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
					feedback: '<p>Well argued.</p>',
				},
			}),
		)

		expect(screen.getByText('17 / 20')).toBeInTheDocument()
		expect(screen.getByText('Well argued.')).toBeInTheDocument()
	})

	it('explains why a closed assignment cannot be handed in', async () => {
		await renderWork(
			response({ open: { open: false, reason: 'This has closed.' } }),
		)

		expect(screen.getByText('This has closed.')).toBeInTheDocument()
		expect(screen.queryByRole('button', { name: 'Hand in' })).toBeNull()
	})

	it('warns about a late penalty before the work is sent', async () => {
		await renderWork(
			response({
				open: { open: true, reason: 'This is late. 10% is deducted for each day.' },
			}),
		)

		expect(screen.getByText(/10% is deducted for each day/)).toBeInTheDocument()
		expect(screen.getByRole('button', { name: 'Hand in' })).toBeInTheDocument()
	})
})
