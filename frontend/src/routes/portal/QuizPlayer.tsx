import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { CircleCheck, CircleX, Clock, LoaderCircle, Send } from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { RichText } from '@/components/RichText'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useAnswer, useQuizResult, useStartQuiz, useSubmitQuiz } from '@/hooks/useQuiz'
import { FrappeError } from '@/lib/frappe'
import { cn } from '@/lib/utils'
import type { QuizAttempt, QuizQuestion } from '@/types'

function message(error: unknown) {
	return error instanceof FrappeError ? error.message : 'Something went wrong.'
}

/**
 * Sitting a quiz.
 *
 * The countdown here is decoration. The server set `expires_at` when the
 * attempt started and refuses a late answer whatever this page believes, so a
 * student who edits the number in devtools has edited a picture of a clock.
 * It is shown because not knowing how long is left is unpleasant, not because
 * anything depends on it.
 */
export function QuizPlayer() {
	const { name = null, assignment = null } = useParams()
	const registration = name ? decodeURIComponent(name) : null
	const target = assignment ? decodeURIComponent(assignment) : null

	const start = useStartQuiz(registration ?? '')
	const [attempt, setAttempt] = useState<QuizAttempt | null>(null)
	const [finished, setFinished] = useState(false)

	useEffect(() => {
		if (!registration || !target || attempt) return
		start.mutate(target, {
			onSuccess: setAttempt,
			onError: (error) => toast.error(message(error)),
		})
	}, [registration, target, attempt, start])

	if (start.isPending && !attempt) {
		return <p className="text-muted-foreground p-6 text-sm">Opening the paper…</p>
	}

	if (start.isError && !attempt) {
		return (
			<Card className="m-4">
				<CardContent className="py-10 text-center">
					<div className="font-medium">This quiz cannot be opened</div>
					<p className="text-muted-foreground mt-1 text-sm">{message(start.error)}</p>
				</CardContent>
			</Card>
		)
	}

	if (!attempt) return null

	if (finished) {
		return <Result registration={registration!} attempt={attempt.attempt} />
	}

	return (
		<Sitting
			attempt={attempt}
			registration={registration!}
			onFinished={() => setFinished(true)}
		/>
	)
}

function Sitting({
	attempt,
	registration,
	onFinished,
}: {
	attempt: QuizAttempt
	registration: string
	onFinished: () => void
}) {
	const answer = useAnswer(registration)
	const submit = useSubmitQuiz(registration)
	const [given, setGiven] = useState<Record<string, unknown>>(
		() =>
			Object.fromEntries(
				attempt.questions
					.filter((question) => question.given !== null)
					.map((question) => [question.name, question.given]),
			) as Record<string, unknown>,
	)

	const remaining = useCountdown(attempt.seconds_remaining)

	const answered = Object.keys(given).length
	const total = attempt.questions.length

	// When the clock reaches zero the server has already stopped accepting
	// answers; handing in is how the student gets their score without waiting
	// for the sweep.
	useEffect(() => {
		if (remaining === 0 && attempt.seconds_remaining !== null) {
			submit.mutate(attempt.attempt, { onSettled: onFinished })
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [remaining])

	const record = (question: string, value: unknown) => {
		setGiven({ ...given, [question]: value })
		answer.mutate(
			{ attempt: attempt.attempt, question, value },
			{
				onError: (error) => {
					toast.error(message(error))
					// The server refused it, so the page must not go on
					// pretending it was recorded.
					if (/time is up/i.test(message(error))) onFinished()
				},
			},
		)
	}

	return (
		<>
			<PageHeader
				title={attempt.title}
				description={`${answered} of ${total} answered`}
				actions={
					<div className="flex items-center gap-3">
						{remaining !== null && (
							<span
								className={cn(
									'flex items-center gap-1.5 text-sm font-medium tabular-nums',
									remaining < 60 && 'text-destructive',
								)}
							>
								<Clock className="size-4" />
								{formatClock(remaining)}
							</span>
						)}
						<Button
							size="sm"
							disabled={submit.isPending}
							onClick={() =>
								submit.mutate(attempt.attempt, {
									onSuccess: () => {
										toast.success('Handed in')
										onFinished()
									},
									onError: (error) => toast.error(message(error)),
								})
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
				}
			/>

			{attempt.description && (
				<Card className="mb-4">
					<CardContent className="py-4">
						<RichText html={attempt.description} />
					</CardContent>
				</Card>
			)}

			<ol className="space-y-3">
				{attempt.questions.map((question, index) => (
					<Question
						key={question.name}
						question={question}
						index={index}
						given={given[question.name]}
						onAnswer={(value) => record(question.name, value)}
					/>
				))}
			</ol>
		</>
	)
}

function Question({
	question,
	index,
	given,
	onAnswer,
}: {
	question: QuizQuestion
	index: number
	given: unknown
	onAnswer: (value: unknown) => void
}) {
	const chosen = Array.isArray(given) ? (given as number[]) : []
	const multiple = question.question_type === 'Multiple answers'

	return (
		<li>
			<Card>
				<CardHeader className="pb-3">
					<CardTitle className="text-sm font-medium">
						<span className="text-muted-foreground mr-2">{index + 1}.</span>
						<RichText html={question.question} inline />
					</CardTitle>
					<span className="text-muted-foreground text-xs">
						{question.points} {question.points === 1 ? 'point' : 'points'}
					</span>
				</CardHeader>

				<CardContent>
					{question.question_type === 'Short answer' ? (
						<Input
							aria-label={`Answer to question ${index + 1}`}
							defaultValue={typeof given === 'string' ? given : ''}
							onBlur={(event) => onAnswer(event.target.value)}
						/>
					) : (
						<div className="space-y-1.5">
							{question.options.map((option) => (
								<label
									key={option.idx}
									className="hover:bg-muted/60 flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm"
								>
									<input
										type={multiple ? 'checkbox' : 'radio'}
										name={question.name}
										checked={chosen.includes(option.idx)}
										onChange={() =>
											onAnswer(
												multiple
													? chosen.includes(option.idx)
														? chosen.filter((value) => value !== option.idx)
														: [...chosen, option.idx]
													: [option.idx],
											)
										}
									/>
									{option.text}
								</label>
							))}
						</div>
					)}
				</CardContent>
			</Card>
		</li>
	)
}

function Result({ registration, attempt }: { registration: string; attempt: string }) {
	const query = useQuizResult(registration, attempt)

	if (query.isPending) {
		return <p className="text-muted-foreground p-6 text-sm">Marking…</p>
	}

	const data = query.data
	if (!data) return null

	return (
		<>
			<PageHeader
				title="Handed in"
				description={
					data.auto_submitted
						? 'Your time ran out, so this was handed in for you.'
						: undefined
				}
			/>

			<Card className="mb-4">
				<CardContent className="py-6 text-center">
					<div className="text-3xl font-semibold tabular-nums">
						{data.score} <span className="text-muted-foreground text-lg">/ {data.points_possible}</span>
					</div>
					{!('questions' in data) && (
						<p className="text-muted-foreground mx-auto mt-2 max-w-sm text-sm">
							The answers are not shown for this quiz.
						</p>
					)}
				</CardContent>
			</Card>

			{'questions' in data && data.questions && (
				<ol className="space-y-3">
					{data.questions.map((row, index) => (
						<li key={row.name}>
							<Card>
								<CardContent className="py-4">
									<div className="flex items-start gap-2">
										{row.is_correct ? (
											<CircleCheck className="mt-0.5 size-4 shrink-0 text-emerald-600" />
										) : (
											<CircleX className="text-destructive mt-0.5 size-4 shrink-0" />
										)}
										<div className="min-w-0 flex-1">
											<span className="text-muted-foreground mr-2 text-sm">
												{index + 1}.
											</span>
											<RichText html={row.question ?? ''} inline />
											{row.explanation && (
												<div className="bg-muted mt-2 rounded-md p-2">
													<RichText html={row.explanation} />
												</div>
											)}
										</div>
										<Badge variant={row.is_correct ? 'default' : 'secondary'}>
											{row.points_awarded}
										</Badge>
									</div>
								</CardContent>
							</Card>
						</li>
					))}
				</ol>
			)}
		</>
	)
}

/**
 * Counts down from what the server said was left.
 *
 * Seeded once and decremented locally rather than polled: the answer that
 * matters is on the server, and asking it every second would be a request per
 * student per second for a number that is only being drawn on a screen.
 */
function useCountdown(seconds: number | null) {
	const [left, setLeft] = useState(seconds)

	useEffect(() => setLeft(seconds), [seconds])

	useEffect(() => {
		if (left === null || left <= 0) return
		const timer = setInterval(() => setLeft((value) => (value === null ? null : value - 1)), 1000)
		return () => clearInterval(timer)
	}, [left])

	return left
}

function formatClock(seconds: number) {
	const minutes = Math.floor(seconds / 60)
	const rest = seconds % 60
	return `${minutes}:${String(rest).padStart(2, '0')}`
}
