import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, Download } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from '@/components/ui/table'
import { frappeGet } from '@/lib/frappe'
import { cn, money } from '@/lib/utils'

interface FieldChoice {
	fieldname: string
	label: string
	fieldtype: string
}

interface ReportRow {
	label: string
	count: number
	total?: number
}

interface ReportResult {
	doctype: string
	group_by: string
	aggregate: string | null
	rows: ReportRow[]
	count: number
	total: number | null
}

export function Reports() {
	const catalogue = useQuery({
		queryKey: ['reports', 'catalogue'],
		queryFn: () => frappeGet<string[]>('sibbcs.api.reports.catalogue'),
	})

	const [doctype, setDoctype] = useState('')
	const [groupBy, setGroupBy] = useState('')
	const [aggregate, setAggregate] = useState('')

	const options = useQuery({
		queryKey: ['reports', 'options', doctype],
		queryFn: () =>
			frappeGet<{ group_by: FieldChoice[]; aggregate: FieldChoice[] }>(
				'sibbcs.api.reports.options',
				{ doctype },
			),
		enabled: Boolean(doctype),
	})

	const result = useQuery({
		queryKey: ['reports', 'run', doctype, groupBy, aggregate],
		queryFn: () =>
			frappeGet<ReportResult>('sibbcs.api.reports.run', {
				doctype,
				group_by: groupBy,
				aggregate: aggregate || undefined,
			}),
		enabled: Boolean(doctype && groupBy),
	})

	return (
		<QueryState query={catalogue} title="Reports">
			{(doctypes) => (
				<>
					<PageHeader
						title="Reports"
						description="Group any record and count or total it"
						actions={
							result.data ? (
								<Button
									variant="outline"
									size="sm"
									onClick={() => exportCsv(result.data)}
								>
									<Download /> CSV
								</Button>
							) : undefined
						}
					/>

					<Card className="mb-4">
						<CardContent className="grid gap-4 p-5 sm:grid-cols-3">
							<Picker
								label="Records"
								value={doctype}
								placeholder="Choose"
								choices={doctypes.map((name) => ({ value: name, label: name }))}
								onChange={(value) => {
									setDoctype(value)
									setGroupBy('')
									setAggregate('')
								}}
							/>
							<Picker
								label="Group by"
								value={groupBy}
								placeholder={doctype ? 'Choose' : 'Pick records first'}
								disabled={!doctype}
								choices={(options.data?.group_by ?? []).map((field) => ({
									value: field.fieldname,
									label: field.label,
								}))}
								onChange={setGroupBy}
							/>
							<Picker
								label="Total (optional)"
								value={aggregate}
								placeholder="Count only"
								disabled={!doctype}
								choices={(options.data?.aggregate ?? []).map((field) => ({
									value: field.fieldname,
									label: field.label,
								}))}
								onChange={setAggregate}
							/>
						</CardContent>
					</Card>

					{!groupBy ? (
						<Card>
							<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
								<BarChart3 className="text-muted-foreground size-6" />
								<div className="font-medium">Choose what to report on</div>
								<p className="text-muted-foreground max-w-sm text-sm">
									Applications by state, invoices by status with the outstanding
									totalled, offerings by term — the same report, different columns.
								</p>
							</CardContent>
						</Card>
					) : result.data ? (
						<Result data={result.data} />
					) : (
						<p className="text-muted-foreground text-sm">Working…</p>
					)}
				</>
			)}
		</QueryState>
	)
}

function Result({ data }: { data: ReportResult }) {
	const peak = Math.max(1, ...data.rows.map((row) => row.count))

	return (
		<Card>
			<CardContent className="p-0">
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead className="pl-5">{data.group_by}</TableHead>
							<TableHead className="w-40">Share</TableHead>
							<TableHead className="text-right">Count</TableHead>
							{data.aggregate && (
								<TableHead className="pr-5 text-right">{data.aggregate}</TableHead>
							)}
						</TableRow>
					</TableHeader>
					<TableBody>
						{data.rows.map((row) => (
							<TableRow key={row.label}>
								<TableCell className="pl-5 font-medium">{row.label}</TableCell>
								<TableCell>
									<div className="bg-muted h-1.5 w-32 overflow-hidden rounded-full">
										<div
											className="bg-primary h-full rounded-full"
											style={{ width: `${(row.count / peak) * 100}%` }}
										/>
									</div>
								</TableCell>
								<TableCell className="text-right tabular-nums">{row.count}</TableCell>
								{data.aggregate && (
									<TableCell className="pr-5 text-right tabular-nums">
										{money(row.total ?? 0)}
									</TableCell>
								)}
							</TableRow>
						))}
						<TableRow className="bg-muted/40">
							<TableCell className="pl-5 font-semibold">Total</TableCell>
							<TableCell />
							<TableCell className="text-right font-semibold tabular-nums">
								{data.count}
							</TableCell>
							{data.aggregate && (
								<TableCell className="pr-5 text-right font-semibold tabular-nums">
									{money(data.total ?? 0)}
								</TableCell>
							)}
						</TableRow>
					</TableBody>
				</Table>
			</CardContent>
		</Card>
	)
}

function Picker({
	label,
	value,
	placeholder,
	choices,
	onChange,
	disabled,
}: {
	label: string
	value: string
	placeholder: string
	choices: { value: string; label: string }[]
	onChange: (value: string) => void
	disabled?: boolean
}) {
	return (
		<div className="space-y-1.5">
			<Label>{label}</Label>
			<select
				value={value}
				disabled={disabled}
				onChange={(event) => onChange(event.target.value)}
				className={cn(
					'border-input bg-card h-9 w-full rounded-md border px-2 text-sm',
					disabled && 'opacity-60',
				)}
			>
				<option value="">{placeholder}</option>
				{choices.map((choice) => (
					<option key={choice.value} value={choice.value}>
						{choice.label}
					</option>
				))}
			</select>
		</div>
	)
}

function exportCsv(data: ReportResult) {
	const headers = [data.group_by, 'count', ...(data.aggregate ? [data.aggregate] : [])]
	const escape = (value: unknown) => {
		const text = value == null ? '' : String(value)
		return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
	}

	const csv = [
		headers.join(','),
		...data.rows.map((row) =>
			[row.label, row.count, ...(data.aggregate ? [row.total ?? 0] : [])]
				.map(escape)
				.join(','),
		),
	].join('\n')

	const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
	const url = URL.createObjectURL(blob)
	const link = document.createElement('a')
	link.href = url
	link.download = `${data.doctype.replace(/\s+/g, '-').toLowerCase()}-by-${data.group_by}.csv`
	link.click()
	URL.revokeObjectURL(url)
}
