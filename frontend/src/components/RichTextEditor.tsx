import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import DOMPurify from 'dompurify'
import {
	Bold,
	Code,
	Heading2,
	Heading3,
	Italic,
	Link as LinkIcon,
	List,
	ListOrdered,
	Pilcrow,
	Quote,
	RemoveFormatting,
	Underline,
	Unlink,
	type LucideIcon,
} from 'lucide-react'

import { RICH_TEXT_STYLES, RichText } from '@/components/RichText'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { cleanPaste, linkAddress } from '@/lib/editing'
import { cn } from '@/lib/utils'

/**
 * A formatting toolbar over an editable page body.
 *
 * Deliberately not TipTap or ProseMirror: the bundle is committed to git, so a
 * library is a permanent addition, and a page needs a dozen commands. The
 * browser's own editing does the work (`contentEditable` and `execCommand` --
 * deprecated in the standards sense, and implemented everywhere, because the
 * web's editors depend on it). What this adds is a toolbar people recognise,
 * paste that leaves Word's styling behind, and links that go somewhere.
 *
 * It writes what the author wrote. Sanitising happens where it always has, in
 * RichText on every render -- and once more on the way *into* this editor, so
 * a stored `<img onerror>` cannot run in the teacher's own browser.
 */

interface Tool {
	key: string
	label: string
	icon: LucideIcon
	/** Tools in the same group sit together between dividers. */
	group: number
	press: () => void
	/** Left out for an action; true or false for a toggle. */
	pressed?: boolean
}

const MARKS = [
	{ command: 'bold', label: 'Bold', icon: Bold },
	{ command: 'italic', label: 'Italic', icon: Italic },
	{ command: 'underline', label: 'Underline', icon: Underline },
] as const

const BLOCKS = [
	{ tag: 'h2', label: 'Heading', icon: Heading2 },
	{ tag: 'h3', label: 'Subheading', icon: Heading3 },
	{ tag: 'p', label: 'Normal text', icon: Pilcrow },
	{ tag: 'blockquote', label: 'Quote', icon: Quote },
] as const

const LISTS = [
	{ command: 'insertUnorderedList', label: 'Bulleted list', icon: List },
	{ command: 'insertOrderedList', label: 'Numbered list', icon: ListOrdered },
] as const

/** Browsers disagree about which of these they implement; jsdom implements none. */
function ask<T>(question: () => T): T | false {
	try {
		return question()
	} catch {
		return false
	}
}

function exec(command: string, argument?: string) {
	ask(() => document.execCommand(command, false, argument))
}

/** Which of the toolbar's toggles the caret is standing in, as one string. */
function formattingHere(): string {
	const on: string[] = []
	for (const { command } of [...MARKS, ...LISTS]) {
		if (ask(() => document.queryCommandState(command))) on.push(command)
	}
	const block = ask(() => document.queryCommandValue('formatBlock'))
	if (typeof block === 'string' && block) on.push(block.toLowerCase())
	return on.join(' ')
}

/** A body emptied back to a stray `<br>` or `<p><br></p>` is an empty body. */
function isBlank(node: HTMLElement) {
	return !node.textContent?.trim() && !node.querySelector('img, iframe, hr')
}

export function RichTextEditor({
	id,
	labelledBy,
	value,
	onChange,
	placeholder = 'Write here…',
	className,
}: {
	id: string
	labelledBy: string
	value: string
	onChange: (html: string) => void
	placeholder?: string
	className?: string
}) {
	const editor = useRef<HTMLDivElement>(null)
	// Where the author's selection was, kept across a trip to the toolbar or
	// the link box -- focus leaving the text must not lose what it applies to.
	const selection = useRef<Range | null>(null)
	const [source, setSource] = useState(false)
	const [blank, setBlank] = useState(!value)
	const [here, setHere] = useState('')
	const [stop, setStop] = useState(0)
	const [link, setLink] = useState<string | null>(null)
	const [linkError, setLinkError] = useState<string | null>(null)

	// The text goes in once per visit to this mode, never per keystroke:
	// rewriting it while somebody types throws their caret back to the start.
	useEffect(() => {
		const node = editor.current
		if (source || !node) return
		node.innerHTML = DOMPurify.sanitize(value, { USE_PROFILES: { html: true } })
		setBlank(isBlank(node))
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [source])

	/**
	 * Keeps the author's selection, when it is in the text.
	 *
	 * Called on every `selectionchange`, and again, synchronously, whenever the
	 * toolbar acts. The event is queued behind input, so a click that follows a
	 * selection quickly enough -- or a script, or assistive technology -- would
	 * otherwise act on the selection before last. In a real browser, Link
	 * wrapped the old caret position instead of the words just chosen.
	 */
	const remember = useCallback(() => {
		const node = editor.current
		const current = document.getSelection()
		if (!node || !current?.rangeCount) return
		const range = current.getRangeAt(0)
		if (!node.contains(range.commonAncestorContainer)) return
		selection.current = range.cloneRange()
		setHere(formattingHere())
	}, [])

	useEffect(() => {
		document.addEventListener('selectionchange', remember)
		return () => document.removeEventListener('selectionchange', remember)
	}, [remember])

	const report = () => {
		const node = editor.current
		if (!node) return
		const empty = isBlank(node)
		setBlank(empty)
		onChange(empty ? '' : node.innerHTML)
	}

	/**
	 * Typing into an empty editor puts bare text straight into it, so the first
	 * line belongs to no paragraph and is spaced like none -- `Line one<p>Line
	 * two</p>`, as seen in a real browser. An empty page starts in a paragraph.
	 */
	const startParagraph = () => {
		const node = editor.current
		if (!node || !isBlank(node)) return
		node.innerHTML = '<p><br></p>'
		const range = document.createRange()
		range.setStart(node.firstChild!, 0)
		range.collapse(true)
		const current = document.getSelection()
		current?.removeAllRanges()
		current?.addRange(range)
	}

	/** Puts focus and the selection back in the text, then acts on it. */
	const run = (command: string, argument?: string) => {
		const node = editor.current
		if (!node) return
		remember()
		node.focus()
		const current = document.getSelection()
		if (selection.current && current) {
			current.removeAllRanges()
			current.addRange(selection.current)
		}
		exec(command, argument)
		report()
		setHere(formattingHere())
	}

	const linkHere = (): HTMLAnchorElement | null => {
		let node: Node | null = selection.current?.startContainer ?? null
		while (node && node !== editor.current) {
			if (node instanceof HTMLAnchorElement) return node
			node = node.parentNode
		}
		return null
	}

	const openLink = () => {
		remember()
		setLink(linkHere()?.getAttribute('href') ?? '')
		setLinkError(null)
	}

	const closeLink = () => {
		setLink(null)
		setLinkError(null)
		editor.current?.focus()
	}

	const applyLink = () => {
		const address = linkAddress(link ?? '')
		if (!address) {
			setLinkError(
				'That is not a web address. Try one starting https://, or an email address.',
			)
			return
		}
		setLink(null)
		setLinkError(null)

		const existing = linkHere()
		if (existing) {
			// Changing where a link goes, not making a second one inside it.
			existing.setAttribute('href', address)
			report()
			editor.current?.focus()
			return
		}
		if (!selection.current || selection.current.collapsed) {
			// Nothing chosen to link, so the address becomes its own text.
			const anchor = document.createElement('a')
			anchor.setAttribute('href', address)
			anchor.textContent = address
			run('insertHTML', anchor.outerHTML)
			return
		}
		run('createLink', address)
	}

	const unlink = () => {
		remember()
		// With only a caret inside a link, browsers unlink nothing, so the
		// whole link becomes the selection.
		const anchor = linkHere()
		if (anchor && selection.current?.collapsed) {
			const range = document.createRange()
			range.selectNodeContents(anchor)
			selection.current = range
		}
		run('unlink')
	}

	const on = new Set(here.split(' '))
	const tools: Tool[] = [
		...MARKS.map(({ command, label, icon }) => ({
			key: command,
			label,
			icon,
			group: 0,
			pressed: on.has(command),
			press: () => run(command),
		})),
		...BLOCKS.map(({ tag, label, icon }) => ({
			key: tag,
			label,
			icon,
			group: 1,
			pressed: on.has(tag),
			// Pressing a heading again makes it ordinary text again.
			press: () => run('formatBlock', on.has(tag) && tag !== 'p' ? '<p>' : `<${tag}>`),
		})),
		...LISTS.map(({ command, label, icon }) => ({
			key: command,
			label,
			icon,
			group: 2,
			pressed: on.has(command),
			press: () => run(command),
		})),
		{ key: 'link', label: 'Link', icon: LinkIcon, group: 3, press: openLink },
		{ key: 'unlink', label: 'Remove link', icon: Unlink, group: 3, press: unlink },
		{
			key: 'clear',
			label: 'Clear formatting',
			icon: RemoveFormatting,
			group: 4,
			press: () => run('removeFormat'),
		},
		{
			key: 'source',
			label: 'Edit as HTML',
			icon: Code,
			group: 5,
			pressed: source,
			press: () => {
				setLink(null)
				setSource(!source)
			},
		},
	]

	// One stop on the tab order, with the arrow keys moving along it -- the
	// toolbar pattern, so a keyboard user is not made to tab through fourteen
	// buttons to reach the text.
	const tabStop = source ? tools.length - 1 : stop

	const moveAlong = (event: React.KeyboardEvent<HTMLDivElement>) => {
		if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
		const buttons = Array.from(
			event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'),
		)
		if (!buttons.length) return
		event.preventDefault()
		const at = buttons.indexOf(document.activeElement as HTMLButtonElement)
		const next =
			event.key === 'Home'
				? 0
				: event.key === 'End'
					? buttons.length - 1
					: (at + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length
		buttons[next]?.focus()
	}

	return (
		<div className={cn('focus-within:border-ring overflow-hidden rounded-md border', className)}>
			<div
				role="toolbar"
				aria-label="Formatting"
				aria-controls={id}
				className="bg-muted/50 flex flex-wrap items-center gap-0.5 border-b p-1"
				onKeyDown={moveAlong}
			>
				{tools.map((tool, index) => {
					const Icon = tool.icon
					return (
						<Fragment key={tool.key}>
							{index > 0 && tools[index - 1]!.group !== tool.group && (
								<span aria-hidden className="bg-border mx-1 h-5 w-px" />
							)}
							<Button
								type="button"
								variant="ghost"
								size="icon"
								className={cn('size-8', tool.pressed && 'bg-accent text-accent-foreground')}
								aria-label={tool.label}
								title={tool.label}
								aria-pressed={tool.pressed}
								disabled={source && tool.key !== 'source'}
								tabIndex={index === tabStop ? 0 : -1}
								// Keeps the selection in the text when a button is clicked.
								onMouseDown={(event) => event.preventDefault()}
								onFocus={() => setStop(index)}
								onClick={tool.press}
							>
								<Icon className="size-4" />
							</Button>
						</Fragment>
					)
				})}
			</div>

			{link !== null && (
				<div className="bg-muted/30 flex flex-wrap items-center gap-2 border-b p-2">
					<Input
						aria-label="Link address"
						autoFocus
						className="h-8 min-w-48 flex-1"
						placeholder="https://… or someone@example.org"
						value={link}
						onChange={(event) => {
							setLink(event.target.value)
							setLinkError(null)
						}}
						onKeyDown={(event) => {
							if (event.key === 'Enter') {
								event.preventDefault()
								applyLink()
							} else if (event.key === 'Escape') {
								event.preventDefault()
								closeLink()
							}
						}}
					/>
					<Button type="button" size="sm" onClick={applyLink}>
						Add link
					</Button>
					<Button type="button" size="sm" variant="outline" onClick={closeLink}>
						Cancel
					</Button>
					{linkError && (
						<p role="alert" className="text-destructive w-full text-xs">
							{linkError}
						</p>
					)}
				</div>
			)}

			{source ? (
				<>
					<Textarea
						id={id}
						aria-labelledby={labelledBy}
						className="min-h-48 rounded-none border-0 font-mono text-xs shadow-none focus-visible:ring-0"
						rows={10}
						value={value}
						onChange={(event) => onChange(event.target.value)}
					/>
					{value && (
						<div className="bg-muted/40 border-t p-3">
							<div className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
								As a student sees it
							</div>
							<RichText html={value} />
						</div>
					)}
				</>
			) : (
				<div className="relative">
					{blank && (
						<span
							aria-hidden
							className="text-muted-foreground pointer-events-none absolute top-2 left-3 text-sm"
						>
							{placeholder}
						</span>
					)}
					<div
						ref={editor}
						id={id}
						role="textbox"
						aria-multiline="true"
						aria-labelledby={labelledBy}
						aria-placeholder={placeholder}
						contentEditable
						suppressContentEditableWarning
						className={cn(
							'text-sm leading-relaxed',
							RICH_TEXT_STYLES,
							'min-h-48 px-3 py-2 outline-none',
						)}
						onInput={report}
						onFocus={() => {
							// Enter should start a paragraph, not the <div> Chrome makes by default.
							exec('defaultParagraphSeparator', 'p')
							startParagraph()
						}}
						onKeyDown={(event) => {
							if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
								event.preventDefault()
								openLink()
							}
						}}
						onPaste={(event) => {
							const html = event.clipboardData.getData('text/html')
							// Plain text is already clean; the browser's own paste will do.
							if (!html) return
							event.preventDefault()
							exec('insertHTML', cleanPaste(html))
							report()
						}}
					/>
				</div>
			)}
		</div>
	)
}
