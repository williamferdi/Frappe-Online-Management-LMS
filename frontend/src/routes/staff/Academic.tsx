import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { GraduationCap, LoaderCircle, TrendingUp, type LucideIcon } from 'lucide-react'
import { toast } from 'sonner'

import { Chip, Empty } from '@/components/Chip'
import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
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
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { useOfferings, usePromote, usePromotions } from '@/hooks/useAcademic'
import { FrappeError } from '@/lib/frappe'
import { cn } from '@/lib/utils'
import type { PromotionRow } from '@/types'

type Tab = 'offerings' | 'promotions'

const TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
	{ id: 'offerings', label: 'Offerings', icon: GraduationCap },
	{ id: 'promotions', label: 'Promotions', icon: TrendingUp },
]

export function Academic() {
	// The tab lives in the address, so a link to the promotions board is a link
	// to the promotions board rather than to whatever tab was last open.
	const [params, setParams] = useSearchParams()
	const tab = (params.get('tab') as Tab) || 'offerings'

	return (
		<>
			<PageHeader title="Academic" description="Course runs and level promotions" />

			<div className="mb-4 flex flex-wrap gap-1">
				{TABS.map((entry) => (
					<Button
						key={entry.id}
						size="sm"
						variant={tab === entry.id ? 'default' : 'outline'}
						onClick={() => setParams(entry.id === 'offerings' ? {} : { tab: entry.id })}
					>
						<entry.icon /> {entry.label}
					</Button>
				))}
			</div>

			{tab === 'offerings' && <Offerings />}
			{tab === 'promotions' && <Promotions />}
		</>
	)
}

function Offerings() {
	const [term, setTerm] = useState('')
	const query = useOfferings(term)

	return (
		<QueryState query={query} title="Offerings">
			{(data) => (
				<>
					<div className="mb-4 flex flex-wrap gap-1">
						<Chip label="All terms" active={!term} onClick={() => setTerm('')} />
						{data.terms.map((option) => (
							<Chip
								key={option.name}
								label={option.term_name}
								active={term === option.name}
								onClick={() => setTerm(option.name)}
							/>
						))}
					</div>

					{data.rows.length === 0 ? (
						<Empty
							icon={GraduationCap}
							title="No course runs"
							detail="A Course Offering is one run of a course in one term."
						/>
					) : (
						<Card>
							<CardContent className="p-0">
								<Table>
									<TableHeader>
										<TableRow>
											<TableHead className="pl-5">Course</TableHead>
											<TableHead>Term</TableHead>
											<TableHead>Format</TableHead>
											<TableHead className="text-right">Registered</TableHead>
											<TableHead className="text-right">Graded</TableHead>
											<TableHead className="pr-5 text-right">Roster</TableHead>
										</TableRow>
									</TableHeader>
									<TableBody>
										{data.rows.map((row) => (
											<TableRow key={row.name}>
												<TableCell className="pl-5">
													<div className="font-medium">{row.course_title || row.course}</div>
													<div className="text-muted-foreground font-mono text-xs">
														{row.course}
														{row.course_level && <> · Level {row.course_level}</>}
													</div>
												</TableCell>
												<TableCell className="text-sm">{row.term}</TableCell>
												<TableCell>
													{row.format && <Badge variant="muted">{row.format}</Badge>}
												</TableCell>
												<TableCell className="text-right tabular-nums">
													{row.registered}
													{row.capacity ? (
														<span className="text-muted-foreground"> / {row.capacity}</span>
													) : null}
												</TableCell>
												<TableCell className="text-right tabular-nums">
													{row.graded > 0 ? (
														<Badge variant={row.graded >= row.registered ? 'success' : 'warning'}>
															{row.graded}
														</Badge>
													) : (
														<span className="text-muted-foreground">—</span>
													)}
												</TableCell>
												<TableCell className="pr-5 text-right">
													<Button size="sm" variant="outline" asChild>
														<Link to={`/staff/academic/offerings/${encodeURIComponent(row.name)}`}>
															Open
														</Link>
													</Button>
												</TableCell>
											</TableRow>
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

function Promotions() {
	const query = usePromotions()
	const [chosen, setChosen] = useState<PromotionRow | null>(null)

	return (
		<QueryState query={query} title="Promotions">
			{(data) => (
				<>
					{!data.may_approve && (
						<Card className="mb-4">
							<CardContent className="py-4 text-sm">
								You can see this board but not act on it. Only the Dean, Registrar or
								Academic Coordinator may move a level.
							</CardContent>
						</Card>
					)}

					{data.rows.length === 0 ? (
						<Empty
							icon={TrendingUp}
							title="Nobody to promote"
							detail="Students appear here as they work through their level."
						/>
					) : (
						<Card>
							<CardContent className="p-0">
								<Table>
									<TableHeader>
										<TableRow>
											<TableHead className="pl-5">Student</TableHead>
											<TableHead>Programme</TableHead>
											<TableHead>Move</TableHead>
											<TableHead>Courses passed</TableHead>
											<TableHead className="pr-5 text-right">Decision</TableHead>
										</TableRow>
									</TableHeader>
									<TableBody>
										{data.rows.map((row) => (
											<TableRow key={row.program_enrollment}>
												<TableCell className="pl-5">
													<div className="font-medium">{row.student_name}</div>
													<div className="text-muted-foreground text-xs">{row.student}</div>
												</TableCell>
												<TableCell className="text-sm">{row.program}</TableCell>
												<TableCell className="text-sm tabular-nums">
													Level {row.from_level} → {row.to_level}
												</TableCell>
												<TableCell>
													<div className="flex items-center gap-2">
														<div className="bg-muted h-1.5 w-16 overflow-hidden rounded-full">
															<div
																className={cn(
																	'h-full rounded-full',
																	row.eligible ? 'bg-success' : 'bg-primary',
																)}
																style={{
																	width: `${Math.min(100, (row.passed / Math.max(1, row.required)) * 100)}%`,
																}}
															/>
														</div>
														<span className="text-xs tabular-nums">
															{row.passed}/{row.required}
														</span>
													</div>
													{/* The reason, in words. A greyed button with no
													    explanation is what the office rings about. */}
													{row.blocked && (
														<div className="text-muted-foreground mt-1 text-xs">
															{row.blocked}
														</div>
													)}
												</TableCell>
												<TableCell className="pr-5 text-right">
													{row.eligible ? (
														<Button
															size="sm"
															disabled={!data.may_approve}
															onClick={() => setChosen(row)}
														>
															Promote
														</Button>
													) : (
														<Badge variant="muted">Not yet</Badge>
													)}
												</TableCell>
											</TableRow>
										))}
									</TableBody>
								</Table>
							</CardContent>
						</Card>
					)}

					<PromoteDialog row={chosen} onClose={() => setChosen(null)} />
				</>
			)}
		</QueryState>
	)
}

function PromoteDialog({
	row,
	onClose,
}: {
	row: PromotionRow | null
	onClose: () => void
}) {
	const promote = usePromote()
	const [remarks, setRemarks] = useState('')

	function confirm() {
		if (!row) return
		promote.mutate(
			{
				program_enrollment: row.program_enrollment,
				to_level: row.to_level,
				remarks: remarks || undefined,
			},
			{
				onSuccess: () => {
					setRemarks('')
					onClose()
					toast.success(`${row.student_name} promoted to Level ${row.to_level}`)
				},
				onError: (error) =>
					toast.error(
						error instanceof FrappeError ? error.message : 'That promotion was refused.',
					),
			},
		)
	}

	return (
		<Dialog open={Boolean(row)} onOpenChange={(open) => !open && onClose()}>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>
						Promote {row?.student_name} to Level {row?.to_level}?
					</DialogTitle>
					<DialogDescription>
						{row?.passed} of {row?.required} courses passed at Level {row?.from_level}.
						This is recorded as a Level Promotion against your name.
					</DialogDescription>
				</DialogHeader>

				<div className="space-y-2">
					<Textarea
						value={remarks}
						onChange={(event) => setRemarks(event.target.value)}
						placeholder="Remarks (optional)"
					/>
				</div>

				<DialogFooter>
					<Button variant="outline" onClick={onClose} disabled={promote.isPending}>
						Cancel
					</Button>
					<Button onClick={confirm} disabled={promote.isPending}>
						{promote.isPending && <LoaderCircle className="animate-spin" />}
						Promote
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	)
}

