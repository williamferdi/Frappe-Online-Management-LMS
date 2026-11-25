import { useState } from 'react'
import { Link } from 'react-router-dom'
import { GraduationCap } from 'lucide-react'

import { QueryState } from '@/components/QueryState'
import { ceilingNote, ScholarshipLine, termsLabel } from '@/components/TuitionStanding'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from '@/components/ui/table'
import { useTuition } from '@/hooks/useFinance'
import { money } from '@/lib/utils'
import type { TuitionRow } from '@/types'

/**
 * Every active student against their programme's tuition ceiling.
 *
 * Those at the ceiling come first, because they are the ones a student will
 * ask about: billing has stopped and no invoice is coming.
 */
export function FinanceTuition() {
	const query = useTuition()
	const [onlyAtCeiling, setOnlyAtCeiling] = useState(false)

	return (
		<QueryState query={query} title="Tuition">
			{(data) => {
				const rows = onlyAtCeiling
					? data.rows.filter((row) => row.state === 'ceiling_reached')
					: data.rows

				return (
					<>
						<div className="mb-3 flex flex-wrap items-center justify-between gap-2">
							<p className="text-muted-foreground text-sm">
								{data.summary.students} active{' '}
								{data.summary.students === 1 ? 'student' : 'students'} ·{' '}
								<span className="text-foreground font-medium">
									{data.summary.at_ceiling} at the ceiling
								</span>{' '}
								· {data.summary.scholarship_spent} with a scholarship fully used
							</p>
							<Button
								size="sm"
								variant={onlyAtCeiling ? 'default' : 'outline'}
								aria-pressed={onlyAtCeiling}
								onClick={() => setOnlyAtCeiling((value) => !value)}
							>
								At the ceiling only
							</Button>
						</div>

						{rows.length === 0 ? (
							<Card>
								<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
									<GraduationCap className="text-muted-foreground size-6" />
									<div className="font-medium">
										{onlyAtCeiling ? 'Nobody has reached the ceiling' : 'No active students'}
									</div>
									<p className="text-muted-foreground max-w-sm text-sm">
										{onlyAtCeiling
											? 'A student appears here once they have been billed all but less than one month of the programme tuition.'
											: 'Active enrolments appear here with how much tuition each has been billed.'}
									</p>
								</CardContent>
							</Card>
						) : (
							<Card>
								<CardContent className="p-0">
									<Table>
										<TableHeader>
											<TableRow>
												<TableHead className="pl-5">Student</TableHead>
												<TableHead>Programme</TableHead>
												<TableHead className="min-w-56">Tuition billed</TableHead>
												<TableHead>Scholarship</TableHead>
												<TableHead className="pr-5">Billing</TableHead>
											</TableRow>
										</TableHeader>
										<TableBody>
											{rows.map((row) => (
												<Row key={row.enrollment} row={row} />
											))}
										</TableBody>
									</Table>
								</CardContent>
							</Card>
						)}
					</>
				)
			}}
		</QueryState>
	)
}

function Row({ row }: { row: TuitionRow }) {
	const reached = row.state === 'ceiling_reached'
	const percent = row.ceiling > 0 ? Math.min((row.billed / row.ceiling) * 100, 100) : 0

	return (
		<TableRow>
			<TableCell className="pl-5">
				<Link
					to={`/staff/students/${encodeURIComponent(row.student)}`}
					className="font-medium hover:underline"
				>
					{row.student_name || row.student}
				</Link>
				<div className="text-muted-foreground font-mono text-xs">{row.student}</div>
			</TableCell>
			<TableCell className="text-sm">
				{row.program}
				<div className="text-muted-foreground text-xs">Level {row.level}</div>
			</TableCell>
			<TableCell>
				{row.state === 'uncapped' ? (
					<div className="text-sm tabular-nums">
						{money(row.billed)}
						<div className="text-muted-foreground text-xs">No ceiling · {termsLabel(row.terms_billed)}</div>
					</div>
				) : (
					<div>
						<div className="mb-1 flex justify-between gap-3 text-xs tabular-nums">
							<span>
								{money(row.billed)} of {money(row.ceiling)}
							</span>
							<span className="text-muted-foreground">{termsLabel(row.terms_billed)}</span>
						</div>
						<Progress value={percent} />
					</div>
				)}
			</TableCell>
			<TableCell className="text-sm">
				{row.scholarship ? <ScholarshipLine scholarship={row.scholarship} /> : '—'}
			</TableCell>
			<TableCell className="pr-5">
				{reached ? (
					<div>
						<Badge variant="warning">Ceiling reached</Badge>
						<div className="text-muted-foreground mt-1 max-w-48 text-xs">{ceilingNote(row)}</div>
					</div>
				) : (
					<Badge variant="muted">{row.state === 'uncapped' ? 'Uncapped' : 'Billing'}</Badge>
				)}
			</TableCell>
		</TableRow>
	)
}
