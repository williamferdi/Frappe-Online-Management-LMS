import { useState } from 'react'
import { useParams } from 'react-router-dom'
import {
	CircleCheck,
	CircleDashed,
	FileText,
	Link2,
	Lock,
	NotebookPen,
	Paperclip,
} from 'lucide-react'
import { toast } from 'sonner'

import { BlockRenderer } from '@/components/BlockRenderer'
import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { RichText } from '@/components/RichText'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useMarkDone, useMyCourse, useReadItem } from '@/hooks/useSyllabus'
import { FrappeError } from '@/lib/frappe'
import { cn } from '@/lib/utils'
import type { CourseOutline, OutlineItem, OutlineModule } from '@/types'

function message(error: unknown) {
	return error instanceof FrappeError ? error.message : 'Something went wrong.'
}

const ICONS: Record<string, typeof FileText> = {
	Lesson: FileText,
	Assignment: NotebookPen,
	Page: FileText,
	File: Paperclip,
	URL: Link2,
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
				<div className="space-y-3">
					{data.modules.map((module) => (
						<Module
							key={module.name}
							module={module}
							registration={registration}
							openItem={open}
							onOpen={setOpen}
						/>
					))}
				</div>
			)}
		</>
	)
}

function Module({
	module,
	registration,
	openItem,
	onOpen,
}: {
	module: OutlineModule
	registration: string
	openItem: string | null
	onOpen: (item: string | null) => void
}) {
	return (
		<Card>
			<CardContent className="p-0">
				<div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
					<div className="flex items-center gap-2">
						<span className="font-medium">{module.title}</span>
						{module.complete && (
							<Badge variant="secondary">
								<CircleCheck className="mr-1 size-3" /> Done
							</Badge>
						)}
					</div>

					{!module.state.open && (
						<span className="text-muted-foreground flex items-center gap-1.5 text-xs">
							<Lock className="size-3.5" /> {module.state.reason}
						</span>
					)}
				</div>

				{module.items.length === 0 ? (
					<p className="text-muted-foreground px-4 py-6 text-sm">Nothing in here yet.</p>
				) : (
					<ul className="divide-y">
						{module.items.map((item) => (
							<Item
								key={item.name}
								item={item}
								registration={registration}
								isOpen={openItem === item.name}
								onOpen={onOpen}
							/>
						))}
					</ul>
				)}
			</CardContent>
		</Card>
	)
}

function Item({
	item,
	registration,
	isOpen,
	onOpen,
}: {
	item: OutlineItem
	registration: string
	isOpen: boolean
	onOpen: (item: string | null) => void
}) {
	const read = useReadItem(registration)
	const done = useMarkDone(registration)

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

	const Icon = ICONS[item.item_type] ?? FileText

	return (
		<li style={{ paddingLeft: `${item.indent * 16}px` }}>
			<div className="flex flex-wrap items-center gap-2 px-4 py-2.5">
				<Icon className="text-muted-foreground size-4 shrink-0" />

				<button
					type="button"
					disabled={item.locked}
					onClick={() => {
						if (isOpen) return onOpen(null)
						onOpen(item.name)
						read.mutate(item.name, {
							onError: (error) => {
								toast.error(message(error))
								onOpen(null)
							},
						})
					}}
					className={cn(
						'min-w-0 flex-1 text-left text-sm',
						item.locked ? 'text-muted-foreground cursor-not-allowed' : 'hover:underline',
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

			{isOpen && !item.locked && (
				<div className="bg-muted/40 border-t px-4 py-4">
					{read.isPending && (
						<p className="text-muted-foreground text-sm">Opening…</p>
					)}

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
			)}
		</li>
	)
}
