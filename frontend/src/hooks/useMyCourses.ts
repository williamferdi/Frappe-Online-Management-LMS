import { useQuery } from '@tanstack/react-query'

import { frappeGet } from '@/lib/frappe'
import type { MyCoursesResponse } from '@/types'

export const myCoursesKey = ['student', 'my-courses'] as const

export function useMyCourses() {
	return useQuery({
		queryKey: myCoursesKey,
		queryFn: () => frappeGet<MyCoursesResponse>('sibbcs.api.student.my_courses'),
	})
}
