import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { frappeGet, frappePost } from '@/lib/frappe'
import type { ContentOutline, LessonDraft, PageDraft } from '@/types'

export const contentKeys = {
	outline: (offering: string) => ['content', 'outline', offering] as const,
	lesson: (name: string) => ['content', 'lesson', name] as const,
	page: (name: string) => ['content', 'page', name] as const,
}

export function useContentOutline(offering: string | null) {
	return useQuery({
		queryKey: contentKeys.outline(offering ?? ''),
		queryFn: () =>
			frappeGet<ContentOutline>('sibbcs.api.content.outline', {
				course_offering: offering,
			}),
		enabled: Boolean(offering),
	})
}

/*
 * A lesson or page, opened to be edited.
 *
 * Never served from a remembered copy (`gcTime: 0`). The editor takes its
 * starting text once, so a copy from before the last save would be saved
 * straight back over it -- the teacher's previous edit quietly undone by the
 * next one.
 */

export function useLesson(name: string | null) {
	return useQuery({
		queryKey: contentKeys.lesson(name ?? ''),
		queryFn: () => frappeGet<LessonDraft>('sibbcs.api.content.lesson', { name }),
		enabled: Boolean(name),
		gcTime: 0,
	})
}

/** The offering goes too, so the server can refuse a page on a course this
 *  teacher does not teach -- by name alone, it would open any page there is. */
export function usePage(name: string | null, offering: string) {
	return useQuery({
		queryKey: contentKeys.page(name ?? ''),
		queryFn: () =>
			frappeGet<PageDraft>('sibbcs.api.content.page', { name, course_offering: offering }),
		enabled: Boolean(name),
		gcTime: 0,
	})
}

/**
 * Writing content invalidates the module builder too: a new lesson or page is
 * immediately something you can add to a module, and a stale picker is how a
 * teacher concludes the thing they just wrote did not save.
 */
function useContentMutation<TArgs, TResult>(
	offering: string,
	call: (args: TArgs) => Promise<TResult>,
) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: call,
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: contentKeys.outline(offering) })
			void queryClient.invalidateQueries({ queryKey: ['syllabus', 'staff', offering] })
			void queryClient.invalidateQueries({ queryKey: ['syllabus', 'content-space'] })
			void queryClient.invalidateQueries({ queryKey: ['content', 'lesson'] })
		},
	})
}

export function useSaveChapter(offering: string) {
	return useContentMutation(offering, (args: { title: string; name?: string }) =>
		frappePost<{ chapter: string }>('sibbcs.api.content.save_chapter', {
			course_offering: offering,
			...args,
		}),
	)
}

export function useSaveLesson(offering: string) {
	return useContentMutation(
		offering,
		(args: {
			chapter: string
			title: string
			blocks: { type: string; data: Record<string, unknown> }[]
			name?: string
		}) =>
			frappePost<{ lesson: string }>('sibbcs.api.content.save_lesson', {
				course_offering: offering,
				...args,
			}),
	)
}

export function useDeleteLesson(offering: string) {
	return useContentMutation(offering, (name: string) =>
		frappePost<{ deleted: string; module_items_removed: number }>(
			'sibbcs.api.content.delete_lesson',
			{ course_offering: offering, name },
		),
	)
}

export function useSavePage(offering: string) {
	return useContentMutation(
		offering,
		(args: { title: string; body?: string; published?: number; name?: string }) =>
			frappePost<{ page: string }>('sibbcs.api.content.save_page', {
				course_offering: offering,
				...args,
			}),
	)
}

export function useDeletePage(offering: string) {
	return useContentMutation(offering, (name: string) =>
		frappePost<{ deleted: string }>('sibbcs.api.content.delete_page', {
			course_offering: offering,
			name,
		}),
	)
}

export function useSaveFile(offering: string) {
	return useContentMutation(
		offering,
		(args: { title: string; file?: string; description?: string; name?: string }) =>
			frappePost<{ file: string }>('sibbcs.api.content.save_file', {
				course_offering: offering,
				...args,
			}),
	)
}

export function useDeleteFile(offering: string) {
	return useContentMutation(offering, (name: string) =>
		frappePost<{ deleted: string }>('sibbcs.api.content.delete_file', {
			course_offering: offering,
			name,
		}),
	)
}
