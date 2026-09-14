import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import type { GradebookGrid } from '@/types'

const OFFERING = 'THST601-TERM-A'

const assignment = {
	name: 'CA-00001',
	title: 'Essay One',
	component: 'Assignment',
	points_possible: 20,
	due_date: '2026-10-01 23:59:00',
	published: 1,
	description: null as string | null,
}

function student(index: number, name: string | null) {
	return {
		course_registration: `REG-${index}`,
		student_name: name,
		final_marks: 15,
		marks_complete: true,
		grade: 'B',
		passed: 1,
		cells: {
			'CA-00001': {
				name: `SUB-${index}`,
				score: 15,
				scored: 1,
				posted: 1,
				excused: 0,
			},
		},
	}
}

function grid(
	names: (string | null)[],
	over: Partial<typeof assignment> = {},
): GradebookGrid {
	return {
		assignments: [{ ...assignment, ...over }],
		rows: names.map((name, index) => student(index, name)),
		scheme: [{ component: 'Assignment', weight_pct: 100, posting_policy: 'Manual' }],
	} as unknown as GradebookGrid
}

async function renderGradebook(data: GradebookGrid) {
	vi.resetModules()
	Object.assign(window, { user: 'faculty@x.com', roles: ['Faculty'], csrf_token: 't' })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: vi.fn(async () => data), frappePost: vi.fn() }
	})

	const { Gradebook } = await import('./Gradebook')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter>
				<Gradebook offering={OFFERING} />
			</MemoryRouter>
		</QueryClientProvider>,
	)

	await waitFor(() => expect(document.querySelector('[data-slot="skeleton"]')).toBeNull())
}

const bodyRows = () =>
	within(screen.getByRole('table')).getAllByRole('row').slice(1) // minus the header

beforeEach(() => vi.resetModules())
afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

describe('what an assignment asked for', () => {
	const brief = '<p>Write <strong>1500 words</strong> on Romans 8.</p>'

	it('shows the description as hover text on its column', async () => {
		await renderGradebook(grid(['Ruth Demo'], { description: brief }))

		expect(screen.getByRole('button', { name: 'About Essay One' })).toHaveAttribute(
			'title',
			'Write 1500 words on Romans 8.',
		)
	})

	it('opens it in full, formatting and all, on a click or tap', async () => {
		await renderGradebook(grid(['Ruth Demo'], { description: brief }))

		await userEvent.click(screen.getByRole('button', { name: 'About Essay One' }))

		const dialog = await screen.findByRole('dialog', { name: 'Essay One' })
		expect(within(dialog).getByText('1500 words').tagName).toBe('STRONG')
	})

	it('offers nothing for an assignment without one', async () => {
		await renderGradebook(grid(['Ruth Demo']))

		expect(screen.queryByRole('button', { name: /About/ })).toBeNull()
		expect(screen.getByRole('link', { name: /Essay One/ })).toBeInTheDocument()
	})
})

describe('the class against the work', () => {
	it('lists a row per student', async () => {
		await renderGradebook(grid(['Beula Patricia', 'Ruth Demo', 'Vignesh Kumar']))

		expect(bodyRows()).toHaveLength(3)
		expect(screen.getByText('Vignesh Kumar')).toBeInTheDocument()
	})

	it('narrows to one student, and says that it has', async () => {
		// A filtered table that looks like a whole table is a trap.
		await renderGradebook(grid(['Beula Patricia', 'Ruth Demo', 'Vignesh Kumar']))

		await userEvent.click(screen.getByRole('combobox', { name: 'Find' }))
		await userEvent.type(screen.getByRole('combobox', { name: 'Find' }), 'kumar')
		await userEvent.click(screen.getByRole('option', { name: /Vignesh Kumar/ }))

		expect(bodyRows()).toHaveLength(1)
		expect(screen.getByText('Showing 1 of 3 students.')).toBeInTheDocument()
	})

	it('gives everybody back', async () => {
		await renderGradebook(grid(['Beula Patricia', 'Ruth Demo', 'Vignesh Kumar']))

		const find = screen.getByRole('combobox', { name: 'Find' })
		await userEvent.click(find)
		await userEvent.click(screen.getByRole('option', { name: /Ruth Demo/ }))
		expect(bodyRows()).toHaveLength(1)

		await userEvent.click(find)
		await userEvent.click(screen.getByRole('option', { name: /Everyone/ }))

		expect(bodyRows()).toHaveLength(3)
		expect(screen.queryByText(/Showing 1 of/)).toBeNull()
	})

	it('does not offer a search of one student', async () => {
		await renderGradebook(grid(['Beula Patricia']))

		expect(screen.queryByRole('combobox', { name: 'Find' })).toBeNull()
		expect(bodyRows()).toHaveLength(1)
	})

	it('says nobody is registered rather than drawing an empty grid', async () => {
		await renderGradebook(grid([]))

		expect(screen.getByText('Nobody is registered')).toBeInTheDocument()
		expect(screen.queryByRole('table')).toBeNull()
	})
})
