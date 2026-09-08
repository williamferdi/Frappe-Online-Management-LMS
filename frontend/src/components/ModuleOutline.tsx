import { useState } from 'react'
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
 * Presentation only. What a row does when it opens belongs to the caller,
 * because that is where the callers genuinely differ: a student's click
 * records progress and is refused on a locked item, while a teacher checking
 * a module that unlocks next week records nothing and is allowed in anyway.
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

export function ModuleOutline({
	modules,
	openItem,
	onOpenItem,
	canOpen = () => true,
	renderBody,
}: {
	modules: OutlineModule[]
	openItem: string | null
	onOpenItem: (item: string | null) => void
	/** Whether a row can be opened at all. */
	canOpen?: (item: OutlineItem) => boolean
	/** What to show underneath an opened row. */
	renderBody: (item: OutlineItem) => React.ReactNode
}) {
	return (
		<div className="space-y-3">
			{modules.map((module) => (
				<ModuleCard
					key={module.name}
					module={module}
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
	openItem,
	onOpenItem,
	canOpen,
	renderBody,
}: {
	module: OutlineModule
	openItem: string | null
	onOpenItem: (item: string | null) => void
	canOpen: (item: OutlineItem) => boolean
	renderBody: (item: OutlineItem) => React.ReactNode
}) {
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
							<ItemRow
								key={item.name}
								item={item}
								isOpen={openItem === item.name}
								onOpenItem={onOpenItem}
								canOpen={canOpen}
								renderBody={renderBody}
							/>
						))}
					</ul>
				))}
		</div>
	)
}

function ItemRow({
	item,
	isOpen,
	onOpenItem,
	canOpen,
	renderBody,
}: {
	item: OutlineItem
	isOpen: boolean
	onOpenItem: (item: string | null) => void
	canOpen: (item: OutlineItem) => boolean
	renderBody: (item: OutlineItem) => React.ReactNode
}) {
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

	return (
		<li style={{ paddingLeft: pad }}>
			<div className="flex items-center gap-2 py-2 pr-3 text-sm">
				{Icon ? (
					<Icon className="text-muted-foreground size-4 shrink-0" aria-hidden />
				) : (
					<span className="size-4 shrink-0" />
				)}

				{/* The button holds the title and nothing else. Folding the second
				    line into it would rename the control to "Lesson 1 Lesson ·
				    View it", which is what anybody looking for it would not say. */}
				<div className="min-w-0 flex-1">
					<button
						type="button"
						disabled={!openable}
						onClick={() => onOpenItem(isOpen ? null : item.name)}
						className={cn(
							'block max-w-full truncate text-left',
							openable
								? 'hover:underline'
								: 'text-muted-foreground cursor-not-allowed',
						)}
					>
						{item.title || item.item_type}
					</button>

					<span className="text-muted-foreground block text-xs">
						{item.item_type}
						{item.completion_requirement !== 'Nothing' &&
							` · ${item.completion_requirement}`}
						{item.completion_requirement === 'Score at least' && ` ${item.min_score}`}
					</span>
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

			{isOpen && renderBody(item)}
		</li>
	)
}
