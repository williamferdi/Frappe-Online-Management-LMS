import { Link } from 'react-router-dom'
import { ArrowRight, TriangleAlert } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { useConsoleDashboard } from '@/hooks/useStaff'
import { boot } from '@/lib/frappe'
import { cn, formatDate, money } from '@/lib/utils'
import type { AcademicPanel, ConsoleDashboard, FinancePanel, Funnel } from '@/types'

const STATE_TONE: Record<string, string> = {
	Draft: 'bg-muted-foreground/40',
	'In Review': 'bg-primary',
	Admitted: 'bg-success',
	Onboarded: 'bg-success',
	Rejected: 'bg-destructive',
	Withdrawn: 'bg-muted-foreground/30',
}

export function StaffDashboard() {
	const query = useConsoleDashboard()

	return (
		<QueryState query={query} title="Overview">
			{(data) => <Loaded data={data} />}
		</QueryState>
	)
}

function Loaded({ data }: { data: ConsoleDashboard }) {
	const { admissions, academic, finance } = data.panels
	const firstName = boot.full_name.split(' ')[0]

	return (
		<>
			<PageHeader
				title={`Good day, ${firstName}`}
				description="Where the college stands this morning"
			/>

			{Object.keys(data.panels).length === 0 && (
				<Card>
					<CardContent className="py-14 text-center">
						<div className="font-medium">Nothing to show</div>
						<p className="text-muted-foreground mx-auto mt-1 max-w-sm text-sm">
							Your roles do not give you access to admissions, academic records or
							finance. Speak to the Registrar if that looks wrong.
						</p>
					</CardContent>
				</Card>
			)}

			{admissions && <Admissions funnel={admissions} />}

			<div className="mt-4 grid gap-4 lg:grid-cols-2">
				{academic && <Academic panel={academic} />}
				{finance && <Finance panel={finance} />}
			</div>
		</>
	)
}

function Admissions({ funnel }: { funnel: Funnel }) {
	const total = funnel.total || 1

	return (
		<Card>
			<CardHeader className="flex-row items-center justify-between">
				<CardTitle className="text-base">Admissions</CardTitle>
				<Button variant="ghost" size="sm" asChild>
					<Link to="/staff/admissions">
						Pipeline <ArrowRight />
					</Link>
				</Button>
			</CardHeader>
			<CardContent className="pt-3">
				<div className="flex items-baseline gap-2">
					<span className="text-3xl font-semibold tabular-nums">{funnel.total}</span>
					<span className="text-muted-foreground text-sm">
						applications · {funnel.live} still in progress
					</span>
				</div>

				{/* One bar, segmented by state -- six separate counters make the
				    reader do the arithmetic to see the shape of the intake. */}
				<div className="bg-muted mt-3 flex h-2 overflow-hidden rounded-full">
					{funnel.by_state
						.filter((row) => row.count > 0)
						.map((row) => (
							<div
								key={row.state}
								className={cn('h-full', STATE_TONE[row.state] ?? 'bg-muted-foreground/40')}
								style={{ width: `${(row.count / total) * 100}%` }}
								title={`${row.state}: ${row.count}`}
							/>
						))}
				</div>
				<div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
					{funnel.by_state.map((row) => (
						<span key={row.state} className="text-muted-foreground flex items-center gap-1.5 text-xs">
							<span
								className={cn(
									'size-1.5 rounded-full',
									STATE_TONE[row.state] ?? 'bg-muted-foreground/40',
								)}
							/>
							{row.state}
							<span className="text-foreground font-medium tabular-nums">{row.count}</span>
						</span>
					))}
				</div>

				{funnel.stuck.length > 0 && (
					<div className="mt-5 border-t pt-4">
						<div className="mb-2 text-sm font-medium">Waiting on</div>
						<p className="text-muted-foreground mb-3 text-xs">
							Steps outstanding across the {funnel.live} live applications. This is
							the morning&rsquo;s work.
						</p>
						<ul className="space-y-1.5">
							{funnel.stuck.slice(0, 6).map((row) => (
								<li key={row.step_no} className="flex items-center gap-3 text-sm">
									<span className="w-8 shrink-0 text-right font-semibold tabular-nums">
										{row.waiting}
									</span>
									<span className="min-w-0 flex-1 truncate">{row.step}</span>
									<Badge variant="muted">{row.owner_role}</Badge>
								</li>
							))}
						</ul>
					</div>
				)}
			</CardContent>
		</Card>
	)
}

function Academic({ panel }: { panel: AcademicPanel }) {
	const peak = Math.max(1, ...panel.by_level.map((row) => row.count))

	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Academic</CardTitle>
			</CardHeader>
			<CardContent className="pt-3">
				<div className="grid grid-cols-2 gap-4">
					<Figure label="Active students" value={String(panel.students)} />
					<Figure label="Enrolments" value={String(panel.enrollments)} />
				</div>

				<div className="mt-5">
					<div className="text-muted-foreground mb-2 text-xs font-medium uppercase tracking-wider">
						By level
					</div>
					<ul className="space-y-1.5">
						{panel.by_level.map((row) => (
							<li key={row.level} className="flex items-center gap-3 text-sm">
								<span className="text-muted-foreground w-12 shrink-0">Level {row.level}</span>
								<div className="bg-muted h-1.5 flex-1 overflow-hidden rounded-full">
									<div
										className="bg-primary h-full rounded-full"
										style={{ width: `${(row.count / peak) * 100}%` }}
									/>
								</div>
								<span className="w-6 text-right tabular-nums">{row.count}</span>
							</li>
						))}
					</ul>
				</div>

				{panel.open_terms.length > 0 && (
					<div className="mt-5 border-t pt-4">
						<div className="text-muted-foreground mb-2 text-xs font-medium uppercase tracking-wider">
							Open terms
						</div>
						{panel.open_terms.map((term) => (
							<div key={term.name} className="flex items-center justify-between text-sm">
								<span>{term.term_name}</span>
								<span className="text-muted-foreground text-xs">
									{term.registration_closes
										? `closes ${formatDate(term.registration_closes)}`
										: 'open'}
								</span>
							</div>
						))}
					</div>
				)}
			</CardContent>
		</Card>
	)
}

function Finance({ panel }: { panel: FinancePanel }) {
	const collectedPct = panel.billed > 0 ? (panel.collected / panel.billed) * 100 : 0

	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Finance</CardTitle>
			</CardHeader>
			<CardContent className="pt-3">
				<div className="grid grid-cols-2 gap-4">
					<Figure label="Collected" value={money(panel.collected)} />
					<Figure label="Outstanding" value={money(panel.outstanding)} />
				</div>

				<div className="mt-4">
					<div className="text-muted-foreground mb-1.5 flex items-center justify-between text-xs">
						<span>{money(panel.billed)} billed</span>
						<span className="tabular-nums">{Math.round(collectedPct)}% collected</span>
					</div>
					<Progress value={collectedPct} />
				</div>

				{panel.overdue_count > 0 && (
					<div className="bg-destructive/8 text-destructive mt-4 flex items-center gap-2 rounded-lg px-3 py-2 text-sm">
						<TriangleAlert className="size-4 shrink-0" />
						<span>
							<span className="font-semibold">{money(panel.overdue)}</span> overdue
							across {panel.overdue_count}{' '}
							{panel.overdue_count === 1 ? 'invoice' : 'invoices'}
						</span>
					</div>
				)}

				{panel.by_category.length > 0 && (
					<div className="mt-5 border-t pt-4">
						<div className="text-muted-foreground mb-2 text-xs font-medium uppercase tracking-wider">
							Outstanding by type
						</div>
						<ul className="space-y-1">
							{panel.by_category.slice(0, 5).map((row) => (
								<li key={row.category} className="flex items-center justify-between text-sm">
									<span className="truncate">{row.category}</span>
									<span className="tabular-nums">{money(row.outstanding)}</span>
								</li>
							))}
						</ul>
					</div>
				)}

				<div className="mt-5 border-t pt-4">
					<div className="text-muted-foreground mb-2 text-xs font-medium uppercase tracking-wider">
						Payments, last {panel.days} days
					</div>
					{panel.recent_payments.length === 0 ? (
						<p className="text-muted-foreground text-sm">Nothing received.</p>
					) : (
						<ul className="space-y-1">
							{panel.recent_payments.map((payment) => (
								<li key={payment.name} className="flex items-center justify-between text-sm">
									<span className="min-w-0 truncate">
										{payment.student_name || payment.name}
										<span className="text-muted-foreground ml-2 text-xs">
											{payment.mode}
										</span>
									</span>
									<span className="tabular-nums">{money(payment.amount)}</span>
								</li>
							))}
						</ul>
					)}
				</div>
			</CardContent>
		</Card>
	)
}

function Figure({ label, value }: { label: string; value: string }) {
	return (
		<div>
			<div className="text-muted-foreground text-xs font-medium uppercase tracking-wider">
				{label}
			</div>
			<div className="mt-0.5 text-2xl font-semibold tabular-nums">{value}</div>
		</div>
	)
}
