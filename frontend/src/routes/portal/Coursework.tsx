import { Link, useParams } from 'react-router-dom'
import { CircleCheck } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { useCoursework } from '@/hooks/useCoursework'
import type { CourseworkResponse, CourseworkRow } from '@/types'

/**
 * A student's own coursework: what is set, and what came back.
 *
 * An index, the way Canvas's assignments page is an index. Each piece has its
 * own address now, so this lists them and that page holds the instructions,
 * the submission and the mark. It used to carry a hand-in form per row, which
 * meant a course with a dozen assignments rendered a dozen forms nobody had
 * asked for, and gave the same work two places to be handed in from.
 */
export function Coursework() {
	const { name = null } = useParams()
	const registration = name ? decodeURIComponent(name) : null
	const query = useCoursework(registration)

	return (
		<QueryState query={query} title="Coursework">
			{(data) => <Loaded data={data} registration={registration!} />}
		</QueryState>
	)
}

function Loaded({
	data,
	registration,
}: {
	data: CourseworkResponse
	registration: string
}) {
	return (
		<>
			<PageHeader
				title={data.registration.course_title || data.registration.course_offering}
				description={
					data.rows.length === 1
						? '1 piece of work'
						: `${data.rows.length} pieces of work`
				}
			/>

			{data.rows.length === 0 ? (
				<Card>
					<CardContent className="py-14 text-center">
						<div className="font-medium">Nothing set yet</div>
						<p className="text-muted-foreground mt-1 text-sm">
							Work appears here when your teacher publishes it.
						</p>
					</CardContent>
				</Card>
			) : (
				<Card>
					<CardContent className="p-0">
						<ul className="divide-y">
							{data.rows.map((row) => (
								<Row key={row.assignment.name} row={row} registration={registration} />
							))}
						</ul>
					</CardContent>
				</Card>
			)}
		</>
	)
}

function Row({ row, registration }: { row: CourseworkRow; registration: string }) {
	const submission = row.submission
	const marked = submission && submission.posted && submission.score !== undefined

	return (
		<li>
			<Link
				to={`/portal/courses/${encodeURIComponent(registration)}/work/${encodeURIComponent(row.assignment.name)}`}
				className="hover:bg-muted/60 flex flex-wrap items-center gap-3 px-4 py-3"
			>
				<div className="min-w-0 flex-1">
					<div className="truncate text-sm font-medium">{row.assignment.title}</div>
					<div className="text-muted-foreground mt-0.5 text-xs">
						{row.assignment.due_date
							? `Due ${row.assignment.due_date.slice(0, 16).replace('T', ' ')}`
							: 'No due date'}
						{' · '}
						<span className="tabular-nums">{row.assignment.points_possible}</span> points
					</div>
				</div>

				{marked ? (
					<Badge>
						{submission.score} / {row.assignment.points_possible}
					</Badge>
				) : submission ? (
					<Badge variant="secondary">
						<CircleCheck className="mr-1 size-3" /> Handed in
					</Badge>
				) : row.open.open ? (
					<Badge variant="outline">Not handed in</Badge>
				) : (
					<Badge variant="secondary">Closed</Badge>
				)}
			</Link>
		</li>
	)
}
