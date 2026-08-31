/** Mirrors what `sibbcs.api.student.my_courses` returns. */

export interface FeeState {
	invoice: string | null
	status: string | null
	outstanding: number
	amount?: number
	payment_link?: string | null
	settled: boolean
	label: string
}

export interface Registration {
	name: string
	course: string
	course_title: string | null
	term: string
	status: string
	credits: number
	grade: string | null
	final_marks: number | null
	passed: 0 | 1
	lms_enrollment_created: 0 | 1
	registration_fee_invoice: string | null
	fee: FeeState
	lms_course: string | null
	lms_url: string | null
	progress: number
}

export interface EnrollmentHeader {
	name: string
	student: string
	student_name: string
	program: string
	program_name?: string
	current_level: string
	credits_earned: number
	cgpa: number | null
	status: string
	expected_completion?: string | null
}

export interface MyCoursesResponse {
	enrollment: EnrollmentHeader | null
	registrations: Registration[]
}

// --- dashboard -------------------------------------------------------------

export interface OpenFee {
	name: string
	status: string
	category: string | null
	fee_type: string | null
	term: string | null
	net_amount: number
	outstanding_amount: number
	due_date: string | null
	payment_link: string | null
	overdue: boolean
}

export interface TermWindow {
	name: string
	term_name: string
	start_date: string | null
	end_date: string | null
	registration_closes: string | null
	closes_in_days: number | null
}

export interface DashboardResponse {
	enrollment: EnrollmentHeader | null
	in_progress?: Registration[]
	in_progress_count?: number
	recent_grades?: Registration[]
	fees?: {
		open: OpenFee[]
		count: number
		outstanding: number
		overdue_count: number
	}
	registration?: {
		terms: TermWindow[]
		eligible_count: number
		open: boolean
	}
}

// --- grades ----------------------------------------------------------------

export interface GradeComponent {
	parent: string
	component: string
	weight_pct: number
	max_marks: number
	obtained_marks: number
	weighted_score: number
	idx: number
}

export interface GradedRegistration {
	name: string
	course: string
	course_title: string | null
	term: string
	status: string
	credits: number
	final_marks: number | null
	grade: string | null
	grade_points: number | null
	passed: 0 | 1
	level_at_registration: string | null
	components: GradeComponent[]
}

export interface GradeBand {
	grade: string
	min_pct: number
	max_pct: number
	grade_points: number
	is_pass: 0 | 1
}

export interface GradesResponse {
	enrollment: EnrollmentHeader | null
	terms: {
		term: string
		term_name: string
		start_date: string | null
		rows: GradedRegistration[]
		credits: number
	}[]
	scale: {
		name: string
		scale_name: string
		pass_percentage: number
		rows: GradeBand[]
	} | null
}

// --- registration ----------------------------------------------------------

export interface Eligibility {
	allowed: boolean
	reason: string | null
	code: string | null
	needs_override: boolean
	hard: boolean
	warnings: string[]
}

export interface Offering {
	name: string
	course: string
	course_title: string | null
	term: string
	format: string | null
	capacity: number | null
	enrolled_count: number | null
	zoom_time: string | null
	credits: number
	course_level: string | null
	already_registered: boolean
	eligibility: Eligibility
	seats_left?: number | null
}

export interface RegistrationOptions {
	enrollment: EnrollmentHeader | null
	terms: {
		term: string
		term_name: string
		start_date: string | null
		end_date: string | null
		registration_closes: string | null
		rows: Offering[]
		eligible_count: number
	}[]
}

// --- profile ---------------------------------------------------------------

export interface StudentRecord {
	name: string
	full_name: string
	dob: string | null
	gender: string | null
	photo: string | null
	status: string
	mobile: string | null
	whatsapp: string | null
	email: string | null
	address: string | null
}

export interface ProfileResponse {
	user: { name: string; full_name?: string; user_image?: string | null; username?: string }
	student: StudentRecord | null
	enrollment: EnrollmentHeader | null
	editable: string[]
}
// --- to do -----------------------------------------------------------------

export type TodoKind = 'fee' | 'blocked' | 'assignment' | 'registration'

export interface TodoItem {
	kind: TodoKind
	title: string
	detail: string
	due: string | null
	url: string | null
	urgent?: boolean
	reference?: string
}

export interface TodoResponse {
	items: TodoItem[]
	count: number
	urgent: number
}

// --- calendar --------------------------------------------------------------

export type EventKind = 'class' | 'timetable' | 'session' | 'fee' | 'term'

export interface CalendarEvent {
	kind: EventKind
	title: string
	start: string
	end: string | null
	url: string | null
	detail?: string
	reference?: string
	all_day?: boolean
}

export interface CalendarResponse {
	events: CalendarEvent[]
	start: string | null
	end: string | null
}

// --- announcements ---------------------------------------------------------

export interface Announcement {
	name: string
	title: string
	body: string
	category: string
	pinned: 0 | 1
	publish_on: string
	expires_on: string | null
	audience: string
	read: boolean
}

export interface AnnouncementsResponse {
	rows: Announcement[]
	unread: number
}

// --- inbox -----------------------------------------------------------------

export interface ThreadSummary {
	thread: string
	subject: string
	count: number
	unread: number
	last: {
		name: string
		sender: string
		sender_name: string
		sent_on: string
		preview: string
	} | null
}

export interface InboxResponse {
	threads: ThreadSummary[]
	unread: number
}

export interface Message {
	name: string
	subject: string
	sender: string
	sender_name: string
	sent_on: string
	body: string
	thread: string | null
	mine: boolean
}

export interface ThreadResponse {
	thread: string
	subject: string
	messages: Message[]
}

export interface OfficeContact {
	name: string
	full_name: string
}

// --- discussions -----------------------------------------------------------

export interface DiscussionRoom {
	course_offering: string
	course: string
	course_title: string | null
	term: string
	topics: number
}

export interface DiscussionTopic {
	name: string
	title: string
	owner: string
	author_name: string
	creation: string
	modified: string
	replies: number
}

export interface DiscussionReply {
	name: string
	reply: string
	owner: string
	author_name: string
	creation: string
	mine: boolean
}

export interface DiscussionThread {
	topic: string
	title: string
	replies: DiscussionReply[]
}

// --- badges ----------------------------------------------------------------

export interface UnreadCounts {
	announcements: number
	inbox: number
}
// --- staff console ---------------------------------------------------------

export interface FunnelState {
	state: string
	count: number
}

export interface StuckStep {
	step_no: number
	step: string
	owner_role: string
	waiting: number
}

export interface Funnel {
	by_state: FunnelState[]
	total: number
	live: number
	stuck: StuckStep[]
}

export interface AcademicPanel {
	students: number
	enrollments: number
	by_level: { level: string; count: number }[]
	by_program: { program: string; count: number }[]
	registrations: Record<string, number>
	open_terms: { name: string; term_name: string; registration_closes: string | null }[]
}

export interface FinancePanel {
	billed: number
	collected: number
	outstanding: number
	overdue: number
	overdue_count: number
	by_category: { category: string; outstanding: number }[]
	recent_payments: {
		name: string
		student_name: string | null
		amount: number
		mode: string
		received_on: string
	}[]
	days: number
}

export interface ConsoleDashboard {
	user: string
	panels: {
		admissions?: Funnel
		academic?: AcademicPanel
		finance?: FinancePanel
	}
}

// --- admissions pipeline ---------------------------------------------------

export interface PipelineRow {
	name: string
	full_name: string
	email: string | null
	mobile: string | null
	program: string | null
	intake_term: string | null
	entry_level: string | null
	workflow_state: string
	application_fee_paid: 0 | 1
	qualifying_exam_score: number | null
	student: string | null
	creation: string
	modified: string
	progress: { done: number; total: number; percent: number }
}

export interface PipelineResponse {
	rows: PipelineRow[]
	states: string[]
	programs: string[]
	can_write: boolean
}

// --- one application -------------------------------------------------------

export interface ChecklistRow {
	step_no: number
	step: string
	status: string
	statuses: string[]
	owner_role: string
	done: boolean
	done_statuses: string[]
	blocked: string | null
	remarks: string | null
	updated_by: string | null
	updated_on: string | null
	action: string | null
}

export interface ChecklistBoard {
	application: string
	state: string
	progress: { done: number; total: number; percent: number } | number
	rows: ChecklistRow[]
	can_write: boolean
}

export interface ApplicationRecord {
	name: string
	full_name: string
	email: string | null
	mobile: string | null
	whatsapp: string | null
	dob: string | null
	age: number | null
	gender: string | null
	address: string | null
	photo: string | null
	church_name: string | null
	current_role: string | null
	years_of_ministry: number | null
	has_bachelors: 0 | 1
	previous_theological_education: string | null
	program: string | null
	intake_term: string | null
	entry_level: string | null
	workflow_state: string
	application_fee_paid: 0 | 1
	admission_fee_paid: 0 | 1
	qualifying_exam_score: number | null
	interview_outcome: string | null
	offer_sent_on: string | null
	student: string | null
	enrolled_on: string | null
	notes: string | null
	scholarship_request: string | null
	applicant_user: string | null
	exam_link_sent_on: string | null
	interview_link_sent_on: string | null
	scholarship_form_sent_on: string | null
	onboard_term: string | null
	onboard_level: string | null
}

export interface ApplicationDetail {
	application: ApplicationRecord
	checklist: ChecklistBoard
	documents: {
		name: string
		document_type: string
		file: string | null
		verified: 0 | 1
		verified_by: string | null
		idx: number
	}[]
	references: {
		name: string
		referee_name: string | null
		referee_email: string | null
		referee_type: string | null
		sent_on: string | null
		submitted_on: string | null
		recommendation: string | null
		idx: number
	}[]
	mentors: {
		name: string
		mentor_name: string | null
		mentor_email: string | null
		sent_on: string | null
		consented_on: string | null
		idx: number
	}[]
	exam: {
		name: string
		total: number
		result: string
		pass_mark: number
		conducted_on: string
	} | null
	interview: {
		name: string
		scheduled_on: string | null
		outcome: string | null
		notes: string | null
		panel: string | null
	} | null
	scholarship: {
		name: string
		status: string
		approved_amount: number
		monthly_discount: number
		requested_amount: number
	} | null
	invoices: {
		name: string
		fee_type: string | null
		category: string | null
		status: string
		net_amount: number
		outstanding_amount: number
		due_date: string | null
		payment_link: string | null
	}[]
}
// --- academic console ------------------------------------------------------

export interface StudentEnrollment {
	name: string
	student: string
	program: string
	current_level: string
	status: string
	credits_earned: number
	cgpa: number | null
}

export interface StudentRow {
	name: string
	full_name: string
	email: string | null
	mobile: string | null
	status: string
	user: string | null
	enrollment: StudentEnrollment | null
}

export interface StudentsResponse {
	rows: StudentRow[]
	programs: string[]
	levels: string[]
	filters: { program: string | null; level: string | null }
}

export interface StudentDetail {
	student: {
		name: string
		full_name: string
		email: string | null
		mobile: string | null
		whatsapp: string | null
		dob: string | null
		gender: string | null
		status: string
		photo: string | null
		address: string | null
		user: string | null
		admission_application: string | null
	}
	enrollment:
		| (StudentEnrollment & {
				enrollment_date: string | null
				expected_completion: string | null
				start_term: string | null
		  })
		| null
	registrations: {
		name: string
		course: string
		course_title: string | null
		term: string
		status: string
		credits: number
		level_at_registration: string | null
		final_marks: number | null
		grade: string | null
		grade_points: number | null
		passed: 0 | 1
		registration_fee_invoice: string | null
		course_offering: string
	}[]
	invoices: {
		name: string
		fee_type: string | null
		category: string | null
		status: string
		net_amount: number
		outstanding_amount: number
		due_date: string | null
	}[]
	promotions: {
		name: string
		from_level: string
		to_level: string
		approved_by: string | null
		approved_on: string | null
		courses_passed: number
		credits_at_promotion: number
		remarks: string | null
	}[]
}

// --- offerings and grading -------------------------------------------------

export interface OfferingRow {
	name: string
	course: string
	course_title: string | null
	term: string
	status: string
	format: string | null
	instructor: string | null
	facilitator: string | null
	capacity: number | null
	enrolled_count: number | null
	credits: number
	course_level: string | null
	zoom_time: string | null
	registered: number
	graded: number
}

export interface OfferingsResponse {
	rows: OfferingRow[]
	terms: { name: string; term_name: string; status: string }[]
}

export interface GradeComponentRow {
	name?: string
	parent?: string
	component: string
	weight_pct: number
	max_marks: number
	obtained_marks: number | null
	weighted_score: number
	idx?: number
}

export interface RosterRegistration {
	name: string
	student: string
	student_name: string
	status: string
	credits: number
	final_marks: number | null
	grade: string | null
	grade_points: number | null
	passed: 0 | 1
	program_enrollment: string
	components: GradeComponentRow[]
	marks_complete: boolean
}

export interface RosterResponse {
	offering: OfferingRow
	registrations: RosterRegistration[]
	components: string[]
	statuses: string[]
	can_grade: boolean
}

export interface SaveGradesResult {
	registration: string
	final_marks: number | null
	grade: string | null
	grade_points: number | null
	passed: 0 | 1
	status: string
	marks_complete: boolean
	components: GradeComponentRow[]
}

// --- promotions ------------------------------------------------------------

export interface PromotionRow {
	program_enrollment: string
	student: string
	student_name: string
	program: string
	from_level: number
	to_level: number
	required: number
	passed: number
	eligible: boolean
	blocked: string | null
}

export interface PromotionsResponse {
	rows: PromotionRow[]
	may_approve: boolean
}
