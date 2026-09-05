import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { frappeGet, frappePost } from '@/lib/frappe'
import type {
	AnnouncementsResponse,
	CalendarResponse,
	DiscussionRoom,
	DiscussionThread,
	DiscussionTopic,
	InboxResponse,
	LessonDiscussion,
	OfficeContact,
	ThreadResponse,
	TodoResponse,
	UnreadCounts,
} from '@/types'

export const commsKeys = {
	all: ['comms'] as const,
	todo: ['comms', 'todo'] as const,
	calendar: (start?: string, end?: string) => ['comms', 'calendar', start, end] as const,
	announcements: ['comms', 'announcements'] as const,
	inbox: ['comms', 'inbox'] as const,
	thread: (name: string) => ['comms', 'thread', name] as const,
	office: ['comms', 'office'] as const,
	rooms: ['comms', 'rooms'] as const,
	topics: (offering: string) => ['comms', 'topics', offering] as const,
	replies: (topic: string) => ['comms', 'replies', topic] as const,
	unread: ['comms', 'unread'] as const,
}

export const useTodo = () =>
	useQuery({
		queryKey: commsKeys.todo,
		queryFn: () => frappeGet<TodoResponse>('sibbcs.api.agenda.todo'),
	})

export const useCalendar = (start?: string, end?: string) =>
	useQuery({
		queryKey: commsKeys.calendar(start, end),
		queryFn: () => frappeGet<CalendarResponse>('sibbcs.api.agenda.calendar', { start, end }),
	})

export const useAnnouncements = () =>
	useQuery({
		queryKey: commsKeys.announcements,
		queryFn: () => frappeGet<AnnouncementsResponse>('sibbcs.api.comms.announcements'),
	})

export const useInbox = () =>
	useQuery({
		queryKey: commsKeys.inbox,
		queryFn: () => frappeGet<InboxResponse>('sibbcs.api.comms.inbox'),
	})

export const useThread = (name: string | null) =>
	useQuery({
		queryKey: commsKeys.thread(name ?? ''),
		queryFn: () => frappeGet<ThreadResponse>('sibbcs.api.comms.thread', { name }),
		enabled: Boolean(name),
	})

export const useOfficeContacts = () =>
	useQuery({
		queryKey: commsKeys.office,
		queryFn: () => frappeGet<OfficeContact[]>('sibbcs.api.comms.office_contacts'),
	})

export const useDiscussionRooms = () =>
	useQuery({
		queryKey: commsKeys.rooms,
		queryFn: () => frappeGet<DiscussionRoom[]>('sibbcs.api.comms.discussion_rooms'),
	})

export const useDiscussionTopics = (offering: string | null) =>
	useQuery({
		queryKey: commsKeys.topics(offering ?? ''),
		queryFn: () =>
			frappeGet<DiscussionTopic[]>('sibbcs.api.comms.discussion_topics', {
				course_offering: offering,
			}),
		enabled: Boolean(offering),
	})

export const useDiscussionReplies = (topic: string | null) =>
	useQuery({
		queryKey: commsKeys.replies(topic ?? ''),
		queryFn: () =>
			frappeGet<DiscussionThread>('sibbcs.api.comms.discussion_replies', { topic }),
		enabled: Boolean(topic),
	})

/**
 * The sidebar badges.
 *
 * Polled rather than pushed. Frappe has socketio, but a count that is a minute
 * stale costs a student nothing, and a websocket per signed-in student costs
 * the box something at a thousand of them.
 */
export const useUnreadCounts = () =>
	useQuery({
		queryKey: commsKeys.unread,
		queryFn: () => frappeGet<UnreadCounts>('sibbcs.api.comms.unread_counts'),
		refetchInterval: 60_000,
		staleTime: 30_000,
	})

export function useMarkAnnouncementRead() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (announcement: string) =>
			frappePost('sibbcs.api.comms.mark_announcement_read', { announcement }),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: commsKeys.announcements })
			void queryClient.invalidateQueries({ queryKey: commsKeys.unread })
		},
	})
}

export function useSendMessage() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (values: { subject?: string; body: string; reply_to?: string }) =>
			frappePost<{ message: string; thread: string }>(
				'sibbcs.api.comms.send_message',
				values,
			),
		onSuccess: (result) => {
			void queryClient.invalidateQueries({ queryKey: commsKeys.inbox })
			void queryClient.invalidateQueries({ queryKey: commsKeys.unread })
			if (result?.thread) {
				void queryClient.invalidateQueries({ queryKey: commsKeys.thread(result.thread) })
			}
		},
	})
}

export function usePostTopic() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (values: { course_offering: string; title: string; reply: string }) =>
			frappePost<{ topic: string }>('sibbcs.api.comms.post_topic', values),
		onSuccess: (_result, values) => {
			void queryClient.invalidateQueries({ queryKey: commsKeys.rooms })
			void queryClient.invalidateQueries({
				queryKey: commsKeys.topics(values.course_offering),
			})
		},
	})
}

export function usePostReply() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (values: { topic: string; reply: string }) =>
			frappePost<{ reply: string }>('sibbcs.api.comms.post_reply', values),
		onSuccess: (_result, values) => {
			void queryClient.invalidateQueries({ queryKey: commsKeys.replies(values.topic) })
		},
	})
}


// --- a thread on one lesson ------------------------------------------------

export const lessonDiscussionKey = (moduleItem: string) =>
	['comms', 'lesson-discussion', moduleItem] as const

export function useLessonDiscussion(moduleItem: string | null) {
	return useQuery({
		queryKey: lessonDiscussionKey(moduleItem ?? ''),
		queryFn: () =>
			frappeGet<LessonDiscussion>('sibbcs.api.comms.lesson_discussion', {
				module_item: moduleItem,
			}),
		enabled: Boolean(moduleItem),
	})
}

export function usePostLessonReply(moduleItem: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (reply: string) =>
			frappePost<{ reply: string; topic: string }>('sibbcs.api.comms.post_lesson_reply', {
				module_item: moduleItem,
				reply,
			}),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: lessonDiscussionKey(moduleItem) })
		},
	})
}
