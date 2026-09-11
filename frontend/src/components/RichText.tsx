import DOMPurify from 'dompurify'

import { cn } from '@/lib/utils'

/**
 * How rich text looks. Shared with the page editor, so what a teacher writes
 * in looks like what a student reads.
 */
export const RICH_TEXT_STYLES = cn(
	'[&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2',
	'[&_p]:my-2 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5',
	'[&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5',
	'[&_strong]:font-semibold [&_h1]:text-base [&_h2]:text-base [&_h3]:text-sm',
	'[&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold [&_h1]:mt-3 [&_h2]:mt-3',
	'[&_blockquote]:border-l-2 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground',
)

/**
 * Renders a Frappe Text Editor field.
 *
 * The body of an announcement or a message is HTML written by another person.
 * Sanitised on the way in, every time -- staff accounts are the ones writing
 * these, but a compromised staff account should not become script running in
 * every student's browser.
 */
export function RichText({
	html,
	className,
	inline = false,
}: {
	html: string
	className?: string
	/** Render a <span> rather than a <div>, for use inside a heading or a
	 * list item where a block element would be invalid markup. */
	inline?: boolean
}) {
	const Tag = inline ? 'span' : 'div'

	return (
		<Tag
			className={cn(!inline && 'text-sm leading-relaxed', RICH_TEXT_STYLES, className)}
			dangerouslySetInnerHTML={{
				__html: DOMPurify.sanitize(html || '', { USE_PROFILES: { html: true } }),
			}}
		/>
	)
}
