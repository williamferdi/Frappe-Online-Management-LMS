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
	choices: {
		components: ['Assignment', 'Exam', 'Attendance'],
		posting_policies: ['Automatic', 'Manual'],
	},
}


// Typed so that `post.mock.calls[0]` is a real pair rather than an empty
// tuple, which is what a bare `vi.fn(async () => ...)` infers.
const post = vi.fn(async (_path: string, _args?: Record<string, unknown>) => ({}))

async function renderCourse(data: CourseDetailData, at = '') {
	vi.resetModules()
	Object.assign(window, { user: 'faculty@x.com', roles: ['Faculty'], csrf_token: 't' })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return {
			...actual,
			frappeGet: vi.fn(async () => data),
			frappePost: post,
		}
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
})
