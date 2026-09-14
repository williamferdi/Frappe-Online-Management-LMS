import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
	ArrowLeft,
	ChevronLeft,
	ChevronRight,
	LoaderCircle,
	Save,
	Send,
} from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { RosterPicker } from '@/components/RosterPicker'
import { RichText } from '@/components/RichText'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useGrade, useMarkingQueue, useSetPosted } from '@/hooks/useMarking'
import { FrappeError } from '@/lib/frappe'
import { cn } from '@/lib/utils'
import type { MarkingQueue as Queue, MarkingRow } from '@/types'

function message(error: unknown) {
	return error instanceof FrappeError ? error.message : 'Something went wrong.'
}

/** Whether a Text Editor value says anything. Frappe's editor saves an
 *  emptied field as markup with nothing in it, which is not a brief. */
function hasContent(html: string | null) {
	if (!html) return false
	const body = new DOMParser().parseFromString(html, 'text/html').body
	return Boolean(body.textContent?.trim() || body.querySelector('img, iframe, video'))
}

/**
 * One piece of work at a time, with the next student a keystroke away.
 *
 * The shape a marker actually works in: read, score, comment, move on. The
 * gradebook grid is for looking at a class; this is for getting through it.
 */
export function MarkingQueue() {
	const { name = null, assignment = null } = useParams()
	const offering = name ? decodeURIComponent(name) : null
	const target = assignment ? decodeURIComponent(assignment) : null
	const query = useMarkingQueue(target)

	return (
		<QueryState query={query} title="Marking">
			{(data) => <Loaded data={data} offering={offering!} assignment={target!} />}
		</QueryState>
	)
}

function Loaded({
	data,
	offering,
	assignment,
}: {
	data: Queue
	offering: string
	assignment: string
}) {
	const [index, setIndex] = useState(0)
	const post = useSetPosted(assignment)

	const rows = data.rows
	const current = rows[Math.min(index, rows.length - 1)]

	return (
		<>
			<PageHeader
				title={data.assignment.title}
				description={`${data.assignment.component} · out of ${data.assignment.points_possible}${
					data.assignment.due_date
						? ` · due ${data.assignment.due_date.slice(0, 16).replace('T', ' ')}`
						: ''
				}`}
				actions={
					<div className="flex gap-2">
						<Button variant="outline" size="sm" asChild>
							<Link to={`/staff/courses/${encodeURIComponent(offering)}`}>
								<ArrowLeft /> Course
							</Link>
						</Button>
						<Button
							size="sm"
							disabled={post.isPending || data.unposted === 0}
							onClick={() =>
								post.mutate(
									{ posted: 1 },
									{
										onSuccess: (result) =>
											toast.success(
												result.changed === 1
													? '1 mark posted'
													: `${result.changed} marks posted`,
											),
										onError: (error) => toast.error(message(error)),
									},
								)
							}
						>
							<Send /> Post all marks
						</Button>
					</div>
				}
			/>

			<div className="mb-4 flex flex-wrap gap-2 text-sm">
				<Badge variant="secondary">{data.ungraded} to mark</Badge>
				<Badge variant="secondary">{data.unposted} marked, not posted</Badge>
				<Badge variant="secondary">{data.missing} nothing handed in</Badge>
			</div>

			{/* What the work asked for, beside the work. Open to begin with; a
			    marker who knows it by heart can fold it away. */}
			{hasContent(data.assignment.description) && (
				<details open className="bg-card mb-4 rounded-lg border">
					<summary className="cursor-pointer px-4 py-2.5 text-sm font-medium">Brief</summary>
					<RichText
						html={data.assignment.description ?? ''}
						className="max-h-72 overflow-y-auto border-t px-4 py-3"
					/>
				</details>
			)}

			{rows.length === 0 ? (
				<Card>
					<CardContent className="py-14 text-center">
						<div className="font-medium">Nobody is registered</div>
						<p className="text-muted-foreground mt-1 text-sm">
							Marks can be entered once students register for this run.
						</p>
					</CardContent>
				</Card>
			) : (
				<div className="grid gap-4 lg:grid-cols-[260px_1fr]">
					<div className="space-y-3">
						{/* A class of two hundred is a list nobody scrolls to find
						    the one person they were asked about. */}
						{rows.length > 1 && (
							<RosterPicker
								roster={rows.map((row) => ({
									name: row.course_registration,
									student_name: row.student_name,
								}))}
								value={current?.course_registration ?? null}
								onChange={(picked) => {
									const found = rows.findIndex(
										(row) => row.course_registration === picked,
									)
									if (found >= 0) setIndex(found)
								}}
								label="Jump to"
								placeholder="Search the class"
								allowAnyone={false}
							/>
						)}

						<StudentList rows={rows} index={index} onPick={setIndex} />
					</div>
					{current && (
						<Marker
							key={current.course_registration}
							row={current}
							data={data}
							assignment={assignment}
							onNext={() => setIndex(Math.min(index + 1, rows.length - 1))}
							hasNext={index < rows.length - 1}
							hasPrevious={index > 0}
							onPrevious={() => setIndex(Math.max(index - 1, 0))}
						/>
					)}
				</div>
			)}
		</>
	)
}

function StudentList({
	rows,
	index,
	onPick,
}: {
	rows: MarkingRow[]
	index: number
	onPick: (index: number) => void
}) {
	return (
		<Card className="h-fit">
			<CardContent className="p-2">
				<ul className="space-y-0.5">
					{rows.map((row, i) => {
						const state = !row.submission
							? 'missing'
							: row.submission.excused
								? 'excused'
								: !row.submission.scored
									? 'to mark'
									: row.submission.posted
										? 'posted'
										: 'marked'

						return (
							<li key={row.course_registration}>
								<button
									type="button"
									onClick={() => onPick(i)}
									aria-current={i === index}
									className={cn(
										'flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm',
										i === index ? 'bg-muted font-medium' : 'hover:bg-muted/60',
									)}
								>
									<span className="truncate">{row.student_name}</span>
									<span
										className={cn(
											'shrink-0 text-[10px] uppercase tracking-wide',
											state === 'to mark'
												? 'text-amber-600'
												: state === 'posted'
													? 'text-emerald-600'
													: 'text-muted-foreground',
										)}
									>
										{state}
									</span>
								</button>
							</li>
						)
					})}
				</ul>
			</CardContent>
		</Card>
	)
}

function Marker({
	row,
	data,
	assignment,
	onNext,
	onPrevious,
	hasNext,
	hasPrevious,
}: {
	row: MarkingRow
	data: Queue
	assignment: string
	onNext: () => void
	onPrevious: () => void
	hasNext: boolean
	hasPrevious: boolean
}) {
	const grade = useGrade(assignment)
	const [score, setScore] = useState<string>(
		row.submission?.scored ? String(row.submission.score ?? '') : '',
	)
	const [feedback, setFeedback] = useState(row.submission?.feedback ?? '')
	const [ratings, setRatings] = useState<Record<string, number>>({})

	const rubric = data.rubric
	const rubricTotal = useMemo(
		() => Object.values(ratings).reduce((sum, points) => sum + points, 0),
		[ratings],
	)

	const save = (alsoPost: boolean, advance: boolean) =>
		grade.mutate(
			{
				course_registration: row.course_registration,
				score: rubric && Object.keys(ratings).length ? undefined : score === '' ? null : Number(score),
				feedback,
				...(alsoPost ? { post: 1 } : {}),
				...(rubric && Object.keys(ratings).length
					? {
							rubric_assessment: Object.entries(ratings).map(([criterion, points]) => ({
								criterion,
								points,
							})),
						}
					: {}),
			},
			{
				onSuccess: () => {
					toast.success(alsoPost ? 'Marked and posted' : 'Marked')
					if (advance && hasNext) onNext()
				},
				onError: (error) => toast.error(message(error)),
			},
		)

	return (
		<div className="space-y-4">
			<Card>
				<CardHeader className="flex-row items-center justify-between space-y-0">
					{/* The student being marked is the heading of this screen. CardTitle is
					    a div everywhere in the app, so the semantics are added here
					    rather than by changing a primitive every card depends on. */}
					<CardTitle className="text-base" role="heading" aria-level={2}>
						{row.student_name}
					</CardTitle>
					<div className="flex gap-1">
						<Button
							variant="ghost"
							size="icon"
							aria-label="Previous student"
							disabled={!hasPrevious}
							onClick={onPrevious}
						>
							<ChevronLeft className="size-4" />
						</Button>
						<Button
							variant="ghost"
							size="icon"
							aria-label="Next student"
							disabled={!hasNext}
							onClick={onNext}
						>
							<ChevronRight className="size-4" />
						</Button>
					</div>
				</CardHeader>

				<CardContent>
					{!row.submission ? (
						<p className="text-muted-foreground text-sm">
							Nothing handed in. A mark can still be entered — for work done on
							paper, or a zero.
						</p>
					) : (
						<>
							<div className="text-muted-foreground mb-3 flex flex-wrap gap-3 text-xs">
								<span>Attempt {row.submission.attempt}</span>
								{row.submission.submitted_on && (
									<span>
										Handed in {row.submission.submitted_on.slice(0, 16).replace('T', ' ')}
									</span>
								)}
								{row.submission.late_days > 0 && (
									<span className="text-amber-600">
										{row.submission.late_days} day
										{row.submission.late_days === 1 ? '' : 's'} late
									</span>
								)}
								{row.effective_score !== null && row.submission.late_days > 0 && (
									<span>counts as {row.effective_score}</span>
								)}
							</div>

							{row.submission.body && <RichText html={row.submission.body} />}
							{row.submission.url && (
								<a
									href={row.submission.url}
									target="_blank"
									rel="noreferrer noopener"
									className="text-primary text-sm underline"
								>
									{row.submission.url}
								</a>
							)}
						</>
					)}
				</CardContent>
			</Card>

			{rubric && (
				<Card>
					<CardHeader>
						<CardTitle className="text-base">{rubric.title}</CardTitle>
					</CardHeader>
					<CardContent className="space-y-4">
						{(rubric.criteria ?? []).map((criterion) => (
							<div key={criterion.name}>
								<div className="flex items-baseline justify-between gap-2">
									<span className="text-sm font-medium">{criterion.title}</span>
									<span className="text-muted-foreground text-xs">
										out of {criterion.points_possible}
									</span>
								</div>
								{criterion.description && (
									<p className="text-muted-foreground mt-0.5 text-xs">
										{criterion.description}
									</p>
								)}
								<div className="mt-2 flex flex-wrap gap-1.5">
									{criterion.ratings.map((rating) => (
										<button
											key={rating.title}
											type="button"
											onClick={() =>
												setRatings({ ...ratings, [criterion.name]: rating.points })
											}
											aria-pressed={ratings[criterion.name] === rating.points}
											className={cn(
												'rounded-md border px-2.5 py-1 text-xs',
												ratings[criterion.name] === rating.points
													? 'border-primary bg-primary/10 font-medium'
													: 'border-input hover:bg-muted',
											)}
										>
											{rating.title} · {rating.points}
										</button>
									))}
								</div>
							</div>
						))}
						<div className="text-sm font-medium tabular-nums">
							Rubric total: {rubricTotal}
						</div>
					</CardContent>
				</Card>
			)}

			<Card>
				<CardContent className="space-y-3 p-4">
					<div className="flex flex-wrap items-end gap-3">
						<div className="w-32">
							<Label htmlFor="score">
								Score <span className="text-muted-foreground">/ {data.assignment.points_possible}</span>
							</Label>
							<Input
								id="score"
								type="number"
								className="mt-1"
								value={score}
								disabled={Boolean(rubric && Object.keys(ratings).length)}
								onChange={(event) => setScore(event.target.value)}
							/>
						</div>
						{row.submission?.posted ? (
							<Badge>Posted</Badge>
						) : row.submission?.scored ? (
							<Badge variant="secondary">Marked, not posted</Badge>
						) : null}
					</div>

					<div>
						<Label htmlFor="feedback">Feedback</Label>
						<Textarea
							id="feedback"
							className="mt-1"
							rows={4}
							value={feedback}
							onChange={(event) => setFeedback(event.target.value)}
						/>
					</div>

					<div className="flex flex-wrap justify-end gap-2">
						<Button
							variant="outline"
							size="sm"
							disabled={grade.isPending}
							onClick={() => save(false, false)}
						>
							{grade.isPending ? <LoaderCircle className="animate-spin" /> : <Save />}
							Save
						</Button>
						<Button size="sm" disabled={grade.isPending} onClick={() => save(false, true)}>
							Save and next
						</Button>
						<Button
							variant="secondary"
							size="sm"
							disabled={grade.isPending}
							onClick={() => save(true, false)}
						>
							<Send /> Save and post
						</Button>
					</div>
				</CardContent>
			</Card>
		</div>
	)
}
