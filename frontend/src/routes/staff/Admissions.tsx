import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, UserRoundCheck } from 'lucide-react'

import { Face } from '@/components/Face'
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
import { usePipeline } from '@/hooks/useStaff'
import { cn, formatDate } from '@/lib/utils'
import type { PipelineResponse, PipelineRow } from '@/types'

const STATE_TONE: Record<string, 'default' | 'success' | 'muted' | 'destructive' | 'warning'> = {
	Draft: 'muted',
	'In Review': 'default',
	Admitted: 'success',
	Onboarded: 'success',
	Rejected: 'destructive',
	Withdrawn: 'muted',
}

export function Admissions() {
	const [search, setSearch] = useState('')
	const [state, setState] = useState('')
	const debounced = useDebounced(search, 300)
	const query = usePipeline({ search: debounced, state })

	return (
		<QueryState query={query} title="Admissions">
			{(data) => (
				<Loaded
					data={data}
					search={search}
					onSearch={setSearch}
					state={state}
					onState={setState}
				/>
			)}
		</QueryState>
	)
}

function Loaded({
	data,
	search,
	onSearch,
	state,
	onState,
}: {
	data: PipelineResponse
	search: string
	onSearch: (value: string) => void
	state: string
	onState: (value: string) => void
}) {
	return (
		<>
			<PageHeader
				title="Admissions"
				description={`${data.rows.length} ${data.rows.length === 1 ? 'application' : 'applications'}`}
			/>

			<div className="mb-4 flex flex-wrap items-center gap-2">
				<div className="relative min-w-56 flex-1">
					<Search className="text-muted-foreground pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2" />
					<Input
						value={search}
						onChange={(event) => onSearch(event.target.value)}
						placeholder="Name, email, phone or reference"
						className="pl-9"
						aria-label="Search applications"
					/>
				</div>
				<div className="flex flex-wrap gap-1">
					<FilterChip label="All" active={state === ''} onClick={() => onState('')} />
					{data.states.map((option) => (
						<FilterChip
							key={option}
							label={option}
							active={state === option}
							onClick={() => onState(option)}
						/>
					))}
				</div>
			</div>

			{data.rows.length === 0 ? (
				<Card>
					<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
						<UserRoundCheck className="text-muted-foreground size-6" />
						<div className="font-medium">No applications match</div>
						<p className="text-muted-foreground max-w-sm text-sm">
							{search || state
								? 'Try a different search or clear the filter.'
								: 'Applications appear here as candidates apply.'}
						</p>
					</CardContent>
				</Card>
			) : (
				<Card>
					<CardContent className="p-0">
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead className="pl-5">Candidate</TableHead>
									<TableHead>Programme</TableHead>
									<TableHead>State</TableHead>
									<TableHead className="w-40">Checklist</TableHead>
									<TableHead className="pr-5 text-right">Updated</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{data.rows.map((row) => (
									<Row key={row.name} row={row} />
								))}
							</TableBody>
						</Table>
					</CardContent>
				</Card>
			)}
		</>
	)
}

function Row({ row }: { row: PipelineRow }) {
	return (
		<TableRow>
			<TableCell className="pl-5">
				<Link
					to={`/staff/admissions/${row.name}`}
					className="hover:text-primary flex min-w-0 items-center gap-3 transition-colors"
				>
					<Face name={row.full_name} photo={row.photo} />
					<span className="min-w-0">
						<span className="block truncate font-medium">{row.full_name}</span>
						<span className="text-muted-foreground block truncate text-xs">
							{row.name}
							{row.email && <> · {row.email}</>}
						</span>
					</span>
				</Link>
			</TableCell>
			<TableCell>
				<div className="text-sm">{row.program || '—'}</div>
				{row.intake_term && (
					<div className="text-muted-foreground text-xs">{row.intake_term}</div>
				)}
			</TableCell>
			<TableCell>
				<Badge variant={STATE_TONE[row.workflow_state] ?? 'muted'}>
					{row.workflow_state}
				</Badge>
			</TableCell>
			<TableCell>
				<div className="flex items-center gap-2">
					<div className="bg-muted h-1.5 w-20 overflow-hidden rounded-full">
						<div
							className={cn(
								'h-full rounded-full',
								row.progress.percent === 100 ? 'bg-success' : 'bg-primary',
							)}
							style={{ width: `${row.progress.percent}%` }}
						/>
					</div>
					<span className="text-muted-foreground text-xs tabular-nums">
						{row.progress.done}/{row.progress.total}
					</span>
				</div>
			</TableCell>
			<TableCell className="text-muted-foreground pr-5 text-right text-xs">
				{formatDate(row.modified)}
			</TableCell>
		</TableRow>
	)
}

function FilterChip({
	label,
	active,
	onClick,
}: {
	label: string
	active: boolean
	onClick: () => void
}) {
	return (
		<Button
			variant={active ? 'default' : 'outline'}
			size="sm"
			onClick={onClick}
			className="h-8"
		>
			{label}
		</Button>
	)
}
