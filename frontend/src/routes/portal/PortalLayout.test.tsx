import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import type { UnreadCounts } from '@/types'

/** The college specified this list and this order. Pin it. */
const EXPECTED = [
	'Dashboard',
	'My Courses',
	'To Do',
	'Calendar',
	'Inbox',
	'Grades',
	'Discussions',
	'Announcements',
	'Profile',
]

async function renderNav(counts: UnreadCounts = { announcements: 0, inbox: 0 }) {
	vi.resetModules()
	Object.assign(window, { user: 's@x.com', roles: ['Student'], full_name: 'A Student' })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: vi.fn(async () => counts) }
	})

	const { PortalLayout } = await import('./PortalLayout')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter initialEntries={['/portal']}>
				<Routes>
					<Route path="/portal" element={<PortalLayout />}>
						<Route index element={<div />} />
					</Route>
				</Routes>
			</MemoryRouter>
		</QueryClientProvider>,
	)
}

function navLabels() {
	return screen
		.getAllByRole('link')
		.map((link) => link.textContent?.trim())
		.map((label) => EXPECTED.find((name) => label?.startsWith(name)))
		.filter(Boolean)
}

beforeEach(() => vi.resetModules())
afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

describe('student portal navigation', () => {
	it('offers the nine sections the college asked for, in order', async () => {
		await renderNav()
		expect(navLabels()).toEqual(EXPECTED)
	})

	it('badges Inbox and Announcements when something is unread', async () => {
		await renderNav({ announcements: 2, inbox: 5 })

		await waitFor(() => {
			expect(screen.getByRole('link', { name: /^Inbox/ })).toHaveTextContent('5')
		})
		expect(screen.getByRole('link', { name: /^Announcements/ })).toHaveTextContent('2')
	})

	it('shows no badge at zero, rather than a zero', async () => {
		await renderNav({ announcements: 0, inbox: 0 })
		await waitFor(() => {
			expect(screen.getByRole('link', { name: /^Inbox/ })).not.toHaveTextContent('0')
		})
	})
})
