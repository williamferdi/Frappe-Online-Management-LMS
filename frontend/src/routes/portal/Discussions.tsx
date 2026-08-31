import { useState, type FormEvent } from 'react'
import { ArrowLeft, LoaderCircle, MessageSquarePlus, MessagesSquare, Send } from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { RichText } from '@/components/RichText'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
	Dialog,
	DialogContent,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
	useDiscussionReplies,
	useDiscussionRooms,
	useDiscussionTopics,
	usePostReply,
	usePostTopic,
} from '@/hooks/useComms'
import { FrappeError } from '@/lib/frappe'
import { cn, formatDate, initials } from '@/lib/utils'
import type { DiscussionRoom } from '@/types'

export function Discussions() {
	const [room, setRoom] = useState<DiscussionRoom | null>(null)
	const [topic, setTopic] = useState<string | null>(null)
	const query = useDiscussionRooms()

	if (topic && room) {
		return <Topic topic={topic} room={room} onBack={() => setTopic(null)} />
	}

	if (room) {
		return <Room room={room} onBack={() => setRoom(null)} onOpen={setTopic} />
	}

	return (
		<QueryState query={query} title="Discussions">
			{(rooms) => <Rooms rooms={rooms} onOpen={setRoom} />}
		</QueryState>
	)
}

function Rooms({
	rooms,
	onOpen,
}: {
	rooms: DiscussionRoom[]
	onOpen: (room: DiscussionRoom) => void
}) {
	if (rooms.length === 0) {
		return (
			<>
				<PageHeader title="Discussions" />
				<Card>
					<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
						<MessagesSquare className="text-muted-foreground size-6" />
						<div className="font-medium">No course discussions yet</div>
						<p className="text-muted-foreground max-w-sm text-sm">
							Each course you register for gets its own discussion room, shared with
							your cohort and the instructor.
						</p>
					</CardContent>
				</Card>
			</>
		)
	}

	return (
		<>
			<PageHeader
				title="Discussions"
				description="One room per course you are registered on"
			/>
			<ul className="grid gap-3 sm:grid-cols-2">
				{rooms.map((room) => (
					<li key={room.course_offering}>
						<button
							type="button"
							onClick={() => onOpen(room)}
							className="w-full text-left"
						>
							<Card className="hover:border-primary/50 h-full transition-colors">
								<CardContent className="p-4">
									<div className="flex items-center justify-between gap-2">
										<span className="font-mono text-xs font-semibold">{room.course}</span>
										<Badge variant="muted">{room.term}</Badge>
									</div>
									<div className="mt-1 font-medium">{room.course_title || room.course}</div>
									<div className="text-muted-foreground mt-1 text-xs">
										{room.topics} {room.topics === 1 ? 'discussion' : 'discussions'}
									</div>
								</CardContent>
							</Card>
						</button>
					</li>
				))}
			</ul>
		</>
	)
}

function Room({
	room,
	onBack,
	onOpen,
}: {
	room: DiscussionRoom
	onBack: () => void
	onOpen: (topic: string) => void
}) {
	const query = useDiscussionTopics(room.course_offering)
	const [starting, setStarting] = useState(false)

	return (
		<QueryState query={query} title={room.course_title || room.course}>
			{(topics) => (
				<>
					<PageHeader
						title={room.course_title || room.course}
						description={`${room.course} · ${room.term}`}
						actions={
							<div className="flex gap-2">
								<Button variant="outline" size="sm" onClick={onBack}>
									<ArrowLeft /> Rooms
								</Button>
								<Button size="sm" onClick={() => setStarting(true)}>
									<MessageSquarePlus /> New discussion
								</Button>
							</div>
						}
					/>

					{topics.length === 0 ? (
						<Card>
							<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
								<MessagesSquare className="text-muted-foreground size-6" />
								<div className="font-medium">Nothing here yet</div>
								<p className="text-muted-foreground max-w-sm text-sm">
									Start the first discussion for this course.
								</p>
							</CardContent>
						</Card>
					) : (
						<Card>
							<CardContent className="p-0">
								<ul className="divide-y">
									{topics.map((topic) => (
										<li key={topic.name}>
											<button
												type="button"
												onClick={() => onOpen(topic.name)}
												className="hover:bg-muted/50 flex w-full items-center gap-3 px-4 py-3 text-left transition-colors"
											>
												<div className="min-w-0 flex-1">
													<div className="truncate font-medium">{topic.title}</div>
													<div className="text-muted-foreground text-xs">
														{topic.author_name} · {formatDate(topic.creation)}
													</div>
												</div>
												<Badge variant="muted">
													{topic.replies} {topic.replies === 1 ? 'reply' : 'replies'}
												</Badge>
											</button>
										</li>
									))}
								</ul>
							</CardContent>
						</Card>
					)}

					<NewTopicDialog
						room={room}
						open={starting}
						onClose={() => setStarting(false)}
						onCreated={onOpen}
					/>
				</>
			)}
		</QueryState>
	)
}

function NewTopicDialog({
	room,
	open,
	onClose,
	onCreated,
}: {
	room: DiscussionRoom
	open: boolean
	onClose: () => void
	onCreated: (topic: string) => void
}) {
	const post = usePostTopic()
	const [title, setTitle] = useState('')
	const [reply, setReply] = useState('')

	function onSubmit(event: FormEvent) {
		event.preventDefault()
		post.mutate(
			{ course_offering: room.course_offering, title, reply },
			{
				onSuccess: (result) => {
					setTitle('')
					setReply('')
					onClose()
					toast.success('Discussion started')
					if (result?.topic) onCreated(result.topic)
				},
				onError: (error) =>
					toast.error(
						error instanceof FrappeError ? error.message : 'That discussion was not started.',
					),
			},
		)
	}

	return (
		<Dialog open={open} onOpenChange={(next) => !next && onClose()}>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>New discussion in {room.course}</DialogTitle>
				</DialogHeader>
				<form onSubmit={onSubmit} className="space-y-4" noValidate>
					<div className="space-y-2">
						<Label htmlFor="topic-title">Title</Label>
						<Input
							id="topic-title"
							value={title}
							onChange={(e) => setTitle(e.target.value)}
							autoFocus
						/>
					</div>
					<div className="space-y-2">
						<Label htmlFor="topic-body">First message</Label>
						<Textarea
							id="topic-body"
							value={reply}
							onChange={(e) => setReply(e.target.value)}
						/>
					</div>
					<DialogFooter>
						<Button type="button" variant="outline" onClick={onClose}>
							Cancel
						</Button>
						<Button type="submit" disabled={!title.trim() || !reply.trim() || post.isPending}>
							{post.isPending && <LoaderCircle className="animate-spin" />}
							Post
						</Button>
					</DialogFooter>
				</form>
			</DialogContent>
		</Dialog>
	)
}

function Topic({
	topic,
	room,
	onBack,
}: {
	topic: string
	room: DiscussionRoom
	onBack: () => void
}) {
	const query = useDiscussionReplies(topic)
	const post = usePostReply()
	const [reply, setReply] = useState('')

	function onSubmit(event: FormEvent) {
		event.preventDefault()
		post.mutate(
			{ topic, reply },
			{
				onSuccess: () => {
					setReply('')
					toast.success('Reply posted')
				},
				onError: (error) =>
					toast.error(
						error instanceof FrappeError ? error.message : 'That reply was not posted.',
					),
			},
		)
	}

	return (
		<QueryState query={query} title="Discussion">
			{(data) => (
				<>
					<PageHeader
						title={data.title}
						description={`${room.course} · ${room.course_title ?? ''}`}
						actions={
							<Button variant="outline" size="sm" onClick={onBack}>
								<ArrowLeft /> Back
							</Button>
						}
					/>

					<ul className="space-y-3">
						{data.replies.map((entry) => (
							<li key={entry.name}>
								<Card className={cn(entry.mine && 'bg-muted/40')}>
									<CardContent className="flex gap-3 p-4">
										<div className="bg-primary/10 text-primary grid size-8 shrink-0 place-items-center rounded-full text-xs font-semibold">
											{initials(entry.author_name)}
										</div>
										<div className="min-w-0 flex-1">
											<div className="flex items-center justify-between gap-2">
												<span className="text-sm font-medium">
													{entry.mine ? 'You' : entry.author_name}
												</span>
												<span className="text-muted-foreground text-xs">
													{formatDate(entry.creation)}
												</span>
											</div>
											<RichText html={entry.reply} className="mt-1" />
										</div>
									</CardContent>
								</Card>
							</li>
						))}
					</ul>

					<Card className="mt-4">
						<CardContent className="p-4">
							<form onSubmit={onSubmit} className="space-y-3">
								<Label htmlFor="discussion-reply">Reply</Label>
								<Textarea
									id="discussion-reply"
									value={reply}
									onChange={(e) => setReply(e.target.value)}
									placeholder="Add to the discussion"
								/>
								<div className="flex justify-end">
									<Button type="submit" disabled={!reply.trim() || post.isPending}>
										{post.isPending && <LoaderCircle className="animate-spin" />}
										<Send /> Post reply
									</Button>
								</div>
							</form>
						</CardContent>
					</Card>
				</>
			)}
		</QueryState>
	)
}
