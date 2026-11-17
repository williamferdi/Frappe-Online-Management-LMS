import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
	ArrowLeft,
	LoaderCircle,
	Plus,
	Save,
	Trash2,
} from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
	useCourse,
	useDeleteScheme,
	useSaveScheme,
} from '@/hooks/useCourses'
import { FrappeError } from '@/lib/frappe'
import { cn } from '@/lib/utils'
import type {
	CourseDetail as CourseDetailData,
	GradeSchemeRow,
} from '@/types'

/** What a course is weighted by before anyone has said otherwise. */
const STARTER: GradeSchemeRow[] = [
	{ component: 'Assignment', weight_pct: 40, drop_lowest: 0, posting_policy: 'Manual' },
	{ component: 'Exam', weight_pct: 40, drop_lowest: 0, posting_policy: 'Manual' },
	{ component: 'Attendance', weight_pct: 20, drop_lowest: 0, posting_policy: 'Manual' },
]

function message(error: unknown) {
	return error instanceof FrappeError ? error.message : 'Something went wrong.'
}

export function CourseDetail() {
	const { name = null } = useParams()
	const offering = name ? decodeURIComponent(name) : null
	const query = useCourse(offering)

	return (
		<QueryState query={query} title="Course">
			{(data) => <Loaded data={data} offering={offering!} />}
		</QueryState>
	)
}

function Loaded({ data, offering }: { data: CourseDetailData; offering: string }) {
	const course = data.offering

	return (
		<>
			<PageHeader
				title={course.course_title || course.course}
				description={`${course.course} · ${course.term} · ${course.enrolled_count ?? 0} registered`}
				actions={
					<div className="flex gap-2">
						<Button variant="outline" size="sm" asChild>
							<Link to={`/staff/academic/offerings/${encodeURIComponent(offering)}`}>
								Grade sheet
							</Link>
						</Button>
						<Button variant="outline" size="sm" asChild>
							<Link to="/staff/courses">
								<ArrowLeft /> Courses
							</Link>
						</Button>
					</div>
				}
			/>

			{/* Assignments, content, modules, the student view, the gradebook
			    grid and groups were tabs here. Teaching is done in Campus LMS
			    Lite now, so what is left is the one thing this system still
			    owns about a course: the shape a released mark lands in. The
			    marks themselves are on the grade sheet, linked above. */}
			<SchemeEditor data={data} offering={offering} />
		</>
	)
}

// ---------------------------------------------------------------------------
// the scheme
// ---------------------------------------------------------------------------

function SchemeEditor({ data, offering }: { data: CourseDetailData; offering: string }) {
	const [rows, setRows] = useState<GradeSchemeRow[]>(data.scheme?.rows ?? STARTER)
	const save = useSaveScheme(offering)
	const remove = useDeleteScheme(offering)

	const total = rows.reduce((sum, row) => sum + (Number(row.weight_pct) || 0), 0)
	const balanced = Math.abs(total - 100) < 0.01

	const update = (index: number, patch: Partial<GradeSchemeRow>) =>
		setRows(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)))

	const onSave = () =>
		save.mutate(rows, {
			onSuccess: () => toast.success('Grade scheme saved'),
			onError: (error) => toast.error(message(error)),
		})

	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">How this course is weighted</CardTitle>
				<p className="text-muted-foreground text-sm">
					Every student on this run gets these columns. An assignment counts towards one
					of them, and the weights have to add up to 100.
				</p>
			</CardHeader>

			<CardContent>
				<div className="space-y-2">
					{rows.map((row, index) => (
						<div key={index} className="flex flex-wrap items-end gap-2">
							<div className="min-w-40 flex-1">
								<Label htmlFor={`component-${index}`} className="text-xs">
									Component
								</Label>
								<select
									id={`component-${index}`}
									className="border-input bg-background mt-1 h-9 w-full rounded-md border px-3 text-sm"
									value={row.component}
									onChange={(event) => update(index, { component: event.target.value })}
								>
									{data.choices.components.map((option) => (
										<option key={option} value={option}>
											{option}
										</option>
									))}
								</select>
							</div>

							<div className="w-24">
								<Label htmlFor={`weight-${index}`} className="text-xs">
									Weight %
								</Label>
								<Input
									id={`weight-${index}`}
									type="number"
									className="mt-1"
									value={row.weight_pct}
									onChange={(event) =>
										update(index, { weight_pct: Number(event.target.value) })
									}
								/>
							</div>

							<div className="w-32">
								<Label htmlFor={`posting-${index}`} className="text-xs">
									Posting
								</Label>
								<select
									id={`posting-${index}`}
									className="border-input bg-background mt-1 h-9 w-full rounded-md border px-3 text-sm"
									value={row.posting_policy}
									onChange={(event) =>
										update(index, { posting_policy: event.target.value })
									}
								>
									{data.choices.posting_policies.map((option) => (
										<option key={option} value={option}>
											{option}
										</option>
									))}
								</select>
							</div>

							<Button
								variant="ghost"
								size="icon"
								aria-label={`Remove ${row.component}`}
								onClick={() => setRows(rows.filter((_, i) => i !== index))}
							>
								<Trash2 className="size-4" />
							</Button>
						</div>
					))}
				</div>

				<div className="mt-4 flex flex-wrap items-center gap-3">
					<Button
						variant="outline"
						size="sm"
						onClick={() =>
							setRows([
								...rows,
								{
									component: data.choices.components[0] ?? 'Assignment',
									weight_pct: 0,
									drop_lowest: 0,
									posting_policy: 'Manual',
								},
							])
						}
					>
						<Plus /> Add component
					</Button>

					<span
						className={cn(
							'text-sm font-medium tabular-nums',
							balanced ? 'text-emerald-600' : 'text-destructive',
						)}
					>
						{total}% of 100
					</span>

					<div className="ml-auto flex gap-2">
						{data.scheme && (
							<Button
								variant="outline"
								size="sm"
								onClick={() =>
									remove.mutate(undefined, {
										onSuccess: () => toast.success('Scheme removed'),
										onError: (error) => toast.error(message(error)),
									})
								}
								disabled={remove.isPending}
							>
								Remove scheme
							</Button>
						)}
						<Button size="sm" onClick={onSave} disabled={save.isPending || !balanced}>
							{save.isPending ? <LoaderCircle className="animate-spin" /> : <Save />}
							Save scheme
						</Button>
					</div>
				</div>

				{!balanced && (
					<p className="text-muted-foreground mt-2 text-xs">
						The weights have to total 100 before this can be saved — otherwise the
						final mark would not mean anything.
					</p>
				)}
			</CardContent>
		</Card>
	)
}
