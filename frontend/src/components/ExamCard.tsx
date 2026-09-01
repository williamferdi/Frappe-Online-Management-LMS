import { useState } from 'react'
import { CircleCheck, CircleX, Download, LoaderCircle, Save } from 'lucide-react'
import { toast } from 'sonner'

import { RichText } from '@/components/RichText'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { usePullExam, useRecordExam } from '@/hooks/useStaff'
import { FrappeError } from '@/lib/frappe'
import { formatDate } from '@/lib/utils'
import type { ExamState } from '@/types'

const ESSAY_LABEL: Record<string, string> = {
	essay_gospel: 'Understanding of the Gospel',
	essay_calling: 'Sense of calling',
	essay_motivation: 'Motivation for study',
}

/**
 * The entrance exam, from both sides.
 *
 * The candidate sits it in the LMS and it is marked there against the rubrics
 * in the course; the college's own record is a Qualifying Exam Result, and the
 * workflow gates on the score it carries. "Sat but not marked" and "marked but
 * never brought across" used to look identical from here -- an application
 * saying the score was zero -- so the card says which it is.
 */
export function ExamCard({
	application,
	exam,
	canWrite,
}: {
	application: string
	exam: ExamState
	canWrite: boolean
}) {
	const pull = usePullExam(application)
	const record = useRecordExam(application)
	const [marks, setMarks] = useState<Record<string, string>>({})

	const submission = exam.submission
	const result = exam.result
	const editing = Object.keys(marks).length > 0

	function markFor(field: string) {
		if (field in marks) return marks[field]
		const stored = result?.[field as keyof typeof result]
		return stored == null ? '' : String(stored)
	}

	function save() {
		record.mutate(
			Object.fromEntries(
				exam.essays.map((field) => [field, Number(markFor(field)) || 0]),
			),
			{
				onSuccess: () => {
					setMarks({})
					toast.success('Marks recorded')
				},
				onError: (error) =>
					toast.error(
						error instanceof FrappeError ? error.message : 'Those marks were refused.',
					),
			},
		)
	}

	return (
		<Card>
			<CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
				<CardTitle className="text-base">Entrance exam</CardTitle>
				<div className="flex items-center gap-2">
					{result && (
						<Badge variant={result.result === 'Pass' ? 'success' : 'destructive'}>
							{result.result === 'Pass' ? <CircleCheck /> : <CircleX />}
							{result.total}% · {result.result}
						</Badge>
					)}
					{canWrite && submission?.marked && (
						<Button
							size="sm"
							variant="outline"
							disabled={pull.isPending}
							onClick={() =>
								pull.mutate(undefined, {
									onSuccess: () => toast.success('Marks pulled from the exam course'),
									onError: (error) =>
										toast.error(
											error instanceof FrappeError
												? error.message
												: 'Those marks could not be pulled.',
										),
								})
							}
						>
							{pull.isPending ? <LoaderCircle className="animate-spin" /> : <Download />}
							Pull marks
						</Button>
					)}
				</div>
			</CardHeader>

			<CardContent className="space-y-4">
				{!submission ? (
					<p className="text-muted-foreground text-sm">
						Not sat yet. The candidate takes the exam in the Entrance Exam course, using
						the login and link the LMS Account step sends them.
					</p>
				) : (
					<>
						<p className="text-muted-foreground text-sm">
							Sat on {formatDate(submission.submitted_on)} as{' '}
							<span className="font-mono text-xs">{submission.member}</span> ·{' '}
							{submission.score} of {submission.score_out_of} in the course.
						</p>

						{!submission.marked && (
							<Alert variant="warning">
								<AlertDescription>
									Nobody has marked this yet. Mark the three essays in the Entrance Exam
									course against its rubrics, or enter the marks here — either way they end
									up on the same record.
								</AlertDescription>
							</Alert>
						)}

						{submission.answers.length > 0 && (
							<div className="space-y-3">
								{submission.answers.map((answer, index) => (
									<details
										key={index}
										className="bg-muted/40 rounded-lg px-3 py-2 text-sm"
									>
										<summary className="cursor-pointer font-medium">
											{ESSAY_LABEL[exam.essays[index]] ?? `Essay ${index + 1}`}
											<span className="text-muted-foreground font-normal">
												{' '}
												— {answer.marks} of {answer.marks_out_of}
											</span>
										</summary>
										<RichText
											html={answer.answer ?? ''}
											className="mt-2 max-h-64 overflow-y-auto text-sm"
										/>
									</details>
								))}
							</div>
						)}
					</>
				)}

				{(submission || result) && (
					<div className="grid gap-3 sm:grid-cols-3">
						{exam.essays.map((field) => (
							<div key={field}>
								<Label htmlFor={`${field}-mark`} className="text-xs">
									{ESSAY_LABEL[field] ?? field}
								</Label>
								<div className="flex items-center gap-1.5">
									<Input
										id={`${field}-mark`}
										type="number"
										min={0}
										max={exam.essay_max}
										className="h-8"
										disabled={!canWrite}
										value={markFor(field)}
										onChange={(event) =>
											setMarks({ ...marks, [field]: event.target.value })
										}
									/>
									<span className="text-muted-foreground text-xs">
										/ {exam.essay_max}
									</span>
								</div>
							</div>
						))}
					</div>
				)}

				{(submission || result) && canWrite && (
					<div className="flex items-center gap-3">
						<Button size="sm" disabled={!editing || record.isPending} onClick={save}>
							{record.isPending ? <LoaderCircle className="animate-spin" /> : <Save />}
							Save marks
						</Button>
						<span className="text-muted-foreground text-xs">
							{result
								? `Pass mark ${result.pass_mark}%. Saving recomputes the total and moves the checklist step.`
								: 'Saving creates the exam record and moves the checklist step.'}
						</span>
					</div>
				)}
			</CardContent>
		</Card>
	)
}
