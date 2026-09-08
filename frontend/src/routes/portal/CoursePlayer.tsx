import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
	ArrowLeft,
	List,
	Bookmark,
	Check,
	ChevronLeft,
	ChevronRight,
	CircleCheck,
	CircleDashed,
	Circle,
	Download,
	FileText,
	Lock,
	MessageSquare,
	NotebookPen,
	PanelLeftClose,
	PanelLeftOpen,
	Paperclip,
} from 'lucide-react'
import { toast } from 'sonner'

import { BlockRenderer } from '@/components/BlockRenderer'
import { QueryState } from '@/components/QueryState'
import { RichText } from '@/components/RichText'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { useDebounced } from '@/hooks/useDebounced'
import { useLessonDiscussion, usePostLessonReply } from '@/hooks/useComms'
import {
	useMarkItemDone,
	usePlayerCourse,
	usePlayerItem,
	useSaveNote,
	useToggleBookmark,
} from '@/hooks/usePlayer'
import { FrappeError } from '@/lib/frappe'
import { cn } from '@/lib/utils'
import type { OutlineItem, OutlineModule, PlayerCourse, PlayerItem } from '@/types'

function message(error: unknown) {
	return error instanceof FrappeError ? error.message : 'Something went wrong.'
}

/**
 * The course player: sidebar of modules, one item at a time, and the way
 * forward.
 *
 * The order and the progress figure both come from the server, which flattens
 * the outline once — so the sidebar, the Next button and the percentage can
 * never disagree about how far through somebody is.
 */
export function CoursePlayer() {
	const { name = null, item = null } = useParams()
	const registration = name ? decodeURIComponent(name) : null
	const query = usePlayerCourse(registration)

	return (
		<QueryState query={query} title="Course">
			{(data) => (
				<Player
					data={data}
					registration={registration!}
					current={item ? decodeURIComponent(item) : null}
				/>
			)}
		</QueryState>
	)
}

function Player({
	data,
	registration,
	current,
}: {
	data: PlayerCourse
	registration: string
	current: string | null
}) {
	const navigate = useNavigate()
	const [open, setOpen] = useState(true)

	// Landing on the course with no item chosen starts at the first thing that
	// is not already done — where somebody left off, not the beginning.
	useEffect(() => {
		if (current || data.sequence.length === 0) return
		const items = data.modules.flatMap((module) => module.items)
		const next =
			items.find((row) => !row.complete && !row.locked && row.item_type !== 'Sub-header') ??
			items.find((row) => row.item_type !== 'Sub-header')
		if (next) {
			navigate(
				`/portal/courses/${encodeURIComponent(registration)}/learn/${encodeURIComponent(next.name)}`,
				{ replace: true },
			)
		}
	}, [current, data, registration, navigate])

	const percent = data.progress.percent

	return (
		<div className="-m-4 flex min-h-[calc(100vh-4rem)] flex-col sm:-m-6">
			<header className="bg-card flex items-center gap-2 border-b px-4 py-3 sm:gap-3">
				{/* Named for what it does to the list beside this, not for the
				    list itself: there is a link to the modules page in this same
				    header, and two controls called "modules" cannot be told
				    apart by anybody listening rather than looking. */}
				<Button
					variant="ghost"
					size="icon"
					aria-label={open ? 'Hide the module list' : 'Show the module list'}
					onClick={() => setOpen(!open)}
				>
					{open ? (
						<PanelLeftClose className="size-4" />
					) : (
						<PanelLeftOpen className="size-4" />
					)}
				</Button>

				<Button variant="ghost" size="sm" asChild>
					<Link to="/portal/courses" aria-label="All my courses">
						<ArrowLeft className="size-4" />
					</Link>
				</Button>

				{/* The whole course as a list. The sidebar is a way to get about
				    inside it; this is the way to stand back and see what is
				    coming, which a narrow rail cannot show. The label goes on
				    narrow screens but the name does not. */}
				<Button variant="ghost" size="sm" asChild>
					<Link
						to={`/portal/courses/${encodeURIComponent(registration)}/modules`}
						aria-label="Modules"
					>
						<List className="size-4" />
						<span className="hidden sm:inline">Modules</span>
					</Link>
				</Button>

				{/* A floor, so the controls beside it can never take the whole
				    bar. Measured: without one this reached nothing at 320px. */}
				<span className="min-w-16 flex-1 truncate font-medium">
					{data.registration.course_title || data.registration.course_offering}
				</span>

				{percent !== null && (
					<div className="flex items-center gap-2">
						<div
							className="bg-muted h-1.5 w-12 overflow-hidden rounded-full sm:w-24"
							role="progressbar"
							aria-valuenow={percent}
							aria-valuemin={0}
							aria-valuemax={100}
							aria-label="Course progress"
						>
							<div
								className="bg-primary h-full rounded-full transition-[width] duration-500"
								style={{ width: `${percent}%` }}
							/>
						</div>
						<span className="text-sm font-medium tabular-nums">{percent}%</span>
						<span className="text-muted-foreground hidden text-xs sm:inline">
							complete
						</span>
					</div>
				)}
			</header>

			<div className="flex min-h-0 flex-1">
				{open && (
					<nav
						aria-label="Modules"
						className="bg-card w-64 shrink-0 overflow-y-auto border-r"
					>
						{data.modules.map((module) => (
							<ModuleGroup
								key={module.name}
								module={module}
								registration={registration}
								current={current}
							/>
						))}
					</nav>
				)}

				<main className="min-w-0 flex-1 overflow-y-auto px-4 py-6 sm:px-8">
					{current ? (
						<ItemPane
							key={current}
							registration={registration}
							moduleItem={current}
						/>
					) : (
						<p className="text-muted-foreground text-sm">
							Nothing published on this course yet.
						</p>
					)}
				</main>
			</div>
		</div>
	)
}

function ModuleGroup({
	module,
	registration,
	current,
}: {
	module: OutlineModule
	registration: string
	current: string | null
}) {
	// A module holding what you are reading stays open; the rest remember
	// whether you opened them.
	const holdsCurrent = module.items.some((item) => item.name === current)
	const [open, setOpen] = useState(holdsCurrent || module.state.open)

	return (
		<div className="border-b last:border-0">
			<button
				type="button"
				onClick={() => setOpen(!open)}
				aria-expanded={open}
				className="hover:bg-muted/60 flex w-full items-center gap-2 px-3 py-2.5 text-left"
			>
				<span className="min-w-0 flex-1 truncate text-sm font-medium">
					{module.title}
				</span>
				{module.complete && (
					<CircleCheck className="size-3.5 shrink-0 text-emerald-600" />
				)}
				{!module.state.open && <Lock className="text-muted-foreground size-3 shrink-0" />}
			</button>

			{open && (
				<ul className="pb-1">
					{module.items.map((item) => (
						<SidebarItem
							key={item.name}
							item={item}
							registration={registration}
							current={current}
						/>
					))}
					{module.items.length === 0 && (
						<li className="text-muted-foreground px-3 pb-2 text-xs">Empty</li>
					)}
				</ul>
			)}

			{!module.state.open && module.state.reason && (
				<p className="text-muted-foreground px-3 pb-2 text-xs">{module.state.reason}</p>
			)}
		</div>
	)
}

function SidebarItem({
	item,
	registration,
	current,
}: {
	item: OutlineItem & { bookmarked?: boolean; has_note?: boolean }
	registration: string
	current: string | null
}) {
	if (item.item_type === 'Sub-header') {
		return (
			<li className="text-muted-foreground px-3 pt-2 pb-1 text-[11px] font-medium tracking-wide uppercase">
				{item.title}
			</li>
		)
	}

	const active = item.name === current
	const to = `/portal/courses/${encodeURIComponent(registration)}/learn/${encodeURIComponent(item.name)}`

	const inner = (
		<>
			{item.locked ? (
				<Lock className="text-muted-foreground size-3.5 shrink-0" />
			) : item.complete ? (
				<CircleCheck className="size-3.5 shrink-0 text-emerald-600" />
			) : active ? (
				<CircleDashed className="text-primary size-3.5 shrink-0" />
			) : (
				<Circle className="text-muted-foreground size-3.5 shrink-0" />
			)}

			<span className="min-w-0 flex-1 truncate">{item.title || item.item_type}</span>

			{item.bookmarked && (
				<Bookmark className="text-primary size-3 shrink-0 fill-current" />
			)}
			{item.has_note && <NotebookPen className="text-muted-foreground size-3 shrink-0" />}
		</>
	)

	return (
		<li>
			{item.locked ? (
				<span
					className="text-muted-foreground flex cursor-not-allowed items-center gap-2 px-3 py-1.5 text-sm"
					title={item.lock_reason ?? undefined}
				>
					{inner}
				</span>
			) : (
				<Link
					to={to}
					className={cn(
						'flex items-center gap-2 px-3 py-1.5 text-sm',
						active ? 'bg-muted font-medium' : 'hover:bg-muted/60',
					)}
				>
					{inner}
				</Link>
			)}
		</li>
	)
}

// ---------------------------------------------------------------------------
// the thing being studied
// ---------------------------------------------------------------------------

function ItemPane({
	registration,
	moduleItem,
}: {
	registration: string
	moduleItem: string
}) {
	const open = usePlayerItem(registration)
	const [data, setData] = useState<PlayerItem | null>(null)
	const [error, setError] = useState<string | null>(null)

	useEffect(() => {
		setData(null)
		setError(null)
		open.mutate(moduleItem, {
			onSuccess: setData,
			onError: (problem) => setError(message(problem)),
		})
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [moduleItem])

	if (error) {
		return (
			<Card className="mx-auto max-w-2xl">
				<CardContent className="py-10 text-center">
					<Lock className="text-muted-foreground mx-auto mb-3 size-6" />
					<div className="font-medium">This is not open yet</div>
					<p className="text-muted-foreground mt-1 text-sm">{error}</p>
				</CardContent>
			</Card>
		)
	}

	if (!data) {
		return <p className="text-muted-foreground text-sm">Opening…</p>
	}

	return <ItemBody data={data} registration={registration} />
}

function ItemBody({ data, registration }: { data: PlayerItem; registration: string }) {
	const item = data.item
	const bookmark = useToggleBookmark(registration)
	const done = useMarkItemDone(registration)
	const content = data.content

	return (
		<article className="mx-auto max-w-3xl space-y-6">
			<header className="space-y-2">
				<div className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
					<span>
						{data.position.index} of {data.position.total}
					</span>
					<span>·</span>
					<span>{item.item_type}</span>
					{item.completion_requirement !== 'Nothing' && (
						<>
							<span>·</span>
							<span>{item.completion_requirement}</span>
						</>
					)}
				</div>

				<div className="flex flex-wrap items-start justify-between gap-3">
					<h1 className="text-2xl font-semibold text-balance">
						{item.title || item.item_type}
					</h1>

					<Button
						variant="ghost"
						size="sm"
						aria-pressed={Boolean(data.note?.bookmarked)}
						onClick={() =>
							bookmark.mutate(item.name, {
								onError: (problem) => toast.error(message(problem)),
							})
						}
					>
						<Bookmark
							className={cn('size-4', data.note?.bookmarked && 'fill-current')}
						/>
						{data.note?.bookmarked ? 'Bookmarked' : 'Bookmark'}
					</Button>
				</div>
			</header>

			{content && 'blocks' in content ? (
				<BlockRenderer
					blocks={content.blocks}
					removed={content.removed}
					lmsUrl={content.lms_url}
				/>
			) : content && 'points_possible' in content ? (
				<AssignmentPanel content={content} registration={registration} />
			) : content && 'file' in content ? (
				<Button asChild>
					<a href={content.file ?? '#'} target="_blank" rel="noreferrer noopener">
						<Download className="size-4" /> {content.title}
					</a>
				</Button>
			) : content && 'body' in content ? (
				<RichText html={content.body ?? ''} />
			) : item.item_type === 'URL' && item.url ? (
				<Button variant="outline" asChild>
					<a href={item.url} target="_blank" rel="noreferrer noopener">
						{item.url}
					</a>
				</Button>
			) : (
				<p className="text-muted-foreground text-sm">
					There is nothing to read here yet.
				</p>
			)}

			{data.resources.length > 0 && <Resources resources={data.resources} />}

			<Notes registration={registration} moduleItem={item.name} initial={data.note?.body ?? ''} />

			{item.completion_requirement === 'Mark it done' && !item.complete && (
				<Button
					onClick={() =>
						done.mutate(item.name, {
							onSuccess: () => toast.success('Marked done'),
							onError: (problem) => toast.error(message(problem)),
						})
					}
				>
					<Check className="size-4" /> Mark done
				</Button>
			)}

			<LessonDiscussionPanel moduleItem={item.name} />

			<nav className="flex items-center justify-between gap-3 border-t pt-4">
				{data.previous ? (
					<Button variant="outline" asChild>
						<Link
							to={`/portal/courses/${encodeURIComponent(registration)}/learn/${encodeURIComponent(data.previous)}`}
						>
							<ChevronLeft className="size-4" /> Previous
						</Link>
					</Button>
				) : (
					<span />
				)}

				{data.next ? (
					<Button asChild>
						<Link
							to={`/portal/courses/${encodeURIComponent(registration)}/learn/${encodeURIComponent(data.next)}`}
						>
							Next <ChevronRight className="size-4" />
						</Link>
					</Button>
				) : (
					<Badge variant="secondary">End of the course</Badge>
				)}
			</nav>
		</article>
	)
}

function AssignmentPanel({
	content,
	registration,
}: {
	content: { name?: string; title: string; description: string | null; points_possible: number; due_date: string | null }
	registration: string
}) {
	return (
		<Card>
			<CardContent className="space-y-3 p-5">
				<div className="text-muted-foreground text-xs">
					{content.points_possible} points
					{content.due_date
						? ` · due ${content.due_date.slice(0, 16).replace('T', ' ')}`
						: ' · no due date'}
				</div>
				{content.description && <RichText html={content.description} />}
				<Button asChild>
					<Link to={`/portal/courses/${encodeURIComponent(registration)}/work`}>
						Hand it in
					</Link>
				</Button>
			</CardContent>
		</Card>
	)
}

function Resources({
	resources,
}: {
	resources: { item: string; title: string; url: string; description: string | null }[]
}) {
	return (
		<section>
			<h2 className="mb-2 flex items-center gap-2 text-sm font-semibold">
				<Paperclip className="size-4" /> Resources
			</h2>
			<ul className="divide-y rounded-md border">
				{resources.map((resource) => (
					<li key={resource.item}>
						<a
							href={resource.url}
							target="_blank"
							rel="noreferrer noopener"
							className="hover:bg-muted/60 flex items-center gap-2 px-3 py-2 text-sm"
						>
							<FileText className="text-muted-foreground size-4 shrink-0" />
							<span className="min-w-0 flex-1 truncate">{resource.title}</span>
							<Download className="text-muted-foreground size-3.5 shrink-0" />
						</a>
					</li>
				))}
			</ul>
		</section>
	)
}

/**
 * A student's private notes on this item.
 *
 * Saved as they are typed, debounced, so nobody has to remember to press a
 * button — and nobody loses a paragraph by closing the tab.
 */
function Notes({
	registration,
	moduleItem,
	initial,
}: {
	registration: string
	moduleItem: string
	initial: string
}) {
	const [body, setBody] = useState(initial)
	const [saved, setSaved] = useState<string | null>(null)
	const save = useSaveNote(registration)
	const settled = useDebounced(body, 800)

	useEffect(() => {
		setBody(initial)
		setSaved(null)
	}, [initial, moduleItem])

	useEffect(() => {
		if (settled === initial) return
		save.mutate(
			{ moduleItem, body: settled },
			{ onSuccess: () => setSaved(new Date().toLocaleTimeString()) },
		)
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [settled])

	return (
		<section>
			<h2 className="mb-2 flex items-center gap-2 text-sm font-semibold">
				<NotebookPen className="size-4" /> My notes
				{saved && (
					<span className="text-muted-foreground text-xs font-normal">
						saved {saved}
					</span>
				)}
			</h2>
			<Textarea
				aria-label="My notes on this lesson"
				rows={4}
				placeholder="Only you can see these."
				value={body}
				onChange={(event) => setBody(event.target.value)}
			/>
		</section>
	)
}

/**
 * The thread for this lesson.
 *
 * Attached to the item rather than the course: a question about verse 14
 * buried in a course-wide thread is a question nobody finds again. A locked
 * lesson\'s thread is locked with it, so this is never a way to read about a
 * lesson you cannot open.
 */
function LessonDiscussionPanel({ moduleItem }: { moduleItem: string }) {
	const query = useLessonDiscussion(moduleItem)
	const post = usePostLessonReply(moduleItem)
	const [draft, setDraft] = useState('')

	const replies = query.data?.replies ?? []

	return (
		<section className="border-t pt-5">
			<h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
				<MessageSquare className="size-4" /> Discussion
				{replies.length > 0 && (
					<span className="text-muted-foreground text-xs font-normal">
						{replies.length}
					</span>
				)}
			</h2>

			{query.isPending ? (
				<p className="text-muted-foreground text-sm">Loading…</p>
			) : replies.length === 0 ? (
				<p className="text-muted-foreground mb-3 text-sm">
					No questions on this one yet. Ask the first.
				</p>
			) : (
				<ul className="mb-4 space-y-3">
					{replies.map((reply) => (
						<li key={reply.name} className="flex gap-3">
							<div className="min-w-0 flex-1">
								<div className="flex flex-wrap items-baseline gap-2">
									<span className="text-sm font-medium">{reply.author_name}</span>
									{reply.from_staff && (
										<Badge variant="secondary" className="text-[10px]">
											Teaching staff
										</Badge>
									)}
									<span className="text-muted-foreground text-xs">
										{reply.creation.slice(0, 16).replace('T', ' ')}
									</span>
								</div>
								<div className="mt-0.5">
									<RichText html={reply.reply} />
								</div>
							</div>
						</li>
					))}
				</ul>
			)}

			<Textarea
				aria-label="Ask about this lesson"
				rows={3}
				placeholder="Ask about this lesson…"
				value={draft}
				onChange={(event) => setDraft(event.target.value)}
			/>
			<div className="mt-2 flex justify-end">
				<Button
					size="sm"
					disabled={!draft.trim() || post.isPending}
					onClick={() =>
						post.mutate(draft, {
							onSuccess: () => setDraft(''),
							onError: (problem) => toast.error(message(problem)),
						})
					}
				>
					Post
				</Button>
			</div>
		</section>
	)
}
