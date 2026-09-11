import { ExternalLink } from 'lucide-react'

import { RichText } from '@/components/RichText'
import { cn } from '@/lib/utils'
import { readVideo } from '@/lib/video'

/**
 * EditorJS lesson content, rendered here rather than in an iframe.
 *
 * The alternative -- iframing the LMS player -- is cheaper to build and more
 * expensive forever: hiding its chrome means another patch to a vendored app,
 * re-applied after every `bench update`, plus a rebuild and a regression test
 * to catch it silently reverting.
 *
 * Block shape is not a contract anybody owns, so the failure mode to design
 * for is a blank lesson. Every unknown block renders a visible notice with a
 * link into the LMS, and a Python test asserts that no block type in stored
 * content is missing from this list. A lesson degrades; it does not vanish.
 *
 * Surveyed across the whole estate: paragraph, embed, list, markdown, header,
 * quiz. The interactive ones are stripped server-side, because an embedded
 * quiz would be a second route to a grade running on the LMS's own scoring.
 */

export type Block = {
	type: string
	data?: Record<string, unknown>
}

export function BlockRenderer({
	blocks,
	removed,
	lmsUrl,
	className,
}: {
	blocks: Block[]
	removed?: string[]
	lmsUrl?: string | null
	className?: string
}) {
	if (!blocks.length) {
		return (
			<p className="text-muted-foreground text-sm">
				This lesson has no content yet.
			</p>
		)
	}

	return (
		<div className={cn('space-y-4', className)}>
			{blocks.map((block, index) => (
				<BlockView key={index} block={block} lmsUrl={lmsUrl} />
			))}

			{removed && removed.length > 0 && (
				<Notice lmsUrl={lmsUrl}>
					{removed.length === 1
						? 'An exercise embedded in this lesson is not shown here.'
						: `${removed.length} exercises embedded in this lesson are not shown here.`}{' '}
					Work that counts towards your grade is listed in the module instead.
				</Notice>
			)}
		</div>
	)
}

function BlockView({ block, lmsUrl }: { block: Block; lmsUrl?: string | null }) {
	const data = (block.data ?? {}) as Record<string, unknown>
	const text = typeof data.text === 'string' ? data.text : ''

	switch (block.type) {
		case 'paragraph':
			return text ? <RichText html={text} /> : null

		case 'header': {
			// EditorJS levels are 1-6; the page already has an h1, so a lesson's
			// own headings start one level down.
			const level = Math.min(Math.max(Number(data.level) || 2, 2), 6)
			const Tag = `h${level}` as 'h2'
			return (
				<Tag
					className={cn(
						'font-semibold',
						level === 2 ? 'text-xl' : level === 3 ? 'text-lg' : 'text-base',
					)}
				>
					<RichText html={text} inline />
				</Tag>
			)
		}

		case 'list': {
			const items = Array.isArray(data.items) ? data.items : []
			const ordered = data.style === 'ordered'
			const Tag = ordered ? 'ol' : 'ul'
			return (
				<Tag className={cn('ml-6 space-y-1', ordered ? 'list-decimal' : 'list-disc')}>
					{items.map((item, index) => (
						<li key={index}>
							<RichText
								html={
									typeof item === 'string'
										? item
										: String((item as { content?: string })?.content ?? '')
								}
								inline
							/>
						</li>
					))}
				</Tag>
			)
		}

		case 'markdown':
			// Frappe LMS stores this block already rendered to HTML.
			return <RichText html={String(data.text ?? '')} />

		case 'quote':
			return (
				<blockquote className="border-muted-foreground/30 border-l-2 pl-4 italic">
					<RichText html={text} />
					{typeof data.caption === 'string' && data.caption && (
						<footer className="text-muted-foreground mt-1 text-sm not-italic">
							— <RichText html={data.caption} inline />
						</footer>
					)}
				</blockquote>
			)

		case 'code':
			return (
				<pre className="bg-muted overflow-x-auto rounded-md p-3 text-xs">
					<code>{String(data.code ?? '')}</code>
				</pre>
			)

		case 'delimiter':
			return <hr className="border-border my-6" />

		case 'image': {
			const file = data.file as { url?: string } | undefined
			const url = file?.url ?? (typeof data.url === 'string' ? data.url : null)
			if (!url) return null
			return (
				<figure>
					<img src={url} alt={String(data.caption ?? '')} className="rounded-md" />
					{typeof data.caption === 'string' && data.caption && (
						<figcaption className="text-muted-foreground mt-1 text-xs">
							{data.caption}
						</figcaption>
					)}
				</figure>
			)
		}

		case 'embed':
			return <Embed data={data} lmsUrl={lmsUrl} />

		case 'table': {
			const rows = Array.isArray(data.content) ? (data.content as string[][]) : []
			if (!rows.length) return null
			return (
				// Wide tables scroll inside their own box; the page never
				// scrolls sideways.
				<div className="overflow-x-auto">
					<table className="w-full text-sm">
						<tbody>
							{rows.map((row, r) => (
								<tr key={r} className="border-b last:border-0">
									{row.map((cell, c) => (
										<td key={c} className="px-3 py-2">
											<RichText html={cell} inline />
										</td>
									))}
								</tr>
							))}
						</tbody>
					</table>
				</div>
			)
		}

		default:
			return (
				<Notice lmsUrl={lmsUrl}>
					Part of this lesson ({block.type}) cannot be shown here yet.
				</Notice>
			)
	}
}

/**
 * An embedded video.
 *
 * Only YouTube and Vimeo, and never a URL from lesson content dropped into
 * `src` as it was stored: `readVideo` builds the address to play from the
 * video's id. That is also what lets a teacher paste the link from the
 * address bar -- YouTube's watch page refuses to be framed ("refused to
 * connect"), and the embed address built from the same id does not.
 */
function Embed({
	data,
	lmsUrl,
}: {
	data: Record<string, unknown>
	lmsUrl?: string | null
}) {
	const stored = typeof data.embed === 'string' ? data.embed : ''
	const source = typeof data.source === 'string' ? data.source : ''
	// Either may hold the link. The LMS writes both; a lesson saved before
	// links were read holds whatever was pasted, in `embed`.
	const video = readVideo(stored) ?? readVideo(source)

	if (!video) {
		// Offered as a link only when it is a web address: a `javascript:` URL
		// out of stored content is not a thing to put under a student's cursor.
		const elsewhere = [source, stored].find((link) => /^https?:\/\//i.test(link))
		return (
			<Notice lmsUrl={lmsUrl}>
				This lesson embeds something from elsewhere.{' '}
				{elsewhere && (
					<a
						href={elsewhere}
						target="_blank"
						rel="noreferrer noopener"
						className="underline"
					>
						Open it directly
					</a>
				)}
			</Notice>
		)
	}

	return (
		<div className="aspect-video overflow-hidden rounded-md">
			<iframe
				src={video.embed}
				title={String(data.caption ?? 'Embedded video')}
				className="size-full"
				allow="accelerometer; clipboard-write; encrypted-media; picture-in-picture"
				allowFullScreen
				referrerPolicy="strict-origin-when-cross-origin"
			/>
		</div>
	)
}

function Notice({
	children,
	lmsUrl,
}: {
	children: React.ReactNode
	lmsUrl?: string | null
}) {
	return (
		<div className="border-muted-foreground/30 text-muted-foreground rounded-md border border-dashed p-3 text-sm">
			{children}
			{lmsUrl && (
				<>
					{' '}
					<a
						href={lmsUrl}
						target="_blank"
						rel="noreferrer noopener"
						className="inline-flex items-center gap-1 underline"
					>
						Open in the LMS <ExternalLink className="size-3" />
					</a>
				</>
			)}
		</div>
	)
}
