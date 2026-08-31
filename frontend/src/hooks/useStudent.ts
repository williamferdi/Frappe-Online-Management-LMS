import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { frappeGet, frappePost } from '@/lib/frappe'
import type {
	DashboardResponse,
	GradesResponse,
	MyCoursesResponse,
	ProfileResponse,
	RegistrationOptions,
	StudentRecord,
} from '@/types'

/** One namespace, so a registration invalidates every screen that shows one. */
export const studentKeys = {
	all: ['student'] as const,
	dashboard: ['student', 'dashboard'] as const,
	myCourses: ['student', 'my-courses'] as const,
	grades: ['student', 'grades'] as const,
	profile: ['student', 'profile'] as const,
	registration: ['student', 'registration-options'] as const,
}

export const useDashboard = () =>
	useQuery({
		queryKey: studentKeys.dashboard,
		queryFn: () => frappeGet<DashboardResponse>('sibbcs.api.student.dashboard'),
	})

export const useMyCourses = () =>
	useQuery({
		queryKey: studentKeys.myCourses,
		queryFn: () => frappeGet<MyCoursesResponse>('sibbcs.api.student.my_courses'),
	})

export const useGrades = () =>
	useQuery({
		queryKey: studentKeys.grades,
		queryFn: () => frappeGet<GradesResponse>('sibbcs.api.student.grades'),
	})

export const useProfile = () =>
	useQuery({
		queryKey: studentKeys.profile,
		queryFn: () => frappeGet<ProfileResponse>('sibbcs.api.student.profile'),
	})

export const useRegistrationOptions = () =>
	useQuery({
		queryKey: studentKeys.registration,
		queryFn: () => frappeGet<RegistrationOptions>('sibbcs.api.student.registration_options'),
	})

/**
 * Registering changes the course list, the fee total and what is still on
 * offer, so the whole student namespace is refetched rather than three keys
 * being kept in step by hand.
 */
export function useRegister() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (courseOffering: string) =>
			frappePost<{ registration: string; lms_ready: boolean }>(
				'sibbcs.academic.portal.register',
				{ course_offering: courseOffering },
			),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: studentKeys.all }),
	})
}

export function useWithdraw() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (registration: string) =>
			frappePost<{ registration: string; status: string }>(
				'sibbcs.academic.portal.withdraw',
				{ registration },
			),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: studentKeys.all }),
	})
}

export function useUpdateProfile() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (values: { mobile?: string; whatsapp?: string; address?: string }) =>
			frappePost<StudentRecord>('sibbcs.api.student.update_profile', values),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: studentKeys.profile }),
	})
}

export function useUpdatePhoto() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: async (file: File) => {
			const content = await readAsBase64(file)
			return frappePost<{ photo: string }>('sibbcs.api.student.update_photo', {
				filename: file.name,
				content,
				content_type: file.type,
			})
		},
		onSuccess: () => queryClient.invalidateQueries({ queryKey: studentKeys.profile }),
	})
}

/** The server takes base64, so strip the `data:...;base64,` prefix. */
function readAsBase64(file: File): Promise<string> {
	return new Promise((resolve, reject) => {
		const reader = new FileReader()
		reader.onerror = () => reject(new Error('That file could not be read.'))
		reader.onload = () => {
			const result = String(reader.result)
			resolve(result.slice(result.indexOf(',') + 1))
		}
		reader.readAsDataURL(file)
	})
}
