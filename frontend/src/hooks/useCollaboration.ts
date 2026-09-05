import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { frappeGet, frappePost } from '@/lib/frappe'
import type {
	CourseDiscussionRow,
	GroupSetsResponse,
	MyDiscussionsResponse,
	OverrideRow,
} from '@/types'

export const collaborationKeys = {
	groups: (offering: string) => ['collab', 'groups', offering] as const,
	discussions: (offering: string) => ['collab', 'discussions', offering] as const,
	overrides: (assignment: string) => ['collab', 'overrides', assignment] as const,
	mine: (registration: string) => ['collab', 'mine', registration] as const,
}

// --- groups ----------------------------------------------------------------

export function useGroupSets(offering: string | null) {
	return useQuery({
		queryKey: collaborationKeys.groups(offering ?? ''),
		queryFn: () =>
			frappeGet<GroupSetsResponse>('sibbcs.api.collaboration.group_sets', {
				course_offering: offering,
			}),
		enabled: Boolean(offering),
	})
}

function useGroupMutation<TArgs, TResult>(
	offering: string,
	call: (args: TArgs) => Promise<TResult>,
) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: call,
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: collaborationKeys.groups(offering) })
			// A group can carry a differentiated date, so what a student sees
			// may have changed with it.
			void queryClient.invalidateQueries({ queryKey: ['coursework'] })
		},
	})
}

export function useSaveGroupSet(offering: string) {
	return useGroupMutation(
		offering,
		(args: { title: string; self_signup?: number; group_limit?: number; name?: string }) =>
			frappePost<{ group_set: string }>('sibbcs.api.collaboration.save_group_set', {
				course_offering: offering,
				...args,
			}),
	)
}

export function useSaveGroup(offering: string) {
	return useGroupMutation(
		offering,
		(args: { group_set: string; title: string; members?: string[]; name?: string }) =>
			frappePost<{ group: string }>('sibbcs.api.collaboration.save_group', args),
	)
}

export function useDeleteGroup(offering: string) {
	return useGroupMutation(offering, (group: string) =>
		frappePost<{ deleted: string }>('sibbcs.api.collaboration.delete_group', { group }),
	)
}

// --- differentiated dates --------------------------------------------------

export function useOverrides(assignment: string | null) {
	return useQuery({
		queryKey: collaborationKeys.overrides(assignment ?? ''),
		queryFn: () =>
			frappeGet<{ rows: OverrideRow[] }>('sibbcs.api.collaboration.overrides_for', {
				assignment,
			}),
		enabled: Boolean(assignment),
	})
}

export function useSaveOverride(assignment: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (args: { values: Record<string, unknown>; name?: string }) =>
			frappePost<{ override: string }>('sibbcs.api.collaboration.save_override', {
				assignment,
				...args,
			}),
		onSuccess: () => {
			void queryClient.invalidateQueries({
				queryKey: collaborationKeys.overrides(assignment),
			})
			void queryClient.invalidateQueries({ queryKey: ['coursework'] })
			void queryClient.invalidateQueries({ queryKey: ['marking'] })
		},
	})
}

export function useDeleteOverride(assignment: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (name: string) =>
			frappePost<{ deleted: string }>('sibbcs.api.collaboration.delete_override', {
				name,
			}),
		onSuccess: () => {
			void queryClient.invalidateQueries({
				queryKey: collaborationKeys.overrides(assignment),
			})
			void queryClient.invalidateQueries({ queryKey: ['coursework'] })
		},
	})
}

// --- discussions -----------------------------------------------------------

export function useCourseDiscussions(offering: string | null) {
	return useQuery({
		queryKey: collaborationKeys.discussions(offering ?? ''),
		queryFn: () =>
			frappeGet<{ rows: CourseDiscussionRow[] }>('sibbcs.api.collaboration.discussions', {
				course_offering: offering,
			}),
		enabled: Boolean(offering),
	})
}

export function useSaveDiscussion(offering: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (args: { values: Record<string, unknown>; name?: string }) =>
			frappePost<{ discussion: string; topic: string | null }>(
				'sibbcs.api.collaboration.save_discussion',
				{ course_offering: offering, ...args },
			),
		onSuccess: () => {
			void queryClient.invalidateQueries({
				queryKey: collaborationKeys.discussions(offering),
			})
		},
	})
}

export function useMyDiscussions(registration: string | null) {
	return useQuery({
		queryKey: collaborationKeys.mine(registration ?? ''),
		queryFn: () =>
			frappeGet<MyDiscussionsResponse>('sibbcs.api.collaboration.my_discussions', {
				course_registration: registration,
			}),
		enabled: Boolean(registration),
	})
}

export function useRecordParticipation(registration: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (discussion: string) =>
			frappePost<{ submission: string | null; posts: number; enough: boolean }>(
				'sibbcs.api.collaboration.record_participation',
				{ course_registration: registration, discussion },
			),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: collaborationKeys.mine(registration) })
			void queryClient.invalidateQueries({ queryKey: ['coursework'] })
		},
	})
}
