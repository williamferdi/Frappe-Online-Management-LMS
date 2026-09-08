import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { BlockRenderer } from '@/components/BlockRenderer'
import { ModuleOutline } from '@/components/ModuleOutline'
import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { RichText } from '@/components/RichText'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useMarkDone, useMyCourse, useReadItem } from '@/hooks/useSyllabus'
import { FrappeError } from '@/lib/frappe'
import type { CourseOutline, OutlineItem } from '@/types'

function message(error: unknown) {
	return error instanceof FrappeError ? error.message : 'Something went wrong.'
}

/** A student's course: modules in order, with what is open and what is not. */
export function MyCourse() {
	const { name = null } = useParams()
	const registration = name ? decodeURIComponent(name) : null
	const query = useMyCourse(registration)

	return (
		<QueryState query={query} title="Course">
			{(data) => <Loaded data={data} registration={registration!} />}
		</QueryState>
	)
}

function Loaded({
	data,
	registration,
}: {
	data: CourseOutline
	registration: string
}) {
	const [open, setOpen] = useState<string | null>(null)

	// One reader for the page rather than one per row: only a single item is
	// open at a time, so the last result is always the open item's.
	const read = useReadItem(registration)

	const onOpenItem = (item: string | null) => {
		setOpen(item)
		if (!item) return
		read.mutate(item, {
			onError: (error) => {
				toast.error(message(error))
				setOpen(null)
			},
		})
	}

	return (
		<>
			<PageHeader
				title={data.registration.course_title || data.registration.course_offering}
				description={
					data.modules.length === 1 ? '1 module' : `${data.modules.length} modules`
				}
			/>

			{data.modules.length === 0 ? (
				<Card>
					<CardContent className="py-14 text-center">
						<div className="font-medium">Nothing here yet</div>
						<p className="text-muted-foreground mt-1 text-sm">
							Modules appear as your teacher publishes them.
						</p>
					</CardContent>
				</Card>
			) : (
				<ModuleOutline
					modules={data.modules}
					openItem={open}
					onOpenItem={onOpenItem}
					// A student cannot open what is locked. The teacher's preview
					// of this same list can, which is why the rule is a prop.
					canOpen={(item) => !item.locked}
					renderBody={(item) => (
						<ItemBody item={item} registration={registration} read={read} />
					)}
				/>
			)}
		</>
	)
}

function ItemBody({
	item,
	registration,
	read,
}: {
	item: OutlineItem
	registration: string
	read: ReturnType<typeof useReadItem>
}) {
	const done = useMarkDone(registration)

	return (
		<div className="bg-muted/40 border-t px-4 py-4">
			{read.isPending && <p className="text-muted-foreground text-sm">Opening…</p>}

			{read.data?.content && (
				<>
					{'blocks' in read.data.content ? (
						<BlockRenderer
							blocks={read.data.content.blocks}
							removed={read.data.content.removed}
							lmsUrl={read.data.content.lms_url}
						/>
					) : 'body' in read.data.content ? (
						<RichText html={read.data.content.body ?? ''} />
					) : 'file' in read.data.content ? (
						<a
							href={read.data.content.file ?? '#'}
							target="_blank"
							rel="noreferrer noopener"
							className="text-primary text-sm underline"
						>
							{read.data.content.title}
						</a>
					) : null}
				</>
			)}

			{item.item_type === 'URL' && item.url && (
				<a
					href={item.url}
					target="_blank"
					rel="noreferrer noopener"
					className="text-primary text-sm underline"
				>
					{item.url}
				</a>
			)}

			{item.completion_requirement === 'Mark it done' && !item.complete && (
				<Button
					size="sm"
					className="mt-4"
					disabled={done.isPending}
					onClick={() =>
						done.mutate(item.name, {
							onSuccess: () => toast.success('Marked done'),
							onError: (error) => toast.error(message(error)),
						})
					}
				>
					Mark done
				</Button>
			)}
		</div>
	)
}
