import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { ProfileResponse } from '@/types'

const data: ProfileResponse = {
	user: { name: 'ruth@example.invalid', full_name: 'Ruth Anandhi', user_image: null },
	student: {
		name: 'SIB-2026-0001',
		full_name: 'Ruth Anandhi',
		dob: '1996-04-11',
		gender: 'Female',
		photo: null,
		status: 'Active',
		mobile: '+91 98400 11223',
		whatsapp: '+91 98400 11223',
		email: 'ruth@example.invalid',
		address: '12 Trichy Road',
	},
	enrollment: {
		name: 'SIB-1-MDIV',
		student: 'SIB-2026-0001',
		student_name: 'Ruth Anandhi',
		program: 'MDIV',
		program_name: 'Master of Divinity',
		current_level: '2',
		credits_earned: 5,
		cgpa: 3.4,
		status: 'Active',
	},
	editable: ['mobile', 'whatsapp', 'address'],
}

const post = vi.fn()

async function renderScreen(response: ProfileResponse = data) {
	vi.resetModules()
	Object.assign(window, { user: 'ruth@example.invalid', roles: ['Student'], csrf_token: 't' })
	post.mockReset().mockResolvedValue(response.student)

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: vi.fn(async () => response), frappePost: post }
	})

	const { Profile } = await import('./Profile')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
	render(
		<QueryClientProvider client={client}>
			<Profile />
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

describe('Profile', () => {
	it('lets a student correct how the college reaches them', async () => {
		await renderScreen()
		expect(await screen.findByLabelText('Mobile')).toHaveValue('+91 98400 11223')
		expect(screen.getByLabelText('WhatsApp')).toBeInTheDocument()
		expect(screen.getByLabelText('Address')).toBeInTheDocument()
	})

	it('does not offer name, date of birth or gender as fields', async () => {
		// These are the college record of who someone is. Correcting them is an
		// office procedure, and update_profile refuses them either way.
		await renderScreen()
		await screen.findByLabelText('Mobile')

		for (const label of [/date of birth/i, /gender/i, /^full name$/i, /^email$/i]) {
			expect(screen.queryByLabelText(label)).not.toBeInTheDocument()
		}
		// Still shown, just as read-only record.
		expect(screen.getByText('Female')).toBeInTheDocument()
	})

	it('keeps Save disabled until something actually changes', async () => {
		await renderScreen()
		const save = await screen.findByRole('button', { name: /save changes/i })
		expect(save).toBeDisabled()

		await userEvent.type(screen.getByLabelText('Mobile'), '4')
		expect(save).toBeEnabled()
	})

	it('sends only the three contact fields', async () => {
		await renderScreen()
		await userEvent.type(await screen.findByLabelText('Mobile'), '4')
		await userEvent.click(screen.getByRole('button', { name: /save changes/i }))

		const [method, args] = post.mock.calls[0]
		expect(method).toBe('sibbcs.api.student.update_profile')
		expect(Object.keys(args).sort()).toEqual(['address', 'mobile', 'whatsapp'])
	})

	it('explains an account with no student record', async () => {
		await renderScreen({ ...data, student: null, enrollment: null })
		expect(await screen.findByText(/not linked to a student record yet/i)).toBeInTheDocument()
	})
})
