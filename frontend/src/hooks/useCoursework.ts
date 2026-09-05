import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { frappeGet, frappePost } from '@/lib/frappe'
import type { CourseworkResponse } from '@/types'

export const courseworkKeys = {
	one: (registration: string) => ['coursework', registration] as const,
}

export function useCoursework(registration: string | null) {
	return useQuery({
		queryKey: courseworkKeys.one(registration ?? ''),
		queryFn: () =>
			frappeGet<CourseworkResponse>('sibbcs.api.coursework.coursework', {
				course_registration: registration,
			}),
		enabled: Boolean(registration),
	})
}

export function useSubmitWork(registration: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (args: { assignment: string; body?: string; url?: string }) =>
			frappePost('sibbcs.api.coursework.submit', {
				course_registration: registration,
				...args,
			}),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: courseworkKeys.one(registration) })
			// Handing work in does not move a grade, but the dashboard counts
			// what is outstanding.
			void queryClient.invalidateQueries({ queryKey: ['student'] })
		},
	})
}
