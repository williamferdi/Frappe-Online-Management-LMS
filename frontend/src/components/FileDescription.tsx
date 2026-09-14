import { cn } from '@/lib/utils'

/**
 * What a teacher wrote about a file, shown with the file.
 *
 * The Course File keeps it as plain text, so it is drawn as text -- never as
 * HTML -- with the teacher's line breaks kept. Nothing is drawn when there is
 * nothing to say.
 */
export function FileDescription({
	text,
	className,
}: {
	text: string | null | undefined
	className?: string
}) {
	const said = text?.trim()
	if (!said) return null

	return (
		<p className={cn('text-muted-foreground text-sm whitespace-pre-line', className)}>{said}</p>
	)
}
