import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, CalendarClock, CircleCheck, Info, LoaderCircle, Lock } from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from '@/components/ui/dialog'
import { useRegister, useRegistrationOptions } from '@/hooks/useStudent'
import { FrappeError } from '@/lib/frappe'
import { formatDate, formatTime } from '@/lib/utils'
import type { Offering, RegistrationOptions } from '@/types'

export function Register() {
	const query = useRegistrationOptions()

	return (
		<QueryState query={query} title="Register for courses" emptyWhen={(d) => !d.enrollment}>
			{(data) => <Loaded data={data} />}
		</QueryState>
	)
}

function Loaded({ data }: { data: RegistrationOptions }) {
	const [chosen, setChosen] = useState<Offering | null>(null)
	const enrollment = data.enrollment!
	const nothingOpen = data.terms.length === 0

	return (
		<>
			<PageHeader
				title="Register for courses"
				description={`Level ${enrollment.current_level} · ${enrollment.program_name || enrollment.program}`}
				actions={
					<Button variant="outline" size="sm" asChild>
						<Link to="/portal/courses">
							<ArrowLeft /> My courses
						</Link>
					</Button>
				}
			/>

			{nothingOpen && (
				<Card>
					<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
						<CalendarClock className="text-muted-foreground size-6" />
						<div className="font-medium">Registration is closed</div>
						<p className="text-muted-foreground max-w-sm text-sm">
							No term is currently accepting registrations. The office announces each
							window before it opens.
						</p>
					</CardContent>
				</Card>
			)}

			{data.terms.map((term) => (
				<Card key={term.term} className="mb-6">
					<CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
						<div>
							<CardTitle className="text-base">{term.term_name}</CardTitle>
							<div className="text-muted-foreground mt-0.5 text-xs">
								{formatDate(term.start_date)} – {formatDate(term.end_date)}
								{term.registration_closes &&
									` · registration closes ${formatDate(term.registration_closes)}`}
							</div>
						</div>
						<Badge variant={term.eligible_count ? 'default' : 'muted'}>
							{term.eligible_count} available to you
						</Badge>
					</CardHeader>
					<CardContent className="space-y-2 pt-3">
						{term.rows.map((offering) => (
							<OfferingRow
								key={offering.name}
								offering={offering}
								onChoose={() => setChosen(offering)}
							/>
						))}
					</CardContent>
				</Card>
			))}

			<ConfirmDialog offering={chosen} onClose={() => setChosen(null)} />
		</>
	)
}

function OfferingRow({
	offering,
	onChoose,
}: {
	offering: Offering
	onChoose: () => void
}) {
	const { allowed, reason, warnings } = offering.eligibility
	const seatsLeft =
		offering.capacity != null
			? Math.max(0, offering.capacity - (offering.enrolled_count ?? 0))
			: null

	return (
		<div className="flex flex-wrap items-center gap-4 rounded-lg border p-3.5">
			<div className="min-w-0 flex-1">
				<div className="flex flex-wrap items-center gap-2">
					<span className="font-mono text-xs font-semibold">{offering.course}</span>
					{offering.course_level && (
						<Badge variant="muted">Level {offering.course_level}</Badge>
					)}
					{offering.format && <Badge variant="secondary">{offering.format}</Badge>}
					{offering.already_registered && <Badge variant="success">Registered</Badge>}
				</div>
				<div className="mt-1 truncate font-medium">
					{offering.course_title || offering.course}
				</div>
				<div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-3 text-xs">
					<span>{offering.credits} credits</span>
					{offering.zoom_time && <span>{formatTime(offering.zoom_time)}</span>}
					{seatsLeft != null && (
						<span>
							{seatsLeft} of {offering.capacity} seats left
						</span>
					)}
				</div>

				{/* Why not, in the student's own words -- this is the question the
				    Registrar otherwise answers by email, one applicant at a time. */}
				{!allowed && reason && (
					<div className="text-muted-foreground mt-2 flex items-start gap-1.5 text-xs">
						<Lock className="mt-0.5 size-3 shrink-0" />
						<span>{reason}</span>
					</div>
				)}
				{allowed && warnings?.length > 0 && (
					<div className="text-warning-foreground mt-2 flex items-start gap-1.5 text-xs">
						<Info className="mt-0.5 size-3 shrink-0" />
						<span>{warnings.join(' ')}</span>
					</div>
				)}
			</div>

			<Button size="sm" disabled={!allowed} onClick={onChoose}>
				{allowed ? 'Register' : 'Unavailable'}
			</Button>
		</div>
	)
}

function ConfirmDialog({
	offering,
	onClose,
}: {
	offering: Offering | null
	onClose: () => void
}) {
	const register = useRegister()

	function confirm() {
		if (!offering) return
		register.mutate(offering.name, {
			onSuccess: () => {
				toast.success(`Registered for ${offering.course}`, {
					description: 'The course opens once the registration fee is settled.',
				})
				onClose()
			},
			onError: (error) =>
				toast.error(
					error instanceof FrappeError ? error.message : 'That registration was refused.',
				),
		})
	}

	return (
		<Dialog open={Boolean(offering)} onOpenChange={(open) => !open && onClose()}>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>Register for {offering?.course}?</DialogTitle>
					<DialogDescription>
						{offering?.course_title} · {offering?.term} · {offering?.credits} credits
					</DialogDescription>
				</DialogHeader>

				<Alert variant="info">
					<CircleCheck />
					<AlertDescription>
						A registration fee is raised when you confirm. The course opens in the
						learning system once that fee is settled.
					</AlertDescription>
				</Alert>

				<DialogFooter>
					<Button variant="outline" onClick={onClose} disabled={register.isPending}>
						Cancel
					</Button>
					<Button onClick={confirm} disabled={register.isPending}>
						{register.isPending && <LoaderCircle className="animate-spin" />}
						Confirm registration
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	)
}
