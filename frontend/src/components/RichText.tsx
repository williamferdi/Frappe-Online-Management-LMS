import DOMPurify from 'dompurify'

import { cn } from '@/lib/utils'

/**
 * Renders a Frappe Text Editor field.
 *
 * The body of an announcement or a message is HTML written by another person.
 * Sanitised on the way in, every time -- staff accounts are the ones writing
 * these, but a compromised staff account should not become script running in
 * every student's browser.
 */
export function RichText({ html, className }: { html: string; className?: string }) {
	return (
		<div
			className={cn(
				'text-sm leading-relaxed',
				'[&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2',
				'[&_p]:my-2 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5',
				'[&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5',
				'[&_strong]:font-semibold [&_h1]:text-base [&_h2]:text-base [&_h3]:text-sm',
				'[&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold [&_h1]:mt-3 [&_h2]:mt-3',
				'[&_blockquote]:border-l-2 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground',
				className,
			)}
			dangerouslySetInnerHTML={{
				__html: DOMPurify.sanitize(html || '', { USE_PROFILES: { html: true } }),
			}}
		/>
	)
}
