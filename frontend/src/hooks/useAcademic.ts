import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { frappeGet, frappePost } from '@/lib/frappe'
import type {
	GradeComponentRow,
	OfferingsResponse,
	PromotionsResponse,
	RosterResponse,
	SaveGradesResult,
	StudentDetail,
	StudentsResponse,
} from '@/types'

export const academicKeys = {
	all: ['academic'] as const,
	students: (filters: StudentFilters) => ['academic', 'students', filters] as const,
	student: (name: string) => ['academic', 'student', name] as const,
	offerings: (term: string) => ['academic', 'offerings', term] as const,
	roster: (offering: string) => ['academic', 'roster', offering] as const,
	promotions: ['academic', 'promotions'] as const,
}

export interface StudentFilters {
	search?: string
	program?: string
	level?: string
}

export const useStudents = (filters: StudentFilters) =>
	useQuery({
		queryKey: academicKeys.students(filters),
		queryFn: () =>
			frappeGet<StudentsResponse>('sibbcs.api.academic_api.students', {
				search: filters.search || undefined,
				program: filters.program || undefined,
				level: filters.level || undefined,
			}),
		placeholderData: (previous) => previous,
	})

export const useStudentDetail = (name: string | null) =>
	useQuery({
		queryKey: academicKeys.student(name ?? ''),
		queryFn: () => frappeGet<StudentDetail>('sibbcs.api.academic_api.student', { name }),
		enabled: Boolean(name),
	})

export const useOfferings = (term: string) =>
	useQuery({
		queryKey: academicKeys.offerings(term),
		queryFn: () =>
			frappeGet<OfferingsResponse>('sibbcs.api.academic_api.offerings', {
				term: term || undefined,
			}),
		placeholderData: (previous) => previous,
	})

export const useRoster = (offering: string | null) =>
	useQuery({
		queryKey: academicKeys.roster(offering ?? ''),
		queryFn: () =>
			frappeGet<RosterResponse>('sibbcs.api.academic_api.roster', {
				course_offering: offering,
			}),
		enabled: Boolean(offering),
	})

export const usePromotions = () =>
	useQuery({
		queryKey: academicKeys.promotions,
		queryFn: () => frappeGet<PromotionsResponse>('sibbcs.api.academic_api.promotions'),
	})

/**
 * Saving marks recomputes the student's credits and CGPA, so the whole
 * academic namespace goes stale, not just the roster.
 */
export function useSaveGrades(offering: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (values: {
			registration: string
			components: GradeComponentRow[]
			status?: string
		}) =>
			frappePost<SaveGradesResult>('sibbcs.api.academic_api.save_grades', {
				registration: values.registration,
				components: values.components,
				status: values.status,
			}),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: academicKeys.roster(offering) })
			void queryClient.invalidateQueries({ queryKey: academicKeys.promotions })
			void queryClient.invalidateQueries({ queryKey: ['academic', 'student'] })
		},
	})
}

export function usePromote() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (values: {
			program_enrollment: string
			to_level: number
			remarks?: string
		}) =>
			frappePost<string>(
				'sibbcs.academic.doctype.level_promotion.level_promotion.promote',
				values,
			),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: academicKeys.all }),
	})
}
