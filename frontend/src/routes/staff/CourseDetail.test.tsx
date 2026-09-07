import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import type { CourseDetail as CourseDetailData } from '@/types'

const OFFERING = 'THST601-TERM-A'

const base: CourseDetailData = {
	offering: {
		name: OFFERING,
		course: 'THST601',
		course_title: 'Systematic Theology I',
		term: 'TERM-A',
		status: 'Published',
		format: 'Zoom Live',
		instructor: 'INS-00001',
		facilitator: null,
		capacity: 30,
		enrolled_count: 12,
		credits: 3,
		course_level: '1',
		zoom_time: null,
		registered: 12,
		graded: 0,
	},
	scheme: null,
	assignments: [],
	choices: {
		components: ['Assignment', 'Exam', 'Attendance'],
		submission_types: ['Text Entry', 'File Upload'],
		grading_types: ['Points', 'Percentage'],
		late_policies: ['Accept', 'Accept with penalty', 'Refuse'],
		posting_policies: ['Automatic', 'Manual'],
	},
}

const withScheme: CourseDetailData = {
	...base,
	scheme: {
		name: OFFERING,
		total_weight: 100,
		rows: [
			{ component: 'Assignment', weight_pct: 60, drop_lowest: 0, posting_policy: 'Manual' },
			{ component: 'Exam', weight_pct: 40, drop_lowest: 0, posting_policy: 'Manual' },
		],
	},
	assignments: [
		{
			name: 'CA-00001',
			title: 'Essay One',
			component: 'Assignment',
			points_possible: 20,
			submission_type: 'Text Entry',
			grading_type: 'Points',
			due_date: '2026-10-01 23:59:00',
			available_from: null,
			available_until: null,
			late_policy: 'Accept',
			late_penalty_pct_per_day: 0,
			allowed_attempts: 1,
			published: 0,
			description: null,
		},
	],
}

// Typed so that `post.mock.calls[0]` is a real pair rather than an empty
// tuple, which is what a bare `vi.fn(async () => ...)` infers.
const post = vi.fn(async (_path: string, _args?: Record<string, unknown>) => ({}))

async function renderCourse(data: CourseDetailData, at = '') {
	vi.resetModules()
	Object.assign(window, { user: 'faculty@x.com', roles: ['Faculty'], csrf_token: 't' })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: vi.fn(async () => data), frappePost: post }
	})

	const { CourseDetail } = await import('./CourseDetail')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter initialEntries={[`/staff/courses/${OFFERING}${at}`]}>
				<Routes>
					<Route path="/staff/courses/:name" element={<CourseDetail />} />
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

describe('building a course', () => {
	it('will not save a scheme whose weights do not total a hundred', async () => {
		// The server refuses it too. Refusing here as well means the teacher
		// finds out while they are still looking at the numbers.
		await renderCourse(base)

		const weights = screen.getAllByLabelText('Weight %')
		await userEvent.clear(weights[0])
		await userEvent.type(weights[0], '10')

		expect(screen.getByRole('button', { name: /Save scheme/ })).toBeDisabled()
		expect(screen.getByText('70% of 100')).toBeInTheDocument()
	})

	it('saves a scheme that balances', async () => {
		await renderCourse(base)

		const save = screen.getByRole('button', { name: /Save scheme/ })
		expect(save).toBeEnabled()
		expect(screen.getByText('100% of 100')).toBeInTheDocument()

		await userEvent.click(save)

		await waitFor(() => expect(post).toHaveBeenCalled())
		const [path, args] = post.mock.calls[0]
		expect(path).toBe('sibbcs.api.course.save_scheme')
		expect(args?.course_offering).toBe(OFFERING)
	})

	it('opens the section the address names', async () => {
		// The sections are a column now rather than a strip, but they are still
		// addressed by `?tab=` -- and "No assignments set yet, *set one*" is a
		// link to this one.
		await renderCourse(withScheme, '?tab=assignments')

		expect(screen.getByRole('tab', { name: /Assignments/ })).toHaveAttribute(
			'aria-selected',
			'true',
		)
		expect(screen.getByText('Essay One')).toBeInTheDocument()
	})

	it('asks for a grade scheme before it will take an assignment', async () => {
		// A score counting towards a bucket that does not exist reaches
		// nobody's grade.
		await renderCourse(base)

		await userEvent.click(screen.getByRole('tab', { name: /Assignments/ }))

		expect(screen.getByText('Set the grade scheme first')).toBeInTheDocument()
		expect(screen.queryByRole('button', { name: /New assignment/ })).toBeNull()
	})

	it('lists the work once a scheme exists, and says it is not published', async () => {
		await renderCourse(withScheme)

		await userEvent.click(screen.getByRole('tab', { name: /Assignments/ }))

		expect(screen.getByText('Essay One')).toBeInTheDocument()
		expect(screen.getByText('Draft')).toBeInTheDocument()
		expect(screen.getByText(/Assignment · 20 points · Text Entry/)).toBeInTheDocument()
	})

	it('offers only the components the scheme actually has', async () => {
		await renderCourse(withScheme)

		await userEvent.click(screen.getByRole('tab', { name: /Assignments/ }))
		await userEvent.click(screen.getByRole('button', { name: /New assignment/ }))

		const select = screen.getByLabelText('Counts towards')
		const options = Array.from(select.querySelectorAll('option')).map((o) => o.textContent)

		expect(options).toEqual(['Assignment', 'Exam'])
		expect(options).not.toContain('Attendance')
	})

	it('publishes a piece of work from the list, without opening it', async () => {
		await renderCourse(withScheme)

		await userEvent.click(screen.getByRole('tab', { name: /Assignments/ }))
		await userEvent.click(screen.getByRole('button', { name: /Publish/ }))

		await waitFor(() => expect(post).toHaveBeenCalled())
		const [path, args] = post.mock.calls[0]
		expect(path).toBe('sibbcs.api.course.set_published')
		expect(args).toMatchObject({ assignment: 'CA-00001', published: 1 })
	})
})
