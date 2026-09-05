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
	photo: string | null
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
	mother_tongue: string | null
	nationality: string | null
	church_denomination: string | null
	salvation_status: string | null
	baptism_status: string | null
	sense_of_call: string | null
	ata_eligible: 0 | 1
	mature_candidate: 0 | 1
	transfer_student: 0 | 1
	education_sequence_mismatch: 0 | 1
	whatsapp_groups: string | null
	theological_writing_status: string | null
	program: string | null
	intake_term: string | null
	entry_level: string | null
	workflow_state: string
	application_fee_paid: 0 | 1
	docs_verified: 0 | 1
	docs_resubmit_requested_on: string | null
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

export interface ApplicationDocumentRow {
	name: string
	document_type: string
	file: string | null
	verified: 0 | 1
	verified_by: string | null
	remarks?: string | null
	idx: number
}

export interface ReferenceRequestRow {
	name: string
	referee_name: string | null
	referee_email: string | null
	referee_type: string | null
	sent_on: string | null
	submitted_on: string | null
	recommendation: string | null
	idx: number
}

export interface MentorConsentRow {
	name: string
	mentor_name: string | null
	mentor_email: string | null
	mentor_mobile?: string | null
	church?: string | null
	denomination?: string | null
	current_position?: string | null
	years_of_ministry?: number | null
	mentoring_experience?: string | null
	prior_theological_education?: string | null
	handbook_acknowledged?: 0 | 1
	consent_file?: string | null
	sent_on: string | null
	consented_on: string | null
	idx: number
}

export interface ExamAnswer {
	question: string | null
	answer: string | null
	marks: number
	marks_out_of: number
}

export interface ExamState {
	application: string
	quiz_exists: boolean
	submission: {
		name: string
		member: string
		submitted_on: string
		score: number
		score_out_of: number
		/** False while the candidate has sat it and nobody has read it yet. */
		marked: boolean
		answers: ExamAnswer[]
	} | null
	result: {
		name: string
		conducted_on: string | null
		pass_mark: number
		total: number
		result: string
		essay_gospel: number
		essay_calling: number
		essay_motivation: number
	} | null
	essay_max: number
	essays: string[]
}

export interface InterviewRecord {
	name: string
	scheduled_on: string | null
	outcome: string | null
	notes: string | null
	modified?: string | null
}

export interface ScholarshipDetail {
	name: string
	program: string | null
	status: string
	requested_amount: number
	approved_amount: number
	monthly_discount: number
	justification: string | null
	signature: string | null
	submitted_on: string | null
	approved_by: string | null
	approved_on: string | null
	cap: number | null
	may_decide: boolean
}

export interface ApplicationDetail {
	application: ApplicationRecord
	checklist: ChecklistBoard
	/** The document types that gate the checklist step. */
	required_documents: string[]
	documents: ApplicationDocumentRow[]
	references: ReferenceRequestRow[]
	mentors: MentorConsentRow[]
	exam: ExamState
	interview: InterviewRecord | null
	interview_outcomes: string[]
	scholarship: ScholarshipDetail | null
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
	photo: string | null
	email: string | null
	mobile: string | null
	status: string
	user: string | null
	enrollment: StudentEnrollment | null
}

export interface Demographics {
	total: number
	panels: {
		key: string
		title: string
		/** What job the colour does: identity, state, an ordered scale, or yes/no. */
		kind: 'categorical' | 'status' | 'ordinal' | 'binary'
		slices: { label: string; count: number }[]
	}[]
}

export interface StudentsResponse {
	rows: StudentRow[]
	/** True when the row cap cut the list short. */
	truncated?: boolean
	programs: string[]
	levels: string[]
	filters: { program: string | null; level: string | null }
}

export interface StudentAdmission {
	application: {
		name: string
		creation: string
		workflow_state: string
		program: string | null
		intake_term: string | null
		entry_level: string | null
		age: number | null
		photo: string | null
		church_name: string | null
		current_role: string | null
		years_of_ministry: number | null
		has_bachelors: 0 | 1
		previous_theological_education: string | null
		mother_tongue: string | null
		nationality: string | null
		church_denomination: string | null
		salvation_status: string | null
		baptism_status: string | null
		sense_of_call: string | null
		ata_eligible: 0 | 1
		mature_candidate: 0 | 1
		transfer_student: 0 | 1
		education_sequence_mismatch: 0 | 1
		whatsapp_groups: string | null
		theological_writing_status: string | null
		ssc_status: string | null
		ssc_year: string | null
		hslc_status: string | null
		hslc_year: string | null
		ug_status: string | null
		ug_year: string | null
		id_document: string | null
		ministry_experience_doc: string | null
		application_fee_paid: 0 | 1
		docs_verified: 0 | 1
		qualifying_exam_score: number | null
		interview_outcome: string | null
		offer_sent_on: string | null
		admission_fee_paid: 0 | 1
		onboard_term: string | null
		onboard_level: string | null
		enrolled_on: string | null
		applicant_user: string | null
		scholarship_request: string | null
	}
	checklist: ChecklistBoard
	documents: ApplicationDocumentRow[]
	references: ReferenceRequestRow[]
	mentors: MentorConsentRow[]
	manuals: {
		name: string
		manual: string
		sent_on: string | null
		acknowledged_on: string | null
		acknowledged_name: string | null
		idx: number
	}[]
	scholarship: {
		name: string
		status: string
		requested_amount: number
		approved_amount: number
		monthly_discount: number
	} | null
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
	/** Null when there is no application, or the reader may not read it. */
	admission: StudentAdmission | null
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
// --- finance ---------------------------------------------------------------

export interface InvoiceRow {
	name: string
	student: string | null
	student_name: string | null
	status: string
	category: string | null
	fee_type: string | null
	term: string | null
	gross_amount: number
	discount_amount: number
	net_amount: number
	paid_amount: number
	outstanding_amount: number
	due_date: string | null
	payment_link: string | null
	course_registration: string | null
	admission_application: string | null
	creation: string
	overdue: boolean
}

export interface FinanceSummary {
	billed: number
	collected: number
	outstanding: number
	overdue: number
	overdue_count: number
}

export interface InvoicesResponse {
	rows: InvoiceRow[]
	statuses: string[]
	categories: string[]
	summary: FinanceSummary
}

export interface PaymentRow {
	name: string
	student: string
	student_name: string | null
	amount: number
	mode: string
	reference_no: string | null
	received_on: string
	allocated_amount: number
	unallocated_amount: number
	reconciled_by: string | null
}

export interface PaymentsResponse {
	rows: PaymentRow[]
	modes: string[]
}

export interface OutstandingInvoice {
	name: string
	fee_type: string | null
	category: string | null
	term: string | null
	net_amount: number
	outstanding_amount: number
	due_date: string | null
}

export interface ScholarshipRow {
	name: string
	application: string | null
	student: string | null
	program: string | null
	status: string
	requested_amount: number
	approved_amount: number
	monthly_discount: number
	approved_by: string | null
	approved_on: string | null
	submitted_on: string | null
	justification: string | null
}

export interface ScholarshipsResponse {
	rows: ScholarshipRow[]
	statuses: string[]
	caps: Record<string, number>
	may_decide: boolean
}

// --- users -----------------------------------------------------------------

export interface UserRow {
	name: string
	full_name: string
	enabled: 0 | 1
	user_type: string
	last_active: string | null
	creation: string
	roles: string[]
	protected_roles: string[]
	student: string | null
}

export interface UsersResponse {
	rows: UserRow[]
	managed_roles: string[]
	protected_roles: string[]
}

export interface RoleCount {
	role: string
	count: number
}

// --- the course shell (Phase 1) ------------------------------------------

export interface GradeSchemeRow {
	component: string
	weight_pct: number
	drop_lowest: number
	posting_policy: string
}

export interface CourseGradeScheme {
	name: string
	total_weight: number
	rows: GradeSchemeRow[]
}

export interface CourseAssignment {
	name: string
	title: string
	component: string
	points_possible: number
	submission_type: string
	grading_type: string
	due_date: string | null
	available_from: string | null
	available_until: string | null
	late_policy: string
	late_penalty_pct_per_day: number
	allowed_attempts: number
	published: number
	description: string | null
}

/** Option lists read from the DocTypes, so a component added in Desk reaches
 * the scheme editor rather than being invisible to it. */
export interface CourseChoices {
	components: string[]
	submission_types: string[]
	grading_types: string[]
	late_policies: string[]
	posting_policies: string[]
}

export interface CourseShelfRow {
	name: string
	course: string
	course_title: string | null
	term: string
	status: string
	format: string | null
	instructor: string | null
	facilitator: string | null
	enrolled_count: number | null
	credits: number
	course_level: string | null
	has_scheme: boolean
	assignments: number
	published_assignments: number
}

export interface CoursesResponse {
	rows: CourseShelfRow[]
	terms: { name: string; term_name: string; status: string }[]
}

export interface CourseDetail {
	offering: OfferingRow
	scheme: CourseGradeScheme | null
	assignments: CourseAssignment[]
	choices: CourseChoices
}

// --- marking (Phase 2) ----------------------------------------------------

export interface SubmissionSummary {
	name: string
	course_registration: string
	student: string | null
	student_name: string | null
	attempt: number
	status: string
	submitted_on: string | null
	late_days: number
	excused: number
	score: number | null
	scored: number
	posted: number
	feedback: string | null
	graded_by: string | null
	graded_on: string | null
	body: string | null
	url: string | null
}

export interface RubricRating {
	title: string
	points: number
	description: string | null
}

export interface RubricCriterion {
	name: string
	title: string
	description: string | null
	points_possible: number
	position: number
	ratings: RubricRating[]
}

export interface RubricDetail {
	name: string
	title: string
	course?: string | null
	total_points?: number
	description?: string | null
	criteria?: RubricCriterion[]
}

export interface MarkingRow {
	course_registration: string
	student: string | null
	student_name: string | null
	submission: SubmissionSummary | null
	effective_score: number | null
}

export interface MarkingQueue {
	assignment: {
		name: string
		title: string
		course_offering: string
		component: string
		points_possible: number
		due_date: string | null
		late_policy: string
		late_penalty_pct_per_day: number
		submission_type: string
		published: number
		rubric: string | null
		description: string | null
	}
	rubric: RubricDetail | null
	rows: MarkingRow[]
	ungraded: number
	unposted: number
	missing: number
}

export interface GradebookGrid {
	assignments: {
		name: string
		title: string
		component: string
		points_possible: number
		due_date: string | null
		published: number
	}[]
	rows: {
		course_registration: string
		student_name: string | null
		final_marks: number | null
		/** False while any component is still unmarked, when `final_marks`
		 * carries the column default rather than a total. */
		marks_complete: boolean
		grade: string | null
		passed: number
		cells: Record<string, SubmissionSummary | null>
	}[]
	scheme: { component: string; weight_pct: number; posting_policy: string }[] | null
}

// --- a student's own coursework -------------------------------------------

export interface StudentSubmission {
	name: string
	attempt: number
	status: string
	submitted_on: string | null
	late_days: number
	excused: number
	body: string | null
	url: string | null
	posted: number
	/** Absent, not null, until the mark is posted. */
	score?: number | null
	effective_score?: number | null
	feedback?: string | null
}

export interface CourseworkRow {
	assignment: {
		name: string
		title: string
		description: string | null
		component: string
		points_possible: number
		grading_type: string
		submission_type: string
		due_date: string | null
		available_from: string | null
		available_until: string | null
		late_policy: string
		late_penalty_pct_per_day: number
		allowed_attempts: number
	}
	submission: StudentSubmission | null
	open: { open: boolean; reason: string | null }
}

export interface CourseworkResponse {
	registration: {
		name: string
		course_title: string | null
		course_offering: string
		status: string
	}
	rows: CourseworkRow[]
}

// --- modules and the course outline (Phase 3) -----------------------------

export interface OutlineItemProgress {
	name: string
	module_item: string
	status: string
	completed_on: string | null
	score: number | null
}

export interface OutlineItem {
	name: string
	module: string
	item_type: string
	title: string | null
	position: number
	indent: number
	published: number
	lesson: string | null
	assignment: string | null
	page: string | null
	file: string | null
	url: string | null
	completion_requirement: string
	min_score: number | null
	progress: OutlineItemProgress | null
	complete: boolean
	locked: boolean
	lock_reason: string | null
}

export interface OutlineModule {
	name: string
	title: string
	position: number
	published: number
	unlock_at: string | null
	require_sequential_progress: number
	prerequisites: string[]
	state: { open: boolean; reason: string | null }
	complete: boolean
	items: OutlineItem[]
}

export interface CourseOutline {
	registration: {
		name: string
		course_title: string | null
		course_offering: string
		status: string
	}
	modules: OutlineModule[]
}

export interface StaffOutline {
	modules: OutlineModule[]
	choices: {
		lessons: { name: string; title: string; chapter: string }[]
		assignments: { name: string; title: string }[]
		pages: { name: string; title: string; published: number }[]
		files: { name: string; title: string }[]
		item_types: string[]
		completion_rules: string[]
	}
}

/** Lesson content, already stripped of its interactive blocks server-side. */
export interface LessonContent {
	name: string
	title: string
	blocks: { type: string; data?: Record<string, unknown> }[]
	removed: string[]
	lms_url: string | null
}

export interface ReadItemResponse {
	item: {
		name: string
		item_type: string
		title: string | null
		lesson: string | null
		assignment: string | null
		page: string | null
		file: string | null
		url: string | null
		completion_requirement: string
		min_score: number | null
	}
	content:
		| LessonContent
		| { title: string; body: string | null }
		| { title: string; file: string | null; description: string | null }
		| null
}

// --- quizzes (Phase 4) ----------------------------------------------------

export interface QuizOption {
	idx: number
	text: string
	/** Deliberately absent: the server never sends which option is correct
	 * while an attempt is open. */
}

export interface QuizQuestion {
	name: string
	question: string
	question_type: string
	points: number
	options: QuizOption[]
	given: unknown
}

export interface QuizAttempt {
	attempt: string
	status: string
	started_at: string | null
	/** The server's deadline. The countdown drawn from it is decoration --
	 * the server refuses a late answer whatever the page believes. */
	expires_at: string | null
	seconds_remaining: number | null
	one_question_at_a_time: number
	title: string
	description: string | null
	questions: QuizQuestion[]
}

export interface QuizResult {
	attempt: string
	status: string
	auto_submitted: number
	submitted_at: string | null
	score: number
	points_possible: number
	/** Present only when the quiz's reveal policy allows it. */
	questions?: {
		name: string
		question: string | null
		explanation: string | null
		given: unknown
		is_correct: number
		points_awarded: number
		correct: number[]
	}[]
}
