import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import type { MyCoursesResponse, Registration } from '@/types'

const paid: Registration = {
	name: 'REG-1',
	course: 'BIST502',
	course_title: 'Introduction to the Old Testament',
	term: '2026-T1',
	status: 'Registered',
	credits: 3,
	grade: null,
	final_marks: null,
	passed: 0,
	lms_enrollment_created: 1,
	registration_fee_invoice: 'FEE-1',
	fee: { invoice: 'FEE-1', status: 'Paid', outstanding: 0, settled: true, label: 'Paid' },
	lms_course: 'intro-to-ot',
	lms_url: 'https://lms.example.invalid',
	progress: 42,
}

const unpaid: Registration = {
	...paid,
	name: 'REG-2',
	course: 'THST601',
	course_title: 'Systematic Theology I',
	lms_enrollment_created: 0,
	fee: {
		invoice: 'FEE-2',
		status: 'Unpaid',
		outstanding: 350,
		payment_link: 'https://pay.example/abc',
		settled: false,
		label: 'Payment pending',
	},
	lms_course: null,
	lms_url: null,
	progress: 0,
}

const enrollment = {
	name: 'SIB-2026-0001-MDIV',
	student: 'SIB-2026-0001',
	student_name: 'A Student',
	program: 'MDIV',
	program_name: 'Master of Divinity',
	current_level: '2',
	credits_earned: 18,
	cgpa: 3.4,
	status: 'Active',
}

type Screen = MyCoursesResponse | { failWith: string; status?: number }

async function renderScreen(response: Screen) {
	vi.resetModules()
	Object.assign(window, { user: 's@x.com', roles: ['Student'], csrf_token: 't' })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		const failure =
			'failWith' in response
				? new actual.FrappeError(response.failWith, response.status ?? 417)
				: null
		return {
			...actual,
			frappeGet: vi.fn(() =>
				failure ? Promise.reject(failure) : Promise.resolve(response),
			),
		}
	})

	const { MyCourses } = await import('./MyCourses')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<MemoryRouter>
			<QueryClientProvider client={client}>
				<MyCourses />
			</QueryClientProvider>
		</MemoryRouter>,
	)
	return screen.findByRole('heading', { name: 'My Courses' })
}

beforeEach(() => vi.resetModules())
afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

describe('My Courses', () => {
	it('shows the enrolment summary', async () => {
		await renderScreen({ enrollment, registrations: [paid] })

		expect(await screen.findByText('Master of Divinity · Level 2')).toBeInTheDocument()
		expect(screen.getByText('18')).toBeInTheDocument()
		expect(screen.getByText('3.40')).toBeInTheDocument()
	})

	it('sends the student to the learning site, which is where teaching happens', async () => {
		// Phase 7 moved lessons, coursework and quizzes to Campus LMS Lite, so
		// the three ways in became one. It opens the LMS itself rather than a
		// course address: the registration number means nothing over there.
		await renderScreen({ enrollment, registrations: [paid] })

		const link = await screen.findByRole('link', { name: /open course/i })
		expect(link).toHaveAttribute('href', 'https://lms.example.invalid')
	})

	it('says so plainly when the learning site is not linked yet', async () => {
		// Better than a button that goes nowhere, which reads as a fault.
		await renderScreen({
			enrollment,
			registrations: [{ ...paid, lms_url: null }],
		})

		expect(await screen.findByText(/not linked yet/i)).toBeInTheDocument()
		expect(screen.queryByRole('link', { name: /open course/i })).toBeNull()
	})
	it('asks for payment instead of a course link when the fee is outstanding', async () => {
		// The course opens on payment. Showing "Open course" here is the reason
		// students email to ask why the link does nothing.
		await renderScreen({ enrollment, registrations: [unpaid] })

		expect(await screen.findByRole('link', { name: /pay now/i })).toHaveAttribute(
			'href',
			'https://pay.example/abc',
		)
		// Neither half is offered while the fee is outstanding: the course is
		// closed, not half open.
		expect(screen.queryByRole('link', { name: /open course/i })).not.toBeInTheDocument()
		expect(screen.queryByRole('link', { name: /coursework/i })).not.toBeInTheDocument()
		expect(screen.queryByRole('link', { name: /in the lms/i })).not.toBeInTheDocument()
	})

	it('totals what is outstanding across registrations', async () => {
		await renderScreen({ enrollment, registrations: [paid, unpaid] })
		const card = (await screen.findByText('Outstanding')).parentElement
		expect(card).toHaveTextContent('₹350')
		// Once in the summary, once on the row that owes it.
		expect(screen.getAllByText('₹350')).toHaveLength(2)
	})

	it('explains an account with no enrolment rather than showing an empty table', async () => {
		await renderScreen({ enrollment: null, registrations: [] })
		expect(await screen.findByText('No active enrollment')).toBeInTheDocument()
	})

	it('tells an enrolled student with nothing registered what happens next', async () => {
		await renderScreen({ enrollment, registrations: [] })
		expect(await screen.findByText('No registrations yet')).toBeInTheDocument()
	})

	it('surfaces the server message when the call fails', async () => {
		await renderScreen({ failWith: 'Your enrolment is not active.' })
		expect(await screen.findByText('Your enrolment is not active.')).toBeInTheDocument()
	})

	it('draws no progress bar, because this screen no longer knows the figure', async () => {
		// Reading it meant a call per course to a system 265ms away, on a
		// screen that draws every registration a student has. The LMS shows
		// progress on the course itself.
		await renderScreen({ enrollment, registrations: [paid] })

		await screen.findByRole('link', { name: /open course/i })
		expect(screen.queryByRole('progressbar')).toBeNull()
	})
})
