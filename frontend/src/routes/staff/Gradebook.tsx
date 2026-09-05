import { Link } from 'react-router-dom'

import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { useGradebook } from '@/hooks/useMarking'
import { cn } from '@/lib/utils'
import type { GradebookGrid, SubmissionSummary } from '@/types'

/**
 * The class against the work: one row per student, one column per assignment.
 *
 * The totals come from the same registration rows the grade sheet reads, not
 * from adding the cells up here -- a gradebook that computes its own total is
 * a gradebook that can disagree with the transcript.
 */
export function Gradebook({ offering }: { offering: string }) {
	const query = useGradebook(offering)

	return (
		<QueryState query={query} title="Gradebook">
			{(data) => <Grid data={data} offering={offering} />}
		</QueryState>
	)
}

function Grid({ data, offering }: { data: GradebookGrid; offering: string }) {
	if (data.rows.length === 0) {
		return (
			<Card>
				<CardContent className="py-14 text-center">
					<div className="font-medium">Nobody is registered</div>
					<p className="text-muted-foreground mt-1 text-sm">
						The gradebook fills in as students register and work is marked.
					</p>
				</CardContent>
			</Card>
		)
	}

	return (
		<Card>
			{/* Wide tables scroll inside their own box; the page never scrolls
			    sideways. */}
			<div className="overflow-x-auto">
				<table className="w-full text-sm">
					<thead>
						<tr className="border-b">
							<th className="bg-card sticky left-0 px-3 py-2 text-left font-medium">
								Student
							</th>
							{data.assignments.map((assignment) => (
								<th key={assignment.name} className="px-3 py-2 text-left font-medium">
									<Link
										to={`/staff/courses/${encodeURIComponent(offering)}/grade/${encodeURIComponent(assignment.name)}`}
										className="hover:underline"
									>
										<span className="block max-w-32 truncate">{assignment.title}</span>
										<span className="text-muted-foreground text-[10px] font-normal">
											{assignment.component} · {assignment.points_possible}
											{!assignment.published && ' · draft'}
										</span>
									</Link>
								</th>
							))}
							<th className="px-3 py-2 text-right font-medium">Total</th>
							<th className="px-3 py-2 text-left font-medium">Grade</th>
						</tr>
					</thead>
					<tbody>
						{data.rows.map((row) => (
							<tr key={row.course_registration} className="border-b last:border-0">
								<td className="bg-card sticky left-0 px-3 py-2 whitespace-nowrap">
									{row.student_name}
								</td>
								{data.assignments.map((assignment) => (
									<td key={assignment.name} className="px-3 py-2 tabular-nums">
										<Cell
											cell={row.cells[assignment.name]}
											possible={assignment.points_possible}
										/>
									</td>
								))}
								<td className="px-3 py-2 text-right tabular-nums">
									{row.final_marks === null || row.final_marks === undefined
										? '—'
										: row.final_marks}
								</td>
								<td className="px-3 py-2">
									{row.grade ? (
										<Badge variant={row.passed ? 'default' : 'destructive'}>
											{row.grade}
										</Badge>
									) : (
										<span className="text-muted-foreground text-xs">not final</span>
									)}
								</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>

			{data.scheme && (
				<CardContent className="text-muted-foreground border-t pt-3 text-xs">
					Weighted as{' '}
					{data.scheme
						.map((row) => `${row.component} ${row.weight_pct}%`)
						.join(' · ')}
				</CardContent>
			)}
		</Card>
	)
}

/**
 * A cell says three different things and must not blur them: nothing handed
 * in, handed in but unmarked, and a mark — which is itself either held back or
 * posted.
 */
function Cell({
	cell,
	possible,
}: {
	cell: SubmissionSummary | null | undefined
	possible: number
}) {
	if (!cell) return <span className="text-muted-foreground">—</span>
	if (cell.excused) return <span className="text-muted-foreground text-xs">excused</span>
	if (!cell.scored) return <span className="text-amber-600 text-xs">to mark</span>

	return (
		<span className={cn(!cell.posted && 'text-muted-foreground')}>
			{cell.score}
			<span className="text-muted-foreground text-xs">/{possible}</span>
			{!cell.posted && <span className="ml-1 text-[10px] uppercase">held</span>}
		</span>
	)
}
