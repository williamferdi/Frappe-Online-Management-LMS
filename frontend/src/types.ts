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
