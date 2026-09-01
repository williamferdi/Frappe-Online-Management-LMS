import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import type { ApplicationDetail as Detail } from '@/types'

const REFERENCE_HTML =
	'<table><tr><td>Your Relationship to the Applicant</td><td><b>Pastor</b></td></tr>' +
	'<tr><td>Would you recommend this applicant?</td><td><b>I strongly recommend</b></td></tr></table>'

const detail: Detail = {
	application: {
		name: 'APP-2026-00011',
		full_name: 'Deborah Vasanthi',
		email: 'd@example.invalid',
		mobile: '+91 90000 00000',
		whatsapp: null,
		dob: '1994-07-15',
		age: 32,
		gender: 'Female',
		address: 'Coimbatore',
		photo: null,
		church_name: 'Grace Baptist',
		current_role: 'Youth Pastor',
		years_of_ministry: 3,
		has_bachelors: 1,
		previous_theological_education: null,
		mother_tongue: null,
		nationality: null,
		church_denomination: null,
		salvation_status: null,
		baptism_status: null,
		sense_of_call: null,
		ata_eligible: 0,
		mature_candidate: 0,
		transfer_student: 0,
		education_sequence_mismatch: 0,
		whatsapp_groups: null,
		theological_writing_status: null,
		program: 'MDIV',
		intake_term: null,
		entry_level: null,
		workflow_state: 'In Review',
		application_fee_paid: 1,
		admission_fee_paid: 1,
		qualifying_exam_score: 78,
		interview_outcome: null,
		offer_sent_on: null,
		student: null,
		enrolled_on: null,
		notes: null,
		scholarship_request: null,
		applicant_user: null,
		exam_link_sent_on: null,
		interview_link_sent_on: null,
		scholarship_form_sent_on: null,
		onboard_term: null,
		onboard_level: null,
		docs_verified: 0,
		docs_resubmit_requested_on: null,
	},
	required_documents: [
		'SSC/10th Mark Sheet',
		'HSLC/12th Mark Sheet',
		'National ID',
		'Photo',
	],
	checklist: {
		application: 'APP-2026-00011',
		state: 'In Review',
		progress: 85,
		can_write: true,
		rows: [
			{
				step_no: 1,
				step: 'Full Application Review',
				status: 'Approved',
				statuses: ['Needs Admin Inspection', 'Under Review', 'Approved', 'Rejected'],
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
				blocked: 'Manual Reading Review must be complete first.',
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
			referee_name: 'Rev. Referee One',
			referee_email: 'one@example.invalid',
			referee_type: 'Pastor-Mentor',
			sent_on: '2026-08-11',
			submitted_on: '2026-08-19',
			recommendation: 'Strong',
			idx: 1,
		},
		{
			name: 'REF-2',
			referee_name: 'Rev. Referee Two',
			referee_email: 'two@example.invalid',
			referee_type: 'Professor-Employer',
			sent_on: '2026-08-11',
			submitted_on: null,
			recommendation: null,
			idx: 2,
		},
	],
	mentors: [
		{
			name: 'MEN-1',
			mentor_name: 'Rev. Daniel Raj',
			mentor_email: 'daniel@example.invalid',
			sent_on: '2026-08-11',
			consented_on: '2026-08-20',
			idx: 1,
		},
	],
	// Sat, marked in the course, and recorded on the admissions side.
	exam: {
		application: 'APP-2026-00011',
		quiz_exists: true,
		submission: {
			name: 'sub-1',
			member: 'deborah@example.invalid',
			submitted_on: '2026-08-20 10:00:00',
			score: 60,
			score_out_of: 75,
			marked: true,
			answers: [
				{ question: 'Essay 1', answer: '<p>The gospel is the good news.</p>', marks: 20, marks_out_of: 25 },
				{ question: 'Essay 2', answer: '<p>My calling came early.</p>', marks: 15, marks_out_of: 25 },
				{ question: 'Essay 3', answer: '<p>Why I want to study here.</p>', marks: 25, marks_out_of: 25 },
			],
		},
		result: {
			name: 'QER-1',
			conducted_on: '2026-08-20',
			pass_mark: 40,
			total: 80,
			result: 'Pass',
			essay_gospel: 20,
			essay_calling: 15,
			essay_motivation: 25,
		},
		essay_max: 25,
		essays: ['essay_gospel', 'essay_calling', 'essay_motivation'],
	},
	interview: {
		name: 'INT-1',
		scheduled_on: '2026-08-25 15:00:00',
		outcome: 'Recommend',
		notes: 'A clear sense of calling.',
	},
	interview_outcomes: ['Recommend', 'Reject', 'Defer'],
	scholarship: {
		name: 'SCH-1',
		program: 'MDIV',
		status: 'Submitted',
		requested_amount: 20000,
		approved_amount: 0,
		monthly_discount: 0,
		justification: 'I support my mother and two sisters.',
		signature: '/private/files/sig.png',
		submitted_on: '2026-08-26 09:00:00',
		approved_by: null,
		approved_on: null,
		cap: 30000,
		may_decide: true,
	},
	invoices: [],
}

const get = vi.fn()
const post = vi.fn()

async function renderScreen(data: Detail = detail) {
	vi.resetModules()
	Object.assign(window, { user: 'admin@x.com', roles: ['System Manager'], csrf_token: 't' })

	post.mockReset().mockResolvedValue({ sent_to: 'd@example.invalid', items: [{}, {}] })
	get.mockReset().mockImplementation(async (method: string) => {
		if (method === 'sibbcs.admissions.reference_form.view') {
			return {
				referee: 'Rev. Referee One',
				email: 'one@example.invalid',
				type: 'Pastor-Mentor',
				recommendation: 'Strong',
				submitted_on: '2026-08-19',
				html: REFERENCE_HTML,
			}
		}
		return data
	})

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: get, frappePost: post }
	})

	const { ApplicationDetail } = await import('./ApplicationDetail')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter initialEntries={['/staff/admissions/APP-2026-00011']}>
				<Routes>
					<Route path="/staff/admissions/:name" element={<ApplicationDetail />} />
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

function rowFor(text: string) {
	return screen.getByText(text).closest('tr') as HTMLElement
}

describe('the application detail screen', () => {
	it('shows each document as a box the officer can tick', async () => {
		await renderScreen()

		expect(await screen.findByText('SSC/10th Mark Sheet')).toBeInTheDocument()
		expect(
			within(rowFor('SSC/10th Mark Sheet')).getByRole('checkbox'),
		).toBeChecked()
		expect(within(rowFor('National ID')).getByRole('checkbox')).not.toBeChecked()
		expect(screen.getByText(/1 of 2 verified/)).toBeInTheDocument()
	})

	it('counts the required documents separately, because those are what gate the step', async () => {
		// Ticking an optional document changes nothing about the checklist, and
		// an officer who is not told that will think the screen is broken.
		await renderScreen()
		expect(screen.getByText(/1 of 4 required/)).toBeInTheDocument()
	})

	it('cannot tick a document that was never uploaded', async () => {
		await renderScreen()
		expect(within(rowFor('National ID')).getByRole('checkbox')).toBeDisabled()
	})

	it('saves a tick against the row, not the document type', async () => {
		await renderScreen()
		await userEvent.click(within(rowFor('SSC/10th Mark Sheet')).getByRole('checkbox'))

		expect(post).toHaveBeenCalledWith('sibbcs.admissions.documents.review', {
			application: 'APP-2026-00011',
			row: 'DOC-1',
			verified: 0,
			remarks: undefined,
		})
	})

	it('saves remarks when the officer leaves the box, and not before', async () => {
		await renderScreen()
		const remarks = within(rowFor('SSC/10th Mark Sheet')).getByRole('textbox')

		await userEvent.type(remarks, 'The scan is cut off')
		expect(post).not.toHaveBeenCalled()

		await userEvent.tab()
		expect(post).toHaveBeenCalledWith('sibbcs.admissions.documents.review', {
			application: 'APP-2026-00011',
			row: 'DOC-1',
			verified: undefined,
			remarks: 'The scan is cut off',
		})
	})

	it('asks for the outstanding documents in one click', async () => {
		await renderScreen()
		await userEvent.click(screen.getByRole('button', { name: /request resubmit/i }))

		const dialog = await screen.findByRole('dialog')
		// The one uploaded but unverified, and the required ones never sent.
		expect(within(dialog).getByText('National ID')).toBeInTheDocument()
		expect(within(dialog).getByText('HSLC/12th Mark Sheet')).toBeInTheDocument()
		expect(within(dialog).getAllByText('Never received')).toHaveLength(3)

		await userEvent.click(within(dialog).getByRole('button', { name: /send the request/i }))

		expect(post).toHaveBeenCalledWith('sibbcs.admissions.documents.request_resubmit', {
			application: 'APP-2026-00011',
			message: undefined,
		})
	})

	it('offers no resubmit button when every document is verified', async () => {
		await renderScreen({
			...detail,
			documents: detail.documents.map((row) => ({ ...row, verified: 1 as const })),
			required_documents: ['SSC/10th Mark Sheet'],
		})

		expect(
			screen.queryByRole('button', { name: /request resubmit/i }),
		).not.toBeInTheDocument()
	})

	it('gives a reader who cannot write the record, not the controls', async () => {
		await renderScreen({
			...detail,
			checklist: { ...detail.checklist, can_write: false },
		})

		expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
		expect(within(rowFor('SSC/10th Mark Sheet')).getByText('Verified')).toBeInTheDocument()
	})

	it('links to the file, and says so when there is none', async () => {
		await renderScreen()

		expect(within(rowFor('SSC/10th Mark Sheet')).getByRole('link', { name: /open/i })).toHaveAttribute(
			'href',
			'/private/files/ssc.pdf',
		)
		expect(within(rowFor('National ID')).getByText('No file')).toBeInTheDocument()
	})

	it('offers Read only for a reference that has actually come back', async () => {
		// The whole point of collecting a reference is reading it; a screen that
		// shows only that one arrived is a status light, not a record.
		await renderScreen()

		expect(within(rowFor('Rev. Referee One')).getByRole('button', { name: /read/i })).toBeInTheDocument()
		expect(
			within(rowFor('Rev. Referee Two')).queryByRole('button', { name: /read/i }),
		).not.toBeInTheDocument()
		expect(within(rowFor('Rev. Referee Two')).getByText('Awaiting')).toBeInTheDocument()
	})

	it('shows the mentor form alongside the references', async () => {
		await renderScreen()
		expect(screen.getByText('Mentor form')).toBeInTheDocument()
		expect(within(rowFor('Rev. Daniel Raj')).getByRole('button', { name: /read/i })).toBeInTheDocument()
	})

	it('opens the answers the referee actually gave', async () => {
		await renderScreen()
		await userEvent.click(within(rowFor('Rev. Referee One')).getByRole('button', { name: /read/i }))

		const dialog = await screen.findByRole('dialog')
		expect(within(dialog).getByText(/your relationship to the applicant/i)).toBeInTheDocument()
		expect(within(dialog).getByText('I strongly recommend')).toBeInTheDocument()

		expect(get).toHaveBeenCalledWith('sibbcs.admissions.reference_form.view', {
			application: 'APP-2026-00011',
			row: 'REF-1',
		})
	})

	it('writes out the reason a step is gated', async () => {
		await renderScreen()
		expect(
			screen.getByText('Manual Reading Review must be complete first.'),
		).toBeInTheDocument()
	})

	it('explains an application with nothing uploaded yet', async () => {
		await renderScreen({ ...detail, documents: [], references: [], mentors: [] })
		expect(await screen.findByText(/nothing uploaded yet/i)).toBeInTheDocument()
		expect(screen.getByText(/no requests sent yet/i)).toBeInTheDocument()
	})
})
