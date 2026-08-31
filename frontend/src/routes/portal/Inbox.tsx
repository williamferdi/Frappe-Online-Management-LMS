import { useState, type FormEvent } from 'react'
import { ArrowLeft, Inbox as InboxIcon, Info, LoaderCircle, Send } from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { RichText } from '@/components/RichText'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
	useInbox,
	useOfficeContacts,
	useSendMessage,
	useThread,
} from '@/hooks/useComms'
import { FrappeError } from '@/lib/frappe'
import { cn, formatDate, initials } from '@/lib/utils'
import type { InboxResponse } from '@/types'

export function Inbox() {
	const [openThread, setOpenThread] = useState<string | null>(null)
	const [composing, setComposing] = useState(false)
	const query = useInbox()

	if (openThread) {
		return <Thread name={openThread} onBack={() => setOpenThread(null)} />
	}

	if (composing) {
		return <Compose onDone={() => setComposing(false)} />
	}

	return (
		<QueryState query={query} title="Inbox">
			{(data) => (
				<Loaded data={data} onOpen={setOpenThread} onCompose={() => setComposing(true)} />
			)}
		</QueryState>
	)
}

function Loaded({
	data,
	onOpen,
	onCompose,
}: {
	data: InboxResponse
	onOpen: (thread: string) => void
	onCompose: () => void
}) {
	return (
		<>
			<PageHeader
				title="Inbox"
				description={data.unread > 0 ? `${data.unread} unread` : 'No unread messages'}
				actions={
					<Button size="sm" onClick={onCompose}>
						<Send /> New message
					</Button>
				}
			/>

			{data.threads.length === 0 ? (
				<Card>
					<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
						<InboxIcon className="text-muted-foreground size-6" />
						<div className="font-medium">No messages</div>
						<p className="text-muted-foreground max-w-sm text-sm">
							Messages from the Registrar, your instructors and the Student Services
							office appear here.
						</p>
						<Button size="sm" className="mt-2" onClick={onCompose}>
							Write to the office
						</Button>
					</CardContent>
				</Card>
			) : (
				<Card>
					<CardContent className="p-0">
						<ul className="divide-y">
							{data.threads.map((thread) => (
								<li key={thread.thread}>
									<button
										type="button"
										onClick={() => onOpen(thread.thread)}
										className="hover:bg-muted/50 flex w-full items-start gap-3 px-4 py-3 text-left transition-colors"
									>
										<div className="bg-primary/10 text-primary mt-0.5 grid size-8 shrink-0 place-items-center rounded-full text-xs font-semibold">
											{initials(thread.last?.sender_name ?? '?')}
										</div>
										<div className="min-w-0 flex-1">
											<div className="flex items-center gap-2">
												<span
													className={cn(
														'truncate',
														thread.unread > 0 ? 'font-semibold' : 'font-medium',
													)}
												>
													{thread.subject}
												</span>
												{thread.unread > 0 && (
													<span className="bg-primary size-2 shrink-0 rounded-full" />
												)}
											</div>
											<div className="text-muted-foreground truncate text-sm">
												{thread.last?.sender_name}: {thread.last?.preview}
											</div>
										</div>
										<div className="text-muted-foreground shrink-0 text-xs">
											{formatDate(thread.last?.sent_on)}
											{thread.count > 1 && (
												<Badge variant="muted" className="ml-2">
													{thread.count}
												</Badge>
											)}
										</div>
									</button>
								</li>
							))}
						</ul>
					</CardContent>
				</Card>
			)}
		</>
	)
}

function Thread({ name, onBack }: { name: string; onBack: () => void }) {
	const query = useThread(name)
	const send = useSendMessage()
	const [reply, setReply] = useState('')

	function onSubmit(event: FormEvent) {
		event.preventDefault()
		send.mutate(
			{ body: reply, reply_to: name },
			{
				onSuccess: () => {
					setReply('')
					toast.success('Reply sent')
				},
				onError: (error) =>
					toast.error(
						error instanceof FrappeError ? error.message : 'That reply was not sent.',
					),
			},
		)
	}

	return (
		<QueryState query={query} title="Conversation">
			{(data) => (
				<>
					<PageHeader
						title={data.subject || 'Conversation'}
						actions={
							<Button variant="outline" size="sm" onClick={onBack}>
								<ArrowLeft /> Inbox
							</Button>
						}
					/>

					<ul className="space-y-3">
						{data.messages.map((message) => (
							<li key={message.name}>
								<Card className={cn(message.mine && 'bg-muted/40')}>
									<CardContent className="p-4">
										<div className="flex items-center justify-between gap-2">
											<span className="text-sm font-medium">
												{message.mine ? 'You' : message.sender_name}
											</span>
											<span className="text-muted-foreground text-xs">
												{formatDate(message.sent_on)}
											</span>
										</div>
										<RichText html={message.body} className="mt-2" />
									</CardContent>
								</Card>
							</li>
						))}
					</ul>

					<Card className="mt-4">
						<CardContent className="p-4">
							<form onSubmit={onSubmit} className="space-y-3">
								<Label htmlFor="reply">Reply</Label>
								<Textarea
									id="reply"
									value={reply}
									onChange={(e) => setReply(e.target.value)}
									placeholder="Write your reply"
								/>
								<div className="flex justify-end">
									<Button type="submit" disabled={!reply.trim() || send.isPending}>
										{send.isPending && <LoaderCircle className="animate-spin" />}
										<Send /> Send
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

function Compose({ onDone }: { onDone: () => void }) {
	const contacts = useOfficeContacts()
	const send = useSendMessage()
	const [subject, setSubject] = useState('')
	const [body, setBody] = useState('')

	const recipients = contacts.data ?? []
	// The endpoint decides who a new message reaches; the student cannot name
	// anyone. If nobody holds an office role there is nowhere for it to go, and
	// saying so here beats letting them write it and fail on send.
	const noRecipients = contacts.isSuccess && recipients.length === 0

	function onSubmit(event: FormEvent) {
		event.preventDefault()
		send.mutate(
			{ subject, body },
			{
				onSuccess: () => {
					toast.success('Message sent to the office')
					onDone()
				},
				onError: (error) =>
					toast.error(
						error instanceof FrappeError ? error.message : 'That message was not sent.',
					),
			},
		)
	}

	return (
		<>
			<PageHeader
				title="New message"
				actions={
					<Button variant="outline" size="sm" onClick={onDone}>
						<ArrowLeft /> Inbox
					</Button>
				}
			/>

			{noRecipients ? (
				<Alert variant="warning">
					<Info />
					<AlertDescription>
						Nobody at the college is set up to receive portal messages yet. Please
						contact the office directly for now.
					</AlertDescription>
				</Alert>
			) : (
				<Card>
					<CardContent className="p-5">
						<form onSubmit={onSubmit} className="space-y-4" noValidate>
							<Alert variant="info">
								<Info />
								<AlertDescription>
									Goes to the college office
									{recipients.length > 0 && (
										<> — {recipients.map((person) => person.full_name).join(', ')}</>
									)}
									.
								</AlertDescription>
							</Alert>

							<div className="space-y-2">
								<Label htmlFor="subject">Subject</Label>
								<Input
									id="subject"
									value={subject}
									onChange={(e) => setSubject(e.target.value)}
									required
								/>
							</div>

							<div className="space-y-2">
								<Label htmlFor="body">Message</Label>
								<Textarea
									id="body"
									className="min-h-40"
									value={body}
									onChange={(e) => setBody(e.target.value)}
									required
								/>
							</div>

							<div className="flex justify-end gap-2">
								<Button type="button" variant="outline" onClick={onDone}>
									Cancel
								</Button>
								<Button
									type="submit"
									disabled={!subject.trim() || !body.trim() || send.isPending}
								>
									{send.isPending && <LoaderCircle className="animate-spin" />}
									<Send /> Send
								</Button>
							</div>
						</form>
					</CardContent>
				</Card>
			)}
		</>
	)
}
