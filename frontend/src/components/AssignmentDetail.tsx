import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CircleCheck, Clock, LoaderCircle, Send } from 'lucide-react'
import { toast } from 'sonner'

import { AssignmentMeta, submittingAs } from '@/components/AssignmentMeta'
import { RichText } from '@/components/RichText'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useSubmitWork } from '@/hooks/useCoursework'
import { FrappeError } from '@/lib/frappe'
import type { CourseworkRow } from '@/types'

function message(error: unknown) {
	return error instanceof FrappeError ? error.message : 'Something went wrong.'
}

/**
 * One piece of work as a student meets it: what it asks for, and what has
 * happened to it.
 *
 * `preview` is a teacher looking at their own assignment. Same strip, same
 * instructions, same Submission section -- with the control described rather
 * than working, because a teacher cannot hand work in to themselves and the
 * server would refuse the attempt anyway.
 *
 * The alternative was a second component drawing the same assignment for
 * staff, which is how a preview stops matching the thing it previews. This is
 * the same argument as `ModuleOutline`, and the same answer.
 */
export function AssignmentDetail({
	row,
	registration,
	preview = false,
}: {
	row: CourseworkRow
	/** Absent in preview: there is no student whose work this would be. */
	registration?: string
	preview?: boolean
}) {
	const [open, setOpen] = useState(false)
	const [body, setBody] = useState('')
	const [url, setUrl] = useState('')

	// Hooks cannot be conditional, so this is built either way and fired only
	// off preview -- where there is no registration to fire it at.
	const submit = useSubmitWork(registration ?? '')

	const submission = row.submission
	const marked = submission && submission.posted && submission.score !== undefined
	const canHandIn = !submission && row.open.open

	return (
		<div className="space-y-4">
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

			{row.assignment.description ? (
				<RichText html={row.assignment.description} />
			) : (
				preview && (
					<p className="text-muted-foreground text-sm">
						No instructions written yet, so a student would see nothing here.
					</p>
				)
			)}

			{/* Everything about what has happened to this, in the order somebody
			    asks it: can I still, did it go, what did it get, what did they
			    say, and how do I. */}
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

				{!submission && !row.open.open && !preview && (
					<p className="text-muted-foreground text-sm">
						This is closed, and nothing was handed in.
					</p>
				)}

				{/* A teacher gets the control described. Rendering a working one
				    would offer them something the server refuses. */}
				{preview ? (
					<p className="text-muted-foreground text-sm">
						{row.assignment.submission_type === 'Quiz'
							? 'A student sits this as a quiz, timed by the server.'
							: `A student hands this in as ${submittingAs(row.assignment.submission_type)}.`}
					</p>
				) : (
					<>
						{canHandIn && row.assignment.submission_type === 'Quiz' && (
							<Button size="sm" asChild>
								<Link
									to={`/portal/courses/${encodeURIComponent(registration!)}/quiz/${encodeURIComponent(row.assignment.name)}`}
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
											<Button
												variant="outline"
												size="sm"
												onClick={() => setOpen(false)}
											>
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
					</>
				)}
			</section>
		</div>
	)
}
