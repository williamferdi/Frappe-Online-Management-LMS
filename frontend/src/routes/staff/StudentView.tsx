import { useState } from 'react'
import { CircleCheck, CircleDashed, Eye, Lock } from 'lucide-react'

import { BlockRenderer } from '@/components/BlockRenderer'
import { QueryState } from '@/components/QueryState'
import { RichText } from '@/components/RichText'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { useModulePreview, usePreviewItem } from '@/hooks/useSyllabus'
import { cn } from '@/lib/utils'
import type { ModulePreview, OutlineItem, OutlineModule } from '@/types'

/**
 * The course as a student sees it.
 *
 * Rendered from `modules.outline` — the same call the portal makes — so this
 * cannot drift from the thing it previews. An unpublished module is absent
 * here exactly as it is absent there, which is usually the answer to "why
 * can't they see the thing I just wrote?".
 */
export function StudentView({ offering }: { offering: string }) {
	const [registration, setRegistration] = useState<string | null>(null)
	const query = useModulePreview(offering, registration)

	return (
		<QueryState query={query} title="Student view">
			{(data) => (
				<Preview
					data={data}
					offering={offering}
					registration={registration}
					onRegistration={setRegistration}
				/>
			)}
		</QueryState>
	)
}

function Preview({
	data,
	offering,
	registration,
	onRegistration,
}: {
	data: ModulePreview
	offering: string
	registration: string | null
	onRegistration: (value: string | null) => void
}) {
	const hidden = data.unpublished_modules + data.unpublished_items
	const [open, setOpen] = useState<string | null>(null)

	return (
		<div className="space-y-4">
			<Card>
				<CardContent className="flex flex-wrap items-center gap-3 p-4">
					<Eye className="text-muted-foreground size-4 shrink-0" />
					<label className="flex items-center gap-2 text-sm">
						<span className="text-muted-foreground">Seen as</span>
						<select
							className="border-input bg-background h-9 rounded-md border px-3 text-sm"
							value={registration ?? ''}
							onChange={(event) => onRegistration(event.target.value || null)}
							aria-label="Preview as"
						>
							<option value="">A student who has just arrived</option>
							{data.roster.map((row) => (
								<option key={row.name} value={row.name}>
									{row.student_name}
								</option>
							))}
						</select>
					</label>

					{hidden > 0 && (
						<span className="text-muted-foreground ml-auto text-xs">
							{data.unpublished_modules > 0 &&
								`${data.unpublished_modules} unpublished module${data.unpublished_modules === 1 ? '' : 's'}`}
							{data.unpublished_modules > 0 && data.unpublished_items > 0 && ' and '}
							{data.unpublished_items > 0 &&
								`${data.unpublished_items} unpublished item${data.unpublished_items === 1 ? '' : 's'}`}
							{' not shown here'}
						</span>
					)}
				</CardContent>
			</Card>

			{data.modules.length === 0 ? (
				<Card>
					<CardContent className="py-14 text-center">
						<div className="font-medium">A student would see nothing yet</div>
						<p className="text-muted-foreground mx-auto mt-1 max-w-md text-sm">
							{hidden > 0
								? 'Everything on this course is still unpublished. Publish a module to make it visible.'
								: 'Build a module and publish it.'}
						</p>
					</CardContent>
				</Card>
			) : (
				data.modules.map((module) => (
					<ModuleBlock
						key={module.name}
						module={module}
						offering={offering}
						open={open}
						onOpen={setOpen}
					/>
				))
			)}
		</div>
	)
}

function ModuleBlock({
	module,
	offering,
	open,
	onOpen,
}: {
	module: OutlineModule
	offering: string
	open: string | null
	onOpen: (item: string | null) => void
}) {
	return (
		<Card>
			<CardContent className="p-0">
				<div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
					<span className="font-medium">{module.title}</span>
					{module.complete && (
						<Badge variant="secondary">
							<CircleCheck className="mr-1 size-3" /> Done
						</Badge>
					)}
					{!module.state.open && (
						<span className="text-muted-foreground ml-auto flex items-center gap-1.5 text-xs">
							<Lock className="size-3.5" /> {module.state.reason}
						</span>
					)}
				</div>

				{module.items.length === 0 ? (
					<p className="text-muted-foreground px-4 py-6 text-sm">Nothing in here yet.</p>
				) : (
					<ul className="divide-y">
						{module.items.map((item) => (
							<ItemLine
								key={item.name}
								item={item}
								offering={offering}
								isOpen={open === item.name}
								onOpen={onOpen}
							/>
						))}
					</ul>
				)}
			</CardContent>
		</Card>
	)
}

function ItemLine({
	item,
	offering,
	isOpen,
	onOpen,
}: {
	item: OutlineItem
	offering: string
	isOpen: boolean
	onOpen: (item: string | null) => void
}) {
	if (item.item_type === 'Sub-header') {
		return (
			<li
				className="text-muted-foreground px-4 py-2 text-xs font-medium tracking-wide uppercase"
				style={{ paddingLeft: `${16 + item.indent * 16}px` }}
			>
				{item.title}
			</li>
		)
	}

	return (
		<li style={{ paddingLeft: `${item.indent * 16}px` }}>
			<div className="flex flex-wrap items-center gap-2 px-4 py-2.5 text-sm">
				{/* Openable even when locked: a teacher checking a module that
				    unlocks next week needs to see inside it. The lock is still
				    reported, so what a student would meet is not misrepresented. */}
				<button
					type="button"
					onClick={() => onOpen(isOpen ? null : item.name)}
					className={cn(
						'min-w-0 flex-1 truncate text-left hover:underline',
						item.locked && 'text-muted-foreground',
					)}
				>
					{item.title || item.item_type}
				</button>

				{item.complete ? (
					<CircleCheck className="size-4 shrink-0 text-emerald-600" />
				) : item.completion_requirement !== 'Nothing' ? (
					<CircleDashed className="text-muted-foreground size-4 shrink-0" />
				) : null}

				{item.locked && (
					<span className="text-muted-foreground flex items-center gap-1 text-xs">
						<Lock className="size-3" /> {item.lock_reason}
					</span>
				)}
			</div>

			{isOpen && <ItemContent item={item} offering={offering} />}
		</li>
	)
}

/** What the item actually holds. Reading it here records nothing. */
function ItemContent({ item, offering }: { item: OutlineItem; offering: string }) {
	const query = usePreviewItem(offering, item.name)

	if (query.isPending) {
		return <p className="text-muted-foreground px-4 pb-3 text-sm">Opening…</p>
	}

	const content = query.data?.content
	if (!content) {
		return (
			<p className="text-muted-foreground px-4 pb-3 text-sm">
				{item.item_type === 'URL' && item.url
					? item.url
					: 'This item points at nothing yet.'}
			</p>
		)
	}

	return (
		<div className="bg-muted/40 border-t px-4 py-4">
			{query.data?.unpublished && (
				<p className="text-muted-foreground mb-2 text-xs">
					This page is unpublished, so a student would not see it.
				</p>
			)}

			{/* Ordered by how specific each test is. "description" is on both the
			    file and the assignment shape, so testing it early swallowed the
			    file branch and left TypeScript with nothing to narrow to. */}
			{'blocks' in content ? (
				<BlockRenderer
					blocks={content.blocks}
					removed={content.removed}
					lmsUrl={content.lms_url}
				/>
			) : 'file' in content ? (
				<a
					href={content.file ?? '#'}
					target="_blank"
					rel="noreferrer noopener"
					className="text-primary text-sm underline"
				>
					{content.title}
				</a>
			) : 'points_possible' in content ? (
				<>
					<div className="mb-1 text-sm font-medium">{content.title}</div>
					<div className="text-muted-foreground mb-2 text-xs">
						{content.points_possible} points
						{content.due_date
							? ` · due ${content.due_date.slice(0, 16).replace('T', ' ')}`
							: ' · no due date'}
						{!content.published && ' · not published'}
					</div>
					<RichText html={content.description ?? ''} />
				</>
			) : 'body' in content ? (
				<RichText html={content.body ?? ''} />
			) : null}
		</div>
	)
}
