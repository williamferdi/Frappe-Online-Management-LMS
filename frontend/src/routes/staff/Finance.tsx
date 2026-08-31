import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
	BadgeIndianRupee,
	HandCoins,
	LoaderCircle,
	Plus,
	Receipt,
	Search,
	TriangleAlert,
} from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { useDebounced } from '@/hooks/useDebounced'
import {
	useDecideScholarship,
	useInvoices,
	useOutstandingFor,
	usePayments,
	useRecordPayment,
	useScholarships,
} from '@/hooks/useFinance'
import { FrappeError } from '@/lib/frappe'
import { cn, formatDate, money } from '@/lib/utils'
import type { FinanceSummary, InvoiceRow, ScholarshipRow } from '@/types'

type Tab = 'invoices' | 'payments' | 'scholarships'

const TABS: { id: Tab; label: string; icon: typeof Receipt }[] = [
	{ id: 'invoices', label: 'Invoices', icon: Receipt },
	{ id: 'payments', label: 'Payments', icon: HandCoins },
	{ id: 'scholarships', label: 'Scholarships', icon: BadgeIndianRupee },
]

const STATUS_TONE: Record<string, 'success' | 'warning' | 'muted' | 'destructive'> = {
	Paid: 'success',
	Waived: 'success',
	Unpaid: 'warning',
	'Partly Paid': 'warning',
	Cancelled: 'muted',
}

export function Finance() {
	const [params, setParams] = useSearchParams()
	const tab = (params.get('tab') as Tab) || 'invoices'

	return (
		<>
			<PageHeader title="Finance" description="Invoices, payments and scholarships" />

			<div className="mb-4 flex flex-wrap gap-1">
				{TABS.map((entry) => (
					<Button
						key={entry.id}
						size="sm"
						variant={tab === entry.id ? 'default' : 'outline'}
						onClick={() => setParams(entry.id === 'invoices' ? {} : { tab: entry.id })}
					>
						<entry.icon /> {entry.label}
					</Button>
				))}
			</div>

			{tab === 'invoices' && <Invoices />}
			{tab === 'payments' && <Payments />}
			{tab === 'scholarships' && <Scholarships />}
		</>
	)
}

function Invoices() {
	const [search, setSearch] = useState('')
	const [status, setStatus] = useState('')
	const [overdue, setOverdue] = useState(false)
	const debounced = useDebounced(search, 300)
	const query = useInvoices({ search: debounced, status, overdue })

	return (
		<QueryState query={query} title="Invoices">
			{(data) => (
				<>
					<Summary summary={data.summary} />

					<div className="my-4 flex flex-wrap items-center gap-2">
						<div className="relative min-w-56 flex-1">
							<Search className="text-muted-foreground pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2" />
							<Input
								value={search}
								onChange={(event) => setSearch(event.target.value)}
								placeholder="Invoice or student"
								className="pl-9"
								aria-label="Search invoices"
							/>
						</div>
						<Chip label="All" active={!status && !overdue} onClick={() => { setStatus(''); setOverdue(false) }} />
						{data.statuses.map((option) => (
							<Chip
								key={option}
								label={option}
								active={status === option && !overdue}
								onClick={() => { setStatus(option); setOverdue(false) }}
							/>
						))}
						<Chip
							label="Overdue"
							active={overdue}
							onClick={() => { setOverdue(true); setStatus('') }}
						/>
					</div>

					{data.rows.length === 0 ? (
						<Empty icon={Receipt} title="No invoices match" />
					) : (
						<Card>
							<CardContent className="p-0">
								<Table>
									<TableHeader>
										<TableRow>
											<TableHead className="pl-5">Invoice</TableHead>
											<TableHead>Student</TableHead>
											<TableHead>Type</TableHead>
											<TableHead>Due</TableHead>
											<TableHead className="text-right">Net</TableHead>
											<TableHead className="text-right">Outstanding</TableHead>
											<TableHead className="pr-5">Status</TableHead>
										</TableRow>
									</TableHeader>
									<TableBody>
										{data.rows.map((row) => (
											<InvoiceLine key={row.name} row={row} />
										))}
									</TableBody>
								</Table>
							</CardContent>
						</Card>
					)}
				</>
			)}
		</QueryState>
	)
}

function InvoiceLine({ row }: { row: InvoiceRow }) {
	return (
		<TableRow>
			<TableCell className="pl-5 font-mono text-xs">{row.name}</TableCell>
			<TableCell className="text-sm">{row.student_name || row.student || '—'}</TableCell>
			<TableCell className="text-sm">
				{row.fee_type || row.category || '—'}
				{row.term && <div className="text-muted-foreground text-xs">{row.term}</div>}
			</TableCell>
			<TableCell className={cn('text-xs', row.overdue && 'text-destructive font-medium')}>
				{formatDate(row.due_date)}
				{row.overdue && ' · overdue'}
			</TableCell>
			<TableCell className="text-right tabular-nums">{money(row.net_amount)}</TableCell>
			<TableCell className="text-right tabular-nums">
				{row.outstanding_amount > 0 ? money(row.outstanding_amount) : '—'}
			</TableCell>
			<TableCell className="pr-5">
				<Badge variant={STATUS_TONE[row.status] ?? 'muted'}>{row.status}</Badge>
			</TableCell>
		</TableRow>
	)
}

function Summary({ summary }: { summary: FinanceSummary }) {
	const collected = summary.billed > 0 ? (summary.collected / summary.billed) * 100 : 0

	return (
		<Card>
			<CardContent className="p-5">
				<div className="grid gap-4 sm:grid-cols-3">
					<Figure label="Billed" value={money(summary.billed)} />
					<Figure label="Collected" value={money(summary.collected)} />
					<Figure label="Outstanding" value={money(summary.outstanding)} />
				</div>
				<div className="mt-4">
					<div className="text-muted-foreground mb-1.5 flex justify-between text-xs">
						<span>Collection</span>
						<span className="tabular-nums">{Math.round(collected)}%</span>
					</div>
					<Progress value={collected} />
				</div>
				{summary.overdue_count > 0 && (
					<div className="bg-destructive/8 text-destructive mt-4 flex items-center gap-2 rounded-lg px-3 py-2 text-sm">
						<TriangleAlert className="size-4 shrink-0" />
						<span>
							<span className="font-semibold">{money(summary.overdue)}</span> overdue
							across {summary.overdue_count}{' '}
							{summary.overdue_count === 1 ? 'invoice' : 'invoices'}
						</span>
					</div>
				)}
			</CardContent>
		</Card>
	)
}

function Payments() {
	const [search, setSearch] = useState('')
	const [recording, setRecording] = useState(false)
	const debounced = useDebounced(search, 300)
	const query = usePayments(debounced)

	return (
		<QueryState query={query} title="Payments">
			{(data) => (
				<>
					<div className="mb-4 flex flex-wrap items-center gap-2">
						<div className="relative min-w-56 flex-1">
							<Search className="text-muted-foreground pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2" />
							<Input
								value={search}
								onChange={(event) => setSearch(event.target.value)}
								placeholder="Student or reference"
								className="pl-9"
								aria-label="Search payments"
							/>
						</div>
						<Button size="sm" onClick={() => setRecording(true)}>
							<Plus /> Record payment
						</Button>
					</div>

					{data.rows.length === 0 ? (
						<Empty icon={HandCoins} title="No payments in this period" />
					) : (
						<Card>
							<CardContent className="p-0">
								<Table>
									<TableHeader>
										<TableRow>
											<TableHead className="pl-5">Received</TableHead>
											<TableHead>Student</TableHead>
											<TableHead>Mode</TableHead>
											<TableHead>Reference</TableHead>
											<TableHead className="text-right">Amount</TableHead>
											<TableHead className="pr-5 text-right">Unallocated</TableHead>
										</TableRow>
									</TableHeader>
									<TableBody>
										{data.rows.map((row) => (
											<TableRow key={row.name}>
												<TableCell className="pl-5 text-sm">
													{formatDate(row.received_on)}
													<div className="text-muted-foreground font-mono text-xs">
														{row.name}
													</div>
												</TableCell>
												<TableCell className="text-sm">
													{row.student_name || row.student}
												</TableCell>
												<TableCell>
													<Badge variant="muted">{row.mode}</Badge>
												</TableCell>
												<TableCell className="text-muted-foreground text-xs">
													{row.reference_no || '—'}
												</TableCell>
												<TableCell className="text-right tabular-nums">
													{money(row.amount)}
												</TableCell>
												<TableCell className="pr-5 text-right tabular-nums">
													{row.unallocated_amount > 0 ? (
														<Badge variant="warning">{money(row.unallocated_amount)}</Badge>
													) : (
														<span className="text-muted-foreground">—</span>
													)}
												</TableCell>
											</TableRow>
										))}
									</TableBody>
								</Table>
							</CardContent>
						</Card>
					)}

					<RecordPaymentDialog
						open={recording}
						modes={data.modes}
						onClose={() => setRecording(false)}
					/>
				</>
			)}
		</QueryState>
	)
}

function RecordPaymentDialog({
	open,
	modes,
	onClose,
}: {
	open: boolean
	modes: string[]
	onClose: () => void
}) {
	const record = useRecordPayment()
	const [student, setStudent] = useState('')
	const [amount, setAmount] = useState('')
	const [mode, setMode] = useState(modes[0] ?? 'UPI')
	const [reference, setReference] = useState('')
	const owing = useOutstandingFor(student.trim() || null)

	const owed = (owing.data ?? []).reduce((sum, row) => sum + row.outstanding_amount, 0)

	function onSubmit(event: FormEvent) {
		event.preventDefault()
		record.mutate(
			{
				student: student.trim(),
				amount: Number(amount),
				mode,
				reference_no: reference || undefined,
			},
			{
				onSuccess: (result) => {
					const settled = (result as { settled?: unknown[] })?.settled?.length ?? 0
					toast.success('Payment recorded', {
						description: `Applied to ${settled} ${settled === 1 ? 'invoice' : 'invoices'}.`,
					})
					setStudent('')
					setAmount('')
					setReference('')
					onClose()
				},
				onError: (error) =>
					toast.error(
						error instanceof FrappeError ? error.message : 'That payment was not recorded.',
					),
			},
		)
	}

	return (
		<Dialog open={open} onOpenChange={(next) => !next && onClose()}>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>Record a payment</DialogTitle>
					<DialogDescription>
						With no allocation given, it settles the oldest invoices first.
					</DialogDescription>
				</DialogHeader>

				<form onSubmit={onSubmit} className="space-y-4" noValidate>
					<div className="space-y-2">
						<Label htmlFor="pay-student">Student ID</Label>
						<Input
							id="pay-student"
							value={student}
							onChange={(event) => setStudent(event.target.value)}
							placeholder="SIB-2026-0001"
							autoFocus
						/>
						{owing.data && (
							<p className="text-muted-foreground text-xs">
								{owing.data.length === 0
									? 'Nothing outstanding for this student.'
									: `${owing.data.length} outstanding, ${money(owed)} owed.`}
							</p>
						)}
					</div>

					<div className="grid gap-4 sm:grid-cols-2">
						<div className="space-y-2">
							<Label htmlFor="pay-amount">Amount</Label>
							<Input
								id="pay-amount"
								type="number"
								inputMode="decimal"
								value={amount}
								onChange={(event) => setAmount(event.target.value)}
							/>
						</div>
						<div className="space-y-2">
							<Label htmlFor="pay-mode">Mode</Label>
							<select
								id="pay-mode"
								value={mode}
								onChange={(event) => setMode(event.target.value)}
								className="border-input bg-card h-9 w-full rounded-md border px-2 text-sm"
							>
								{modes.map((option) => (
									<option key={option} value={option}>
										{option}
									</option>
								))}
							</select>
						</div>
					</div>

					<div className="space-y-2">
						<Label htmlFor="pay-reference">Reference</Label>
						<Input
							id="pay-reference"
							value={reference}
							onChange={(event) => setReference(event.target.value)}
							placeholder="UPI or bank reference"
						/>
					</div>

					<DialogFooter>
						<Button type="button" variant="outline" onClick={onClose}>
							Cancel
						</Button>
						<Button
							type="submit"
							disabled={!student.trim() || !Number(amount) || record.isPending}
						>
							{record.isPending && <LoaderCircle className="animate-spin" />}
							Record
						</Button>
					</DialogFooter>
				</form>
			</DialogContent>
		</Dialog>
	)
}

function Scholarships() {
	const query = useScholarships()
	const [deciding, setDeciding] = useState<ScholarshipRow | null>(null)

	return (
		<QueryState query={query} title="Scholarships">
			{(data) => (
				<>
					{data.rows.length === 0 ? (
						<Empty
							icon={BadgeIndianRupee}
							title="No scholarship requests"
							detail="Requests appear here once a candidate submits the form sent after their interview."
						/>
					) : (
						<Card>
							<CardContent className="p-0">
								<Table>
									<TableHeader>
										<TableRow>
											<TableHead className="pl-5">Request</TableHead>
											<TableHead>Programme</TableHead>
											<TableHead className="text-right">Requested</TableHead>
											<TableHead className="text-right">Awarded</TableHead>
											<TableHead>Status</TableHead>
											<TableHead className="pr-5 text-right">Decision</TableHead>
										</TableRow>
									</TableHeader>
									<TableBody>
										{data.rows.map((row) => (
											<TableRow key={row.name}>
												<TableCell className="pl-5">
													<div className="font-mono text-xs">{row.name}</div>
													<div className="text-muted-foreground text-xs">
														{row.application || row.student}
													</div>
												</TableCell>
												<TableCell className="text-sm">
													{row.program}
													{data.caps[row.program ?? ''] ? (
														<div className="text-muted-foreground text-xs">
															cap {money(data.caps[row.program!])}
														</div>
													) : null}
												</TableCell>
												<TableCell className="text-right tabular-nums">
													{money(row.requested_amount)}
												</TableCell>
												<TableCell className="text-right tabular-nums">
													{row.approved_amount ? money(row.approved_amount) : '—'}
												</TableCell>
												<TableCell>
													<Badge
														variant={
															row.status === 'Approved'
																? 'success'
																: row.status === 'Rejected'
																	? 'destructive'
																	: 'warning'
														}
													>
														{row.status}
													</Badge>
												</TableCell>
												<TableCell className="pr-5 text-right">
													{row.status === 'Approved' || row.status === 'Rejected' ? (
														<span className="text-muted-foreground text-xs">
															{formatDate(row.approved_on)}
														</span>
													) : (
														<Button
															size="sm"
															disabled={!data.may_decide}
															onClick={() => setDeciding(row)}
														>
															Decide
														</Button>
													)}
												</TableCell>
											</TableRow>
										))}
									</TableBody>
								</Table>
							</CardContent>
						</Card>
					)}

					<DecideDialog
						row={deciding}
						cap={deciding ? data.caps[deciding.program ?? ''] : undefined}
						onClose={() => setDeciding(null)}
					/>
				</>
			)}
		</QueryState>
	)
}

function DecideDialog({
	row,
	cap,
	onClose,
}: {
	row: ScholarshipRow | null
	cap?: number
	onClose: () => void
}) {
	const decide = useDecideScholarship()
	const [awarded, setAwarded] = useState('')
	const [discount, setDiscount] = useState('')
	const [remarks, setRemarks] = useState('')

	const overCap = Boolean(cap && Number(awarded) > cap)

	function submit(outcome: 'Approved' | 'Rejected') {
		if (!row) return
		decide.mutate(
			{
				request: row.name,
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
					onClose()
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
		<Dialog open={Boolean(row)} onOpenChange={(open) => !open && onClose()}>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>Scholarship for {row?.application || row?.student}</DialogTitle>
					<DialogDescription>
						{row?.program} · requested {money(row?.requested_amount ?? 0)}
					</DialogDescription>
				</DialogHeader>

				{row?.justification && (
					<div className="bg-muted/60 rounded-lg px-3 py-2 text-sm">{row.justification}</div>
				)}

				{cap ? (
					<Alert variant={overCap ? 'destructive' : 'info'}>
						<BadgeIndianRupee />
						<AlertDescription>
							The {row?.program} cap is {money(cap)}
							{overCap && ' — the amount above is over it and will be refused.'}
						</AlertDescription>
					</Alert>
				) : null}

				<div className="grid gap-4 sm:grid-cols-2">
					<div className="space-y-2">
						<Label htmlFor="award">Amount awarded</Label>
						<Input
							id="award"
							type="number"
							inputMode="decimal"
							value={awarded}
							onChange={(event) => setAwarded(event.target.value)}
						/>
					</div>
					<div className="space-y-2">
						<Label htmlFor="discount">Monthly discount</Label>
						<Input
							id="discount"
							type="number"
							inputMode="decimal"
							value={discount}
							onChange={(event) => setDiscount(event.target.value)}
						/>
					</div>
				</div>

				<Textarea
					value={remarks}
					onChange={(event) => setRemarks(event.target.value)}
					placeholder="Remarks (optional)"
				/>

				<DialogFooter>
					<Button
						variant="outline"
						onClick={() => submit('Rejected')}
						disabled={decide.isPending}
					>
						Reject
					</Button>
					<Button
						onClick={() => submit('Approved')}
						disabled={!Number(awarded) || overCap || decide.isPending}
					>
						{decide.isPending && <LoaderCircle className="animate-spin" />}
						Approve
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	)
}

function Figure({ label, value }: { label: string; value: string }) {
	return (
		<div>
			<div className="text-muted-foreground text-xs font-medium uppercase tracking-wider">
				{label}
			</div>
			<div className="mt-0.5 text-2xl font-semibold tabular-nums">{value}</div>
		</div>
	)
}

function Chip({
	label,
	active,
	onClick,
}: {
	label: string
	active: boolean
	onClick: () => void
}) {
	return (
		<Button size="sm" variant={active ? 'default' : 'outline'} className="h-8" onClick={onClick}>
			{label}
		</Button>
	)
}

function Empty({
	icon: Icon,
	title,
	detail,
}: {
	icon: typeof Receipt
	title: string
	detail?: string
}) {
	return (
		<Card>
			<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
				<Icon className="text-muted-foreground size-6" />
				<div className="font-medium">{title}</div>
				{detail && <p className="text-muted-foreground max-w-sm text-sm">{detail}</p>}
			</CardContent>
		</Card>
	)
}
