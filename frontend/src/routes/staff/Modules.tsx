import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
	ChevronDown,
	ChevronUp,
	ExternalLink,
	LoaderCircle,
	Plus,
	Trash2,
} from 'lucide-react'
import { toast } from 'sonner'

import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
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
import { FrappeError } from '@/lib/frappe'
import type { OutlineItem, OutlineModule, StaffOutline } from '@/types'

function message(error: unknown) {
	return error instanceof FrappeError ? error.message : 'Something went wrong.'
}

/**
 * The module builder.
 *
 * Ordering is done with move controls rather than drag and drop: the bundle is
 * committed to git so a drag-and-drop library is a permanent addition, and
 * buttons are reorderable from a keyboard without any extra work.
 */
export function Modules({ offering }: { offering: string }) {
	const query = useStaffOutline(offering)

	return (
		<QueryState query={query} title="Modules">
			{(data) => <Builder data={data} offering={offering} />}
		</QueryState>
	)
}

function Builder({ data, offering }: { data: StaffOutline; offering: string }) {
	const [adding, setAdding] = useState(false)
	const [title, setTitle] = useState('')
	const save = useSaveModule(offering)
	const reorder = useReorder(offering)
	const space = useContentSpace(offering)
	const makeSpace = useCreateContentSpace(offering)

	const move = (index: number, by: number) => {
		const order = data.modules.map((module) => module.name)
		const target = index + by
		if (target < 0 || target >= order.length) return
		;[order[index], order[target]] = [order[target], order[index]]
		reorder.mutate({ order }, { onError: (error) => toast.error(message(error)) })
	}

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
					<Button size="sm" onClick={() => setAdding(true)}>
						<Plus /> New module
					</Button>
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
						onMoveUp={() => move(index, -1)}
						onMoveDown={() => move(index, 1)}
						first={index === 0}
						last={index === data.modules.length - 1}
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
	onMoveUp,
	onMoveDown,
	first,
	last,
}: {
	module: OutlineModule
	data: StaffOutline
	offering: string
	onMoveUp: () => void
	onMoveDown: () => void
	first: boolean
	last: boolean
}) {
	const [adding, setAdding] = useState(false)
	const [editing, setEditing] = useState(false)
	const save = useSaveModule(offering)
	const remove = useDeleteModule(offering)

	return (
		<Card>
			<CardContent className="p-0">
				<div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
					<div className="flex gap-0.5">
						<Button
							variant="ghost"
							size="icon"
							aria-label={`Move ${module.title} up`}
							disabled={first}
							onClick={onMoveUp}
						>
							<ChevronUp className="size-4" />
						</Button>
						<Button
							variant="ghost"
							size="icon"
							aria-label={`Move ${module.title} down`}
							disabled={last}
							onClick={onMoveDown}
						>
							<ChevronDown className="size-4" />
						</Button>
					</div>

					<span className="min-w-0 flex-1 truncate font-medium">{module.title}</span>

					<Badge variant={module.published ? 'default' : 'secondary'}>
						{module.published ? 'Published' : 'Draft'}
					</Badge>

					<Button variant="ghost" size="sm" onClick={() => setEditing(!editing)}>
						Edit
					</Button>

					<Button
						variant="ghost"
						size="sm"
						onClick={() =>
							save.mutate(
								{
									values: { published: module.published ? 0 : 1 },
									module: module.name,
								},
								{ onError: (error) => toast.error(message(error)) },
							)
						}
					>
						{module.published ? 'Unpublish' : 'Publish'}
					</Button>

					<Button
						variant="ghost"
						size="icon"
						aria-label={`Delete ${module.title}`}
						onClick={() =>
							remove.mutate(module.name, {
								onSuccess: () => toast.success('Module deleted'),
								onError: (error) => toast.error(message(error)),
							})
						}
					>
						<Trash2 className="size-4" />
					</Button>
				</div>

				{editing && (
					<div className="border-b px-4 py-3">
						<ModuleForm
							module={module}
							data={data}
							offering={offering}
							onDone={() => setEditing(false)}
						/>
					</div>
				)}

				<ul className="divide-y">
					{module.items.map((item) => (
						<ItemRow key={item.name} item={item} offering={offering} />
					))}
				</ul>

				<div className="px-4 py-3">
					{adding ? (
						<ItemForm
							module={module.name}
							data={data}
							offering={offering}
							onDone={() => setAdding(false)}
						/>
					) : (
						<Button variant="outline" size="sm" onClick={() => setAdding(true)}>
							<Plus /> Add item
						</Button>
					)}
				</div>
			</CardContent>
		</Card>
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

function ItemRow({ item, offering }: { item: OutlineItem; offering: string }) {
	const remove = useDeleteItem(offering)

	return (
		<li className="flex flex-wrap items-center gap-2 px-4 py-2 text-sm">
			<span className="text-muted-foreground w-20 shrink-0 text-xs">
				{item.item_type}
			</span>
			<span className="min-w-0 flex-1 truncate">{item.title || '(untitled)'}</span>
			{item.completion_requirement !== 'Nothing' && (
				<span className="text-muted-foreground text-xs">
					{item.completion_requirement}
					{item.completion_requirement === 'Score at least' && ` ${item.min_score}`}
				</span>
			)}
			<Button
				variant="ghost"
				size="icon"
				aria-label={`Delete ${item.title || item.item_type}`}
				onClick={() =>
					remove.mutate(item.name, {
						onError: (error) => toast.error(message(error)),
					})
				}
			>
				<Trash2 className="size-4" />
			</Button>
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
							onChange={(event) => setTarget(event.target.value)}
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
						placeholder="Optional"
						value={title}
						onChange={(event) => setTitle(event.target.value)}
					/>
				</label>
			</div>

			<div className="grid gap-3 sm:grid-cols-3">
				<label className="block">
					<span className="text-xs font-medium">What counts as done</span>
					<select
						className="border-input bg-background mt-1 h-9 w-full rounded-md border px-3 text-sm"
						value={requirement}
						onChange={(event) => setRequirement(event.target.value)}
					>
						{data.choices.completion_rules.map((option) => (
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
							onChange={(event) => setMinScore(event.target.value)}
						/>
					</label>
				)}
			</div>

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
									title,
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
