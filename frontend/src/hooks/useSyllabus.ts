import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { frappeGet, frappePost } from '@/lib/frappe'
import type {
	CourseOutline,
	ModulePreview,
	PreviewItemResponse,
	ReadItemResponse,
	StaffOutline,
} from '@/types'

export const syllabusKeys = {
	staff: (offering: string) => ['syllabus', 'staff', offering] as const,
	mine: (registration: string) => ['syllabus', 'mine', registration] as const,
}

// --- the student's side ----------------------------------------------------

export function useMyCourse(registration: string | null) {
	return useQuery({
		queryKey: syllabusKeys.mine(registration ?? ''),
		queryFn: () =>
			frappeGet<CourseOutline>('sibbcs.api.syllabus.my_course', {
				course_registration: registration,
			}),
		enabled: Boolean(registration),
	})
}

/**
 * Opening an item is a read that can also record progress, so it is a
 * mutation: a query would be cached and the second view would never reach the
 * server, and "I opened it" is exactly what some items count as done.
 */
export function useReadItem(registration: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (moduleItem: string) =>
			frappeGet<ReadItemResponse>('sibbcs.api.syllabus.read_item', {
				course_registration: registration,
				module_item: moduleItem,
			}),
		onSuccess: () => {
			// Opening one item can unlock the next, so the outline is stale.
			void queryClient.invalidateQueries({ queryKey: syllabusKeys.mine(registration) })
		},
	})
}

export function useMarkDone(registration: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (moduleItem: string) =>
			frappePost<{ item: string; complete: boolean }>('sibbcs.api.syllabus.mark_done', {
				course_registration: registration,
				module_item: moduleItem,
			}),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: syllabusKeys.mine(registration) })
		},
	})
}

// --- the staff side --------------------------------------------------------

export function useStaffOutline(offering: string | null) {
	return useQuery({
		queryKey: syllabusKeys.staff(offering ?? ''),
		queryFn: () =>
			frappeGet<StaffOutline>('sibbcs.api.syllabus.outline', {
				course_offering: offering,
			}),
		enabled: Boolean(offering),
	})
}

function useOutlineMutation<TArgs, TResult>(
	offering: string,
	call: (args: TArgs) => Promise<TResult>,
) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: call,
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: syllabusKeys.staff(offering) })
			// A student's view of the same course has just changed too.
			void queryClient.invalidateQueries({ queryKey: ['syllabus', 'mine'] })
		},
	})
}

export function useSaveModule(offering: string) {
	return useOutlineMutation(
		offering,
		({ values, module }: { values: Record<string, unknown>; module?: string }) =>
			frappePost<{ module: string }>('sibbcs.api.syllabus.save_module', {
				course_offering: offering,
				values,
				...(module ? { module } : {}),
			}),
	)
}

export function useDeleteModule(offering: string) {
	return useOutlineMutation(offering, (module: string) =>
		frappePost<{ deleted: string }>('sibbcs.api.syllabus.delete_module', { module }),
	)
}

export function useSaveItem(offering: string) {
	return useOutlineMutation(
		offering,
		({
			module,
			values,
			item,
		}: {
			module: string
			values: Record<string, unknown>
			item?: string
		}) =>
			frappePost<{ item: string }>('sibbcs.api.syllabus.save_item', {
				module,
				values,
				...(item ? { item } : {}),
			}),
	)
}

export function useDeleteItem(offering: string) {
	return useOutlineMutation(offering, (item: string) =>
		frappePost<{ deleted: string }>('sibbcs.api.syllabus.delete_item', { item }),
	)
}

export function useReorder(offering: string) {
	return useOutlineMutation(
		offering,
		({ module, order }: { module?: string; order: string[] }) =>
			frappePost<{ ordered: number }>('sibbcs.api.syllabus.reorder', {
				...(module ? { module } : { course_offering: offering }),
				order,
			}),
	)
}


// --- somewhere to write lessons -------------------------------------------

export function useContentSpace(offering: string | null) {
	return useQuery({
		queryKey: ['syllabus', 'content-space', offering ?? ''],
		queryFn: () =>
			frappeGet<{
				course: string
				lms_course: string | null
				lessons: number
				authoring_url: string | null
			}>('sibbcs.api.course.content_space', { course_offering: offering }),
		enabled: Boolean(offering),
	})
}

export function useCreateContentSpace(offering: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: () =>
			frappePost<{ lms_course: string; authoring_url: string }>(
				'sibbcs.api.course.create_content_space',
				{ course_offering: offering },
			),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: ['syllabus', 'content-space'] })
			// The module builder lists the course's lessons, so it is stale too.
			void queryClient.invalidateQueries({ queryKey: syllabusKeys.staff(offering) })
		},
	})
}


/**
 * What a student sees, for a teacher to check.
 *
 * Keyed on the registration as well as the offering, so switching who it is
 * previewed as refetches rather than showing the previous student's locks.
 */
export function useModulePreview(offering: string | null, registration: string | null) {
	return useQuery({
		queryKey: ['syllabus', 'preview', offering ?? '', registration ?? ''],
		queryFn: () =>
			frappeGet<ModulePreview>('sibbcs.api.syllabus.preview', {
				course_offering: offering,
				...(registration ? { course_registration: registration } : {}),
			}),
		enabled: Boolean(offering),
	})
}


/**
 * One item's content, for a teacher checking the course.
 *
 * A query rather than a mutation, unlike the student's `useReadItem`: this
 * writes nothing, so caching it is right and reopening an item need not ask
 * the server again.
 */
export function usePreviewItem(offering: string, moduleItem: string | null) {
	return useQuery({
		queryKey: ['syllabus', 'preview-item', offering, moduleItem ?? ''],
		queryFn: () =>
			frappeGet<PreviewItemResponse>('sibbcs.api.syllabus.preview_item', {
				course_offering: offering,
				module_item: moduleItem,
			}),
		enabled: Boolean(moduleItem),
	})
}
