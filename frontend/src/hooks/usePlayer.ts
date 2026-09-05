import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { frappeGet, frappePost } from '@/lib/frappe'
import type { PlayerCourse, PlayerItem } from '@/types'

export const playerKeys = {
	course: (registration: string) => ['player', 'course', registration] as const,
	item: (registration: string, item: string) =>
		['player', 'item', registration, item] as const,
}

export function usePlayerCourse(registration: string | null) {
	return useQuery({
		queryKey: playerKeys.course(registration ?? ''),
		queryFn: () =>
			frappeGet<PlayerCourse>('sibbcs.api.player.course', {
				course_registration: registration,
			}),
		enabled: Boolean(registration),
	})
}

/**
 * Opening an item is a read that records progress, so it is a mutation: a
 * cached query would mean the second visit never reaches the server, and
 * "I opened it" is exactly what some items count as done.
 */
export function usePlayerItem(registration: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (moduleItem: string) =>
			frappeGet<PlayerItem>('sibbcs.api.player.item', {
				course_registration: registration,
				module_item: moduleItem,
			}),
		onSuccess: () => {
			// Opening one item can complete it, which can unlock the next and
			// move the progress figure in the header.
			void queryClient.invalidateQueries({ queryKey: playerKeys.course(registration) })
		},
	})
}

export function useMarkItemDone(registration: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (moduleItem: string) =>
			frappePost<{ item: string; complete: boolean }>('sibbcs.api.syllabus.mark_done', {
				course_registration: registration,
				module_item: moduleItem,
			}),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: playerKeys.course(registration) })
		},
	})
}

/**
 * Notes save themselves as they are typed, debounced by the caller. No
 * invalidation: the textarea already holds what was sent, and refetching would
 * fight the cursor.
 */
export function useSaveNote(registration: string) {
	return useMutation({
		mutationFn: ({ moduleItem, body }: { moduleItem: string; body: string }) =>
			frappePost<{ saved: boolean; at: string }>('sibbcs.api.player.save_note', {
				course_registration: registration,
				module_item: moduleItem,
				body,
			}),
	})
}

export function useToggleBookmark(registration: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (moduleItem: string) =>
			frappePost<{ bookmarked: number }>('sibbcs.api.player.toggle_bookmark', {
				course_registration: registration,
				module_item: moduleItem,
			}),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: playerKeys.course(registration) })
		},
	})
}
