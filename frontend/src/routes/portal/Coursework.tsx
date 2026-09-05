import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { CircleCheck, Clock, LoaderCircle, Send } from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { RichText } from '@/components/RichText'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useCoursework, useSubmitWork } from '@/hooks/useCoursework'
import { FrappeError } from '@/lib/frappe'
import type { CourseworkResponse, CourseworkRow } from '@/types'

function message(error: unknown) {
	return error instanceof FrappeError ? error.message : 'Something went wrong.'
}

/** A student's own coursework: what is set, and what came back. */
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
					data.rows.length === 1 ? '1 piece of work' : `${data.rows.length} pieces of work`
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
				<div className="space-y-3">
					{data.rows.map((row) => (
						<Piece key={row.assignment.name} row={row} registration={registration} />
					))}
				</div>
			)}
		</>
	)
}

function Piece({ row, registration }: { row: CourseworkRow; registration: string }) {
	const [open, setOpen] = useState(false)
	const [body, setBody] = useState('')
	const [url, setUrl] = useState('')
	const submit = useSubmitWork(registration)

	const submission = row.submission
	const marked = submission && submission.posted && submission.score !== undefined

	return (
		<Card>
			<CardHeader className="pb-3">
				<div className="flex flex-wrap items-start justify-between gap-2">
					<div>
						<CardTitle className="text-base">{row.assignment.title}</CardTitle>
						<p className="text-muted-foreground mt-0.5 text-xs">
							out of {row.assignment.points_possible}
							{row.assignment.due_date
								? ` · due ${row.assignment.due_date.slice(0, 16).replace('T', ' ')}`
								: ' · no due date'}
						</p>
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
				</div>
			</CardHeader>

			<CardContent className="space-y-3">
				{row.assignment.description && <RichText html={row.assignment.description} />}

				{row.open.reason && (
					<p className="text-muted-foreground flex items-center gap-1.5 text-xs">
						<Clock className="size-3.5" /> {row.open.reason}
					</p>
				)}

				{marked && submission.feedback && (
					<div className="bg-muted rounded-md p-3">
						<div className="mb-1 text-xs font-medium">Feedback</div>
						<RichText html={submission.feedback} />
					</div>
				)}

				{submission && !marked && (
					<p className="text-muted-foreground text-xs">
						Handed in
						{submission.submitted_on
							? ` ${submission.submitted_on.slice(0, 16).replace('T', ' ')}`
							: ''}
						. Not marked yet.
					</p>
				)}

				{/* A quiz is sat, not typed into a box. The assignment still
				    holds the due date and the points; the quiz holds the clock. */}
				{!submission && row.open.open && row.assignment.submission_type === 'Quiz' && (
					<Button size="sm" asChild>
						<Link
							to={`/portal/courses/${encodeURIComponent(registration)}/quiz/${encodeURIComponent(row.assignment.name)}`}
						>
							Start quiz
						</Link>
					</Button>
				)}

				{!submission && row.open.open && row.assignment.submission_type !== 'Quiz' && (
					<>
						{open ? (
							<div className="space-y-3">
								{row.assignment.submission_type === 'URL' ? (
									<div>
										<Label htmlFor={`url-${row.assignment.name}`}>Link</Label>
										<Input
											id={`url-${row.assignment.name}`}
											className="mt-1"
											value={url}
											onChange={(event) => setUrl(event.target.value)}
										/>
									</div>
								) : (
									<div>
										<Label htmlFor={`body-${row.assignment.name}`}>Your answer</Label>
										<Textarea
											id={`body-${row.assignment.name}`}
											className="mt-1"
											rows={8}
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
			</CardContent>
		</Card>
	)
}
