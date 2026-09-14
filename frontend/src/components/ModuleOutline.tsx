import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
	ChevronDown,
	ChevronRight,
	CircleCheck,
	CircleDashed,
	ClipboardList,
	FileText,
	FileType,
	Link2,
	Lock,
	Paperclip,
	type LucideIcon,
} from 'lucide-react'

import { FileDescription } from '@/components/FileDescription'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { OutlineItem, OutlineModule } from '@/types'

/**
 * A course as a student meets it: modules in order, with what is open and
 * what is not.
 *
 * The same bars and rows the builder draws, minus everything that edits --
 * which is what Canvas does, and the reason a teacher can trust the preview.
 * It is not a second drawing of the same course; it is the same component,
 * so the two cannot drift apart the way the two hand-written copies this
 * replaces had already started to.
 *
 * Presentation only. What a row does belongs to the caller, because that is
 * where the callers genuinely differ. A student's row is a link into the
 * player, which is where reading, notes, bookmarks and marking something done
 * all live. A teacher's row on the Student view tab cannot be: the player is
 * addressed by a registration and a teacher does not have one, so theirs
 * opens in place against `preview_item`, which records that nobody read it.
 *
 * Hence two ways in: give `itemHref` and rows become links; give
 * `renderBody` and they become toggles.
 */

const ITEM_ICON: Record<string, LucideIcon> = {
	Lesson: FileText,
	Assignment: ClipboardList,
	Page: FileType,
	File: Paperclip,
	URL: Link2,
}

/** The same step the builder indents by, so a row does not shift when a
 *  teacher looks at the same course through the other tab. */
const INDENT_STEP = 1.5
const MAX_INDENT = 3

export interface OutlineBehaviour {
	/** Where a row leads. Returning null leaves it a toggle instead. */
	itemHref?: (item: OutlineItem) => string | null
	/** Which row is open, when rows open in place rather than lead somewhere. */
	openItem?: string | null
	onOpenItem?: (item: string | null) => void
	/** Whether a row can be followed or opened at all. */
	canOpen?: (item: OutlineItem) => boolean
	/** What to show underneath a row opened in place. */
	renderBody?: (item: OutlineItem) => React.ReactNode
}

export function ModuleOutline({
	modules,
	itemHref,
	openItem = null,
	onOpenItem,
	canOpen = () => true,
	renderBody,
}: OutlineBehaviour & { modules: OutlineModule[] }) {
	return (
		<div className="space-y-3">
			{modules.map((module) => (
				<ModuleCard
					key={module.name}
					module={module}
					itemHref={itemHref}
					openItem={openItem}
					onOpenItem={onOpenItem}
					canOpen={canOpen}
					renderBody={renderBody}
				/>
			))}
		</div>
	)
}

function ModuleCard({
	module,
	...behaviour
}: OutlineBehaviour & { module: OutlineModule }) {
	const [shut, setShut] = useState(false)
	const locked = !module.state.open

	return (
		<div
			className={cn(
				'bg-card overflow-hidden rounded-lg border border-l-2',
				// On the builder the rule means "a student can see this". Here
				// everything is visible by definition, so it carries the thing a
				// student actually wants at a glance: what is finished.
				module.complete && 'border-l-success',
			)}
		>
			<div className="bg-muted flex items-center gap-1.5 border-b px-3 py-2">
				<Button
					variant="ghost"
					size="icon"
					className="size-7 shrink-0"
					aria-label={`${shut ? 'Expand' : 'Collapse'} ${module.title}`}
					aria-expanded={!shut}
					onClick={() => setShut(!shut)}
				>
					{shut ? (
						<ChevronRight className="size-4" />
					) : (
						<ChevronDown className="size-4" />
					)}
				</Button>

				{/* The floor on the title is the point: without one, a long lock
				    reason on a narrow bar leaves the module name a single letter. */}
				<div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
					<span className="min-w-24 flex-1 truncate font-semibold">
						{module.title}
					</span>

					{module.complete && (
						<Badge variant="outline" className="font-normal">
							<CircleCheck className="text-success mr-1 size-3" /> Done
						</Badge>
					)}

					{locked && (
						<Badge variant="outline" className="max-w-64 truncate font-normal">
							<Lock className="mr-1 size-3" /> {module.state.reason}
						</Badge>
					)}
				</div>
			</div>

			{!shut &&
				(module.items.length === 0 ? (
					<p className="text-muted-foreground px-3 py-4 text-sm">
						Nothing in this module yet.
					</p>
				) : (
					<ul className="divide-y">
						{module.items.map((item) => (
							<ItemRow key={item.name} item={item} {...behaviour} />
						))}
					</ul>
				))}
		</div>
	)
}

function ItemRow({
	item,
	itemHref,
	openItem = null,
	onOpenItem,
	canOpen = () => true,
	renderBody,
}: OutlineBehaviour & { item: OutlineItem }) {
	const isOpen = openItem === item.name
	const indent = Math.min(Math.max(item.indent ?? 0, 0), MAX_INDENT)
	const pad = `${0.75 + indent * INDENT_STEP}rem`

	// A sub-header names the rows under it and points at nothing, so it gets
	// no icon and nothing to open -- and sits a little left of what it groups.
	if (item.item_type === 'Sub-header') {
		return (
			<li className="py-2 pr-3 text-sm font-semibold" style={{ paddingLeft: pad }}>
				{item.title}
			</li>
		)
	}

	const Icon = ITEM_ICON[item.item_type]
	const openable = canOpen(item)
	// A locked row never becomes a link: the player would only refuse it, and
	// a link that leads to a refusal is worse than one that does not lead.
	const href = openable ? (itemHref?.(item) ?? null) : null

	return (
		<li style={{ paddingLeft: pad }}>
			<div className="flex items-center gap-2 py-2 pr-3 text-sm">
				{Icon ? (
					<Icon className="text-muted-foreground size-4 shrink-0" aria-hidden />
				) : (
					<span className="size-4 shrink-0" />
				)}

				{/* The control holds the title and nothing else. Folding the second
				    line into it would rename it to "Lesson 1 Lesson · View it",
				    which is what nobody looking for it would say. */}
				<div className="min-w-0 flex-1">
					{href ? (
						<Link to={href} className="block max-w-full truncate hover:underline">
							{item.title || item.item_type}
						</Link>
					) : (
						<button
							type="button"
							disabled={!openable}
							onClick={() => onOpenItem?.(isOpen ? null : item.name)}
							className={cn(
								'block max-w-full truncate text-left',
								openable
									? 'hover:underline'
									: 'text-muted-foreground cursor-not-allowed',
							)}
						>
							{item.title || item.item_type}
						</button>
					)}

					<span className="text-muted-foreground block text-xs">
						{item.item_type}
						{item.completion_requirement !== 'Nothing' &&
							` · ${item.completion_requirement}`}
						{item.completion_requirement === 'Score at least' && ` ${item.min_score}`}
					</span>

					{/* Outside the control too, for the same reason. */}
					<FileDescription text={item.description} className="mt-0.5 line-clamp-2 text-xs" />
				</div>

				{item.locked && (
					<span className="text-muted-foreground flex shrink-0 items-center gap-1 text-xs">
						<Lock className="size-3" /> {item.lock_reason}
					</span>
				)}

				{item.complete ? (
					<CircleCheck className="text-success size-4 shrink-0" />
				) : item.completion_requirement !== 'Nothing' ? (
					<CircleDashed className="text-muted-foreground size-4 shrink-0" />
				) : null}
			</div>

			{isOpen && renderBody?.(item)}
		</li>
	)
}
