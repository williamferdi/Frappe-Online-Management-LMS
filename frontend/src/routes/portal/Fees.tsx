import { useState } from 'react'
import { Download, Printer, Receipt } from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useFees } from '@/hooks/useStudent'
import { frappeDownload } from '@/lib/frappe'
import { cn, formatDate, money } from '@/lib/utils'
import type { FeeInvoiceRow, FeePayment, FeesResponse } from '@/types'

const STATUS_TONE: Record<string, 'success' | 'warning' | 'muted'> = {
	Paid: 'success',
	Waived: 'muted',
	Unpaid: 'warning',
	'Partly Paid': 'warning',
}

/**
 * What a student has been billed, what they have paid, and the paper to prove
 * it.
 *
 * Until this page the portal showed only what was currently owed: pay an
 * invoice and it vanished, with no receipt and no statement anywhere. Receipts
 * and the statement are PDFs made on the server. The statement can also be
 * printed straight from the browser, which needs no renderer at all -- so a
 * student is never left without a way to get it on paper.
 */
export function Fees() {
	const query = useFees()

	return (
		<QueryState query={query} title="Fees" emptyWhen={(d) => !d.enrollment}>
			{(data) => <Loaded data={data} />}
		</QueryState>
	)
}

function Loaded({ data }: { data: FeesResponse }) {
	const { summary } = data
	const [busy, setBusy] = useState<string | null>(null)

	async function savePdf(key: string, path: string, args: Record<string, unknown>, filename: string) {
		setBusy(key)
		try {
			const blob = await frappeDownload(path, args)
			const url = URL.createObjectURL(blob)
			const link = document.createElement('a')
			link.href = url
			link.download = filename
			document.body.appendChild(link)
			link.click()
			link.remove()
			URL.revokeObjectURL(url)
		} catch (error) {
			// The PDF is made by a program on the server that may be unavailable.
			// Say so, and say what still works.
			toast.error(error instanceof Error ? error.message : 'The PDF could not be made.')
		} finally {
			setBusy(null)
		}
	}

	return (
		<>
			<PageHeader
				title="Fees"
				description={`${data.enrollment!.program_name || data.enrollment!.program} · ${data.enrollment!.student_name}`}
			/>

			<div className="grid gap-3 sm:grid-cols-4">
				<Stat label="Billed" value={money(summary.billed)} />
				<Stat label="Paid" value={money(summary.paid)} />
				<Stat label="Outstanding" value={money(summary.outstanding)} />
				<Stat
					label="Overdue"
					value={money(summary.overdue)}
					tone={summary.overdue_count > 0 ? 'bad' : undefined}
					note={
						summary.overdue_count > 0
							? `${summary.overdue_count} ${summary.overdue_count === 1 ? 'invoice' : 'invoices'}`
							: undefined
					}
				/>
			</div>

			<Tabs defaultValue="invoices" className="mt-6">
				<TabsList>
					<TabsTrigger value="invoices">Invoices</TabsTrigger>
					<TabsTrigger value="payments">Payments &amp; receipts</TabsTrigger>
					<TabsTrigger value="statement">Statement</TabsTrigger>
				</TabsList>

				<TabsContent value="invoices">
					<Invoices rows={data.invoices} />
				</TabsContent>

				<TabsContent value="payments">
					<Payments
						rows={data.payments}
						busy={busy}
						onReceipt={(payment) =>
							savePdf(
								`receipt:${payment.name}`,
								'sibbcs.api.student_fees.receipt',
								{ payment: payment.name },
								`receipt-${payment.name}.pdf`,
							)
						}
					/>
				</TabsContent>

				<TabsContent value="statement">
					<Statement
						data={data}
						busy={busy === 'statement'}
						onPdf={() =>
							savePdf(
								'statement',
								'sibbcs.api.student_fees.statement',
								{},
								`statement-${data.enrollment!.student}.pdf`,
							)
						}
					/>
				</TabsContent>
			</Tabs>
		</>
	)
}

function Stat({
	label,
	value,
	tone,
	note,
}: {
	label: string
	value: string
	tone?: 'bad'
	note?: string
}) {
	return (
		<Card>
			<CardContent className="p-4">
				<div className="text-muted-foreground text-xs">{label}</div>
				<div
					className={cn(
						'mt-1 text-xl font-semibold tabular-nums',
						tone === 'bad' && 'text-destructive',
					)}
				>
					{value}
				</div>
				{note && <div className="text-muted-foreground mt-0.5 text-xs">{note}</div>}
			</CardContent>
		</Card>
	)
}

function Empty({ title, detail }: { title: string; detail: string }) {
	return (
		<Card className="mt-4">
			<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
				<Receipt className="text-muted-foreground size-6" />
				<div className="font-medium">{title}</div>
				<p className="text-muted-foreground max-w-sm text-sm">{detail}</p>
			</CardContent>
		</Card>
	)
}

function Invoices({ rows }: { rows: FeeInvoiceRow[] }) {
	if (rows.length === 0) {
		return (
			<Empty
				title="Nothing has been billed yet"
				detail="Invoices appear here as the college raises them, and stay here once they are paid."
			/>
		)
	}

	return (
		<Card className="mt-4">
			<CardContent className="p-0">
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead className="pl-5">Invoice</TableHead>
							<TableHead>For</TableHead>
							<TableHead>Due</TableHead>
							<TableHead className="text-right">Amount</TableHead>
							<TableHead className="text-right">Paid</TableHead>
							<TableHead className="text-right">Outstanding</TableHead>
							<TableHead className="pr-5">Status</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{rows.map((row) => (
							<TableRow key={row.name}>
								<TableCell className="pl-5 font-mono text-xs">{row.name}</TableCell>
								<TableCell className="text-sm">
									{row.fee_type || row.category}
									{row.term && (
										<div className="text-muted-foreground text-xs">{row.term}</div>
									)}
									{row.discount_amount > 0 && (
										<div className="text-muted-foreground text-xs">
											Scholarship −{money(row.discount_amount)}
										</div>
									)}
								</TableCell>
								<TableCell className="text-sm">
									{row.due_date ? formatDate(row.due_date) : '—'}
								</TableCell>
								<TableCell className="text-right tabular-nums">
									{money(row.net_amount)}
								</TableCell>
								<TableCell className="text-right tabular-nums">
									{money(row.paid_amount)}
								</TableCell>
								<TableCell className="text-right tabular-nums">
									{money(row.outstanding_amount)}
								</TableCell>
								<TableCell className="pr-5">
									<div className="flex flex-wrap items-center gap-1.5">
										<Badge variant={STATUS_TONE[row.status] ?? 'muted'}>{row.status}</Badge>
										{row.overdue && <Badge variant="destructive">Overdue</Badge>}
										{row.payment_link && row.outstanding_amount > 0 && (
											<Button size="sm" asChild>
												<a href={row.payment_link}>Pay</a>
											</Button>
										)}
									</div>
								</TableCell>
							</TableRow>
						))}
					</TableBody>
				</Table>
			</CardContent>
		</Card>
	)
}

function Payments({
	rows,
	busy,
	onReceipt,
}: {
	rows: FeePayment[]
	busy: string | null
	onReceipt: (payment: FeePayment) => void
}) {
	if (rows.length === 0) {
		return (
			<Empty
				title="No payments recorded yet"
				detail="Once the college has recorded a payment from you, it appears here with a receipt you can download."
			/>
		)
	}

	return (
		<Card className="mt-4">
			<CardContent className="p-0">
				<ul className="divide-y">
					{rows.map((payment) => (
						<li
							key={payment.name}
							className="flex flex-wrap items-start justify-between gap-3 px-5 py-4"
						>
							<div className="min-w-0">
								<div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
									<span className="font-semibold tabular-nums">{money(payment.amount)}</span>
									<span className="text-muted-foreground text-sm">
										{formatDate(payment.received_on)} · {payment.mode}
										{payment.reference_no ? ` · ${payment.reference_no}` : ''}
									</span>
								</div>
								<div className="text-muted-foreground mt-0.5 font-mono text-xs">
									{payment.name}
								</div>
								{payment.applied_to.length > 0 && (
									<ul className="text-muted-foreground mt-2 space-y-0.5 text-sm">
										{payment.applied_to.map((row) => (
											<li key={row.invoice}>
												{money(row.amount)} towards {row.fee_type || row.invoice}
												{row.term ? ` · ${row.term}` : ''}
											</li>
										))}
									</ul>
								)}
								{payment.unallocated_amount > 0.005 && (
									<p className="text-muted-foreground mt-1 text-sm">
										{money(payment.unallocated_amount)} held as credit against future fees.
									</p>
								)}
							</div>
							<Button
								size="sm"
								variant="outline"
								disabled={busy === `receipt:${payment.name}`}
								onClick={() => onReceipt(payment)}
								aria-label={`Download receipt for ${money(payment.amount)} paid ${formatDate(payment.received_on)}`}
							>
								<Download /> Receipt
							</Button>
						</li>
					))}
				</ul>
			</CardContent>
		</Card>
	)
}

function Statement({
	data,
	busy,
	onPdf,
}: {
	data: FeesResponse
	busy: boolean
	onPdf: () => void
}) {
	const { statement } = data

	if (statement.rows.length === 0) {
		return (
			<Empty
				title="Nothing to show yet"
				detail="Your statement lists every charge and payment once the college has billed you."
			/>
		)
	}

	const standing =
		statement.balance > 0.005 ? 'Outstanding' : statement.balance < -0.005 ? 'In credit' : 'Settled'

	return (
		<>
			<div className="print-hide mt-4 flex flex-wrap justify-end gap-2">
				<Button size="sm" variant="outline" onClick={() => window.print()}>
					<Printer /> Print
				</Button>
				<Button size="sm" variant="outline" disabled={busy} onClick={onPdf}>
					<Download /> Download PDF
				</Button>
			</div>

			<Card className="print-area mt-3">
				<CardContent className="p-0">
					<div className="border-b px-5 py-4">
						<div className="text-muted-foreground text-xs tracking-wide uppercase">
							South India Baptist Bible College &amp; Seminary
						</div>
						<div className="mt-1 text-lg font-semibold">Statement of account</div>
						<div className="text-muted-foreground text-sm">
							{data.enrollment!.student_name} · {data.enrollment!.student}
						</div>
					</div>

					<Table>
						<TableHeader>
							<TableRow>
								<TableHead className="pl-5">Date</TableHead>
								<TableHead>Particulars</TableHead>
								<TableHead className="text-right">Charge</TableHead>
								<TableHead className="text-right">Paid</TableHead>
								<TableHead className="pr-5 text-right">Balance</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{statement.rows.map((row, index) => (
								<TableRow key={`${row.reference}:${row.kind}:${index}`}>
									<TableCell className="pl-5 text-sm whitespace-nowrap">
										{row.date ? formatDate(row.date) : '—'}
									</TableCell>
									<TableCell className="text-sm">
										{row.particulars}
										<div className="text-muted-foreground font-mono text-xs">{row.reference}</div>
									</TableCell>
									<TableCell className="text-right tabular-nums">
										{row.charge ? money(row.charge) : ''}
									</TableCell>
									<TableCell className="text-right tabular-nums">
										{row.credit ? money(row.credit) : ''}
									</TableCell>
									<TableCell className="pr-5 text-right tabular-nums">
										{money(row.balance)}
									</TableCell>
								</TableRow>
							))}
						</TableBody>
					</Table>

					<div className="flex flex-wrap items-center justify-between gap-3 border-t px-5 py-4 text-sm">
						<span className="text-muted-foreground">
							Charged {money(statement.charges)} · Paid or waived {money(statement.credits)}
						</span>
						<span className="font-semibold">
							{money(Math.abs(statement.balance))}{' '}
							<Badge variant={standing === 'Outstanding' ? 'warning' : 'success'}>
								{standing}
							</Badge>
						</span>
					</div>
				</CardContent>
			</Card>
		</>
	)
}
