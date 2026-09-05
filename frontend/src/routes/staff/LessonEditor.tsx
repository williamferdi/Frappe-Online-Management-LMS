import { useState } from 'react'
import { ChevronDown, ChevronUp, LoaderCircle, Plus, Save, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { BlockRenderer, type Block } from '@/components/BlockRenderer'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useSaveLesson } from '@/hooks/useContent'
import { FrappeError } from '@/lib/frappe'

function message(error: unknown) {
	return error instanceof FrappeError ? error.message : 'Something went wrong.'
}

/**
 * A block editor for a lesson.
 *
 * Deliberately not EditorJS itself: the bundle is committed to git, so the
 * library would be a permanent addition, and what a lesson needs is a short
 * list of block types with a field each. It writes the same JSON EditorJS
 * does, so a lesson written here is still editable in the LMS and vice versa.
 *
 * The reader is shown live beside the editor, using the same BlockRenderer a
 * student gets — so what a lesson will look like is not a thing you find out
 * after saving.
 */

const LABELS: Record<string, string> = {
	header: 'Heading',
	paragraph: 'Paragraph',
	list: 'List',
	quote: 'Quote',
	code: 'Code',
	image: 'Image',
	embed: 'Video',
	delimiter: 'Divider',
}

/** What a new block of each type starts as. */
function blank(type: string): Block {
	switch (type) {
		case 'header':
			return { type, data: { text: '', level: 2 } }
		case 'list':
			return { type, data: { style: 'unordered', items: [''] } }
		case 'quote':
			return { type, data: { text: '', caption: '' } }
		case 'code':
			return { type, data: { code: '' } }
		case 'image':
			return { type, data: { url: '', caption: '' } }
		case 'embed':
			return { type, data: { embed: '', caption: '' } }
		case 'delimiter':
			return { type, data: {} }
		default:
			return { type: 'paragraph', data: { text: '' } }
	}
}

export function LessonEditor({
	offering,
	chapter,
	lessonName,
	initialTitle,
	initialBlocks,
	blockTypes,
	onDone,
}: {
	offering: string
	chapter: string
	lessonName?: string
	initialTitle: string
	initialBlocks: Block[]
	blockTypes: string[]
	onDone: () => void
}) {
	const [title, setTitle] = useState(initialTitle)
	const [blocks, setBlocks] = useState<Block[]>(
		initialBlocks.length ? initialBlocks : [blank('paragraph')],
	)
	const save = useSaveLesson(offering)

	const update = (index: number, data: Record<string, unknown>) =>
		setBlocks(blocks.map((b, i) => (i === index ? { ...b, data } : b)))

	const move = (index: number, by: number) => {
		const next = index + by
		if (next < 0 || next >= blocks.length) return
		const copy = [...blocks]
		;[copy[index], copy[next]] = [copy[next], copy[index]]
		setBlocks(copy)
	}

	return (
		<div className="space-y-4">
			<div>
				<Label htmlFor="lesson-title">Lesson title</Label>
				<Input
					id="lesson-title"
					className="mt-1"
					value={title}
					onChange={(event) => setTitle(event.target.value)}
				/>
			</div>

			<div className="grid gap-4 lg:grid-cols-2">
				<div className="space-y-2">
					{blocks.map((block, index) => (
						<BlockEditor
							key={index}
							block={block}
							index={index}
							total={blocks.length}
							onChange={(data) => update(index, data)}
							onMove={(by) => move(index, by)}
							onRemove={() => setBlocks(blocks.filter((_, i) => i !== index))}
						/>
					))}

					<div className="flex flex-wrap gap-1.5 pt-1">
						{blockTypes.map((type) => (
							<Button
								key={type}
								variant="outline"
								size="sm"
								onClick={() => setBlocks([...blocks, blank(type)])}
							>
								<Plus className="size-3.5" /> {LABELS[type] ?? type}
							</Button>
						))}
					</div>
				</div>

				<Card className="h-fit lg:sticky lg:top-4">
					<CardContent className="p-4">
						<div className="text-muted-foreground mb-3 text-xs font-medium tracking-wide uppercase">
							As a student sees it
						</div>
						<h3 className="mb-3 text-lg font-semibold">{title || 'Untitled lesson'}</h3>
						<BlockRenderer blocks={blocks} />
					</CardContent>
				</Card>
			</div>

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
								chapter,
								title,
								// Every block carries data; the optional type is the
								// renderer's, which must tolerate content it did not write.
								blocks: blocks.map((b) => ({ type: b.type, data: b.data ?? {} })),
								name: lessonName,
							},
							{
								onSuccess: () => {
									toast.success(lessonName ? 'Lesson saved' : 'Lesson created')
									onDone()
								},
								onError: (error) => toast.error(message(error)),
							},
						)
					}
				>
					{save.isPending ? <LoaderCircle className="animate-spin" /> : <Save />}
					Save lesson
				</Button>
			</div>
		</div>
	)
}

function BlockEditor({
	block,
	index,
	total,
	onChange,
	onMove,
	onRemove,
}: {
	block: Block
	index: number
	total: number
	onChange: (data: Record<string, unknown>) => void
	onMove: (by: number) => void
	onRemove: () => void
}) {
	const data = (block.data ?? {}) as Record<string, unknown>
	const text = typeof data.text === 'string' ? data.text : ''

	return (
		<Card>
			<CardContent className="p-3">
				<div className="mb-2 flex items-center gap-1">
					<span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
						{LABELS[block.type] ?? block.type}
					</span>
					<div className="ml-auto flex gap-0.5">
						<Button
							variant="ghost"
							size="icon"
							aria-label={`Move block ${index + 1} up`}
							disabled={index === 0}
							onClick={() => onMove(-1)}
						>
							<ChevronUp className="size-4" />
						</Button>
						<Button
							variant="ghost"
							size="icon"
							aria-label={`Move block ${index + 1} down`}
							disabled={index === total - 1}
							onClick={() => onMove(1)}
						>
							<ChevronDown className="size-4" />
						</Button>
						<Button
							variant="ghost"
							size="icon"
							aria-label={`Remove block ${index + 1}`}
							onClick={onRemove}
						>
							<Trash2 className="size-4" />
						</Button>
					</div>
				</div>

				{block.type === 'delimiter' && (
					<p className="text-muted-foreground text-xs">A horizontal rule.</p>
				)}

				{block.type === 'header' && (
					<div className="flex gap-2">
						<Input
							aria-label={`Heading ${index + 1}`}
							value={text}
							onChange={(event) => onChange({ ...data, text: event.target.value })}
						/>
						<select
							aria-label={`Heading level ${index + 1}`}
							className="border-input bg-background h-9 rounded-md border px-2 text-sm"
							value={Number(data.level) || 2}
							onChange={(event) =>
								onChange({ ...data, level: Number(event.target.value) })
							}
						>
							{[2, 3, 4].map((level) => (
								<option key={level} value={level}>
									H{level}
								</option>
							))}
						</select>
					</div>
				)}

				{block.type === 'paragraph' && (
					<Textarea
						aria-label={`Paragraph ${index + 1}`}
						rows={3}
						value={text}
						onChange={(event) => onChange({ ...data, text: event.target.value })}
					/>
				)}

				{block.type === 'quote' && (
					<div className="space-y-2">
						<Textarea
							aria-label={`Quote ${index + 1}`}
							rows={2}
							value={text}
							onChange={(event) => onChange({ ...data, text: event.target.value })}
						/>
						<Input
							aria-label={`Quote attribution ${index + 1}`}
							placeholder="Who said it"
							value={typeof data.caption === 'string' ? data.caption : ''}
							onChange={(event) => onChange({ ...data, caption: event.target.value })}
						/>
					</div>
				)}

				{block.type === 'code' && (
					<Textarea
						aria-label={`Code ${index + 1}`}
						className="font-mono text-xs"
						rows={4}
						value={typeof data.code === 'string' ? data.code : ''}
						onChange={(event) => onChange({ ...data, code: event.target.value })}
					/>
				)}

				{block.type === 'list' && (
					<ListEditor
						items={Array.isArray(data.items) ? (data.items as string[]) : ['']}
						ordered={data.style === 'ordered'}
						index={index}
						onChange={(items, ordered) =>
							onChange({ ...data, items, style: ordered ? 'ordered' : 'unordered' })
						}
					/>
				)}

				{block.type === 'image' && (
					<div className="space-y-2">
						<Input
							aria-label={`Image address ${index + 1}`}
							placeholder="https://…"
							value={typeof data.url === 'string' ? data.url : ''}
							onChange={(event) => onChange({ ...data, url: event.target.value })}
						/>
						<Input
							aria-label={`Image caption ${index + 1}`}
							placeholder="Caption"
							value={typeof data.caption === 'string' ? data.caption : ''}
							onChange={(event) => onChange({ ...data, caption: event.target.value })}
						/>
					</div>
				)}

				{block.type === 'embed' && (
					<div className="space-y-2">
						<Input
							aria-label={`Video address ${index + 1}`}
							placeholder="https://www.youtube.com/embed/…"
							value={typeof data.embed === 'string' ? data.embed : ''}
							onChange={(event) => onChange({ ...data, embed: event.target.value })}
						/>
						<p className="text-muted-foreground text-xs">
							YouTube or Vimeo embed address. Anything else is shown as a link
							rather than played in the page.
						</p>
					</div>
				)}
			</CardContent>
		</Card>
	)
}

function ListEditor({
	items,
	ordered,
	index,
	onChange,
}: {
	items: string[]
	ordered: boolean
	index: number
	onChange: (items: string[], ordered: boolean) => void
}) {
	return (
		<div className="space-y-2">
			<label className="flex items-center gap-2 text-xs">
				<input
					type="checkbox"
					checked={ordered}
					onChange={(event) => onChange(items, event.target.checked)}
				/>
				Numbered
			</label>

			{items.map((item, i) => (
				<div key={i} className="flex gap-2">
					<Input
						aria-label={`List ${index + 1} item ${i + 1}`}
						value={item}
						onChange={(event) =>
							onChange(
								items.map((value, j) => (j === i ? event.target.value : value)),
								ordered,
							)
						}
					/>
					<Button
						variant="ghost"
						size="icon"
						aria-label={`Remove list item ${i + 1}`}
						disabled={items.length === 1}
						onClick={() => onChange(items.filter((_, j) => j !== i), ordered)}
					>
						<Trash2 className="size-4" />
					</Button>
				</div>
			))}

			<Button
				variant="outline"
				size="sm"
				onClick={() => onChange([...items, ''], ordered)}
			>
				<Plus className="size-3.5" /> Item
			</Button>
		</div>
	)
}
