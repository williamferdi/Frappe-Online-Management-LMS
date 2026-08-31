import { useState } from 'react'
import { ChevronDown, ChevronRight, GraduationCap } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from '@/components/ui/table'
import { useGrades } from '@/hooks/useStudent'
import { cn } from '@/lib/utils'
import type { GradedRegistration, GradesResponse } from '@/types'

export function Grades() {
	const query = useGrades()

	return (
		<QueryState query={query} title="Grades" emptyWhen={(d) => !d.enrollment}>
			{(data) => <Loaded data={data} />}
		</QueryState>
	)
}

function Loaded({ data }: { data: GradesResponse }) {
	const enrollment = data.enrollment!
	const graded = data.terms.flatMap((term) => term.rows).filter((row) => row.grade)

	return (
		<>
			<PageHeader
				title="Grades"
				description={`${enrollment.program_name || enrollment.program} · Level ${enrollment.current_level}`}
			/>

			<div className="grid gap-3 sm:grid-cols-3">
				<Stat label="CGPA" value={enrollment.cgpa ? enrollment.cgpa.toFixed(2) : '—'} />
				<Stat label="Credits earned" value={String(enrollment.credits_earned ?? 0)} />
				<Stat label="Courses graded" value={String(graded.length)} />
			</div>

			{graded.length === 0 && (
				<Card className="mt-6">
					<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
						<GraduationCap className="text-muted-foreground size-6" />
						<div className="font-medium">No grades yet</div>
						<p className="text-muted-foreground max-w-sm text-sm">
							Marks appear here once your instructor has finished assessing a course.
						</p>
					</CardContent>
				</Card>
			)}

			{data.terms.map((term) => (
				<Card key={term.term} className="mt-6">
					<CardHeader className="flex-row items-center justify-between">
						<CardTitle className="text-base">{term.term_name}</CardTitle>
						<span className="text-muted-foreground text-xs">
							{term.credits} {term.credits === 1 ? 'credit' : 'credits'} earned
						</span>
					</CardHeader>
					<CardContent className="px-0 pb-2 pt-1">
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead className="pl-5">Course</TableHead>
									<TableHead className="text-right">Credits</TableHead>
									<TableHead className="text-right">Marks</TableHead>
									<TableHead className="text-right">Grade</TableHead>
									<TableHead className="pr-5 text-right">Points</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{term.rows.map((row) => (
									<CourseRows key={row.name} row={row} />
								))}
							</TableBody>
						</Table>
					</CardContent>
				</Card>
			))}

			{data.scale && (
				<Card className="mt-6">
					<CardHeader>
						<CardTitle className="text-base">{data.scale.scale_name}</CardTitle>
					</CardHeader>
					<CardContent className="pt-3">
						<div className="flex flex-wrap gap-2">
							{data.scale.rows.map((band) => (
								<div
									key={band.grade}
									className="bg-muted/60 flex items-center gap-2 rounded-md px-2.5 py-1.5 text-xs"
								>
									<Badge variant={band.is_pass ? 'success' : 'destructive'}>
										{band.grade}
									</Badge>
									<span className="text-muted-foreground tabular-nums">
										{band.min_pct}–{band.max_pct}%
									</span>
									<span className="text-muted-foreground">·</span>
									<span className="tabular-nums">{band.grade_points}</span>
								</div>
							))}
						</div>
						<p className="text-muted-foreground mt-3 text-xs">
							Pass mark {data.scale.pass_percentage}%.
						</p>
					</CardContent>
				</Card>
			)}
		</>
	)
}

/**
 * A course row, and its component marks underneath when opened.
 *
 * "Why is my grade a B?" is answerable from the weighted components, so they
 * are one click away rather than a mail to the office.
 */
function CourseRows({ row }: { row: GradedRegistration }) {
	const [open, setOpen] = useState(false)
	const hasDetail = row.components.length > 0

	return (
		<>
			<TableRow
				className={cn(hasDetail && 'cursor-pointer')}
				onClick={hasDetail ? () => setOpen((value) => !value) : undefined}
			>
				<TableCell className="pl-5">
					<div className="flex items-center gap-1.5">
						{hasDetail ? (
							open ? (
								<ChevronDown className="text-muted-foreground size-3.5 shrink-0" />
							) : (
								<ChevronRight className="text-muted-foreground size-3.5 shrink-0" />
							)
						) : (
							<span className="size-3.5 shrink-0" />
						)}
						<div className="min-w-0">
							<div className="truncate font-medium">
								{row.course_title || row.course}
							</div>
							<div className="text-muted-foreground font-mono text-xs">{row.course}</div>
						</div>
					</div>
				</TableCell>
				<TableCell className="text-right tabular-nums">{row.credits}</TableCell>
				<TableCell className="text-right tabular-nums">
					{row.grade ? (row.final_marks ?? 0).toFixed(1) : '—'}
				</TableCell>
				<TableCell className="text-right">
					{row.grade ? (
						<Badge variant={row.passed ? 'success' : 'destructive'}>{row.grade}</Badge>
					) : (
						<Badge variant="muted">{row.status}</Badge>
					)}
				</TableCell>
				<TableCell className="pr-5 text-right tabular-nums">
					{row.grade ? (row.grade_points ?? 0).toFixed(1) : '—'}
				</TableCell>
			</TableRow>

			{open &&
				row.components.map((component) => (
					<TableRow key={`${row.name}-${component.idx}`} className="bg-muted/30">
						<TableCell className="text-muted-foreground pl-11 text-xs">
							{component.component}
							<span className="ml-2 opacity-70">{component.weight_pct}% weight</span>
						</TableCell>
						<TableCell />
						<TableCell className="text-muted-foreground text-right text-xs tabular-nums">
							{component.obtained_marks} / {component.max_marks}
						</TableCell>
						<TableCell />
						<TableCell className="text-muted-foreground pr-5 text-right text-xs tabular-nums">
							{component.weighted_score.toFixed(1)}
						</TableCell>
					</TableRow>
				))}
		</>
	)
}

function Stat({ label, value }: { label: string; value: string }) {
	return (
		<Card>
			<CardContent className="p-4">
				<div className="text-muted-foreground text-xs font-medium uppercase tracking-wider">
					{label}
				</div>
				<div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
			</CardContent>
		</Card>
	)
}
