import { AlertCircle, ArrowUpRight, BookOpen, CreditCard, GraduationCap } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useMyCourses } from '@/hooks/useMyCourses'
import { FrappeError } from '@/lib/frappe'
import { cn, money } from '@/lib/utils'
import type { EnrollmentHeader, Registration } from '@/types'

export function MyCourses() {
	const { data, isPending, error } = useMyCourses()

	if (isPending) return <LoadingState />
	if (error) return <ErrorState error={error} />

	const enrollment = data?.enrollment ?? null
	const registrations = data?.registrations ?? []

	if (!enrollment) return <NoEnrollment />

	return (
		<>
			<PageHeader
				title="My Courses"
				description={`${enrollment.program_name || enrollment.program} · Level ${enrollment.current_level}`}
			/>

			<Summary enrollment={enrollment} registrations={registrations} />

			{registrations.length === 0 ? (
				<Card className="mt-6">
					<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
						<BookOpen className="text-muted-foreground size-6" />
						<div className="font-medium">No registrations yet</div>
						<p className="text-muted-foreground max-w-sm text-sm">
							When registration opens for a term, the courses you are eligible for
							will appear here.
						</p>
					</CardContent>
				</Card>
			) : (
				<ul className="mt-6 space-y-3">
					{registrations.map((registration) => (
						<CourseRow key={registration.name} registration={registration} />
					))}
				</ul>
			)}
		</>
	)
}

function Summary({
	enrollment,
	registrations,
}: {
	enrollment: EnrollmentHeader
	registrations: Registration[]
}) {
	const active = registrations.filter((r) =>
		['Registered', 'Active'].includes(r.status),
	).length
	const owed = registrations.reduce((total, r) => total + (r.fee?.outstanding ?? 0), 0)

	return (
		<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
			<Stat label="Level" value={enrollment.current_level} />
			<Stat label="Credits earned" value={String(enrollment.credits_earned ?? 0)} />
			<Stat
				label="CGPA"
				value={enrollment.cgpa ? enrollment.cgpa.toFixed(2) : '—'}
			/>
			<Stat
				label={owed > 0 ? 'Outstanding' : 'In progress'}
				value={owed > 0 ? money(owed) : String(active)}
				tone={owed > 0 ? 'warning' : 'default'}
			/>
		</div>
	)
}

function Stat({
	label,
	value,
	tone = 'default',
}: {
	label: string
	value: string
	tone?: 'default' | 'warning'
}) {
	return (
		<Card>
			<CardContent className="p-4">
				<div className="text-muted-foreground text-xs font-medium uppercase tracking-wider">
					{label}
				</div>
				<div
					className={cn(
						'mt-1 text-2xl font-semibold tabular-nums',
						tone === 'warning' && 'text-warning-foreground',
					)}
				>
					{value}
				</div>
			</CardContent>
		</Card>
	)
}

function CourseRow({ registration }: { registration: Registration }) {
	const fee = registration.fee
	const locked = !fee?.settled && !registration.lms_enrollment_created

	return (
		<li>
			<Card>
				<CardContent className="flex flex-wrap items-center gap-4 p-4">
					<div className="min-w-0 flex-1">
						<div className="flex flex-wrap items-center gap-2">
							<span className="font-mono text-xs font-semibold tracking-wide">
								{registration.course}
							</span>
							<Badge variant="muted">{registration.term}</Badge>
							<StatusBadge status={registration.status} />
							{registration.grade && (
								<Badge variant={registration.passed ? 'success' : 'destructive'}>
									{registration.grade}
								</Badge>
							)}
						</div>
						<div className="mt-1 truncate font-medium">
							{registration.course_title || registration.course}
						</div>
						<div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
							<span>{registration.credits} credits</span>
							{registration.lms_course && (
								<span className="flex items-center gap-1">
									<span
										className="bg-muted h-1.5 w-20 overflow-hidden rounded-full"
										role="progressbar"
										aria-valuenow={Math.round(registration.progress)}
										aria-valuemin={0}
										aria-valuemax={100}
									>
										<span
											className="bg-primary block h-full rounded-full"
											style={{ width: `${Math.min(registration.progress, 100)}%` }}
										/>
									</span>
									{Math.round(registration.progress)}%
								</span>
							)}
						</div>
					</div>

					<div className="flex items-center gap-2">
						{locked ? (
							<>
								<span className="text-warning-foreground flex items-center gap-1.5 text-xs font-medium">
									<CreditCard className="size-3.5" />
									{fee?.outstanding ? money(fee.outstanding) : fee?.label}
								</span>
								{fee?.payment_link && (
									<Button size="sm" asChild>
										<a href={fee.payment_link}>Pay now</a>
									</Button>
								)}
							</>
						) : registration.lms_url ? (
							<Button size="sm" variant="outline" asChild>
								<a href={registration.lms_url}>
									Open course <ArrowUpRight />
								</a>
							</Button>
						) : (
							<span className="text-muted-foreground text-xs">Not yet opened</span>
						)}
					</div>
				</CardContent>
			</Card>
		</li>
	)
}

const STATUS_TONE: Record<string, 'default' | 'success' | 'muted' | 'destructive'> = {
	Registered: 'default',
	Active: 'default',
	Completed: 'success',
	Withdrawn: 'muted',
	Dropped: 'destructive',
}

function StatusBadge({ status }: { status: string }) {
	return <Badge variant={STATUS_TONE[status] ?? 'muted'}>{status}</Badge>
}

function NoEnrollment() {
	return (
		<>
			<PageHeader title="My Courses" />
			<Card>
				<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
					<GraduationCap className="text-muted-foreground size-6" />
					<div className="font-medium">No active enrollment</div>
					<p className="text-muted-foreground max-w-sm text-sm">
						Your account is not linked to an active programme enrolment yet. The
						Registrar's office will complete this once your admission is confirmed.
					</p>
				</CardContent>
			</Card>
		</>
	)
}

function LoadingState() {
	return (
		<>
			<PageHeader title="My Courses" />
			<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
				{Array.from({ length: 4 }, (_, i) => (
					<Skeleton key={i} className="h-[5.25rem]" />
				))}
			</div>
			<div className="mt-6 space-y-3">
				{Array.from({ length: 3 }, (_, i) => (
					<Skeleton key={i} className="h-[6.5rem]" />
				))}
			</div>
		</>
	)
}

function ErrorState({ error }: { error: unknown }) {
	const message =
		error instanceof FrappeError ? error.message : 'Something went wrong loading your courses.'
	return (
		<>
			<PageHeader title="My Courses" />
			<Card>
				<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
					<AlertCircle className="text-destructive size-6" />
					<div className="font-medium">Could not load your courses</div>
					<p className="text-muted-foreground max-w-sm text-sm">{message}</p>
					<Button
						variant="outline"
						size="sm"
						className="mt-1"
						onClick={() => window.location.reload()}
					>
						Try again
					</Button>
				</CardContent>
			</Card>
		</>
	)
}
