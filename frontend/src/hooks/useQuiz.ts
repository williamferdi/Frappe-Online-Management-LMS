import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { frappeGet, frappePost } from '@/lib/frappe'
import type { QuizAttempt, QuizResult } from '@/types'

export const quizKeys = {
	result: (attempt: string) => ['quiz', 'result', attempt] as const,
	attempts: (assignment: string) => ['quiz', 'attempts', assignment] as const,
}

/**
 * Starting is a mutation even though it reads a paper: it creates an attempt
 * and sets a clock, and a cached query would hand a student a stale deadline.
 */
export function useStartQuiz(registration: string) {
	return useMutation({
		mutationFn: (assignment: string) =>
			frappePost<QuizAttempt>('sibbcs.api.quiz.start', {
				course_registration: registration,
				assignment,
			}),
	})
}

export function useAnswer(registration: string) {
	return useMutation({
		mutationFn: ({
			attempt,
			question,
			value,
		}: {
			attempt: string
			question: string
			value: unknown
		}) =>
			frappePost<{ question: string; seconds_remaining: number | null }>(
				'sibbcs.api.quiz.answer',
				{
					course_registration: registration,
					attempt,
					question,
					value,
				},
			),
	})
}

export function useSubmitQuiz(registration: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (attempt: string) =>
			frappePost<QuizResult>('sibbcs.api.quiz.submit', {
				course_registration: registration,
				attempt,
			}),
		onSuccess: (_data, attempt) => {
			void queryClient.invalidateQueries({ queryKey: quizKeys.result(attempt) })
			// A quiz score becomes an Assignment Submission, so the coursework
			// page and the module outline are both stale.
			void queryClient.invalidateQueries({ queryKey: ['coursework'] })
			void queryClient.invalidateQueries({ queryKey: ['syllabus', 'mine'] })
		},
	})
}

export function useQuizResult(registration: string, attempt: string) {
	return useQuery({
		queryKey: quizKeys.result(attempt),
		queryFn: () =>
			frappeGet<QuizResult>('sibbcs.api.quiz.result', {
				course_registration: registration,
				attempt,
			}),
		enabled: Boolean(attempt),
	})
}

// --- staff -----------------------------------------------------------------

export function useQuizAttempts(assignment: string | null) {
	return useQuery({
		queryKey: quizKeys.attempts(assignment ?? ''),
		queryFn: () =>
			frappeGet<{ rows: Record<string, unknown>[] }>('sibbcs.api.quiz.attempts', {
				assignment,
			}),
		enabled: Boolean(assignment),
	})
}
