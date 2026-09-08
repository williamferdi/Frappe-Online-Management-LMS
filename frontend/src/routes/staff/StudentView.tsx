import { useState } from 'react'
import { Eye } from 'lucide-react'

import { BlockRenderer } from '@/components/BlockRenderer'
import { ModuleOutline } from '@/components/ModuleOutline'
import { RosterPicker } from '@/components/RosterPicker'
import { QueryState } from '@/components/QueryState'
import { RichText } from '@/components/RichText'
import { Card, CardContent } from '@/components/ui/card'
import { useModulePreview, usePreviewItem } from '@/hooks/useSyllabus'
import type { ModulePreview, OutlineItem } from '@/types'

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
					<RosterPicker
						roster={data.roster}
						value={registration}
						onChange={onRegistration}
					/>

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
				<ModuleOutline
					modules={data.modules}
					openItem={open}
					onOpenItem={setOpen}
					// Openable even when locked: a teacher checking a module that
					// unlocks next week needs to see inside it. The lock is still
					// reported on the row, so what a student would meet is not
					// misrepresented -- only what this reader may do about it.
					renderBody={(item) => <ItemContent item={item} offering={offering} />}
				/>
			)}
		</div>
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
