import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen, CircleCheck, CircleDashed } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { useCourses } from '@/hooks/useCourses'
import type { CoursesResponse, CourseShelfRow } from '@/types'

/**
 * The shelf: every course this user may build.
 *
 * Scoped on the server, not here -- a teacher sees the runs they teach and a
 * coordinator sees all of them, and the front end is told the answer rather
 * than deciding it.
 */
export function Courses() {
	const [term, setTerm] = useState<string | null>(null)
	const query = useCourses(term)

	return (
		<QueryState query={query} title="Courses">
			{(data) => <Loaded data={data} term={term} onTerm={setTerm} />}
		</QueryState>
	)
}

function Loaded({
	data,
	term,
	onTerm,
}: {
	data: CoursesResponse
	term: string | null
	onTerm: (term: string | null) => void
}) {
	return (
		<>
			<PageHeader
				title="Courses"
				description={
					data.rows.length === 1
						? '1 run of a course'
						: `${data.rows.length} runs of a course`
				}
				actions={
					<select
						className="border-input bg-background h-9 rounded-md border px-3 text-sm"
						value={term ?? ''}
						onChange={(event) => onTerm(event.target.value || null)}
						aria-label="Term"
					>
						<option value="">Every term</option>
						{data.terms.map((row) => (
							<option key={row.name} value={row.name}>
								{row.term_name || row.name}
							</option>
						))}
					</select>
				}
			/>

			{data.rows.length === 0 ? (
				<Empty />
			) : (
				<div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
					{data.rows.map((row) => (
						<CourseCard key={row.name} row={row} />
					))}
				</div>
			)}
		</>
	)
}

function Empty() {
	return (
		<Card>
			<CardContent className="py-14 text-center">
				<BookOpen className="text-muted-foreground mx-auto mb-3 size-8" />
				<div className="font-medium">No courses to build</div>
				<p className="text-muted-foreground mx-auto mt-1 max-w-md text-sm">
					A course appears here once you are named as its instructor or facilitator.
					If you are teaching something that is not listed, ask the Academic
					Coordinator to put you on the offering.
				</p>
			</CardContent>
		</Card>
	)
}

function CourseCard({ row }: { row: CourseShelfRow }) {
	return (
		<Card className="hover:border-primary/40 transition-colors">
			<CardContent className="p-4">
				<Link to={`/staff/courses/${encodeURIComponent(row.name)}`} className="block">
					<div className="flex items-start justify-between gap-2">
						<div className="min-w-0">
							<div className="truncate font-medium">{row.course_title || row.course}</div>
							<div className="text-muted-foreground mt-0.5 text-xs">
								{row.course} · {row.term}
							</div>
						</div>
						<Badge variant={row.status === 'Published' ? 'default' : 'secondary'}>
							{row.status}
						</Badge>
					</div>

					<div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
						<span className="inline-flex items-center gap-1.5">
							{row.has_scheme ? (
								<CircleCheck className="size-3.5 text-emerald-600" />
							) : (
								<CircleDashed className="text-muted-foreground size-3.5" />
							)}
							{row.has_scheme ? 'Grade scheme set' : 'No grade scheme'}
						</span>
						<span className="text-muted-foreground">
							{row.assignments === 1 ? '1 assignment' : `${row.assignments} assignments`}
							{row.assignments > 0 && ` · ${row.published_assignments} published`}
						</span>
						<span className="text-muted-foreground">
							{row.enrolled_count ?? 0} registered
						</span>
					</div>
				</Link>
			</CardContent>
		</Card>
	)
}
