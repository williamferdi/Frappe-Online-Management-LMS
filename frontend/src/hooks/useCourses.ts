import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { frappeGet, frappePost } from '@/lib/frappe'
import type {
	CourseDetail,
	CoursesResponse,
	GradeSchemeRow,
} from '@/types'

export const courseKeys = {
	all: ['course'] as const,
	shelf: (term: string | null) => ['course', 'shelf', term ?? ''] as const,
	one: (offering: string) => ['course', 'one', offering] as const,
}

export function useCourses(term: string | null) {
	return useQuery({
		queryKey: courseKeys.shelf(term),
		queryFn: () =>
			frappeGet<CoursesResponse>('sibbcs.api.course.courses', {
				...(term ? { term } : {}),
			}),
	})
}

export function useCourse(offering: string | null) {
	return useQuery({
		queryKey: courseKeys.one(offering ?? ''),
		queryFn: () =>
			frappeGet<CourseDetail>('sibbcs.api.course.course', {
				course_offering: offering,
			}),
		enabled: Boolean(offering),
	})
}

/**
 * Every mutation invalidates both the one course and the shelf: the shelf
 * shows whether a course has a scheme and how many assignments it has, so
 * leaving it stale means a teacher returns to a list that disagrees with the
 * page they just edited.
 */
function useCourseMutation<TArgs, TResult>(
	offering: string,
	call: (args: TArgs) => Promise<TResult>,
) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: call,
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: courseKeys.one(offering) })
			void queryClient.invalidateQueries({ queryKey: ['course', 'shelf'] })
			// A scheme change rewrites every registration's components.
			void queryClient.invalidateQueries({ queryKey: ['academic'] })
		},
	})
}

export function useSaveScheme(offering: string) {
	return useCourseMutation(offering, (rows: GradeSchemeRow[]) =>
		frappePost<{ scheme: CourseDetail['scheme'] }>('sibbcs.api.course.save_scheme', {
			course_offering: offering,
			rows,
		}),
	)
}

export function useDeleteScheme(offering: string) {
	return useCourseMutation(offering, () =>
		frappePost<{ scheme: null }>('sibbcs.api.course.delete_scheme', {
			course_offering: offering,
		}),
	)
}
