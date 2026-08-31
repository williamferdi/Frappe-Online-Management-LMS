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
}

export interface MyCoursesResponse {
	enrollment: EnrollmentHeader | null
	registrations: Registration[]
}
