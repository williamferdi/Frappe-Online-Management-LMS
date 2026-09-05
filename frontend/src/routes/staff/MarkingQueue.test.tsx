import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import type { MarkingQueue as Queue } from '@/types'

const OFFERING = 'THST601-TERM-A'
const ASSIGNMENT = 'CA-00001'

function submission(overrides: Record<string, unknown> = {}) {
	return {
		name: 'SUB-00001',
		course_registration: 'REG-1',
		student: 'STU-1',
		student_name: 'Beula Patricia',
		attempt: 1,
		status: 'Submitted',
		submitted_on: '2026-10-01 10:00:00',
		late_days: 0,
		excused: 0,
		score: null,
		scored: 0,
		posted: 0,
		feedback: null,
		graded_by: null,
		graded_on: null,
		body: '<p>My essay</p>',
		url: null,
		...overrides,
	}
}

const queue: Queue = {
	assignment: {
		name: ASSIGNMENT,
		title: 'Essay One',
		course_offering: OFFERING,
		component: 'Assignment',
		points_possible: 20,
		due_date: '2026-10-01 23:59:00',
		late_policy: 'Accept',
		late_penalty_pct_per_day: 0,
		submission_type: 'Text Entry',
		published: 1,
		rubric: null,
		description: null,
	},
	rubric: null,
	rows: [
		{
			course_registration: 'REG-1',
			student: 'STU-1',
			student_name: 'Beula Patricia',
			submission: submission(),
			effective_score: null,
		},
		{
			course_registration: 'REG-2',
			student: 'STU-2',
			student_name: 'Gandham Vijay Kumar',
			submission: null,
			effective_score: null,
		},
		{
			course_registration: 'REG-3',
			student: 'STU-3',
			student_name: 'Ruth Demo',
			submission: submission({
				name: 'SUB-00003',
				course_registration: 'REG-3',
				student_name: 'Ruth Demo',
				score: 18,
				scored: 1,
				posted: 0,
			}),
			effective_score: 18,
		},
	],
	ungraded: 1,
	unposted: 1,
	missing: 1,
}

const post = vi.fn(async (_path: string, _args?: Record<string, unknown>) => ({
	changed: 1,
	posted: 1,
}))

async function renderQueue(data: Queue = queue) {
	vi.resetModules()
	Object.assign(window, { user: 'faculty@x.com', roles: ['Faculty'], csrf_token: 't' })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: vi.fn(async () => data), frappePost: post }
	})

	const { MarkingQueue } = await import('./MarkingQueue')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter initialEntries={[`/staff/courses/${OFFERING}/grade/${ASSIGNMENT}`]}>
				<Routes>
					<Route
						path="/staff/courses/:name/grade/:assignment"
						element={<MarkingQueue />}
					/>
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

describe('the marking queue', () => {
	it('says how much is waiting, marked and missing', async () => {
		await renderQueue()

		expect(screen.getByText('1 to mark')).toBeInTheDocument()
		expect(screen.getByText('1 marked, not posted')).toBeInTheDocument()
		expect(screen.getByText('1 nothing handed in')).toBeInTheDocument()
	})

	it('lists a student who handed nothing in, rather than leaving them out', async () => {
		// "Who has not submitted" is the question a marker actually asks.
		await renderQueue()

		const list = screen.getByRole('list')
		expect(within(list).getByText('Gandham Vijay Kumar')).toBeInTheDocument()
		expect(within(list).getByText('missing')).toBeInTheDocument()
	})

	it('shows the work and takes a mark for it', async () => {
		await renderQueue()

		expect(screen.getByText('My essay')).toBeInTheDocument()

		await userEvent.type(screen.getByLabelText(/Score/), '17')
		await userEvent.click(screen.getByRole('button', { name: /^Save$/ }))

		await waitFor(() => expect(post).toHaveBeenCalled())
		const [path, args] = post.mock.calls[0]
		expect(path).toBe('sibbcs.api.marking.grade')
		expect(args).toMatchObject({ course_registration: 'REG-1', score: 17 })
	})

	it('moves to the next student without leaving the page', async () => {
		await renderQueue()

		expect(screen.getByRole('heading', { name: 'Beula Patricia' })).toBeInTheDocument()

		await userEvent.click(screen.getByRole('button', { name: 'Next student' }))

		expect(
			screen.getByRole('heading', { name: 'Gandham Vijay Kumar' }),
		).toBeInTheDocument()
	})

	it('offers to enter a mark for work never handed in', async () => {
		// An offline paper, or a zero for nothing at all.
		await renderQueue()

		await userEvent.click(screen.getByRole('button', { name: 'Next student' }))

		expect(screen.getByText(/Nothing handed in/)).toBeInTheDocument()
		expect(screen.getByLabelText(/Score/)).toBeEnabled()
	})

	it('posts every marked piece at once', async () => {
		await renderQueue()

		await userEvent.click(screen.getByRole('button', { name: /Post all marks/ }))

		await waitFor(() => expect(post).toHaveBeenCalled())
		const [path, args] = post.mock.calls[0]
		expect(path).toBe('sibbcs.api.marking.set_posted')
		expect(args).toMatchObject({ assignment: ASSIGNMENT, posted: 1 })
	})

	it('will not offer to post when nothing is waiting to be posted', async () => {
		await renderQueue({ ...queue, unposted: 0 })

		expect(screen.getByRole('button', { name: /Post all marks/ })).toBeDisabled()
	})

	it('distinguishes a held mark from a posted one', async () => {
		await renderQueue()

		const list = screen.getByRole('list')
		expect(within(list).getByText('marked')).toBeInTheDocument()
		expect(within(list).queryByText('posted')).toBeNull()
	})
})
