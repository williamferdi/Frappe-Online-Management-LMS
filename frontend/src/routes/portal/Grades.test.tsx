import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { GradesResponse } from '@/types'

const data: GradesResponse = {
	enrollment: {
		name: 'SIB-1-MDIV',
		student: 'SIB-1',
		student_name: 'Ruth Anandhi',
		program: 'MDIV',
		program_name: 'Master of Divinity',
		current_level: '2',
		credits_earned: 5,
		cgpa: 3.4,
		status: 'Active',
	},
	terms: [
		{
			term: 'T-A',
			term_name: 'Term A',
			start_date: '2026-01-01',
			credits: 5,
			rows: [
				{
					name: 'REG-1',
					course: 'GEST501',
					course_title: 'Orientation to Online Study',
					term: 'T-A',
					status: 'Completed',
					credits: 3,
					final_marks: 85.6,
					grade: 'B',
					grade_points: 3,
					passed: 1,
					level_at_registration: '1',
					components: [
						{
							parent: 'REG-1',
							component: 'Assignment',
							weight_pct: 40,
							max_marks: 100,
							obtained_marks: 88,
							weighted_score: 35.2,
							idx: 1,
						},
						{
							parent: 'REG-1',
							component: 'Final Paper',
							weight_pct: 60,
							max_marks: 100,
							obtained_marks: 84,
							weighted_score: 50.4,
							idx: 2,
						},
					],
				},
			],
		},
	],
	scale: {
		name: 'Scale',
		scale_name: 'SIBBCS Grade Scale',
		pass_percentage: 60,
		rows: [
			{ grade: 'A', min_pct: 90, max_pct: 100, grade_points: 4, is_pass: 1 },
			{ grade: 'F', min_pct: 0, max_pct: 59.99, grade_points: 0, is_pass: 0 },
		],
	},
}

async function renderScreen(response: GradesResponse = data) {
	vi.resetModules()
	Object.assign(window, { user: 's@x.com', roles: ['Student'], csrf_token: 't' })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: vi.fn(async () => response) }
	})

	const { Grades } = await import('./Grades')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
	render(
		<QueryClientProvider client={client}>
			<Grades />
		</QueryClientProvider>,
	)
	// QueryState paints the page heading during loading too, so waiting on
	// the heading proves nothing about the data. Wait for the skeletons to go.
	await waitFor(() =>
		expect(document.querySelector('[data-slot="skeleton"]')).toBeNull(),
	)
}

beforeEach(() => vi.resetModules())
afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

describe('Grades', () => {
	it('shows the grade and the marks behind it', async () => {
		await renderScreen()
		expect(await screen.findByText('B')).toBeInTheDocument()
		expect(screen.getByText('85.6')).toBeInTheDocument()
	})

	it('keeps the components one click away, not one email away', async () => {
		// Why a grade came out a B is answerable from the weighted components,
		// so they sit under the row rather than behind a mail to the office.
		await renderScreen()
		expect(screen.queryByText('Assignment')).not.toBeInTheDocument()

		await userEvent.click(screen.getByText('Orientation to Online Study'))

		expect(await screen.findByText('Assignment')).toBeInTheDocument()
		expect(screen.getByText('88 / 100')).toBeInTheDocument()
		expect(screen.getByText('35.2')).toBeInTheDocument()
	})

	it('shows the scale, so a letter means something', async () => {
		await renderScreen()
		expect(await screen.findByText('SIBBCS Grade Scale')).toBeInTheDocument()
		expect(screen.getByText('90–100%')).toBeInTheDocument()
		expect(screen.getByText('Pass mark 60%.')).toBeInTheDocument()
	})

	it('says there are no grades yet rather than showing an empty table', async () => {
		await renderScreen({ ...data, terms: [] })
		expect(await screen.findByText('No grades yet')).toBeInTheDocument()
	})
})
