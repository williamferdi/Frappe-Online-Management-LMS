import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { frappeGet, frappePost } from '@/lib/frappe'
import type { GradebookGrid, MarkingQueue, RubricDetail } from '@/types'

export const markingKeys = {
	all: ['marking'] as const,
	queue: (assignment: string) => ['marking', 'queue', assignment] as const,
	grid: (offering: string) => ['marking', 'grid', offering] as const,
	rubrics: ['marking', 'rubrics'] as const,
}

export function useMarkingQueue(assignment: string | null) {
	return useQuery({
		queryKey: markingKeys.queue(assignment ?? ''),
		queryFn: () =>
			frappeGet<MarkingQueue>('sibbcs.api.marking.queue', { assignment }),
		enabled: Boolean(assignment),
	})
}

export function useGradebook(offering: string | null) {
	return useQuery({
		queryKey: markingKeys.grid(offering ?? ''),
		queryFn: () =>
			frappeGet<GradebookGrid>('sibbcs.api.marking.gradebook_grid', {
				course_offering: offering,
			}),
		enabled: Boolean(offering),
	})
}

/**
 * A mark changes the gradebook, the queue and the student's transcript, so
 * everything academic is invalidated rather than just the screen in front of
 * you. Getting this wrong shows a marker a total that disagrees with the marks
 * they can see above it.
 */
function useMarkingMutation<TArgs, TResult>(
	assignment: string,
	call: (args: TArgs) => Promise<TResult>,
) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: call,
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: markingKeys.queue(assignment) })
			void queryClient.invalidateQueries({ queryKey: ['marking', 'grid'] })
			void queryClient.invalidateQueries({ queryKey: ['academic'] })
		},
	})
}

export function useGrade(assignment: string) {
	return useMarkingMutation(
		assignment,
		(args: {
			course_registration: string
			score?: number | null
			feedback?: string | null
			excused?: number
			post?: number
			rubric_assessment?: { criterion: string; points: number; comment?: string }[]
		}) => frappePost('sibbcs.api.marking.grade', { assignment, ...args }),
	)
}

export function useSetPosted(assignment: string) {
	return useMarkingMutation(
		assignment,
		(args: { posted: number; course_registration?: string }) =>
			frappePost<{ posted: number; changed: number }>('sibbcs.api.marking.set_posted', {
				assignment,
				...args,
			}),
	)
}

export function useRubrics() {
	return useQuery({
		queryKey: markingKeys.rubrics,
		queryFn: () =>
			frappeGet<{ rows: RubricDetail[] }>('sibbcs.api.marking.rubrics'),
	})
}
