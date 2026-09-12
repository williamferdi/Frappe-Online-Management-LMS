import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
	ChevronDown,
	ChevronRight,
	CircleCheck,
	CircleSlash,
	ClipboardList,
	EllipsisVertical,
	ExternalLink,
	FileText,
	FileType,
	GripVertical,
	Link2,
	LoaderCircle,
	Paperclip,
	Plus,
	type LucideIcon,
} from 'lucide-react'
import { toast } from 'sonner'

import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuSeparator,
	DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
	useContentSpace,
	useCreateContentSpace,
	useDeleteItem,
	useDeleteModule,
	useReorder,
	useSaveItem,
	useSaveModule,
	useStaffOutline,
} from '@/hooks/useSyllabus'
import { useDragOrder } from '@/hooks/useDragOrder'
import { FrappeError } from '@/lib/frappe'
import { cn } from '@/lib/utils'
import type { OutlineItem, OutlineModule, StaffOutline } from '@/types'

function message(error: unknown) {
	return error instanceof FrappeError ? error.message : 'Something went wrong.'
}

/**
 * The module builder.
 *
 * A module is a bar with rows under it, the shape Canvas uses and the reason
 * a long course stays readable: the bars are the weeks, and everything else
 * is detail you can fold away.
 *
 * Ordering is by dragging, with the same move controls kept in each row's
 * menu -- native drag and drop cannot be driven from a keyboard at all.
 */
export function Modules({ offering }: { offering: string }) {
	const query = useStaffOutline(offering)

	return (
		<QueryState query={query} title="Modules">
			{(data) => <Builder data={data} offering={offering} />}
		</QueryState>
	)
}

/**
 * Published or not, as one control.
 *
 * A tick or a slash rather than the word, because an eye finds a shape down a
 * column of twenty rows faster than it reads "Published" twenty times. The
 * state is in the button's name as well as its colour, so it survives being
 * read aloud or seen by somebody who does not separate red from green.
 */
function PublishToggle({
	published,
	what,
	pending,
	onChange,
}: {
	published: boolean
	what: string
	pending: boolean
	onChange: (next: boolean) => void
}) {
	return (
		<Button
			variant="ghost"
			size="icon"
			className="size-7 shrink-0"
			disabled={pending}
			aria-label={`${published ? 'Unpublish' : 'Publish'} ${what}`}
			onClick={() => onChange(!published)}
		>
			{published ? (
				<CircleCheck className="text-success size-4" />
			) : (
				<CircleSlash className="text-muted-foreground size-4" />
			)}
		</Button>
	)
}

function Builder({ data, offering }: { data: StaffOutline; offering: string }) {
	const [adding, setAdding] = useState(false)
	const [title, setTitle] = useState('')
	// Which modules are folded shut. Deliberately not remembered between
	// visits: where somebody had scrolled to is not worth a storage key.
	const [shut, setShut] = useState<Set<string>>(new Set())
	const save = useSaveModule(offering)
	const reorder = useReorder(offering)
	const space = useContentSpace(offering)
	const makeSpace = useCreateContentSpace(offering)

	const drag = useDragOrder(
		data.modules.map((module) => module.name),
		(order) =>
			reorder.mutate({ order }, { onError: (error) => toast.error(message(error)) }),
	)

	const allShut = data.modules.length > 0 && shut.size === data.modules.length

	const setShutFor = (name: string, next: boolean) =>
		setShut((current) => {
			const updated = new Set(current)
			if (next) updated.add(name)
			else updated.delete(name)
			return updated
		})

	return (
		<div className="space-y-4">
			{/* Lessons live in the LMS, and a course has nowhere to write them
			    until somebody makes the space. This is where a teacher finds
			    that out, so this is where the answer belongs. */}
			{space.data && data.choices.lessons.length === 0 && (
				<Card>
					<CardContent className="flex flex-wrap items-center gap-3 p-4">
						<div className="min-w-0 flex-1">
							<div className="text-sm font-medium">
								{space.data.lms_course
									? 'No lessons written yet'
									: 'This course has nowhere to write lessons yet'}
							</div>
							<p className="text-muted-foreground mt-0.5 text-sm">
								{space.data.lms_course
									? 'Write them in the LMS and they appear here as items you can add to a module.'
									: 'Lessons are written in the LMS and read here. Create the space once, then write them.'}
							</p>
						</div>

						{space.data.lms_course ? (
							<Button variant="outline" size="sm" asChild>
								<a
									href={space.data.authoring_url ?? '#'}
									target="_blank"
									rel="noreferrer noopener"
								>
									Write lessons <ExternalLink className="size-3.5" />
								</a>
							</Button>
						) : (
							<Button
								size="sm"
								disabled={makeSpace.isPending}
								onClick={() =>
									makeSpace.mutate(undefined, {
										onSuccess: (result) => {
											toast.success('Ready for lessons')
											window.open(result.authoring_url, '_blank', 'noopener')
										},
										onError: (error) => toast.error(message(error)),
									})
								}
							>
								{makeSpace.isPending ? (
									<LoaderCircle className="animate-spin" />
								) : null}
								Set up lessons
							</Button>
						)}
					</CardContent>
				</Card>
			)}

			<div className="flex flex-wrap items-end justify-between gap-2">
				{adding ? (
					<div className="flex flex-wrap items-end gap-2">
						<div>
							<Label htmlFor="module-title">Module title</Label>
							<Input
								id="module-title"
								className="mt-1 w-64"
								value={title}
								onChange={(event) => setTitle(event.target.value)}
							/>
						</div>
						<Button
							size="sm"
							disabled={!title || save.isPending}
							onClick={() =>
								save.mutate(
									{ values: { title, published: 0 } },
									{
										onSuccess: () => {
											toast.success('Module added')
											setTitle('')
											setAdding(false)
										},
										onError: (error) => toast.error(message(error)),
									},
								)
							}
						>
							{save.isPending ? <LoaderCircle className="animate-spin" /> : null}
							Add
						</Button>
						<Button variant="outline" size="sm" onClick={() => setAdding(false)}>
							Cancel
						</Button>
					</div>
				) : (
					<div className="ml-auto flex gap-2">
						{data.modules.length > 0 && (
							<Button
								variant="outline"
								size="sm"
								onClick={() =>
									setShut(
										allShut
											? new Set()
											: new Set(data.modules.map((module) => module.name)),
									)
								}
							>
								{allShut ? 'Expand all' : 'Collapse all'}
							</Button>
						)}
						<Button size="sm" onClick={() => setAdding(true)}>
							<Plus /> Module
						</Button>
					</div>
				)}
			</div>

			{data.modules.length === 0 ? (
				<Card>
					<CardContent className="py-14 text-center">
						<div className="font-medium">No modules yet</div>
						<p className="text-muted-foreground mx-auto mt-1 max-w-md text-sm">
							A module is a group of things in the order you want them done — a
							lesson, a piece of work, a page, a file.
						</p>
					</CardContent>
				</Card>
			) : (
				data.modules.map((module, index) => (
					<ModuleCard
						key={module.name}
						module={module}
						data={data}
						offering={offering}
						drag={drag}
						first={index === 0}
						last={index === data.modules.length - 1}
						shut={shut.has(module.name)}
						onShut={(next) => setShutFor(module.name, next)}
					/>
				))
			)}
		</div>
	)
}

function ModuleCard({
	module,
	data,
	offering,
	drag,
	first,
	last,
	shut,
	onShut,
}: {
	module: OutlineModule
	data: StaffOutline
	offering: string
	drag: ReturnType<typeof useDragOrder>
	first: boolean
	last: boolean
	shut: boolean
	onShut: (next: boolean) => void
}) {
	const [adding, setAdding] = useState(false)
	const [editing, setEditing] = useState(false)
	const save = useSaveModule(offering)
	const remove = useDeleteModule(offering)

	// Prerequisites arrive as module names; they were chosen by title, so they
	// are shown by title. A name that no longer resolves is dropped rather
	// than printed raw.
	const waitsFor = module.prerequisites
		.map((name) => data.modules.find((row) => row.name === name)?.title)
		.filter((value): value is string => Boolean(value))

	const open = () => onShut(false)

	return (
		<div
			{...drag.handlers(module.name)}
			className={cn(
				'bg-card overflow-hidden rounded-lg border border-l-2',
				// The rule down the edge answers the question a teacher actually
				// has on this screen: which of these can a student see? A draft
				// keeps the border it inherits rather than a transparent one,
				// which would read as a card missing its left side.
				module.published && 'border-l-primary',
				drag.dragging === module.name && 'opacity-50',
				drag.over === module.name &&
					drag.dragging !== module.name &&
					'border-t-primary border-t-2',
			)}
		>
			<div className="bg-muted flex items-center gap-1.5 border-b px-3 py-2">
				<GripVertical
					className="text-muted-foreground size-4 shrink-0 cursor-grab"
					aria-hidden
				/>

				<Button
					variant="ghost"
					size="icon"
					className="size-7 shrink-0"
					aria-label={`${shut ? 'Expand' : 'Collapse'} ${module.title}`}
					aria-expanded={!shut}
					onClick={() => onShut(!shut)}
				>
					{shut ? (
						<ChevronRight className="size-4" />
					) : (
						<ChevronDown className="size-4" />
					)}
				</Button>

				{/* The title and what qualifies it, wrapping together. The floor on
				    the title is the point: without one, three chips on a narrow
				    bar leave it a single letter. */}
				<div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
					<span className="min-w-24 flex-1 truncate font-semibold">
						{module.title}
					</span>

					{waitsFor.length > 0 && (
						<Badge variant="outline" className="max-w-48 truncate font-normal">
							After {waitsFor.join(', ')}
						</Badge>
					)}
					{module.require_sequential_progress ? (
						<Badge variant="outline" className="font-normal">
							In order
						</Badge>
					) : null}
					{module.unlock_at && (
						<Badge variant="outline" className="font-normal">
							Unlocks {module.unlock_at.slice(0, 16).replace('T', ' ')}
						</Badge>
					)}
				</div>

				<div className="flex shrink-0 items-center gap-0.5">
						<PublishToggle
						published={Boolean(module.published)}
						what={`module ${module.title}`}
						pending={save.isPending}
						onChange={(next) =>
							save.mutate(
								{ values: { published: next ? 1 : 0 }, module: module.name },
								{ onError: (error) => toast.error(message(error)) },
							)
						}
					/>

					<Button
						variant="ghost"
						size="icon"
						className="size-7 shrink-0"
						aria-label={`Add an item to ${module.title}`}
						onClick={() => {
							open()
							setAdding(true)
						}}
					>
						<Plus className="size-4" />
					</Button>

					<DropdownMenu>
						<DropdownMenuTrigger asChild>
							<Button
								variant="ghost"
								size="icon"
								className="size-7 shrink-0"
								aria-label={`More for ${module.title}`}
							>
								<EllipsisVertical className="size-4" />
							</Button>
						</DropdownMenuTrigger>
						<DropdownMenuContent align="end">
							<DropdownMenuItem
								onSelect={() => {
									open()
									setEditing(true)
								}}
							>
								Edit
							</DropdownMenuItem>
							<DropdownMenuItem
								disabled={first}
								onSelect={() => drag.moveBy(module.name, -1)}
							>
								Move up
							</DropdownMenuItem>
							<DropdownMenuItem
								disabled={last}
								onSelect={() => drag.moveBy(module.name, 1)}
							>
								Move down
							</DropdownMenuItem>
							<DropdownMenuSeparator />
							<DropdownMenuItem
								variant="destructive"
								onSelect={() =>
									remove.mutate(module.name, {
										onSuccess: () => toast.success('Module deleted'),
										onError: (error) => toast.error(message(error)),
									})
								}
							>
								Delete
							</DropdownMenuItem>
						</DropdownMenuContent>
					</DropdownMenu>
					</div>
			</div>

			{!shut && (
				<>
					{editing && (
						<div className="border-b px-3 py-3">
							<ModuleForm
								module={module}
								data={data}
								offering={offering}
								onDone={() => setEditing(false)}
							/>
						</div>
					)}

					<ItemList module={module} data={data} offering={offering} />

					<div className="px-3 py-2">
						{adding ? (
							<ItemForm
								module={module.name}
								data={data}
								offering={offering}
								onDone={() => setAdding(false)}
							/>
						) : (
							<Button
								variant="ghost"
								size="sm"
								className="text-muted-foreground"
								onClick={() => setAdding(true)}
							>
								<Plus className="size-4" /> Add item
							</Button>
						)}
					</div>
				</>
			)}
		</div>
	)
}

/**
 * Renaming a module, and the three things that decide when it opens.
 *
 * `unlock_at` is a datetime-local: blanking it means "no date", which is not
 * the same as leaving it alone, so the empty string is sent as null rather
 * than skipped.
 */
function ModuleForm({
	module,
	data,
	offering,
	onDone,
}: {
	module: OutlineModule
	data: StaffOutline
	offering: string
	onDone: () => void
}) {
	const [title, setTitle] = useState(module.title)
	const [unlockAt, setUnlockAt] = useState((module.unlock_at ?? '').slice(0, 16))
	const [sequential, setSequential] = useState(
		Boolean(module.require_sequential_progress),
	)
	const [prerequisites, setPrerequisites] = useState<string[]>(module.prerequisites ?? [])
	const save = useSaveModule(offering)

	// A module cannot wait for itself, and the server drops it anyway.
	const others = data.modules.filter((row) => row.name !== module.name)

	return (
		<div className="space-y-3">
			<div className="grid gap-3 sm:grid-cols-2">
				<label className="block">
					<span className="text-xs font-medium">Title</span>
					<Input
						className="mt-1"
						value={title}
						onChange={(event) => setTitle(event.target.value)}
					/>
				</label>

				<label className="block">
					<span className="text-xs font-medium">Unlocks at</span>
					<Input
						type="datetime-local"
						className="mt-1"
						value={unlockAt}
						onChange={(event) => setUnlockAt(event.target.value)}
					/>
					<span className="text-muted-foreground mt-1 block text-xs">
						Leave blank to open as soon as it is published.
					</span>
				</label>
			</div>

			<label className="flex items-center gap-2 text-sm">
				<input
					type="checkbox"
					checked={sequential}
					onChange={(event) => setSequential(event.target.checked)}
				/>
				Items must be done in order
			</label>

			{others.length > 0 && (
				<fieldset>
					<legend className="text-xs font-medium">Requires first</legend>
					<div className="mt-1 flex flex-wrap gap-2">
						{others.map((row) => (
							<label
								key={row.name}
								className="border-input hover:bg-muted flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1 text-sm"
							>
								<input
									type="checkbox"
									checked={prerequisites.includes(row.name)}
									onChange={() =>
										setPrerequisites(
											prerequisites.includes(row.name)
												? prerequisites.filter((value) => value !== row.name)
												: [...prerequisites, row.name],
										)
									}
								/>
								{row.title}
							</label>
						))}
					</div>
				</fieldset>
			)}

			<div className="flex justify-end gap-2">
				<Button variant="outline" size="sm" onClick={onDone}>
					Cancel
				</Button>
				<Button
					size="sm"
					disabled={!title || save.isPending}
					onClick={() =>
						save.mutate(
							{
								values: {
									title,
									unlock_at: unlockAt || null,
									require_sequential_progress: sequential ? 1 : 0,
									prerequisites,
								},
								module: module.name,
							},
							{
								onSuccess: () => {
									toast.success('Module saved')
									onDone()
								},
								onError: (error) => toast.error(message(error)),
							},
						)
					}
				>
					{save.isPending ? <LoaderCircle className="animate-spin" /> : null}
					Save module
				</Button>
			</div>
		</div>
	)
}

/**
 * The items of one module, in the order a student meets them.
 *
 * Their own list rather than rows inside the card, because reordering needs
 * the whole set — a row cannot know what it is being dropped above.
 */
function ItemList({
	module,
	data,
	offering,
}: {
	module: OutlineModule
	data: StaffOutline
	offering: string
}) {
	const reorder = useReorder(offering)
	const drag = useDragOrder(
		module.items.map((item) => item.name),
		(order) =>
			reorder.mutate(
				{ module: module.name, order },
				{ onError: (error) => toast.error(message(error)) },
			),
	)

	if (module.items.length === 0) {
		return (
			<p className="text-muted-foreground px-3 py-4 text-sm">
				Nothing in this module yet.
			</p>
		)
	}

	return (
		<ul className="divide-y">
			{module.items.map((item, index) => (
				<ItemRow
					key={item.name}
					item={item}
					data={data}
					offering={offering}
					drag={drag}
					first={index === 0}
					last={index === module.items.length - 1}
				/>
			))}
		</ul>
	)
}

/** What kind of thing a row points at, at a glance. */
const ITEM_ICON: Record<string, LucideIcon> = {
	Lesson: FileText,
	Assignment: ClipboardList,
	Page: FileType,
	File: Paperclip,
	URL: Link2,
}

/** How far one step of indent moves a row, in rem, and how many steps are
 *  allowed. Indent is presentation only: nothing about ordering, access or
 *  completion reads it, so the cap is about the row staying readable rather
 *  than about meaning running out. */
const INDENT_STEP = 1.5
const MAX_INDENT = 3

function ItemRow({
	item,
	data,
	offering,
	drag,
	first,
	last,
}: {
	item: OutlineItem
	data: StaffOutline
	offering: string
	drag: ReturnType<typeof useDragOrder>
	first: boolean
	last: boolean
}) {
	const [editing, setEditing] = useState(false)
	const save = useSaveItem(offering)
	const remove = useDeleteItem(offering)

	const label = item.title || '(untitled)'
	const indent = Math.min(Math.max(item.indent ?? 0, 0), MAX_INDENT)

	// A sub-header names the rows under it and points at nothing, so it gets
	// no type icon and no second line -- which also leaves it sitting a little
	// to the left of what it groups, and reading as the heading it is.
	const heading = item.item_type === 'Sub-header'
	const Icon = ITEM_ICON[item.item_type]

	const set = (values: Record<string, unknown>) =>
		save.mutate(
			{ module: item.module, values, item: item.name },
			{ onError: (error) => toast.error(message(error)) },
		)

	return (
		<li
			// Not draggable while its form is open: a drag begun inside a text
			// box would carry the whole row off instead of selecting the words.
			{...(editing ? {} : drag.handlers(item.name))}
			className={cn(
				drag.dragging === item.name && 'opacity-50',
				drag.over === item.name &&
					drag.dragging !== item.name &&
					'border-primary border-t-2',
			)}
		>
			<div
				className="flex items-center gap-2 py-2 pr-3 text-sm"
				style={{ paddingLeft: `${0.75 + indent * INDENT_STEP}rem` }}
			>
				<GripVertical
					className="text-muted-foreground size-4 shrink-0 cursor-grab"
					aria-hidden
				/>

				{heading ? null : Icon ? (
					<Icon className="text-muted-foreground size-4 shrink-0" aria-hidden />
				) : (
					<span className="size-4 shrink-0" />
				)}

				<div className="min-w-0 flex-1">
					<span className={cn('block truncate', heading && 'font-semibold')}>
						{label}
					</span>
					{!heading && (
						<span className="text-muted-foreground block text-xs">
							{item.item_type}
							{item.completion_requirement !== 'Nothing' &&
								` · ${item.completion_requirement}`}
							{item.completion_requirement === 'Score at least' &&
								` ${item.min_score}`}
						</span>
					)}
				</div>

				<PublishToggle
					published={Boolean(item.published)}
					what={label}
					pending={save.isPending}
					onChange={(next) => set({ published: next ? 1 : 0 })}
				/>

				<DropdownMenu>
					<DropdownMenuTrigger asChild>
						<Button
							variant="ghost"
							size="icon"
							className="size-7 shrink-0"
							aria-label={`More for ${label}`}
						>
							<EllipsisVertical className="size-4" />
						</Button>
					</DropdownMenuTrigger>
					<DropdownMenuContent align="end">
						<DropdownMenuItem onSelect={() => setEditing(true)}>Edit</DropdownMenuItem>
						<DropdownMenuItem
							disabled={first}
							onSelect={() => drag.moveBy(item.name, -1)}
						>
							Move up
						</DropdownMenuItem>
						<DropdownMenuItem
							disabled={last}
							onSelect={() => drag.moveBy(item.name, 1)}
						>
							Move down
						</DropdownMenuItem>
						<DropdownMenuSeparator />
						<DropdownMenuItem
							disabled={indent >= MAX_INDENT}
							onSelect={() => set({ indent: indent + 1 })}
						>
							Indent
						</DropdownMenuItem>
						<DropdownMenuItem
							disabled={indent <= 0}
							onSelect={() => set({ indent: indent - 1 })}
						>
							Outdent
						</DropdownMenuItem>
						<DropdownMenuSeparator />
						<DropdownMenuItem
							variant="destructive"
							onSelect={() =>
								remove.mutate(item.name, {
									onError: (error) => toast.error(message(error)),
								})
							}
						>
							Delete
						</DropdownMenuItem>
					</DropdownMenuContent>
				</DropdownMenu>
			</div>

			{editing && (
				<div className="bg-muted/30 border-t px-3 py-3">
					<ItemEditForm
						item={item}
						data={data}
						offering={offering}
						onDone={() => setEditing(false)}
					/>
				</div>
			)}
		</li>
	)
}

/** What to say when a type has nothing to point at, and where to go.
 *  The tab is a link, because naming a place is less use than going there. */
const EMPTY: Record<string, { text: string; tab: string; label: string }> = {
	Lesson: { text: 'No lessons written yet.', tab: 'content', label: 'Write one' },
	Assignment: { text: 'No assignments set yet.', tab: 'assignments', label: 'Set one' },
	Page: { text: 'No pages written yet.', tab: 'content', label: 'Write one' },
	File: { text: 'No files added yet.', tab: 'content', label: 'Add one' },
}

function ItemForm({
	module,
	data,
	offering,
	onDone,
}: {
	module: string
	data: StaffOutline
	offering: string
	onDone: () => void
}) {
	const [type, setType] = useState('Lesson')
	const [target, setTarget] = useState('')
	const [title, setTitle] = useState('')
	// The title last copied in from the chosen content. While the box still
	// says that, choosing something else replaces it; once somebody has typed
	// their own, it is theirs and nothing here touches it.
	const [copied, setCopied] = useState('')
	const [requirement, setRequirement] = useState('Nothing')
	const [minScore, setMinScore] = useState('')
	const save = useSaveItem(offering)

	// The field the chosen type points at, so a lesson item cannot be saved
	// carrying an assignment.
	const targetField: Record<string, string> = {
		Lesson: 'lesson',
		Assignment: 'assignment',
		Page: 'page',
		File: 'file',
		URL: 'url',
	}

	// Which types point at something that has to exist first. URL is typed in
	// and Sub-header points at nothing at all.
	const needsTarget = ['Lesson', 'Assignment', 'Page', 'File'].includes(type)

	const options =
		type === 'Lesson'
			? data.choices.lessons.map((row) => ({ value: row.name, label: row.title }))
			: type === 'Assignment'
				? data.choices.assignments.map((row) => ({ value: row.name, label: row.title }))
				: type === 'Page'
					? data.choices.pages.map((row) => ({ value: row.name, label: row.title }))
					: type === 'File'
						? data.choices.files.map((row) => ({ value: row.name, label: row.title }))
						: []

	const labelOf = (value: string) =>
		options.find((option) => option.value === value)?.label ?? ''

	/** Point at something, and take its title unless the teacher chose one. */
	const choose = (value: string) => {
		setTarget(value)
		if (title === '' || title === copied) {
			const label = labelOf(value)
			setTitle(label)
			setCopied(label)
		}
	}

	return (
		<div className="space-y-3">
			<div className="grid gap-3 sm:grid-cols-3">
				<label className="block">
					<span className="text-xs font-medium">Type</span>
					<select
						className="border-input bg-background mt-1 h-9 w-full rounded-md border px-3 text-sm"
						value={type}
						onChange={(event) => {
							setType(event.target.value)
							setTarget('')
							// A title copied from a lesson says nothing about the
							// page chosen next.
							if (title === copied) {
								setTitle('')
								setCopied('')
							}
						}}
					>
						{data.choices.item_types.map((option) => (
							<option key={option} value={option}>
								{option}
							</option>
						))}
					</select>
				</label>

				{needsTarget && options.length > 0 && (
					<label className="block">
						<span className="text-xs font-medium">Which one</span>
						<select
							className="border-input bg-background mt-1 h-9 w-full rounded-md border px-3 text-sm"
							value={target}
							onChange={(event) => choose(event.target.value)}
						>
							<option value="">Choose…</option>
							{options.map((option) => (
								<option key={option.value} value={option.value}>
									{option.label}
								</option>
							))}
						</select>
					</label>
				)}

				{/* Rendering nothing here left a dead Add button with no reason
				    for it. There is always something to say: what is missing,
				    and where to make one. */}
				{needsTarget && options.length === 0 && (
					<div className="sm:col-span-2">
						<span className="text-xs font-medium">Which one</span>
						<p className="text-muted-foreground mt-1 text-sm">
							{EMPTY[type]?.text ?? `No ${type.toLowerCase()}s on this course yet.`}{' '}
							{EMPTY[type] && (
								<Link
									to={`/staff/courses/${encodeURIComponent(offering)}?tab=${EMPTY[type].tab}`}
									className="text-primary underline underline-offset-2"
								>
									{EMPTY[type].label}
								</Link>
							)}
						</p>
					</div>
				)}

				{type === 'URL' && (
					<label className="block">
						<span className="text-xs font-medium">Link</span>
						<Input
							className="mt-1"
							value={target}
							onChange={(event) => setTarget(event.target.value)}
						/>
					</label>
				)}

				<label className="block">
					<span className="text-xs font-medium">Title</span>
					<Input
						className="mt-1"
						placeholder={needsTarget ? 'Taken from what you choose' : 'Optional'}
						value={title}
						onChange={(event) => setTitle(event.target.value)}
					/>
				</label>
			</div>

			<CompletionFields
				rules={data.choices.completion_rules}
				requirement={requirement}
				minScore={minScore}
				onRequirement={setRequirement}
				onMinScore={setMinScore}
			/>

			<div className="flex justify-end gap-2">
				<Button variant="outline" size="sm" onClick={onDone}>
					Cancel
				</Button>
				<Button
					size="sm"
					disabled={save.isPending || (type !== 'Sub-header' && !target)}
					title={
						type !== 'Sub-header' && !target
							? needsTarget && options.length === 0
								? `There are no ${type.toLowerCase()}s to add yet`
								: `Choose which ${type.toLowerCase()} to add`
							: undefined
					}
					onClick={() =>
						save.mutate(
							{
								module,
								values: {
									item_type: type,
									// Emptied on purpose or never filled, it is still
									// called what it opens rather than "(untitled)".
									title: title.trim() || labelOf(target),
									completion_requirement: requirement,
									...(requirement === 'Score at least'
										? { min_score: Number(minScore) || 0 }
										: {}),
									...(targetField[type] ? { [targetField[type]]: target } : {}),
								},
							},
							{
								onSuccess: () => {
									toast.success('Item added')
									onDone()
								},
								onError: (error) => toast.error(message(error)),
							},
						)
					}
				>
					Add
				</Button>
			</div>
		</div>
	)
}

/** What counts as done, and the score when that is the rule. Adding an item
 *  and editing one ask the same question, so they ask it the same way. */
function CompletionFields({
	rules,
	requirement,
	minScore,
	onRequirement,
	onMinScore,
}: {
	rules: string[]
	requirement: string
	minScore: string
	onRequirement: (value: string) => void
	onMinScore: (value: string) => void
}) {
	return (
		<div className="grid gap-3 sm:grid-cols-3">
			<label className="block">
				<span className="text-xs font-medium">What counts as done</span>
				<select
					className="border-input bg-background mt-1 h-9 w-full rounded-md border px-3 text-sm"
					value={requirement}
					onChange={(event) => onRequirement(event.target.value)}
				>
					{rules.map((option) => (
						<option key={option} value={option}>
							{option}
						</option>
					))}
				</select>
			</label>

			{requirement === 'Score at least' && (
				<label className="block">
					<span className="text-xs font-medium">Minimum score</span>
					<Input
						type="number"
						className="mt-1"
						value={minScore}
						onChange={(event) => onMinScore(event.target.value)}
					/>
				</label>
			)}
		</div>
	)
}

/** The lesson, assignment, page or file an item opens, by the title it was
 *  chosen by -- or null when that is no longer on the course. */
function pointsAt(item: OutlineItem, data: StaffOutline): string | null {
	const { choices } = data
	const found =
		item.item_type === 'Lesson'
			? choices.lessons.find((row) => row.name === item.lesson)
			: item.item_type === 'Assignment'
				? choices.assignments.find((row) => row.name === item.assignment)
				: item.item_type === 'Page'
					? choices.pages.find((row) => row.name === item.page)
					: item.item_type === 'File'
						? choices.files.find((row) => row.name === item.file)
						: undefined
	return found?.title ?? null
}

/**
 * Changing an item already in a module: what it is called, what counts as
 * done, and -- for a link -- where it goes.
 *
 * Not what it points at. A student's progress belongs to the lesson or piece
 * of work they actually opened, so moving an item onto a different one would
 * carry their ticks across to something they have never seen. Canvas draws
 * the same line. To point at something else, add that and delete this.
 *
 * So neither `item_type` nor the pointer is ever sent, and `save_item` -- which
 * sets exactly the fields it is given -- leaves both as they were.
 */
function ItemEditForm({
	item,
	data,
	offering,
	onDone,
}: {
	item: OutlineItem
	data: StaffOutline
	offering: string
	onDone: () => void
}) {
	const [title, setTitle] = useState(item.title ?? '')
	const [url, setUrl] = useState(item.url ?? '')
	const [requirement, setRequirement] = useState(item.completion_requirement)
	const [minScore, setMinScore] = useState(
		item.min_score == null ? '' : String(item.min_score),
	)
	const save = useSaveItem(offering)

	const heading = item.item_type === 'Sub-header'
	const link = item.item_type === 'URL'
	const target = heading || link ? null : pointsAt(item, data)

	return (
		<div className="space-y-3">
			{!heading && !link && (
				<p className="text-muted-foreground text-xs">
					Opens the {item.item_type.toLowerCase()}{' '}
					<span className="text-foreground font-medium">
						{target ?? 'that is no longer on this course'}
					</span>
					. To point it at something else, add that as a new item and delete this
					one: a student&apos;s progress stays with what they actually opened.
				</p>
			)}

			<div className="grid gap-3 sm:grid-cols-3">
				<label className="block">
					<span className="text-xs font-medium">Title</span>
					<Input
						className="mt-1"
						value={title}
						onChange={(event) => setTitle(event.target.value)}
					/>
				</label>

				{link && (
					<label className="block sm:col-span-2">
						<span className="text-xs font-medium">Link</span>
						<Input
							className="mt-1"
							value={url}
							onChange={(event) => setUrl(event.target.value)}
						/>
					</label>
				)}
			</div>

			{!heading && (
				<CompletionFields
					rules={data.choices.completion_rules}
					requirement={requirement}
					minScore={minScore}
					onRequirement={setRequirement}
					onMinScore={setMinScore}
				/>
			)}

			<div className="flex justify-end gap-2">
				<Button variant="outline" size="sm" onClick={onDone}>
					Cancel
				</Button>
				<Button
					size="sm"
					// A sub-header is nothing but its words, and a link nothing
					// without its address.
					disabled={save.isPending || (heading && !title.trim()) || (link && !url.trim())}
					onClick={() =>
						save.mutate(
							{
								module: item.module,
								item: item.name,
								values: {
									title,
									...(link ? { url: url.trim() } : {}),
									...(heading ? {} : { completion_requirement: requirement }),
									...(!heading && requirement === 'Score at least'
										? { min_score: Number(minScore) || 0 }
										: {}),
								},
							},
							{
								onSuccess: () => {
									toast.success('Item saved')
									onDone()
								},
								onError: (error) => toast.error(message(error)),
							},
						)
					}
				>
					{save.isPending ? <LoaderCircle className="animate-spin" /> : null}
					Save item
				</Button>
			</div>
		</div>
	)
}
