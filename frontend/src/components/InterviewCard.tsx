import { useState } from 'react'
import { LoaderCircle, Save } from 'lucide-react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useRecordInterview } from '@/hooks/useStaff'
import { FrappeError } from '@/lib/frappe'
import { formatDate } from '@/lib/utils'
import type { InterviewRecord } from '@/types'

const VERDICT: Record<string, 'success' | 'destructive' | 'warning'> = {
	Recommend: 'success',
	Reject: 'destructive',
	Defer: 'warning',
}

/**
 * What the panel decided, written down where it is read.
 *
 * The record existed as a DocType and nothing in the console could create one,
 * so an interview that had actually happened left its step at Awaiting and its
 * outcome nowhere. Saving here moves the step -- `InterviewRecord.on_update`
 * does that, not this screen.
 */
export function InterviewCard({
	application,
	interview,
	outcomes,
	canWrite,
}: {
	application: string
	interview: InterviewRecord | null
	outcomes: string[]
	canWrite: boolean
}) {
	const record = useRecordInterview(application)
	const [outcome, setOutcome] = useState<string | null>(null)
	const [scheduled, setScheduled] = useState<string | null>(null)
	const [notes, setNotes] = useState<string | null>(null)

	const currentOutcome = outcome ?? interview?.outcome ?? ''
	const currentScheduled = scheduled ?? (interview?.scheduled_on ?? '').slice(0, 16)
	const currentNotes = notes ?? interview?.notes ?? ''
	const changed = outcome !== null || scheduled !== null || notes !== null

	function save() {
		record.mutate(
			{
				outcome: currentOutcome,
				scheduled_on: currentScheduled || '',
				notes: currentNotes,
			},
			{
				onSuccess: () => {
					setOutcome(null)
					setScheduled(null)
					setNotes(null)
					toast.success('Interview recorded')
				},
				onError: (error) =>
					toast.error(
						error instanceof FrappeError ? error.message : 'That was not recorded.',
					),
			},
		)
	}

	return (
		<Card>
			<CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
				<CardTitle className="text-base">Zoom interview</CardTitle>
				{interview?.outcome && (
					<Badge variant={VERDICT[interview.outcome] ?? 'muted'}>{interview.outcome}</Badge>
				)}
			</CardHeader>

			<CardContent className="space-y-3">
				{!interview && (
					<p className="text-muted-foreground text-sm">
						Nothing recorded yet. The booking link goes out from the checklist step above;
						what the panel decided is written here.
					</p>
				)}

				<div className="grid gap-3 sm:grid-cols-2">
					<div>
						<Label htmlFor="interview-when" className="text-xs">
							Held on
						</Label>
						<Input
							id="interview-when"
							type="datetime-local"
							className="h-8"
							disabled={!canWrite}
							value={currentScheduled}
							onChange={(event) => setScheduled(event.target.value)}
						/>
					</div>
					<div>
						<Label htmlFor="interview-outcome" className="text-xs">
							Outcome
						</Label>
						<select
							id="interview-outcome"
							className="border-input bg-background h-8 w-full rounded-md border px-2 text-sm"
							disabled={!canWrite}
							value={currentOutcome}
							onChange={(event) => setOutcome(event.target.value)}
						>
							<option value="">Not decided</option>
							{outcomes.map((option) => (
								<option key={option} value={option}>
									{option}
								</option>
							))}
						</select>
					</div>
				</div>

				<div>
					<Label htmlFor="interview-notes" className="text-xs">
						Panel notes
					</Label>
					<Textarea
						id="interview-notes"
						rows={3}
						disabled={!canWrite}
						value={currentNotes}
						placeholder="What the panel heard, and why they decided as they did"
						onChange={(event) => setNotes(event.target.value)}
					/>
				</div>

				{canWrite && (
					<div className="flex items-center gap-3">
						<Button size="sm" disabled={!changed || record.isPending} onClick={save}>
							{record.isPending ? <LoaderCircle className="animate-spin" /> : <Save />}
							Save interview
						</Button>
						<span className="text-muted-foreground text-xs">
							{interview
								? `Last updated ${formatDate(interview.modified ?? null)}`
								: 'Recording an outcome moves the checklist step.'}
						</span>
					</div>
				)}
			</CardContent>
		</Card>
	)
}
