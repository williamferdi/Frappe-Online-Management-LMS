import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import type { AttentionCounts } from '@/types'

async function renderNav(counts: AttentionCounts = { documents: 0 }) {
	vi.resetModules()
	Object.assign(window, {
		user: 'officer@x.com',
		roles: ['Admissions Officer'],
		full_name: 'An Officer',
	})

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: vi.fn(async () => counts) }
	})

	const { StaffLayout } = await import('./StaffLayout')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter initialEntries={['/staff']}>
				<Routes>
					<Route path="/staff" element={<StaffLayout />}>
						<Route index element={<div />} />
					</Route>
				</Routes>
			</MemoryRouter>
		</QueryClientProvider>,
	)
}

beforeEach(() => vi.resetModules())
afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

describe('staff console navigation', () => {
	it('badges Admissions when documents are waiting to be checked', async () => {
		await renderNav({ documents: 3 })
		await waitFor(() => {
			expect(screen.getByRole('link', { name: /^Admissions/ })).toHaveTextContent('3')
		})
	})

	it('shows no badge when nothing is waiting, rather than a zero', async () => {
		await renderNav({ documents: 0 })
		await waitFor(() => {
			expect(screen.getByRole('link', { name: /^Admissions/ })).not.toHaveTextContent('0')
		})
	})

	it('badges Admissions and nothing else', async () => {
		await renderNav({ documents: 2 })
		await waitFor(() => {
			expect(screen.getByRole('link', { name: /^Admissions/ })).toHaveTextContent('2')
		})
		expect(screen.getByRole('link', { name: /^Finance/ })).not.toHaveTextContent('2')
		expect(screen.getByRole('link', { name: /^Students/ })).not.toHaveTextContent('2')
	})
})
