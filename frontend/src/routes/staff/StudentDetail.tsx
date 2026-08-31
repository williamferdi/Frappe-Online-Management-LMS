import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Pencil, TrendingUp } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from '@/components/ui/table'
import { useStudentDetail } from '@/hooks/useAcademic'
import { formatDate, money } from '@/lib/utils'
import type { StudentDetail as Detail } from '@/types'

export function StudentDetail() {
	const { name = null } = useParams()
	const query = useStudentDetail(name)

	return (
		<QueryState query={query} title="Student">
			{(data) => <Loaded data={data} />}
		</QueryState>
	)
}

function Loaded({ data }: { data: Detail }) {
	const student = data.student
	const enrollment = data.enrollment

	return (
		<>
			<PageHeader
				title={student.full_name}
				description={
					enrollment
						? `${student.name} · ${enrollment.program} · Level ${enrollment.current_level}`
						: student.name
				}
				actions={
					<div className="flex gap-2">
						<Button variant="outline" size="sm" asChild>
							<Link to="/staff/academic">
								<ArrowLeft /> Students
							</Link>
						</Button>
						<Button size="sm" asChild>
							<Link
								to={`/staff/data/Student/${encodeURIComponent(student.name)}`}
							>
								<Pencil /> Edit
							</Link>
						</Button>
					</div>
				}
			/>

			{enrollment && (
				<div className="mb-4 grid gap-3 sm:grid-cols-4">
					<Stat label="Level" value={enrollment.current_level} />
					<Stat label="Credits" value={String(enrollment.credits_earned ?? 0)} />
					<Stat label="CGPA" value={enrollment.cgpa ? enrollment.cgpa.toFixed(2) : '—'} />
					<Stat label="Enrolment" value={enrollment.status} />
				</div>
			)}

			<div className="grid gap-4 lg:grid-cols-3">
				<Card className="lg:col-span-2">
					<CardHeader>
						<CardTitle className="text-base">Registrations</CardTitle>
					</CardHeader>
					<CardContent className="p-0 pb-2">
						{data.registrations.length === 0 ? (
							<p className="text-muted-foreground px-5 pb-5 text-sm">
								No course registrations yet.
							</p>
						) : (
							<Table>
								<TableHeader>
									<TableRow>
										<TableHead className="pl-5">Course</TableHead>
										<TableHead>Term</TableHead>
										<TableHead>Status</TableHead>
										<TableHead className="text-right">Marks</TableHead>
										<TableHead className="pr-5 text-right">Grade</TableHead>
									</TableRow>
								</TableHeader>
								<TableBody>
									{data.registrations.map((row) => (
										<TableRow key={row.name}>
											<TableCell className="pl-5">
												<Link
													to={`/staff/academic/offerings/${encodeURIComponent(row.course_offering)}`}
													className="hover:text-primary transition-colors"
												>
													<div className="font-medium">{row.course_title || row.course}</div>
													<div className="text-muted-foreground font-mono text-xs">
														{row.course}
														{row.level_at_registration && (
															<> · at Level {row.level_at_registration}</>
														)}
													</div>
												</Link>
											</TableCell>
											<TableCell className="text-sm">{row.term}</TableCell>
											<TableCell>
												<Badge variant={row.status === 'Completed' ? 'success' : 'muted'}>
													{row.status}
												</Badge>
											</TableCell>
											<TableCell className="text-right tabular-nums">
												{row.grade ? row.final_marks : '—'}
											</TableCell>
											<TableCell className="pr-5 text-right">
												{row.grade ? (
													<Badge variant={row.passed ? 'success' : 'destructive'}>
														{row.grade}
													</Badge>
												) : (
													<span className="text-muted-foreground text-xs">—</span>
												)}
											</TableCell>
										</TableRow>
									))}
								</TableBody>
							</Table>
						)}
					</CardContent>
				</Card>

				<div className="space-y-4">
					<Card>
						<CardHeader>
							<CardTitle className="text-base">Record</CardTitle>
						</CardHeader>
						<CardContent className="pt-3">
							<dl className="space-y-2.5">
								<Field label="Email" value={student.email} />
								<Field label="Mobile" value={student.mobile} />
								<Field label="Date of birth" value={formatDate(student.dob)} />
								<Field label="Gender" value={student.gender} />
								<Field label="Login" value={student.user} />
								{enrollment && (
									<>
										<Field label="Enrolled" value={formatDate(enrollment.enrollment_date)} />
										<Field label="Start term" value={enrollment.start_term} />
									</>
								)}
							</dl>
						</CardContent>
					</Card>

					{data.invoices.length > 0 && (
						<Card>
							<CardHeader>
								<CardTitle className="text-base">Fees</CardTitle>
							</CardHeader>
							<CardContent className="pt-3">
								<ul className="space-y-1.5 text-sm">
									{data.invoices.map((invoice) => (
										<li key={invoice.name} className="flex items-center justify-between gap-2">
											<span className="min-w-0 truncate">
												{invoice.fee_type || invoice.category}
											</span>
											<span className="flex shrink-0 items-center gap-2">
												<span className="tabular-nums">{money(invoice.net_amount)}</span>
												<Badge variant={invoice.status === 'Paid' ? 'success' : 'warning'}>
													{invoice.status}
												</Badge>
											</span>
										</li>
									))}
								</ul>
							</CardContent>
						</Card>
					)}

					<Card>
						<CardHeader>
							<CardTitle className="text-base">Level history</CardTitle>
						</CardHeader>
						<CardContent className="pt-3">
							{data.promotions.length === 0 ? (
								<p className="text-muted-foreground text-sm">
									No promotions recorded. A level only moves through a Level
									Promotion, which records who approved it and on what evidence.
								</p>
							) : (
								<ul className="space-y-2.5 text-sm">
									{data.promotions.map((row) => (
										<li key={row.name} className="flex items-start gap-2">
											<TrendingUp className="text-success mt-0.5 size-3.5 shrink-0" />
											<div>
												<div>
													Level {row.from_level} → {row.to_level}
												</div>
												<div className="text-muted-foreground text-xs">
													{formatDate(row.approved_on)}
													{row.approved_by && <> · {row.approved_by}</>}
													{' · '}
													{row.courses_passed} courses
												</div>
											</div>
										</li>
									))}
								</ul>
							)}
						</CardContent>
					</Card>
				</div>
			</div>
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

function Field({ label, value }: { label: string; value: string | null | undefined }) {
	return (
		<div>
			<dt className="text-muted-foreground text-xs font-medium uppercase tracking-wider">
				{label}
			</dt>
			<dd className="text-sm">{value || '—'}</dd>
		</div>
	)
}
