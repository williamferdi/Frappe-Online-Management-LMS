import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import type { GroupSetsResponse } from '@/types'

const OFFERING = 'THST601-TERM-A'

const data: GroupSetsResponse = {
	sets: [
		{
			name: 'CGS-00001',
			title: 'Seminar groups',
			self_signup: 0,
			group_limit: 3,
			groups: [
				{
					name: 'CGR-00001',
					title: 'Group 1',
					position: 0,
					members: [{ course_registration: 'REG-1', student_name: 'Beula Patricia' }],
				},
			],
		},
	],
	roster: [
		{ name: 'REG-1', student_name: 'Beula Patricia' },
		{ name: 'REG-2', student_name: 'Gandham Vijay Kumar' },
		{ name: 'REG-3', student_name: 'Ruth Demo' },
	],
}

const post = vi.fn(async (_path: string, _args?: Record<string, unknown>) => ({}))

async function renderGroups(payload: GroupSetsResponse = data) {
	vi.resetModules()
	Object.assign(window, { user: 'faculty@x.com', roles: ['Faculty'], csrf_token: 't' })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: vi.fn(async () => payload), frappePost: post }
	})

	const { Groups } = await import('./Groups')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter>
				<Groups offering={OFFERING} />
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

describe('group sets', () => {
	it('shows each set with its groups and who is in them', async () => {
		await renderGroups()

		expect(screen.getByText('Seminar groups')).toBeInTheDocument()
		expect(screen.getByText('Group 1')).toBeInTheDocument()
		expect(screen.getByText('Beula Patricia')).toBeInTheDocument()
		expect(screen.getByText('max 3')).toBeInTheDocument()
	})

	it('counts who is not in a group yet', async () => {
		await renderGroups()

		expect(screen.getByText('2 not in a group')).toBeInTheDocument()
	})

	it('offers only students who are not already in a group of that set', async () => {
		// A set is a partition. The picker must not offer somebody the server
		// would refuse.
		await renderGroups()

		await userEvent.click(screen.getByRole('button', { name: /Group$/ }))

		const members = screen.getByRole('group', { name: 'Members' })
		expect(members).toHaveTextContent('Gandham Vijay Kumar')
		expect(members).toHaveTextContent('Ruth Demo')
		expect(members).not.toHaveTextContent('Beula Patricia')
	})

	it('creates a group with the members that were ticked', async () => {
		await renderGroups()

		await userEvent.click(screen.getByRole('button', { name: /Group$/ }))
		await userEvent.click(screen.getByLabelText('Ruth Demo'))
		await userEvent.click(screen.getByRole('button', { name: 'Create' }))

		await waitFor(() => expect(post).toHaveBeenCalled())
		const [path, args] = post.mock.calls[0]
		expect(path).toBe('sibbcs.api.collaboration.save_group')
		expect(args).toMatchObject({ group_set: 'CGS-00001', members: ['REG-3'] })
	})

	it('says what a group set is for when there are none', async () => {
		await renderGroups({ sets: [], roster: data.roster })

		expect(screen.getByText('No groups yet')).toBeInTheDocument()
		expect(screen.getByText(/can carry its own deadlines/)).toBeInTheDocument()
	})

	it('says so when everybody is already placed', async () => {
		await renderGroups({
			sets: [
				{
					...data.sets[0],
					groups: [
						{
							name: 'CGR-00001',
							title: 'Group 1',
							position: 0,
							members: data.roster.map((row) => ({
								course_registration: row.name,
								student_name: row.student_name,
							})),
						},
					],
				},
			],
			roster: data.roster,
		})

		await userEvent.click(screen.getByRole('button', { name: /Group$/ }))
		expect(screen.getByText(/already in a group of this set/)).toBeInTheDocument()
	})
})
