import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import type { Offering, RegistrationOptions } from '@/types'

const open: Offering = {
	name: 'BIST502-T1',
	course: 'BIST502',
	course_title: 'Introduction to the Old Testament',
	term: '2026-T1',
	format: 'Zoom Live',
	capacity: 25,
	enrolled_count: 20,
	zoom_time: '18:30:00',
	credits: 3,
	course_level: '1',
	already_registered: false,
	eligibility: { allowed: true, reason: null, code: null, needs_override: false, hard: false, warnings: [] },
}

const blocked: Offering = {
	...open,
	name: 'THST701-T1',
	course: 'THST701',
	course_title: 'Advanced Theology Seminar',
	course_level: '4',
	eligibility: {
		allowed: false,
		reason: 'THST701 is a Level 4 course and you are at Level 2.',
		code: 'level',
		needs_override: true,
		hard: false,
		warnings: [],
	},
}

const options: RegistrationOptions = {
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
			term: '2026-T1',
			term_name: '2026-T1',
			start_date: '2026-09-01',
			end_date: '2026-11-01',
			registration_closes: '2026-09-20',
			rows: [open, blocked],
			eligible_count: 1,
		},
	],
}

const post = vi.fn()

async function renderScreen(data: RegistrationOptions = options) {
	vi.resetModules()
	Object.assign(window, { user: 's@x.com', roles: ['Student'], csrf_token: 't' })
	post.mockReset().mockResolvedValue({ registration: 'REG-9', lms_ready: false })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: vi.fn(async () => data), frappePost: post }
	})

	const { Register } = await import('./Register')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<MemoryRouter>
			<QueryClientProvider client={client}>
				<Register />
			</QueryClientProvider>
		</MemoryRouter>,
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

/**
 * The offering card for one course.
 *
 * Anchored on the card border rather than on flex classes: the badges
 * directly around the course code are themselves a `flex flex-wrap` div, so
 * climbing to the nearest one of those finds a row with no button in it.
 */
function rowFor(course: string) {
	const card = screen.getByText(course).closest('div.rounded-lg.border')
	if (!card) throw new Error(`no offering card found for ${course}`)
	return card as HTMLElement
}

describe('registering for a course', () => {
	it('says why a course is unavailable instead of hiding it', async () => {
		// Hiding blocked courses is what turns "why can't I take this?" into an
		// email to the Registrar, one student at a time.
		await renderScreen()
		expect(
			await screen.findByText('THST701 is a Level 4 course and you are at Level 2.'),
		).toBeInTheDocument()
	})

	it('disables the button on a course the rules refuse', async () => {
		await renderScreen()
		const row = rowFor('THST701')
		expect(within(row).getByRole('button', { name: /unavailable/i })).toBeDisabled()
	})

	it('offers a course the student may take', async () => {
		await renderScreen()
		const row = rowFor('BIST502')
		expect(within(row).getByRole('button', { name: /^register$/i })).toBeEnabled()
	})

	it('asks before registering, and does not register until confirmed', async () => {
		// Registering raises a fee, so it must never happen on a stray click.
		await renderScreen()
		await userEvent.click(within(rowFor('BIST502')).getByRole('button', { name: /^register$/i }))

		expect(await screen.findByRole('dialog')).toBeInTheDocument()
		expect(post).not.toHaveBeenCalled()

		await userEvent.click(screen.getByRole('button', { name: /confirm registration/i }))
		expect(post).toHaveBeenCalledWith('sibbcs.academic.portal.register', {
			course_offering: 'BIST502-T1',
		})
	})

	it('sends no override flag, whatever the reason given', async () => {
		// The student endpoint deliberately has no override parameter; a
		// cross-level exception is the Registrar's to grant, not a form field.
		await renderScreen()
		await userEvent.click(within(rowFor('BIST502')).getByRole('button', { name: /^register$/i }))
		await userEvent.click(screen.getByRole('button', { name: /confirm registration/i }))

		const [, args] = post.mock.calls[0]
		expect(Object.keys(args)).toEqual(['course_offering'])
	})

	it('warns that the fee decides when the course opens', async () => {
		await renderScreen()
		await userEvent.click(within(rowFor('BIST502')).getByRole('button', { name: /^register$/i }))
		expect(
			await screen.findByText(/opens in the learning system once that fee is settled/i),
		).toBeInTheDocument()
	})

	it('explains a closed registration period rather than showing nothing', async () => {
		await renderScreen({ ...options, terms: [] })
		expect(await screen.findByText('Registration is closed')).toBeInTheDocument()
	})
})
