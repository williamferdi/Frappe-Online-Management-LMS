import { Link } from 'react-router-dom'
import {
	ArrowRight,
	ArrowUpRight,
	BookOpen,
	CalendarClock,
	CreditCard,
	GraduationCap,
} from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { useDashboard } from '@/hooks/useStudent'
import { boot } from '@/lib/frappe'
import { formatDate, money } from '@/lib/utils'
import type { DashboardResponse } from '@/types'

export function Dashboard() {
	const query = useDashboard()

	return (
		<QueryState query={query} title="Dashboard" emptyWhen={(d) => !d.enrollment}>
			{(data) => <Loaded data={data} />}
		</QueryState>
	)
}

function Loaded({ data }: { data: DashboardResponse }) {
	const enrollment = data.enrollment!
	const fees = data.fees
	const registration = data.registration
	const firstName = (enrollment.student_name || boot.full_name).split(' ')[0]

	return (
		<>
			<PageHeader
				title={`Welcome back, ${firstName}`}
				description={`${enrollment.program_name || enrollment.program} · Level ${enrollment.current_level}`}
			/>

			<Attention data={data} />

			<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
				<Stat label="Level" value={enrollment.current_level} />
				<Stat label="Credits earned" value={String(enrollment.credits_earned ?? 0)} />
				<Stat label="CGPA" value={enrollment.cgpa ? enrollment.cgpa.toFixed(2) : '—'} />
				<Stat
					label="Courses in progress"
					value={String(data.in_progress_count ?? 0)}
				/>
			</div>

			<div className="mt-6 grid gap-4 lg:grid-cols-3">
				<Card className="lg:col-span-2">
					<CardHeader className="flex-row items-center justify-between">
						<CardTitle className="text-base">In progress</CardTitle>
						<Button variant="ghost" size="sm" asChild>
							<Link to="/portal/courses">
								All courses <ArrowRight />
							</Link>
						</Button>
					</CardHeader>
					<CardContent className="pt-3">
						{data.in_progress?.length ? (
							<ul className="space-y-4">
								{data.in_progress.map((course) => (
									<li key={course.name}>
										<div className="flex items-center justify-between gap-3">
											<div className="min-w-0">
												<div className="truncate text-sm font-medium">
													{course.course_title || course.course}
												</div>
												<div className="text-muted-foreground text-xs">
													{course.course} · {course.term}
												</div>
											</div>
											{course.lms_url && course.fee?.settled ? (
												<Button size="sm" variant="outline" asChild>
													<a href={course.lms_url}>
														Open <ArrowUpRight />
													</a>
												</Button>
											) : (
												<Badge variant="warning">Payment pending</Badge>
											)}
										</div>
										<Progress value={course.progress} className="mt-2" />
									</li>
								))}
							</ul>
						) : (
							<Empty
								icon={BookOpen}
								text="Nothing in progress. Register for a course to get started."
							/>
						)}
					</CardContent>
				</Card>

				<div className="space-y-4">
					<Card>
						<CardHeader>
							<CardTitle className="text-base">Recent grades</CardTitle>
						</CardHeader>
						<CardContent className="pt-3">
							{data.recent_grades?.length ? (
								<ul className="space-y-2.5">
									{data.recent_grades.map((row) => (
										<li key={row.name} className="flex items-center justify-between gap-2">
											<div className="min-w-0">
												<div className="truncate text-sm">
													{row.course_title || row.course}
												</div>
												<div className="text-muted-foreground text-xs">{row.term}</div>
											</div>
											<Badge variant={row.passed ? 'success' : 'destructive'}>
												{row.grade}
											</Badge>
										</li>
									))}
								</ul>
							) : (
								<Empty icon={GraduationCap} text="No grades yet." />
							)}
						</CardContent>
					</Card>

					{registration?.terms?.length ? (
						<Card>
							<CardHeader>
								<CardTitle className="text-base">Registration</CardTitle>
							</CardHeader>
							<CardContent className="space-y-3 pt-3">
								{registration.terms.map((term) => (
									<div key={term.name} className="text-sm">
										<div className="font-medium">{term.term_name}</div>
										<div className="text-muted-foreground text-xs">
											{term.registration_closes
												? `Closes ${formatDate(term.registration_closes)}` +
													(term.closes_in_days !== null && term.closes_in_days >= 0
														? ` · ${term.closes_in_days} days left`
														: '')
												: 'Open'}
										</div>
									</div>
								))}
								<Button size="sm" className="w-full" asChild>
									<Link to="/portal/courses/register">
										{registration.eligible_count} available to you
										<ArrowRight />
									</Link>
								</Button>
							</CardContent>
						</Card>
					) : null}
				</div>
			</div>

			{fees && fees.count > 0 && (
				<Card className="mt-4">
					<CardHeader>
						<CardTitle className="text-base">Outstanding fees</CardTitle>
					</CardHeader>
					<CardContent className="pt-3">
						<ul className="divide-y">
							{fees.open.map((fee) => (
								<li
									key={fee.name}
									className="flex flex-wrap items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0"
								>
									<div className="min-w-0">
										<div className="text-sm font-medium">
											{fee.fee_type || fee.category}
										</div>
										<div className="text-muted-foreground text-xs">
											{fee.term ? `${fee.term} · ` : ''}
											{fee.due_date ? `Due ${formatDate(fee.due_date)}` : 'No due date'}
											{fee.overdue && ' · overdue'}
										</div>
									</div>
									<div className="flex items-center gap-3">
										<span className="text-sm font-semibold tabular-nums">
											{money(fee.outstanding_amount)}
										</span>
										{fee.payment_link && (
											<Button size="sm" asChild>
												<a href={fee.payment_link}>Pay</a>
											</Button>
										)}
									</div>
								</li>
							))}
						</ul>
					</CardContent>
				</Card>
			)}
		</>
	)
}

/** The one block that earns the top of the page: what is actually blocking. */
function Attention({ data }: { data: DashboardResponse }) {
	const overdue = data.fees?.overdue_count ?? 0
	const unpaid = data.fees?.count ?? 0
	const blocked = data.in_progress?.filter((c) => !c.fee?.settled).length ?? 0

	if (!unpaid && !blocked) return null

	return (
		<Alert variant={overdue ? 'destructive' : 'warning'} className="mb-5">
			<CreditCard />
			<div className="min-w-0">
				<AlertTitle>
					{overdue
						? `${overdue} overdue ${overdue === 1 ? 'payment' : 'payments'}`
						: `${money(data.fees?.outstanding ?? 0)} outstanding`}
				</AlertTitle>
				<AlertDescription>
					{blocked > 0
						? `${blocked} ${blocked === 1 ? 'course stays' : 'courses stay'} closed until the fee is settled.`
						: 'Settle it from the list below to keep your registration active.'}
				</AlertDescription>
			</div>
		</Alert>
	)
}

function Stat({ label, value }: { label: string; value: string }) {
	return (
		<Card>
			<CardContent className="p-4">
				<div className="text-muted-foreground text-xs font-medium uppercase tracking-wider">
					{label}
				</div>
				<div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
			</CardContent>
		</Card>
	)
}

function Empty({
	icon: Icon,
	text,
}: {
	icon: typeof BookOpen | typeof CalendarClock
	text: string
}) {
	return (
		<div className="text-muted-foreground flex flex-col items-center gap-2 py-6 text-center text-sm">
			<Icon className="size-5" />
			{text}
		</div>
	)
}
