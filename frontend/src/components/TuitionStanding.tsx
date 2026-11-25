import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { money } from '@/lib/utils'
import type { TuitionPosition } from '@/types'

/**
 * How much of a programme's tuition a student has been billed, and how much of
 * their scholarship is spent.
 *
 * The nightly job stops billing a student the moment the ceiling is reached,
 * and until this existed it said so only in a log. An officer found out when a
 * student asked why no invoice had come. The state is decided on the server by
 * the same rule the job uses, so this only reports it.
 */
export function TuitionStanding({ position }: { position: TuitionPosition }) {
	const reached = position.state === 'ceiling_reached'
	const percent = position.ceiling > 0 ? Math.min((position.billed / position.ceiling) * 100, 100) : 0

	return (
		<div className="space-y-3 text-sm" data-testid="tuition-standing">
			<div className="flex items-center justify-between gap-2">
				<span className="font-medium">Tuition billed</span>
				{reached && <Badge variant="warning">Ceiling reached</Badge>}
			</div>

			{position.state === 'uncapped' ? (
				<p className="text-muted-foreground">
					{money(position.billed)} billed over {termsLabel(position.terms_billed)}. This
					programme has no tuition ceiling.
				</p>
			) : (
				<div>
					<div className="text-muted-foreground mb-1.5 flex justify-between text-xs">
						<span className="tabular-nums">
							{money(position.billed)} of {money(position.ceiling)}
						</span>
						<span>{termsLabel(position.terms_billed)}</span>
					</div>
					<Progress value={percent} />
					<p className="text-muted-foreground mt-1.5 text-xs">{ceilingNote(position)}</p>
				</div>
			)}

			{position.scholarship && <ScholarshipLine scholarship={position.scholarship} />}
		</div>
	)
}

export function ScholarshipLine({
	scholarship,
}: {
	scholarship: NonNullable<TuitionPosition['scholarship']>
}) {
	const spent = scholarship.cap > 0 && scholarship.remaining <= 0

	return (
		<div className="flex items-center justify-between gap-2">
			<span className="text-muted-foreground">
				Scholarship {money(scholarship.used)} of {money(scholarship.cap)} used
			</span>
			{spent && <Badge variant="muted">Fully used</Badge>}
		</div>
	)
}

export function termsLabel(count: number): string {
	return count === 1 ? '1 term billed' : `${count} terms billed`
}

/** What the ceiling means for the next invoice, in a sentence. */
export function ceilingNote(position: TuitionPosition): string {
	if (position.state === 'ceiling_reached') {
		const left = position.remaining ?? 0
		return left > 0
			? `No further tuition will be invoiced. ${money(left)} is left, which is less than one month.`
			: 'No further tuition will be invoiced.'
	}
	return `${money(position.remaining ?? 0)} still to bill.`
}
