import { cn } from '@/lib/utils'

/**
 * What a piece of work is: when it is due, what it is worth, and how it is
 * handed in.
 *
 * The strip Canvas puts under an assignment title, and the most recognisable
 * thing on that page. It is three labelled facts rather than a sentence,
 * because they are read separately -- somebody checking a deadline is not
 * reading about the submission type on the way past.
 *
 * Shared by the assignment inside the player and the coursework list, so the
 * two cannot end up describing the same assignment differently.
 */

/** How the college says a submission type, rather than how the field spells
 *  it. "Text Entry" is a Select option; "a text box" is what it is. */
const HOW: Record<string, string> = {
	'Text Entry': 'a text box',
	'File Upload': 'a file',
	URL: 'a link',
	Quiz: 'a quiz',
	'On Paper': 'on paper',
	'No Submission': 'nothing to hand in',
}

/** How work goes in, in the college's words rather than the field's. Exported
 *  because the assignment page says it in a sentence as well as in the strip. */
export function submittingAs(type: string) {
	return HOW[type] ?? type
}

function when(date: string | null) {
	// The stored value is `YYYY-MM-DD HH:MM:SS`; the seconds are noise on a
	// deadline and the T is an artefact of the wire format.
	return date ? date.slice(0, 16).replace('T', ' ') : 'No due date'
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
	return (
		<div className="min-w-0">
			<dt className="text-muted-foreground text-[11px] font-medium tracking-wide uppercase">
				{label}
			</dt>
			<dd className="mt-0.5 truncate text-sm">{children}</dd>
		</div>
	)
}

export function AssignmentMeta({
	points,
	dueDate,
	submissionType,
	className,
}: {
	points: number
	dueDate: string | null
	submissionType: string
	className?: string
}) {
	return (
		<dl
			className={cn(
				// A rule above only. The sections under it carry their own, so
				// a bottom rule here would double up whenever the instructions
				// happen to be empty.
				'grid grid-cols-2 gap-x-6 gap-y-3 border-t pt-3 sm:grid-cols-3',
				className,
			)}
		>
			<Fact label="Due">{when(dueDate)}</Fact>
			<Fact label="Points">
				<span className="tabular-nums">{points}</span>
			</Fact>
			<Fact label="Submitting">{submittingAs(submissionType)}</Fact>
		</dl>
	)
}
