import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, CircleCheck, Clock, LoaderCircle, Send } from 'lucide-react'
import { toast } from 'sonner'

import { AssignmentMeta } from '@/components/AssignmentMeta'
import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { RichText } from '@/components/RichText'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useCoursework, useSubmitWork } from '@/hooks/useCoursework'
import { FrappeError } from '@/lib/frappe'
import type { CourseworkRow } from '@/types'

function message(error: unknown) {
	return error instanceof FrappeError ? error.message : 'Something went wrong.'
}

/**
 * One piece of work: what it asks for, and what has happened to it.
 *
 * Its own address, so a student can keep it, a teacher can send it, and the
 * module item that points at it can point at *it* rather than at the list
 * that contains it.
 *
 * Read out of the coursework payload rather than through an endpoint of its
 * own. That is not only cheaper: it means this page and the list share a
 * cache entry, so handing work in here leaves the list correct without either
 * knowing about the other.
 */
export function Assignment() {
	const { name = null, assignment = null } = useParams()
	const registration = name ? decodeURIComponent(name) : null
	const wanted = assignment ? decodeURIComponent(assignment) : null
	const query = useCoursework(registration)

	return (
		<QueryState query={query} title="Assignment">
			{(data) => {
				const row = data.rows.find((piece) => piece.assignment.name === wanted)
				const back = `/portal/courses/${encodeURIComponent(registration!)}/work`

				if (!row) {
					return (
						<>
							<PageHeader title="Not found" />
							<Card>
								<CardContent className="py-14 text-center">
									<div className="font-medium">
										There is no such piece of work on this course
									</div>
									<p className="text-muted-foreground mx-auto mt-1 max-w-md text-sm">
										It may have been withdrawn, or the link may be for another
										course.
									</p>
									<Button variant="outline" size="sm" className="mt-4" asChild>
										<Link to={back}>All coursework</Link>
									</Button>
								</CardContent>
							</Card>
						</>
					)
				}

				return (
					<>
						<PageHeader
							title={row.assignment.title}
							description={
								data.registration.course_title || data.registration.course_offering
							}
							actions={
								<Button variant="outline" size="sm" asChild>
									<Link to={back}>
										<ArrowLeft /> Coursework
									</Link>
								</Button>
							}
						/>

						<Detail row={row} registration={registration!} />
					</>
				)
			}}
		</QueryState>
	)
}

function Detail({ row, registration }: { row: CourseworkRow; registration: string }) {
	const [open, setOpen] = useState(false)
	const [body, setBody] = useState('')
	const [url, setUrl] = useState('')
	const submit = useSubmitWork(registration)

	const submission = row.submission
	const marked = submission && submission.posted && submission.score !== undefined
	const canHandIn = !submission && row.open.open

	return (
		<Card>
			<CardContent className="space-y-4 pt-6">
				<div className="flex flex-wrap items-center justify-between gap-2">
					<AssignmentMeta
						className="min-w-0 flex-1 border-t-0 pt-0"
						points={row.assignment.points_possible}
						dueDate={row.assignment.due_date}
						submissionType={row.assignment.submission_type}
					/>

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
				</div>

				{row.assignment.description && <RichText html={row.assignment.description} />}

				{/* Everything about what has happened to this, in the order
				    somebody asks it: can I still, did it go, what did it get,
				    what did they say, and how do I. */}
				<section className="border-t pt-4">
					<h2 className="mb-2 text-sm font-semibold">Submission</h2>

					{row.open.reason && (
						<p className="text-muted-foreground mb-2 flex items-center gap-1.5 text-xs">
							<Clock className="size-3.5" /> {row.open.reason}
						</p>
					)}

					{submission && !marked && (
						<p className="text-muted-foreground text-sm">
							Handed in
							{submission.submitted_on
								? ` ${submission.submitted_on.slice(0, 16).replace('T', ' ')}`
								: ''}
							. Not marked yet.
						</p>
					)}

					{marked && (
						<p className="text-sm">
							Marked{' '}
							<span className="font-medium tabular-nums">
								{submission.score} out of {row.assignment.points_possible}
							</span>
							.
						</p>
					)}

					{marked && submission.feedback && (
						<div className="bg-muted mt-3 rounded-md p-3">
							<div className="mb-1 text-xs font-medium">Feedback</div>
							<RichText html={submission.feedback} />
						</div>
					)}

					{!submission && !row.open.open && (
						<p className="text-muted-foreground text-sm">
							This is closed, and nothing was handed in.
						</p>
					)}

					{/* A quiz is sat, not typed into a box. The assignment still
					    holds the due date and the points; the quiz holds the clock. */}
					{canHandIn && row.assignment.submission_type === 'Quiz' && (
						<Button size="sm" asChild>
							<Link
								to={`/portal/courses/${encodeURIComponent(registration)}/quiz/${encodeURIComponent(row.assignment.name)}`}
							>
								Start quiz
							</Link>
						</Button>
					)}

					{canHandIn && row.assignment.submission_type !== 'Quiz' && (
						<>
							{open ? (
								<div className="space-y-3">
									{row.assignment.submission_type === 'URL' ? (
										<div>
											<Label htmlFor="submission-url">Link</Label>
											<Input
												id="submission-url"
												className="mt-1"
												value={url}
												onChange={(event) => setUrl(event.target.value)}
											/>
										</div>
									) : (
										<div>
											<Label htmlFor="submission-body">Your answer</Label>
											<Textarea
												id="submission-body"
												className="mt-1"
												rows={10}
												value={body}
												onChange={(event) => setBody(event.target.value)}
											/>
										</div>
									)}

									<div className="flex justify-end gap-2">
										<Button variant="outline" size="sm" onClick={() => setOpen(false)}>
											Cancel
										</Button>
										<Button
											size="sm"
											disabled={submit.isPending || (!body && !url)}
											onClick={() =>
												submit.mutate(
													{ assignment: row.assignment.name, body, url },
													{
														onSuccess: () => {
															toast.success('Handed in')
															setOpen(false)
														},
														onError: (error) => toast.error(message(error)),
													},
												)
											}
										>
											{submit.isPending ? (
												<LoaderCircle className="animate-spin" />
											) : (
												<Send />
											)}
											Hand in
										</Button>
									</div>
								</div>
							) : (
								<Button size="sm" onClick={() => setOpen(true)}>
									Hand in
								</Button>
							)}
						</>
					)}
				</section>
			</CardContent>
		</Card>
	)
}
