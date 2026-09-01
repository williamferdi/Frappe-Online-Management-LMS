import { useState } from 'react'
import { BadgeIndianRupee, LoaderCircle } from 'lucide-react'
import { toast } from 'sonner'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useDecideScholarship } from '@/hooks/useFinance'
import { FrappeError } from '@/lib/frappe'
import { formatDate, money } from '@/lib/utils'
import type { ScholarshipDetail } from '@/types'

const TONE: Record<string, 'success' | 'destructive' | 'warning' | 'muted'> = {
	Approved: 'success',
	Rejected: 'destructive',
	Submitted: 'warning',
	Draft: 'muted',
}

/**
 * The scholarship, decided where the rest of the application is read.
 *
 * It was only ever in Finance, as a row and a dialog. The officer working an
 * application could see that a request existed and not what the candidate had
 * written, and the Registrar had to leave the application to answer it. The
 * decision still goes through `scholarship.decide`, which enforces the
 * programme cap -- this screen only asks.
 */
export function ScholarshipCard({
	scholarship,
	onDecided,
}: {
	scholarship: ScholarshipDetail
	onDecided: () => void
}) {
	const decide = useDecideScholarship()
	const [awarded, setAwarded] = useState('')
	const [discount, setDiscount] = useState('')
	const [remarks, setRemarks] = useState('')

	const decided = scholarship.status === 'Approved' || scholarship.status === 'Rejected'
	const overCap = Boolean(scholarship.cap && Number(awarded) > scholarship.cap)

	function submit(outcome: 'Approved' | 'Rejected') {
		decide.mutate(
			{
				request: scholarship.name,
				outcome,
				approved_amount: outcome === 'Approved' ? Number(awarded) : 0,
				monthly_discount: outcome === 'Approved' ? Number(discount) || 0 : 0,
				remarks: remarks || undefined,
			},
			{
				onSuccess: () => {
					setAwarded('')
					setDiscount('')
					setRemarks('')
					onDecided()
					toast.success(`Scholarship ${outcome.toLowerCase()}`)
				},
				onError: (error) =>
					toast.error(
						error instanceof FrappeError ? error.message : 'That decision was refused.',
					),
			},
		)
	}

	return (
		<Card>
			<CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
				<CardTitle className="text-base">Scholarship</CardTitle>
				<Badge variant={TONE[scholarship.status] ?? 'muted'}>{scholarship.status}</Badge>
			</CardHeader>

			<CardContent className="space-y-4">
				<dl className="grid gap-x-6 gap-y-3 sm:grid-cols-3">
					<Field label="Requested" value={money(scholarship.requested_amount)} />
					<Field
						label="Awarded"
						value={scholarship.approved_amount ? money(scholarship.approved_amount) : '—'}
					/>
					<Field
						label="Monthly discount"
						value={
							scholarship.monthly_discount ? money(scholarship.monthly_discount) : '—'
						}
					/>
					<Field label="Submitted" value={formatDate(scholarship.submitted_on)} />
					{decided && (
						<>
							<Field label="Decided on" value={formatDate(scholarship.approved_on)} />
							<Field label="Decided by" value={scholarship.approved_by ?? '—'} />
						</>
					)}
				</dl>

				{scholarship.justification && (
					<div>
						<div className="text-muted-foreground mb-1 text-xs font-medium uppercase tracking-wider">
							What they wrote
						</div>
						<p className="bg-muted/50 whitespace-pre-line rounded-lg px-3 py-2 text-sm">
							{scholarship.justification}
						</p>
					</div>
				)}

				{scholarship.signature && (
					<div>
						<div className="text-muted-foreground mb-1 text-xs font-medium uppercase tracking-wider">
							Signed
						</div>
						{/* A private file: the img loads on the session the reader already has. */}
						<img
							src={scholarship.signature}
							alt="Applicant signature"
							className="bg-card max-h-24 rounded-md border p-2"
						/>
					</div>
				)}

				{!decided && scholarship.may_decide && (
					<>
						{scholarship.cap ? (
							<Alert variant={overCap ? 'destructive' : 'info'}>
								<BadgeIndianRupee />
								<AlertDescription>
									The {scholarship.program} cap is {money(scholarship.cap)}
									{overCap && ' — the amount below is over it and will be refused.'}
								</AlertDescription>
							</Alert>
						) : null}

						<div className="grid gap-3 sm:grid-cols-2">
							<div>
								<Label htmlFor="sch-awarded" className="text-xs">
									Award
								</Label>
								<Input
									id="sch-awarded"
									type="number"
									min={0}
									className="h-8"
									value={awarded}
									onChange={(event) => setAwarded(event.target.value)}
								/>
							</div>
							<div>
								<Label htmlFor="sch-discount" className="text-xs">
									Monthly discount
								</Label>
								<Input
									id="sch-discount"
									type="number"
									min={0}
									className="h-8"
									value={discount}
									onChange={(event) => setDiscount(event.target.value)}
								/>
							</div>
						</div>

						<Textarea
							rows={2}
							value={remarks}
							placeholder="Remarks for the checklist step (optional)"
							onChange={(event) => setRemarks(event.target.value)}
						/>

						<div className="flex flex-wrap gap-2">
							<Button size="sm" disabled={decide.isPending} onClick={() => submit('Approved')}>
								{decide.isPending && <LoaderCircle className="animate-spin" />}
								Approve
							</Button>
							<Button
								size="sm"
								variant="outline"
								disabled={decide.isPending}
								onClick={() => submit('Rejected')}
							>
								Reject
							</Button>
						</div>
					</>
				)}

				{!decided && !scholarship.may_decide && (
					<p className="text-muted-foreground text-sm">
						The Registrar decides scholarships; your role may read this one but not answer
						it.
					</p>
				)}
			</CardContent>
		</Card>
	)
}

function Field({ label, value }: { label: string; value: string }) {
	return (
		<div>
			<dt className="text-muted-foreground text-xs font-medium uppercase tracking-wider">
				{label}
			</dt>
			<dd className="text-sm tabular-nums">{value}</dd>
		</div>
	)
}
