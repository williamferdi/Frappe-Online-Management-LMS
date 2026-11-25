import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import type { TuitionResponse, TuitionRow } from '@/types'

const base: TuitionRow = {
	enrollment: 'SIB-2026-0003-M.DIV.',
	student: 'SIB-2026-0003',
	student_name: 'Patricia Example',
	program: 'M.DIV.',
	level: '2',
	state: 'billing',
	monthly: 2166,
	ceiling: 78000,
	billed: 4332,
	remaining: 73668,
	terms_billed: 1,
	scholarship: { monthly: 666, cap: 24000, used: 1332, remaining: 22668 },
}

const atCeiling: TuitionRow = {
	...base,
	enrollment: 'SIB-2026-0009-M.DIV.',
	student: 'SIB-2026-0009',
	student_name: 'Samuel Example',
	state: 'ceiling_reached',
	billed: 77976,
	remaining: 24,
	terms_billed: 18,
	scholarship: { monthly: 1500, cap: 24000, used: 24000, remaining: 0 },
}

async function renderTab(rows: TuitionRow[]) {
	vi.resetModules()
	Object.assign(window, { user: 'accounts@x.invalid', roles: ['Accounts'], csrf_token: 't' })

	const response: TuitionResponse = {
		rows,
		summary: {
			students: rows.length,
			at_ceiling: rows.filter((r) => r.state === 'ceiling_reached').length,
			scholarship_spent: rows.filter((r) => r.scholarship && r.scholarship.remaining <= 0).length,
		},
	}
	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: vi.fn(async () => response), frappePost: vi.fn() }
	})

	const { FinanceTuition } = await import('./FinanceTuition')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
	render(
		<QueryClientProvider client={client}>
			<MemoryRouter>
				<FinanceTuition />
			</MemoryRouter>
		</QueryClientProvider>,
	)
	await waitFor(() => expect(document.querySelector('[data-slot="skeleton"]')).toBeNull())
}

afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

describe('the tuition roster', () => {
	it('says how many students are at the ceiling', async () => {
		await renderTab([atCeiling, base])

		expect(screen.getByText(/2 active students/)).toBeInTheDocument()
		expect(screen.getByText('1 at the ceiling')).toBeInTheDocument()
		expect(screen.getByText(/1 with a scholarship fully used/)).toBeInTheDocument()
	})

	it('marks the student whose billing has stopped, and says nothing alarming about the rest', async () => {
		await renderTab([atCeiling, base])

		const rows = screen.getAllByRole('row').slice(1)
		const samuel = rows.find((row) => within(row).queryByText('Samuel Example'))!
		const patricia = rows.find((row) => within(row).queryByText('Patricia Example'))!

		expect(within(samuel).getByText('Ceiling reached')).toBeInTheDocument()
		expect(within(samuel).getByText(/₹77,976 of ₹78,000/)).toBeInTheDocument()
		expect(within(samuel).getByText('Fully used')).toBeInTheDocument()
		expect(within(patricia).queryByText('Ceiling reached')).not.toBeInTheDocument()
		expect(within(patricia).getByText('Billing')).toBeInTheDocument()
		expect(within(patricia).getByText(/₹4,332 of ₹78,000/)).toBeInTheDocument()
	})

	it('links each student to their own page', async () => {
		await renderTab([base])

		expect(screen.getByRole('link', { name: 'Patricia Example' })).toHaveAttribute(
			'href',
			'/staff/students/SIB-2026-0003',
		)
	})

	it('can narrow to those at the ceiling', async () => {
		await renderTab([atCeiling, base])

		await userEvent.click(screen.getByRole('button', { name: 'At the ceiling only' }))

		expect(screen.getByText('Samuel Example')).toBeInTheDocument()
		expect(screen.queryByText('Patricia Example')).not.toBeInTheDocument()
	})

	it('says so when nobody has reached it', async () => {
		await renderTab([base])

		await userEvent.click(screen.getByRole('button', { name: 'At the ceiling only' }))

		expect(screen.getByText('Nobody has reached the ceiling')).toBeInTheDocument()
	})
})
