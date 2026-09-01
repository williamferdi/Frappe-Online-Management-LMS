import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import type { StudentDetail as Detail } from '@/types'

const MENTOR_HTML =
	'<table><tr><td>How long have you known the applicant?</td><td><b>More than 6 years</b></td></tr></table>'

const detail: Detail = {
	student: {
		name: 'SIB-2026-0007',
		full_name: 'Chettebathula Anil Kumar',
		email: 'anil@example.invalid',
		mobile: '+91 93900 70957',
		whatsapp: null,
		dob: '1998-06-10',
		gender: 'Male',
		status: 'Active',
		photo: null,
		address: 'Jaggampeta, Andhra Pradesh',
		user: 'anil@example.invalid',
		admission_application: 'APP-2026-00011',
	},
	enrollment: {
		name: 'ENR-0007',
		student: 'SIB-2026-0007',
		program: 'MDIV',
		current_level: '1',
		status: 'Active',
		credits_earned: 6,
		cgpa: 3.4,
		enrollment_date: '2026-06-20',
		expected_completion: null,
		start_term: 'Term 1 2026',
	},
	registrations: [],
	invoices: [],
	promotions: [],
	admission: {
		application: {
			name: 'APP-2026-00011',
			creation: '2026-06-13 09:00:00',
			workflow_state: 'Admitted',
			program: 'MDIV',
			intake_term: 'Term 1 2026',
			entry_level: '1',
			age: 28,
			photo: null,
			church_name: 'New Life Church',
			current_role: 'Assistant pastor',
			years_of_ministry: 2,
			has_bachelors: 1,
			previous_theological_education: null,
			mother_tongue: 'Telugu',
			nationality: 'Indian',
			church_denomination: 'Independent',
			salvation_status: 'I am Saved',
			baptism_status: 'Baptised',
			sense_of_call: 'Yes, clearly',
			ata_eligible: 1,
			mature_candidate: 0,
			transfer_student: 0,
			education_sequence_mismatch: 0,
			whatsapp_groups: 'Awaiting',
			theological_writing_status: 'Waiting For Payment',
			ssc_status: 'Completed',
			ssc_year: '2014',
			hslc_status: 'Completed',
			hslc_year: '2016',
			ug_status: 'Pursuing',
			ug_year: '2026',
			id_document: null,
			ministry_experience_doc: null,
			application_fee_paid: 1,
			docs_verified: 1,
			qualifying_exam_score: 78,
			interview_outcome: 'Attended & Passed',
			offer_sent_on: '2026-06-18',
			admission_fee_paid: 0,
			onboard_term: 'Term 1 2026',
			onboard_level: '1',
			enrolled_on: '2026-06-20 10:00:00',
			applicant_user: 'anil@example.invalid',
			scholarship_request: null,
		},
		checklist: {
			application: 'APP-2026-00011',
			state: 'Admitted',
			progress: 62,
			can_write: true,
			rows: [
				{
					step_no: 1,
					step: 'Full Application Review',
					status: 'Approved',
					statuses: ['Under Review', 'Approved'],
					owner_role: 'Admissions Officer',
					done: true,
					done_statuses: ['Approved'],
					blocked: null,
					remarks: null,
					updated_by: null,
					updated_on: null,
					action: null,
				},
				{
					step_no: 13,
					step: 'Onboarding Status',
					status: 'Awaiting Onboarding',
					statuses: ['Awaiting Onboarding', 'Onboarded'],
					owner_role: 'Registrar',
					done: false,
					done_statuses: ['Onboarded'],
					blocked: null,
					remarks: null,
					updated_by: null,
					updated_on: null,
					action: 'onboard_student',
				},
			],
		},
		documents: [
			{
				name: 'DOC-1',
				document_type: 'SSC/10th Mark Sheet',
				file: '/private/files/ssc.pdf',
				verified: 1,
				verified_by: 'Administrator',
				idx: 1,
			},
			{
				name: 'DOC-2',
				document_type: 'National ID',
				file: null,
				verified: 0,
				verified_by: null,
				idx: 2,
			},
		],
		references: [
			{
				name: 'REF-1',
				referee_name: 'Pastor Rajesh',
				referee_email: 'rajesh@example.invalid',
				referee_type: 'Pastor-Mentor',
				sent_on: '2026-06-14',
				submitted_on: '2026-06-16',
				recommendation: 'Strong',
				idx: 1,
			},
		],
		mentors: [
			{
				name: 'MEN-1',
				mentor_name: 'Benny',
				mentor_email: 'benny@example.invalid',
				mentor_mobile: '+91 80986 19631',
				church: 'New Life Church',
				denomination: 'Independent',
				current_position: 'Bible college professor',
				years_of_ministry: 12,
				handbook_acknowledged: 1,
				consent_file: null,
				sent_on: '2026-06-14',
				consented_on: '2026-06-17',
				idx: 1,
			},
		],
		manuals: [],
		scholarship: null,
	},
}

let get: ReturnType<typeof vi.fn>

async function renderProfile(data: Detail = detail) {
	vi.resetModules()
	Object.assign(window, { user: 'registrar@x.invalid', roles: ['Registrar'], csrf_token: 't' })

	get = vi.fn(async (method: string) => {
		if (method === 'sibbcs.admissions.mentor_form.view') {
			return {
				mentor: 'Benny',
				email: 'benny@example.invalid',
				consented_on: '2026-06-17',
				html: MENTOR_HTML,
			}
		}
		return data
	})

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: get, frappePost: vi.fn() }
	})

	const { StudentDetail } = await import('./StudentDetail')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter initialEntries={['/staff/students/SIB-2026-0007']}>
				<Routes>
					<Route path="/staff/students/:name" element={<StudentDetail />} />
				</Routes>
			</MemoryRouter>
		</QueryClientProvider>,
	)

	await waitFor(() => expect(document.querySelector('[data-slot="skeleton"]')).toBeNull())
}

beforeEach(() => vi.resetModules())
afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

function cardFor(title: string) {
	return screen.getByText(title).closest('[data-slot="card"]') as HTMLElement
}

describe('the student profile', () => {
	it('leads with who the person is and how far they have got', async () => {
		await renderProfile()

		expect(
			screen.getByRole('heading', { name: 'Chettebathula Anil Kumar' }),
		).toBeInTheDocument()
		expect(screen.getByText('Level 1')).toBeInTheDocument()
		// The number is in the banner and again in the card below it.
		expect(
			within(cardFor('Personal information')).getByText('+91 93900 70957'),
		).toBeInTheDocument()
		expect(screen.getByRole('link', { name: 'anil@example.invalid' })).toHaveAttribute(
			'href',
			'mailto:anil@example.invalid',
		)
	})

	it('shows the schooling the application asked for', async () => {
		// None of this is on the Student record; it only exists because the
		// profile reads the admission application behind it.
		await renderProfile()

		const card = cardFor('Educational details')
		expect(within(card).getByText('Completed · 2014')).toBeInTheDocument()
		expect(within(card).getByText('Pursuing · 2026')).toBeInTheDocument()
	})

	it('shows the mentor as formation, not as an academic record', async () => {
		await renderProfile()

		const card = cardFor('Formational details')
		expect(within(card).getByText('Benny')).toBeInTheDocument()
		expect(within(card).getByText('Bible college professor')).toBeInTheDocument()
		expect(within(card).getByText('New Life Church · Independent')).toBeInTheDocument()
		expect(within(card).getByText(/received/i)).toBeInTheDocument()
	})

	it('carries the admission checklist as the admissions console derives it', async () => {
		await renderProfile()

		expect(screen.getByText('Full Application Review')).toBeInTheDocument()
		expect(screen.getByText('Awaiting Onboarding')).toBeInTheDocument()
		expect(screen.getByText('62%')).toBeInTheDocument()
	})

	it('carries the documents the candidate uploaded', async () => {
		await renderProfile()

		const card = cardFor('Student documents')
		expect(within(card).getByText('1 of 2 verified')).toBeInTheDocument()
		expect(
			within(within(card).getByText('SSC/10th Mark Sheet').closest('tr') as HTMLElement).getByRole(
				'link',
				{ name: /open/i },
			),
		).toHaveAttribute('href', '/private/files/ssc.pdf')
	})

	it('opens what the mentor actually wrote', async () => {
		await renderProfile()

		await userEvent.click(
			within(screen.getByText('Mentor form').closest('tr') as HTMLElement).getByRole('button', {
				name: /read/i,
			}),
		)

		const dialog = await screen.findByRole('dialog')
		expect(within(dialog).getByText(/how long have you known/i)).toBeInTheDocument()
		expect(get).toHaveBeenCalledWith('sibbcs.admissions.mentor_form.view', {
			application: 'APP-2026-00011',
			row: 'MEN-1',
		})
	})

	it('says a student was created directly rather than admitted', async () => {
		await renderProfile({
			...detail,
			student: { ...detail.student, admission_application: null },
			admission: null,
		})

		expect(screen.getAllByText(/created directly rather than admitted/i).length).toBeGreaterThan(0)
	})

	it('says when the admission record exists but is not this reader’s to see', async () => {
		// Faculty may grade a student and hold nothing on Admission Application.
		// "Empty" and "not yours" are different facts and must read differently.
		await renderProfile({ ...detail, admission: null })

		expect(screen.getAllByText(/your role may not read/i).length).toBeGreaterThan(0)
	})

	it('shows what the candidate said about themselves', async () => {
		await renderProfile()

		const personal = cardFor('Personal information')
		expect(within(personal).getByText('Telugu')).toBeInTheDocument()
		expect(within(personal).getByText('Indian')).toBeInTheDocument()

		const formation = cardFor('Formational details')
		expect(within(formation).getByText('I am Saved')).toBeInTheDocument()
		expect(within(formation).getByText('Baptised')).toBeInTheDocument()
		expect(within(formation).getByText('Yes, clearly')).toBeInTheDocument()
		expect(within(formation).getByText('Independent')).toBeInTheDocument()
	})

	it('badges only the determinations that are actually true', async () => {
		// Four flags, one set. A row of "No" badges is noise the eye has to
		// read past to find the one that matters.
		await renderProfile()

		expect(screen.getByText('ATA eligible')).toBeInTheDocument()
		expect(screen.queryByText('Transfer student')).not.toBeInTheDocument()
		expect(screen.queryByText('Mature candidate')).not.toBeInTheDocument()
		expect(screen.getByText('Waiting For Payment')).toBeInTheDocument()
	})
})
