import { Link, useParams } from 'react-router-dom'
import {
	ArrowLeft,
	BookOpen,
	CircleCheck,
	CircleDashed,
	FileText,
	Mail,
	Pencil,
	Phone,
	TrendingUp,
	UserRoundCheck,
} from 'lucide-react'

import { DocumentsCard, ResponsesCard } from '@/components/AdmissionEvidence'
import { QueryState } from '@/components/QueryState'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from '@/components/ui/table'
import { useStudentDetail } from '@/hooks/useAcademic'
import { cn, formatDate, initials, money } from '@/lib/utils'
import type { StudentAdmission, StudentDetail as Detail } from '@/types'

/**
 * Everything the college holds about one person, on one page.
 *
 * Two records make it up. `Student` is identity and contact; the Admission
 * Application behind it holds the schooling, the ministry, the certificates and
 * what the referees and the mentor wrote. Nothing is copied between them at
 * onboarding, so the profile reads both -- and says plainly when the second is
 * absent or not this reader's to see, rather than showing blanks.
 */
export function StudentDetail() {
	const { name = null } = useParams()
	const query = useStudentDetail(name)

	return (
		<QueryState query={query} title="Student">
			{(data) => <Loaded data={data} />}
		</QueryState>
	)
}

function Loaded({ data }: { data: Detail }) {
	const { student, enrollment, admission } = data

	return (
		<>
			<Banner data={data} />

			<div className="mt-4 grid gap-4 lg:grid-cols-3">
				<Personal data={data} />
				<Educational admission={admission} linked={student.admission_application} />
				<Formational admission={admission} linked={student.admission_application} />
			</div>

			<Onboarding data={data} />

			{admission && (
				<div className="mt-4 grid gap-4 xl:grid-cols-2">
					<DocumentsCard
						documents={admission.documents}
						title="Student documents"
						empty="Nothing was uploaded with the application."
					/>
					<ResponsesCard
						application={admission.application.name}
						references={admission.references}
						mentors={admission.mentors}
						title="References and mentor form"
						empty="No reference or mentor request was sent with this application."
					/>
				</div>
			)}

			<div className="mt-4 grid gap-4 lg:grid-cols-3">
				<Academic data={data} />

				<div className="space-y-4">
					{data.invoices.length > 0 && <Fees data={data} />}
					<Promotions data={data} />
					{enrollment && admission && admission.manuals.length > 0 && (
						<Manuals admission={admission} />
					)}
				</div>
			</div>
		</>
	)
}

/** Who this is, at a glance. */
function Banner({ data }: { data: Detail }) {
	const { student, enrollment, admission } = data
	const photo = student.photo || admission?.application.photo || undefined

	return (
		<Card>
			<CardContent className="flex flex-wrap items-start justify-between gap-6 p-5">
				<div className="flex min-w-0 items-start gap-4">
					<Avatar className="size-20 rounded-xl">
						<AvatarImage src={photo} alt="" className="object-cover" />
						<AvatarFallback className="rounded-xl text-lg">
							{initials(student.full_name)}
						</AvatarFallback>
					</Avatar>

					<div className="min-w-0">
						<h1 className="truncate text-2xl font-semibold tracking-tight">
							{student.full_name}
						</h1>
						<p className="text-primary mt-0.5 text-sm font-medium">
							{enrollment?.program || admission?.application.program || 'No programme'}
							<span className="text-muted-foreground font-mono font-normal">
								{' · '}
								{student.name}
							</span>
						</p>
						<div className="text-muted-foreground mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
							{student.mobile && (
								<span className="flex items-center gap-1.5">
									<Phone className="size-3.5" /> {student.mobile}
								</span>
							)}
							{student.email && (
								<a
									href={`mailto:${student.email}`}
									className="hover:text-primary flex items-center gap-1.5 transition-colors"
								>
									<Mail className="size-3.5" /> {student.email}
								</a>
							)}
						</div>
					</div>
				</div>

				<div className="flex flex-col items-end gap-3">
					<div className="flex gap-2">
						<Button variant="outline" size="sm" asChild>
							<Link to="/staff/students">
								<ArrowLeft /> Students
							</Link>
						</Button>
						{student.admission_application && (
							<Button variant="outline" size="sm" asChild>
								<Link
									to={`/staff/admissions/${encodeURIComponent(student.admission_application)}`}
								>
									<UserRoundCheck /> Application
								</Link>
							</Button>
						)}
						<Button size="sm" asChild>
							<Link to={`/staff/data/Student/${encodeURIComponent(student.name)}`}>
								<Pencil /> Edit
							</Link>
						</Button>
					</div>

					<div className="text-right">
						<div className="text-muted-foreground text-xs font-medium uppercase tracking-wider">
							Academic progress
						</div>
						<div className="text-primary text-xl font-semibold">
							{enrollment ? `Level ${enrollment.current_level}` : 'Not enrolled'}
						</div>
						<div className="mt-1 flex justify-end gap-2">
							<Badge variant={student.status === 'Active' ? 'success' : 'muted'}>
								{student.status}
							</Badge>
							{enrollment && enrollment.status !== student.status && (
								<Badge variant="muted">{enrollment.status}</Badge>
							)}
						</div>
					</div>
				</div>
			</CardContent>
		</Card>
	)
}

function Personal({ data }: { data: Detail }) {
	const { student, admission } = data
	const age = admission?.application.age

	return (
		<Section title="Personal information">
			<Field label="Gender" value={student.gender} />
			<Field
				label="Date of birth"
				value={student.dob ? `${formatDate(student.dob)}${age ? ` · ${age} years` : ''}` : null}
			/>
			<Field label="Mobile" value={student.mobile} />
			<Field label="WhatsApp" value={student.whatsapp} />
			<Field label="Email" value={student.email} />
			<Field label="Address" value={student.address} />
			<Field label="Login" value={student.user} />
		</Section>
	)
}

function Educational({
	admission,
	linked,
}: {
	admission: StudentAdmission | null
	linked: string | null
}) {
	if (!admission) return <Missing title="Educational details" linked={linked} />
	const record = admission.application

	return (
		<Section title="Educational details">
			<Field label="SSC / 10th" value={completion(record.ssc_status, record.ssc_year)} />
			<Field label="HSLC / 12th" value={completion(record.hslc_status, record.hslc_year)} />
			<Field
				label="Undergraduate degree"
				value={completion(record.ug_status, record.ug_year)}
			/>
			<Field label="Bachelor degree held" value={record.has_bachelors ? 'Yes' : 'No'} />
			<Field
				label="Previous theological education"
				value={record.previous_theological_education}
			/>
			<Field label="Entry level" value={record.entry_level} />
		</Section>
	)
}

/** The mentor: the college's formational relationship, not an academic one. */
function Formational({
	admission,
	linked,
}: {
	admission: StudentAdmission | null
	linked: string | null
}) {
	if (!admission) return <Missing title="Formational details" linked={linked} />

	const mentor = admission.mentors[0]
	const record = admission.application

	return (
		<Section title="Formational details">
			{mentor ? (
				<>
					<Field label="Mentor" value={mentor.mentor_name} />
					<Field label="Mentor email" value={mentor.mentor_email} />
					<Field label="Mentor phone" value={mentor.mentor_mobile} />
					<Field label="Mentor role" value={mentor.current_position} />
					<Field
						label="Mentor church"
						value={[mentor.church, mentor.denomination].filter(Boolean).join(' · ') || null}
					/>
					<div>
						<dt className="text-muted-foreground text-xs font-medium uppercase tracking-wider">
							Mentor consent
						</dt>
						<dd className="mt-0.5">
							{mentor.consented_on ? (
								<Badge variant="success">Received {formatDate(mentor.consented_on)}</Badge>
							) : (
								<Badge variant="muted">Awaiting</Badge>
							)}
						</dd>
					</div>
				</>
			) : (
				<p className="text-muted-foreground text-sm">
					No mentor was recorded on the application.
				</p>
			)}

			<Field label="Church" value={record.church_name} />
			<Field label="Role in church" value={record.current_role} />
			<Field
				label="Ministry experience"
				value={record.years_of_ministry ? `${record.years_of_ministry} years` : null}
			/>
		</Section>
	)
}

/**
 * The admission decision and everything that had to happen around it.
 *
 * The statuses are the thirteen-step checklist as `checklist.board()` derives
 * them -- read here, never stored a second time, so this page cannot disagree
 * with the admissions console about where somebody stands.
 */
function Onboarding({ data }: { data: Detail }) {
	const { student, enrollment, admission } = data

	if (!admission) {
		return (
			<div className="mt-4">
				<Missing title="Enrolment and onboarding" linked={student.admission_application} />
			</div>
		)
	}

	const record = admission.application
	const progress = admission.checklist.progress
	const percent = typeof progress === 'number' ? progress : progress.percent

	return (
		<Card className="mt-4">
			<CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
				<CardTitle className="text-base">Enrolment and onboarding</CardTitle>
				<div className="flex items-center gap-3">
					<Progress value={percent} className="h-2 w-32" />
					<span className="text-muted-foreground text-xs tabular-nums">
						{Math.round(percent)}%
					</span>
					<Badge>{admission.checklist.state}</Badge>
				</div>
			</CardHeader>
			<CardContent className="space-y-5">
				<dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
					<Field label="Application" value={record.name} />
					<Field label="Application received" value={formatDate(record.creation)} />
					<Field label="Intake term" value={record.intake_term} />
					<Field label="Admitted into" value={record.onboard_term} />
					<Field label="Admitted at level" value={record.onboard_level} />
					<Field label="Interview outcome" value={record.interview_outcome} />
					<Field
						label="Entrance exam score"
						value={
							record.qualifying_exam_score == null
								? null
								: String(record.qualifying_exam_score)
						}
					/>
					<Field label="Offer sent" value={formatDate(record.offer_sent_on)} />
					<Field label="Onboarded" value={formatDate(record.enrolled_on)} />
					<Field label="Enrolment date" value={formatDate(enrollment?.enrollment_date)} />
					<Field label="Start term" value={enrollment?.start_term} />
					<Field label="Applicant login" value={record.applicant_user} />
				</dl>

				<div className="flex flex-wrap gap-2">
					<Gate label="Application fee" done={Boolean(record.application_fee_paid)} />
					<Gate label="Documents verified" done={Boolean(record.docs_verified)} />
					<Gate label="Admission fee" done={Boolean(record.admission_fee_paid)} />
					{admission.scholarship && (
						<Badge
							variant={admission.scholarship.status === 'Approved' ? 'success' : 'muted'}
						>
							Scholarship {admission.scholarship.status.toLowerCase()}
							{admission.scholarship.monthly_discount
								? ` · ${money(admission.scholarship.monthly_discount)}/month`
								: ''}
						</Badge>
					)}
				</div>

				<div>
					<div className="text-muted-foreground mb-2 text-xs font-medium uppercase tracking-wider">
						Admission checklist
					</div>
					<ul className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
						{admission.checklist.rows.map((row) => (
							<li key={row.step_no} className="flex items-start gap-2 text-sm">
								{row.done ? (
									<CircleCheck className="text-success mt-0.5 size-4 shrink-0" />
								) : (
									<CircleDashed className="text-muted-foreground mt-0.5 size-4 shrink-0" />
								)}
								<span className="min-w-0 flex-1 truncate">{row.step}</span>
								<span
									className={cn(
										'shrink-0 text-xs',
										row.done ? 'text-success' : 'text-muted-foreground',
									)}
								>
									{row.status || 'Awaiting'}
								</span>
							</li>
						))}
					</ul>
				</div>
			</CardContent>
		</Card>
	)
}

function Academic({ data }: { data: Detail }) {
	const enrollment = data.enrollment

	return (
		<Card className="lg:col-span-2">
			<CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
				<CardTitle className="text-base">Academic record</CardTitle>
				{enrollment && (
					<div className="text-muted-foreground flex gap-4 text-xs">
						<span>
							Credits{' '}
							<b className="text-foreground tabular-nums">{enrollment.credits_earned ?? 0}</b>
						</span>
						<span>
							CGPA{' '}
							<b className="text-foreground tabular-nums">
								{enrollment.cgpa ? enrollment.cgpa.toFixed(2) : '—'}
							</b>
						</span>
						<span>
							Courses{' '}
							<b className="text-foreground tabular-nums">{data.registrations.length}</b>
						</span>
					</div>
				)}
			</CardHeader>
			<CardContent className="p-0 pb-2">
				{data.registrations.length === 0 ? (
					<p className="text-muted-foreground px-5 pb-5 pt-1 text-sm">
						No course registrations yet.
					</p>
				) : (
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead className="pl-5">Course</TableHead>
								<TableHead>Term</TableHead>
								<TableHead>Status</TableHead>
								<TableHead className="text-right">Marks</TableHead>
								<TableHead className="pr-5 text-right">Grade</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{data.registrations.map((row) => (
								<TableRow key={row.name}>
									<TableCell className="pl-5">
										<Link
											to={`/staff/academic/offerings/${encodeURIComponent(row.course_offering)}`}
											className="hover:text-primary transition-colors"
										>
											<div className="font-medium">{row.course_title || row.course}</div>
											<div className="text-muted-foreground font-mono text-xs">
												{row.course}
												{row.level_at_registration && (
													<> · at Level {row.level_at_registration}</>
												)}
											</div>
										</Link>
									</TableCell>
									<TableCell className="text-sm">{row.term}</TableCell>
									<TableCell>
										<Badge variant={row.status === 'Completed' ? 'success' : 'muted'}>
											{row.status}
										</Badge>
									</TableCell>
									<TableCell className="text-right tabular-nums">
										{row.grade ? row.final_marks : '—'}
									</TableCell>
									<TableCell className="pr-5 text-right">
										{row.grade ? (
											<Badge variant={row.passed ? 'success' : 'destructive'}>{row.grade}</Badge>
										) : (
											<span className="text-muted-foreground text-xs">—</span>
										)}
									</TableCell>
								</TableRow>
							))}
						</TableBody>
					</Table>
				)}
			</CardContent>
		</Card>
	)
}

function Fees({ data }: { data: Detail }) {
	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Fees</CardTitle>
			</CardHeader>
			<CardContent className="pt-3">
				<ul className="space-y-1.5 text-sm">
					{data.invoices.map((invoice) => (
						<li key={invoice.name} className="flex items-center justify-between gap-2">
							<span className="min-w-0 truncate">{invoice.fee_type || invoice.category}</span>
							<span className="flex shrink-0 items-center gap-2">
								<span className="tabular-nums">{money(invoice.net_amount)}</span>
								<Badge variant={invoice.status === 'Paid' ? 'success' : 'warning'}>
									{invoice.status}
								</Badge>
							</span>
						</li>
					))}
				</ul>
			</CardContent>
		</Card>
	)
}

function Promotions({ data }: { data: Detail }) {
	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Level history</CardTitle>
			</CardHeader>
			<CardContent className="pt-3">
				{data.promotions.length === 0 ? (
					<p className="text-muted-foreground text-sm">
						No promotions recorded. A level only moves through a Level Promotion, which
						records who approved it and on what evidence.
					</p>
				) : (
					<ul className="space-y-2.5 text-sm">
						{data.promotions.map((row) => (
							<li key={row.name} className="flex items-start gap-2">
								<TrendingUp className="text-success mt-0.5 size-3.5 shrink-0" />
								<div>
									<div>
										Level {row.from_level} → {row.to_level}
									</div>
									<div className="text-muted-foreground text-xs">
										{formatDate(row.approved_on)}
										{row.approved_by && <> · {row.approved_by}</>}
										{' · '}
										{row.courses_passed} courses
									</div>
								</div>
							</li>
						))}
					</ul>
				)}
			</CardContent>
		</Card>
	)
}

function Manuals({ admission }: { admission: StudentAdmission }) {
	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Programme manuals</CardTitle>
			</CardHeader>
			<CardContent className="pt-3">
				<ul className="space-y-2 text-sm">
					{admission.manuals.map((row) => (
						<li key={row.name} className="flex items-start justify-between gap-2">
							<span className="flex min-w-0 items-start gap-2">
								<BookOpen className="text-muted-foreground mt-0.5 size-3.5 shrink-0" />
								<span className="min-w-0 truncate">{row.manual}</span>
							</span>
							{row.acknowledged_on ? (
								<Badge variant="success">{formatDate(row.acknowledged_on)}</Badge>
							) : (
								<Badge variant="muted">Awaiting</Badge>
							)}
						</li>
					))}
				</ul>
			</CardContent>
		</Card>
	)
}

// --- small pieces ----------------------------------------------------------

/** "Passed · 2014", or nothing at all when neither half was answered. */
function completion(status: string | null, year: string | null): string | null {
	return [status, year].filter(Boolean).join(' · ') || null
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">{title}</CardTitle>
			</CardHeader>
			<CardContent className="pt-3">
				<dl className="space-y-3">{children}</dl>
			</CardContent>
		</Card>
	)
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
	return (
		<div>
			<dt className="text-muted-foreground text-xs font-medium uppercase tracking-wider">
				{label}
			</dt>
			<dd className="whitespace-pre-line text-sm">{value || '—'}</dd>
		</div>
	)
}

function Gate({ label, done }: { label: string; done: boolean }) {
	return (
		<Badge variant={done ? 'success' : 'muted'}>
			{done ? <CircleCheck className="size-3.5" /> : <CircleDashed className="size-3.5" />}
			{label}
		</Badge>
	)
}

/**
 * Says which of the two reasons the admission record is absent.
 *
 * "Nothing here" and "not yours to see" are different facts, and a registrar
 * chasing a missing certificate needs to know which one they are looking at.
 */
function Missing({ title, linked }: { title: string; linked: string | null }) {
	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">{title}</CardTitle>
			</CardHeader>
			<CardContent className="pt-3">
				<p className="text-muted-foreground flex items-start gap-2 text-sm">
					<FileText className="mt-0.5 size-4 shrink-0" />
					{linked
						? 'This student came from an admission application your role may not read, so the details it holds are not shown here.'
						: 'This student was created directly rather than admitted through an application, so there is no admission record behind them.'}
				</p>
			</CardContent>
		</Card>
	)
}
