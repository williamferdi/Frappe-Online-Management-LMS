import { useState } from 'react'
import { BookText, FileText, LoaderCircle, Paperclip, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { QueryState } from '@/components/QueryState'
import { RichTextEditor } from '@/components/RichTextEditor'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { LessonEditor } from '@/routes/staff/LessonEditor'
import {
	useContentOutline,
	useDeleteFile,
	useDeleteLesson,
	useDeletePage,
	useLesson,
	usePage,
	useSaveChapter,
	useSaveFile,
	useSavePage,
} from '@/hooks/useContent'
import { useCreateContentSpace } from '@/hooks/useSyllabus'
import { FrappeError, frappeUpload } from '@/lib/frappe'
import type { ContentOutline } from '@/types'

function message(error: unknown) {
	return error instanceof FrappeError ? error.message : 'Something went wrong.'
}

/**
 * Everything a course is made of: lessons, pages and files.
 *
 * Lessons are still stored in the LMS -- this writes the same Course Lesson,
 * Course Chapter and reference rows its own editor does, so a lesson written
 * here stays readable and editable there.
 */
export function Content({ offering }: { offering: string }) {
	const query = useContentOutline(offering)

	return (
		<QueryState query={query} title="Content">
			{(data) => <Loaded data={data} offering={offering} />}
		</QueryState>
	)
}

function Loaded({ data, offering }: { data: ContentOutline; offering: string }) {
	if (!data.lms_course) {
		return <NoSpace offering={offering} />
	}

	return (
		<div className="space-y-6">
			<Lessons data={data} offering={offering} />
			<Pages data={data} offering={offering} />
			<Files data={data} offering={offering} />
		</div>
	)
}

function NoSpace({ offering }: { offering: string }) {
	const make = useCreateContentSpace(offering)

	return (
		<Card>
			<CardContent className="py-12 text-center">
				<BookText className="text-muted-foreground mx-auto mb-3 size-8" />
				<div className="font-medium">This course has nowhere to keep lessons yet</div>
				<p className="text-muted-foreground mx-auto mt-1 mb-4 max-w-md text-sm">
					Lessons are stored in the LMS and written here. Set the space up once and
					it is there for every future term of this course.
				</p>
				<Button
					size="sm"
					disabled={make.isPending}
					onClick={() =>
						make.mutate(undefined, {
							onSuccess: () => toast.success('Ready for lessons'),
							onError: (error) => toast.error(message(error)),
						})
					}
				>
					{make.isPending ? <LoaderCircle className="animate-spin" /> : null}
					Set up lessons
				</Button>
			</CardContent>
		</Card>
	)
}

/**
 * Said instead of opening an editor over something that did not load.
 *
 * The editors take their starting text once. Opened empty over a lesson or
 * page that failed to arrive, the first Save would write that emptiness over
 * it -- so this goes no further than saying so.
 */
function CouldNotOpen({
	what,
	error,
	onBack,
}: {
	what: string
	error: unknown
	onBack: () => void
}) {
	return (
		<Card>
			<CardContent className="space-y-3 py-8 text-center">
				<div className="font-medium">This {what} could not be opened</div>
				<p className="text-muted-foreground text-sm">
					{message(error)} Nothing has been changed.
				</p>
				<Button variant="outline" size="sm" onClick={onBack}>
					Back
				</Button>
			</CardContent>
		</Card>
	)
}

// ---------------------------------------------------------------------------
// lessons
// ---------------------------------------------------------------------------

function Lessons({ data, offering }: { data: ContentOutline; offering: string }) {
	const [addingChapter, setAddingChapter] = useState(false)
	const [chapterTitle, setChapterTitle] = useState('')
	const [editing, setEditing] = useState<{ chapter: string; lesson?: string } | null>(null)
	const saveChapter = useSaveChapter(offering)

	if (editing) {
		return (
			<LessonPane
				offering={offering}
				chapter={editing.chapter}
				lessonName={editing.lesson}
				blockTypes={data.block_types}
				onDone={() => setEditing(null)}
			/>
		)
	}

	return (
		<section>
			<div className="mb-3 flex flex-wrap items-center justify-between gap-2">
				<h3 className="text-sm font-semibold">Lessons</h3>
				{addingChapter ? (
					<div className="flex items-end gap-2">
						<Input
							aria-label="Chapter title"
							className="w-56"
							placeholder="Week One"
							value={chapterTitle}
							onChange={(event) => setChapterTitle(event.target.value)}
						/>
						<Button
							size="sm"
							disabled={!chapterTitle || saveChapter.isPending}
							onClick={() =>
								saveChapter.mutate(
									{ title: chapterTitle },
									{
										onSuccess: () => {
											toast.success('Chapter added')
											setChapterTitle('')
											setAddingChapter(false)
										},
										onError: (error) => toast.error(message(error)),
									},
								)
							}
						>
							Add
						</Button>
						<Button variant="outline" size="sm" onClick={() => setAddingChapter(false)}>
							Cancel
						</Button>
					</div>
				) : (
					<Button size="sm" onClick={() => setAddingChapter(true)}>
						<Plus /> New chapter
					</Button>
				)}
			</div>

			{data.chapters.length === 0 ? (
				<Card>
					<CardContent className="py-10 text-center">
						<div className="font-medium">No chapters yet</div>
						<p className="text-muted-foreground mx-auto mt-1 max-w-md text-sm">
							A chapter groups lessons. Add one, then write lessons inside it.
						</p>
					</CardContent>
				</Card>
			) : (
				<div className="space-y-3">
					{data.chapters.map((chapter) => (
						<Card key={chapter.name}>
							<CardContent className="p-0">
								<div className="flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
									<span className="font-medium">{chapter.title}</span>
									<span className="text-muted-foreground text-xs">
										{chapter.lessons.length === 1
											? '1 lesson'
											: `${chapter.lessons.length} lessons`}
									</span>
									<Button
										variant="outline"
										size="sm"
										className="ml-auto"
										onClick={() => setEditing({ chapter: chapter.name })}
									>
										<Plus /> Lesson
									</Button>
								</div>

								{chapter.lessons.length > 0 && (
									<ul className="divide-y">
										{chapter.lessons.map((lesson) => (
											<LessonRow
												key={lesson.name}
												lesson={lesson}
												offering={offering}
												onEdit={() =>
													setEditing({ chapter: chapter.name, lesson: lesson.name })
												}
											/>
										))}
									</ul>
								)}
							</CardContent>
						</Card>
					))}
				</div>
			)}
		</section>
	)
}

function LessonRow({
	lesson,
	offering,
	onEdit,
}: {
	lesson: { name: string; title: string }
	offering: string
	onEdit: () => void
}) {
	const remove = useDeleteLesson(offering)

	return (
		<li className="flex flex-wrap items-center gap-2 px-4 py-2 text-sm">
			<FileText className="text-muted-foreground size-4 shrink-0" />
			<span className="min-w-0 flex-1 truncate">{lesson.title}</span>
			<Button variant="ghost" size="sm" onClick={onEdit}>
				Edit
			</Button>
			<Button
				variant="ghost"
				size="icon"
				aria-label={`Delete ${lesson.title}`}
				onClick={() =>
					remove.mutate(lesson.name, {
						onSuccess: (result) =>
							toast.success(
								result.module_items_removed
									? `Lesson deleted, and removed from ${result.module_items_removed} module item(s)`
									: 'Lesson deleted',
							),
						onError: (error) => toast.error(message(error)),
					})
				}
			>
				<Trash2 className="size-4" />
			</Button>
		</li>
	)
}

/** Loads an existing lesson before editing it; a new one starts empty. */
function LessonPane({
	offering,
	chapter,
	lessonName,
	blockTypes,
	onDone,
}: {
	offering: string
	chapter: string
	lessonName?: string
	blockTypes: string[]
	onDone: () => void
}) {
	const existing = useLesson(lessonName ?? null, offering)

	if (lessonName && existing.isPending) {
		return <p className="text-muted-foreground text-sm">Opening…</p>
	}

	if (lessonName && existing.isError) {
		return <CouldNotOpen what="lesson" error={existing.error} onBack={onDone} />
	}

	return (
		<LessonEditor
			offering={offering}
			chapter={chapter}
			lessonName={lessonName}
			initialTitle={existing.data?.title ?? ''}
			initialBlocks={existing.data?.blocks ?? []}
			blockTypes={blockTypes}
			onDone={onDone}
		/>
	)
}

// ---------------------------------------------------------------------------
// pages
// ---------------------------------------------------------------------------

function Pages({ data, offering }: { data: ContentOutline; offering: string }) {
	// No `name` is a new page; a `name` is the page being edited.
	const [editing, setEditing] = useState<{ name?: string } | null>(null)
	const remove = useDeletePage(offering)

	return (
		<section>
			<div className="mb-3 flex items-center justify-between gap-2">
				<h3 className="text-sm font-semibold">Pages</h3>
				{!editing && (
					<Button size="sm" variant="outline" onClick={() => setEditing({})}>
						<Plus /> New page
					</Button>
				)}
			</div>

			{editing ? (
				<PagePane offering={offering} name={editing.name} onDone={() => setEditing(null)} />
			) : data.pages.length === 0 ? (
				<Card>
					<CardContent className="py-8 text-center">
						<p className="text-muted-foreground text-sm">
							A page is course text that is not a lesson — a syllabus, a reading
							list, an office-hours note.
						</p>
					</CardContent>
				</Card>
			) : (
				<Card>
					<CardContent className="p-0">
						<ul className="divide-y">
							{data.pages.map((page) => (
								<li
									key={page.name}
									className="flex flex-wrap items-center gap-2 px-4 py-2 text-sm"
								>
									<FileText className="text-muted-foreground size-4 shrink-0" />
									<span className="min-w-0 flex-1 truncate">{page.title}</span>
									<Badge variant={page.published ? 'default' : 'secondary'}>
										{page.published ? 'Published' : 'Draft'}
									</Badge>
									<Button
										variant="ghost"
										size="sm"
										aria-label={`Edit ${page.title}`}
										onClick={() => setEditing({ name: page.name })}
									>
										Edit
									</Button>
									<Button
										variant="ghost"
										size="icon"
										aria-label={`Delete ${page.title}`}
										onClick={() =>
											remove.mutate(page.name, {
												onSuccess: () => toast.success('Page deleted'),
												onError: (error) => toast.error(message(error)),
											})
										}
									>
										<Trash2 className="size-4" />
									</Button>
								</li>
							))}
						</ul>
					</CardContent>
				</Card>
			)}
		</section>
	)
}

/** Loads an existing page before editing it; a new one starts empty. */
function PagePane({
	offering,
	name,
	onDone,
}: {
	offering: string
	name?: string
	onDone: () => void
}) {
	const existing = usePage(name ?? null, offering)

	if (name && existing.isPending) {
		return <p className="text-muted-foreground text-sm">Opening…</p>
	}

	if (name && existing.isError) {
		return <CouldNotOpen what="page" error={existing.error} onBack={onDone} />
	}

	return (
		<PageEditor
			offering={offering}
			name={name}
			initialTitle={existing.data?.title ?? ''}
			initialBody={existing.data?.body ?? ''}
			// A new page is published, as it always was here. An existing one
			// keeps what it has: editing a draft must not publish it.
			initialPublished={existing.data ? existing.data.published : 1}
			onDone={onDone}
		/>
	)
}

function PageEditor({
	offering,
	name,
	initialTitle,
	initialBody,
	initialPublished,
	onDone,
}: {
	offering: string
	name?: string
	initialTitle: string
	initialBody: string
	initialPublished: number
	onDone: () => void
}) {
	const [title, setTitle] = useState(initialTitle)
	const [body, setBody] = useState(initialBody)
	const [published, setPublished] = useState(initialPublished)
	const save = useSavePage(offering)

	return (
		<Card>
			<CardContent className="space-y-3 p-4">
				<div>
					<Label htmlFor="page-title">Title</Label>
					<Input
						id="page-title"
						className="mt-1"
						value={title}
						onChange={(event) => setTitle(event.target.value)}
					/>
				</div>
				<div>
					<Label id="page-body-label" htmlFor="page-body">
						Body
					</Label>
					<RichTextEditor
						id="page-body"
						labelledBy="page-body-label"
						className="mt-1"
						value={body}
						onChange={setBody}
						placeholder="Write the page, or paste it from Word or Google Docs."
					/>
				</div>
				<label className="flex items-center gap-2 text-sm">
					<input
						type="checkbox"
						checked={Boolean(published)}
						onChange={(event) => setPublished(event.target.checked ? 1 : 0)}
					/>
					Students can see this page
				</label>
				<div className="flex justify-end gap-2">
					<Button variant="outline" size="sm" onClick={onDone}>
						Cancel
					</Button>
					<Button
						size="sm"
						disabled={!title || save.isPending}
						onClick={() =>
							save.mutate(
								{ title, body, published, name },
								{
									onSuccess: () => {
										toast.success(name ? 'Page saved' : 'Page created')
										onDone()
									},
									onError: (error) => toast.error(message(error)),
								},
							)
						}
					>
						{save.isPending ? <LoaderCircle className="animate-spin" /> : null}
						Save page
					</Button>
				</div>
			</CardContent>
		</Card>
	)
}

// ---------------------------------------------------------------------------
// files
// ---------------------------------------------------------------------------

function Files({ data, offering }: { data: ContentOutline; offering: string }) {
	const [adding, setAdding] = useState(false)
	const [title, setTitle] = useState('')
	const [url, setUrl] = useState('')
	const [uploading, setUploading] = useState(false)
	const save = useSaveFile(offering)
	const remove = useDeleteFile(offering)

	return (
		<section>
			<div className="mb-3 flex items-center justify-between gap-2">
				<h3 className="text-sm font-semibold">Files</h3>
				{!adding && (
					<Button size="sm" variant="outline" onClick={() => setAdding(true)}>
						<Plus /> Add file
					</Button>
				)}
			</div>

			{adding && (
				<Card className="mb-3">
					<CardContent className="flex flex-wrap items-end gap-3 p-4">
						<div>
							<Label htmlFor="file-title">Title</Label>
							<Input
								id="file-title"
								className="mt-1 w-56"
								value={title}
								onChange={(event) => setTitle(event.target.value)}
							/>
						</div>

						<div className="min-w-64 flex-1">
							<Label htmlFor="file-upload">File</Label>
							<Input
								id="file-upload"
								type="file"
								className="mt-1"
								disabled={uploading}
								onChange={async (event) => {
									const chosen = event.target.files?.[0]
									if (!chosen) return
									setUploading(true)
									try {
										const stored = await frappeUpload(chosen)
										setUrl(stored.file_url)
										// The file's own name is the obvious title, and
										// retyping it is work nobody asked for.
										if (!title) setTitle(chosen.name)
									} catch (error) {
										toast.error(message(error))
									} finally {
										setUploading(false)
									}
								}}
							/>
							{url && (
								<p className="text-muted-foreground mt-1 truncate text-xs">
									{uploading ? 'Uploading…' : `Stored at ${url}`}
								</p>
							)}
						</div>

						<Button
							size="sm"
							disabled={!title || !url || uploading || save.isPending}
							onClick={() =>
								save.mutate(
									{ title, file: url },
									{
										onSuccess: () => {
											toast.success('File added')
											setTitle('')
											setUrl('')
											setAdding(false)
										},
										onError: (error) => toast.error(message(error)),
									},
								)
							}
						>
							Add
						</Button>
						<Button variant="outline" size="sm" onClick={() => setAdding(false)}>
							Cancel
						</Button>
					</CardContent>
				</Card>
			)}

			{data.files.length === 0 ? (
				<Card>
					<CardContent className="py-8 text-center">
						<p className="text-muted-foreground text-sm">
							A reading, a handout, a slide deck. Upload one here and it can be
							added to a module, and offered beside the lesson it belongs to.
						</p>
					</CardContent>
				</Card>
			) : (
				<Card>
					<CardContent className="p-0">
						<ul className="divide-y">
							{data.files.map((file) => (
								<li
									key={file.name}
									className="flex flex-wrap items-center gap-2 px-4 py-2 text-sm"
								>
									<Paperclip className="text-muted-foreground size-4 shrink-0" />
									<span className="min-w-0 flex-1 truncate">{file.title}</span>
									<Button
										variant="ghost"
										size="icon"
										aria-label={`Delete ${file.title}`}
										onClick={() =>
											remove.mutate(file.name, {
												onSuccess: () => toast.success('File removed'),
												onError: (error) => toast.error(message(error)),
											})
										}
									>
										<Trash2 className="size-4" />
									</Button>
								</li>
							))}
						</ul>
					</CardContent>
				</Card>
			)}
		</section>
	)
}
