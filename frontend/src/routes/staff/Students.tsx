import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, Users } from 'lucide-react'

import { Chip, Empty } from '@/components/Chip'
import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
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
import { useStudents } from '@/hooks/useAcademic'
import type { StudentsResponse } from '@/types'

/**
 * The roll.
 *
 * Its own place in the navigation rather than a tab inside Academic: looking a
 * student up is the most common thing anyone does in this console, and it is
 * not only an academic question -- the registrar wants their certificates, the
 * accountant their invoices.
 */
export function Students() {
	const [search, setSearch] = useState('')
	const [program, setProgram] = useState('')
	const [level, setLevel] = useState('')
	const debounced = useDebounced(search, 300)
	const query = useStudents({ search: debounced, program, level })

	return (
		<>
			<PageHeader
				title="Students"
				description="Every enrolled student, and the full profile behind each one"
			/>

			<QueryState query={query} title="Students">
				{(data) => (
					<>
						<Filters
							data={data}
							search={search}
							onSearch={setSearch}
							program={program}
							onProgram={setProgram}
							level={level}
							onLevel={setLevel}
						/>

						{data.rows.length === 0 ? (
							<Empty
								icon={Users}
								title="No students match"
								detail="Students appear here once an admitted candidate is onboarded."
							/>
						) : (
							<>
								{data.truncated && (
									<p className="text-muted-foreground mb-2 text-xs">
										Showing the first {data.rows.length}. Narrow the search to see the rest.
									</p>
								)}
								<Card>
									<CardContent className="p-0">
										<Table>
											<TableHeader>
												<TableRow>
													<TableHead className="pl-5">Student</TableHead>
													<TableHead>Programme</TableHead>
													<TableHead>Level</TableHead>
													<TableHead className="text-right">Credits</TableHead>
													<TableHead className="text-right">CGPA</TableHead>
													<TableHead className="pr-5">Status</TableHead>
												</TableRow>
											</TableHeader>
											<TableBody>
												{data.rows.map((row) => (
													<TableRow key={row.name}>
														<TableCell className="pl-5">
															<Link
																to={`/staff/students/${encodeURIComponent(row.name)}`}
																className="hover:text-primary block transition-colors"
															>
																<div className="font-medium">{row.full_name}</div>
																<div className="text-muted-foreground text-xs">
																	{row.name}
																	{row.email && <> · {row.email}</>}
																</div>
															</Link>
														</TableCell>
														<TableCell className="text-sm">
															{row.enrollment?.program || '—'}
														</TableCell>
														<TableCell className="text-sm">
															{row.enrollment ? `Level ${row.enrollment.current_level}` : '—'}
														</TableCell>
														<TableCell className="text-right tabular-nums">
															{row.enrollment?.credits_earned ?? '—'}
														</TableCell>
														<TableCell className="text-right tabular-nums">
															{row.enrollment?.cgpa ? row.enrollment.cgpa.toFixed(2) : '—'}
														</TableCell>
														<TableCell className="pr-5">
															<Badge variant={row.status === 'Active' ? 'success' : 'muted'}>
																{row.status}
															</Badge>
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
		</>
	)
}

function Filters({
	data,
	search,
	onSearch,
	program,
	onProgram,
	level,
	onLevel,
}: {
	data: StudentsResponse
	search: string
	onSearch: (value: string) => void
	program: string
	onProgram: (value: string) => void
	level: string
	onLevel: (value: string) => void
}) {
	return (
		<div className="mb-4 flex flex-wrap items-center gap-2">
			<div className="relative min-w-56 flex-1">
				<Search className="text-muted-foreground pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2" />
				<Input
					value={search}
					onChange={(event) => onSearch(event.target.value)}
					placeholder="Name, email or student ID"
					className="pl-9"
					aria-label="Search students"
				/>
			</div>
			<Chip label="All programmes" active={!program} onClick={() => onProgram('')} />
			{data.programs.map((option) => (
				<Chip
					key={option}
					label={option}
					active={program === option}
					onClick={() => onProgram(option)}
				/>
			))}
			<Chip label="All levels" active={!level} onClick={() => onLevel('')} />
			{data.levels.map((option) => (
				<Chip
					key={option}
					label={`L${option}`}
					active={level === option}
					onClick={() => onLevel(option)}
				/>
			))}
		</div>
	)
}
