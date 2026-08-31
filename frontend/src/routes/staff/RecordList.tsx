import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Download, Plus, Search } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from '@/components/ui/table'
import { useDebounced } from '@/hooks/useDebounced'
import { useDescribe, useRecordList, type FieldMeta } from '@/hooks/useRecords'
import { formatDate, money } from '@/lib/utils'

export function RecordList() {
	const { doctype = '' } = useParams()
	const [search, setSearch] = useState('')
	const debounced = useDebounced(search, 300)
	const meta = useDescribe(doctype)
	const list = useRecordList(doctype, debounced)

	return (
		<QueryState query={list} title={doctype}>
			{(page) => (
				<>
					<PageHeader
						title={meta.data?.label ?? doctype}
						description={`${page.total} ${page.total === 1 ? 'record' : 'records'}`}
						actions={
							<div className="flex gap-2">
								<Button variant="outline" size="sm" onClick={() => exportCsv(page.rows, page.columns, doctype)}>
									<Download /> CSV
								</Button>
								{meta.data?.can_create && (
									<Button size="sm" asChild>
										<Link to={`/staff/data/${encodeURIComponent(doctype)}/new`}>
											<Plus /> New
										</Link>
									</Button>
								)}
							</div>
						}
					/>

					<div className="mb-4 flex items-center gap-2">
						<div className="relative flex-1">
							<Search className="text-muted-foreground pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2" />
							<Input
								value={search}
								onChange={(event) => setSearch(event.target.value)}
								placeholder={`Search ${doctype}`}
								className="pl-9"
								aria-label={`Search ${doctype}`}
							/>
						</div>
						<Button variant="outline" size="sm" asChild>
							<Link to="/staff/data">
								<ArrowLeft /> All records
							</Link>
						</Button>
					</div>

					{page.rows.length === 0 ? (
						<Card>
							<CardContent className="py-14 text-center">
								<div className="font-medium">Nothing here</div>
								<p className="text-muted-foreground mt-1 text-sm">
									{search ? 'No record matches that search.' : `No ${doctype} yet.`}
								</p>
							</CardContent>
						</Card>
					) : (
						<>
							{page.truncated && (
								<p className="text-muted-foreground mb-2 text-xs">
									Showing the first {page.rows.length} of {page.total}. Narrow the
									search to see the rest.
								</p>
							)}
							<Card>
								<CardContent className="p-0">
									<Table>
										<TableHeader>
											<TableRow>
												<TableHead className="pl-5">Name</TableHead>
												{page.columns
													.filter((c) => c.fieldname !== 'name')
													.map((column) => (
														<TableHead key={column.fieldname}>
															{column.label || column.fieldname}
														</TableHead>
													))}
												<TableHead className="pr-5 text-right">Modified</TableHead>
											</TableRow>
										</TableHeader>
										<TableBody>
											{page.rows.map((row) => (
												<TableRow key={String(row.name)}>
													<TableCell className="pl-5">
														<Link
															to={`/staff/data/${encodeURIComponent(doctype)}/${encodeURIComponent(String(row.name))}`}
															className="hover:text-primary font-medium transition-colors"
														>
															{String(row.name)}
														</Link>
													</TableCell>
													{page.columns
														.filter((c) => c.fieldname !== 'name')
														.map((column) => (
															<TableCell key={column.fieldname}>
																<Cell field={column} value={row[column.fieldname]} />
															</TableCell>
														))}
													<TableCell className="text-muted-foreground pr-5 text-right text-xs">
														{formatDate(String(row.modified ?? ''))}
													</TableCell>
												</TableRow>
											))}
										</TableBody>
									</Table>
								</CardContent>
							</Card>
						</>
					)}
				</>
			)}
		</QueryState>
	)
}

function Cell({ field, value }: { field: FieldMeta; value: unknown }) {
	if (value == null || value === '') {
		return <span className="text-muted-foreground">—</span>
	}
	if (field.fieldtype === 'Check') {
		return <Badge variant={value ? 'success' : 'muted'}>{value ? 'Yes' : 'No'}</Badge>
	}
	if (field.fieldtype === 'Currency') {
		return <span className="tabular-nums">{money(Number(value))}</span>
	}
	if (['Date', 'Datetime'].includes(field.fieldtype)) {
		return <span className="text-sm">{formatDate(String(value))}</span>
	}
	if (field.fieldtype === 'Select') {
		return <Badge variant="muted">{String(value)}</Badge>
	}
	return <span className="text-sm">{String(value)}</span>
}

/**
 * Export what is on screen.
 *
 * Deliberately the rows already fetched rather than a second, unfiltered
 * request: a CSV that quietly holds more than the table it came from is how
 * data leaves by accident.
 */
function exportCsv(
	rows: Record<string, unknown>[],
	columns: FieldMeta[],
	doctype: string,
) {
	const headers = ['name', ...columns.filter((c) => c.fieldname !== 'name').map((c) => c.fieldname)]
	const escape = (value: unknown) => {
		const text = value == null ? '' : String(value)
		return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
	}

	const csv = [
		headers.join(','),
		...rows.map((row) => headers.map((header) => escape(row[header])).join(',')),
	].join('\n')

	const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
	const url = URL.createObjectURL(blob)
	const link = document.createElement('a')
	link.href = url
	link.download = `${doctype.replace(/\s+/g, '-').toLowerCase()}.csv`
	link.click()
	URL.revokeObjectURL(url)
}
