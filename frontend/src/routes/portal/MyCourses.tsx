import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, BookOpen, CreditCard, LoaderCircle, Plus } from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from '@/components/ui/dialog'
import { Progress } from '@/components/ui/progress'
import { useMyCourses, useWithdraw } from '@/hooks/useStudent'
import { FrappeError } from '@/lib/frappe'
import { cn, money } from '@/lib/utils'
import type { EnrollmentHeader, MyCoursesResponse, Registration } from '@/types'

export function MyCourses() {
	const query = useMyCourses()

	return (
		<QueryState query={query} title="My Courses" emptyWhen={(d) => !d.enrollment}>
			{(data) => <Loaded data={data} />}
		</QueryState>
	)
}

function Loaded({ data }: { data: MyCoursesResponse }) {
	const [withdrawing, setWithdrawing] = useState<Registration | null>(null)
	const enrollment = data.enrollment!
	const registrations = data.registrations

	return (
		<>
			<PageHeader
				title="My Courses"
				description={`${enrollment.program_name || enrollment.program} · Level ${enrollment.current_level}`}
				actions={
					<Button size="sm" asChild>
						<Link to="/portal/courses/register">
							<Plus /> Register
						</Link>
					</Button>
				}
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
						<Button size="sm" className="mt-2" asChild>
							<Link to="/portal/courses/register">Browse courses</Link>
						</Button>
					</CardContent>
				</Card>
			) : (
				<ul className="mt-6 space-y-3">
					{registrations.map((registration) => (
						<CourseRow
							key={registration.name}
							registration={registration}
							onWithdraw={() => setWithdrawing(registration)}
						/>
					))}
				</ul>
			)}

			<WithdrawDialog
				registration={withdrawing}
				onClose={() => setWithdrawing(null)}
			/>
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
			<Stat label="CGPA" value={enrollment.cgpa ? enrollment.cgpa.toFixed(2) : '—'} />
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

const WITHDRAWABLE = ['Registered', 'Active']

function CourseRow({
	registration,
	onWithdraw,
}: {
	registration: Registration
	onWithdraw: () => void
}) {
	const fee = registration.fee
	// The server decides this: whether the fee gates access at all is a site
	// setting the browser cannot see, so working it out here showed a student
	// a bill for a fee that was gating nothing.
	const access = registration.access
	const locked = access ? !access.open : !fee?.settled && !registration.lms_enrollment_created
	const blockedByFee = access ? access.state === 'fee' : locked

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
								<span className="flex items-center gap-1.5">
									<Progress
										value={registration.progress}
										className="w-20"
										aria-label={`${registration.course} progress`}
									/>
									{Math.round(registration.progress)}%
								</span>
							)}
						</div>
					</div>

					<div className="flex items-center gap-2">
						{WITHDRAWABLE.includes(registration.status) && (
							<Button size="sm" variant="ghost" onClick={onWithdraw}>
								Withdraw
							</Button>
						)}
						{locked && blockedByFee ? (
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
						) : locked ? (
							/* Not a money problem. Saying so beats a balance the
							   student can do nothing useful about. */
							<span className="text-muted-foreground text-xs">
								{access?.reason ?? 'This course is still being set up.'}
							</span>
						) : (
							<>
								{/* Open course goes to the player, which resumes where the
								    student left off rather than at the top. Coursework keeps
								    its own entrance because it is what a student checks most
								    often, and the LMS link stays as the fallback for content
								    we cannot render. */}
								<Button size="sm" asChild>
									<Link
										to={`/portal/courses/${encodeURIComponent(registration.name)}/learn`}
									>
										Open course
									</Link>
								</Button>
								<Button size="sm" variant="outline" asChild>
									<Link
										to={`/portal/courses/${encodeURIComponent(registration.name)}/work`}
									>
										Coursework
									</Link>
								</Button>
								{registration.lms_url && (
									<Button size="sm" variant="ghost" asChild>
										<a href={registration.lms_url}>
											In the LMS <ArrowUpRight />
										</a>
									</Button>
								)}
							</>
						)}
					</div>
				</CardContent>
			</Card>
		</li>
	)
}

function WithdrawDialog({
	registration,
	onClose,
}: {
	registration: Registration | null
	onClose: () => void
}) {
	const withdraw = useWithdraw()

	function confirm() {
		if (!registration) return
		withdraw.mutate(registration.name, {
			onSuccess: () => {
				toast.success(`Withdrawn from ${registration.course}`)
				onClose()
			},
			onError: (error) =>
				toast.error(
					error instanceof FrappeError ? error.message : 'That withdrawal was refused.',
				),
		})
	}

	return (
		<Dialog open={Boolean(registration)} onOpenChange={(open) => !open && onClose()}>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>Withdraw from {registration?.course}?</DialogTitle>
					<DialogDescription>
						{registration?.course_title} · {registration?.term}
					</DialogDescription>
				</DialogHeader>

				<p className="text-muted-foreground text-sm">
					Your access to the course closes. A fee already paid is not refunded
					automatically — speak to the Accounts Office about that separately.
				</p>

				<DialogFooter>
					<Button variant="outline" onClick={onClose} disabled={withdraw.isPending}>
						Keep my place
					</Button>
					<Button
						variant="destructive"
						onClick={confirm}
						disabled={withdraw.isPending}
					>
						{withdraw.isPending && <LoaderCircle className="animate-spin" />}
						Withdraw
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
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
