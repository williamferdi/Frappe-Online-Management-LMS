import DOMPurify from 'dompurify'

/**
 * What the page editor lets in: pasted text, and the addresses links go to.
 */

/** The formatting a page keeps from a paste. The rest is Word's opinion. */
const PASTE_TAGS = [
	'p',
	'br',
	'h2',
	'h3',
	'h4',
	'strong',
	'b',
	'em',
	'i',
	'u',
	'ul',
	'ol',
	'li',
	'a',
	'blockquote',
]

/**
 * Clipboard HTML, reduced to its structure.
 *
 * Word and Google Docs put a font, a colour, a margin and a class name on
 * every run of text. Pasted as-is, a page stops looking like the rest of the
 * course, in ways the toolbar cannot undo. Kept: paragraphs, headings, lists,
 * bold, italic, underline, links and quotes.
 *
 * Images are dropped too. Word's point at files on the teacher's own disk and
 * Docs' at addresses that expire, so either would be a broken picture a week
 * later.
 */
export function cleanPaste(html: string): string {
	const doc = new DOMParser().parseFromString(html, 'text/html')

	// Google Docs wraps the whole clipboard in a <b> it does not mean.
	doc.querySelectorAll('b[id^="docs-internal-guid"]').forEach(unwrap)

	// Both editors say bold and italic with styles, which are about to go --
	// so say it with tags first, or the emphasis goes with them.
	doc.querySelectorAll('span[style]').forEach((span) => {
		const style = (span.getAttribute('style') ?? '').toLowerCase()
		const tags = [
			/(^|;)\s*font-weight:\s*(bold|[6-9]00)/.test(style) && 'strong',
			/(^|;)\s*font-style:\s*italic/.test(style) && 'em',
			/(^|;)\s*text-decoration[^;]*underline/.test(style) && 'u',
		].filter((tag): tag is string => Boolean(tag))
		if (!tags.length) return

		let content: Node[] = Array.from(span.childNodes)
		for (const tag of tags) {
			const wrapper = doc.createElement(tag)
			wrapper.append(...content)
			content = [wrapper]
		}
		span.replaceWith(...content)
	})

	// The page's title is its only top-level heading; a pasted one sits under it.
	doc.querySelectorAll('h1').forEach((heading) => rename(heading, 'h2'))
	doc.querySelectorAll('h5, h6').forEach((heading) => rename(heading, 'h4'))

	return DOMPurify.sanitize(doc.body.innerHTML, {
		ALLOWED_TAGS: PASTE_TAGS,
		ALLOWED_ATTR: ['href'],
	})
}

function unwrap(element: Element) {
	element.replaceWith(...Array.from(element.childNodes))
}

function rename(element: Element, tag: string) {
	const renamed = element.ownerDocument.createElement(tag)
	renamed.append(...Array.from(element.childNodes))
	element.replaceWith(renamed)
}

/**
 * What a teacher typed into the link box, as an address -- or null.
 *
 * People type `www.bible.com`, or an email address, or a path on this site,
 * and all of those should work. What must not work is anything that is not a
 * place: a `javascript:` URL, a `data:` URL, or a bare word that would become
 * `https://notes`, which is nobody's address.
 */
export function linkAddress(input: string): string | null {
	const text = input.trim()
	if (!text || /\s/.test(text)) return null

	if (/^mailto:/i.test(text)) {
		return /^mailto:[^@\s]+@[^@\s]+\.[^@\s]+$/i.test(text) ? text : null
	}
	if (/^[^@\s/:]+@[^@\s/]+\.[a-z]{2,}$/i.test(text)) return `mailto:${text}`

	// A path on this site -- but not `//host`, which is somebody else's.
	if (text.startsWith('//')) return null
	if (text.startsWith('/')) return text

	const candidate = /^[a-z][a-z0-9+.-]*:/i.test(text) ? text : `https://${text}`
	let url: URL
	try {
		url = new URL(candidate)
	} catch {
		return null
	}
	if (url.protocol !== 'https:' && url.protocol !== 'http:') return null
	if (!url.hostname.includes('.')) return null
	return candidate
}
