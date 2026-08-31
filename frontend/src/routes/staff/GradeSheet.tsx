import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, LoaderCircle, Plus, Save, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useRoster, useSaveGrades } from '@/hooks/useAcademic'
import { FrappeError } from '@/lib/frappe'
import { cn } from '@/lib/utils'
import type { GradeComponentRow, RosterRegistration, RosterResponse } from '@/types'

/** The default sheet for a course nobody has graded yet. */
const STARTER: Omit<GradeComponentRow, 'weighted_score'>[] = [
	{ component: 'Assignment', weight_pct: 40, max_marks: 100, obtained_marks: null },
	{ component: 'Final Paper', weight_pct: 60, max_marks: 100, obtained_marks: null },
]

export function GradeSheet() {
	const { name = null } = useParams()
	const offering = name ? decodeURIComponent(name) : null
	const query = useRoster(offering)

	return (
		<QueryState query={query} title="Roster">
			{(data) => <Loaded data={data} offering={offering!} />}
		</QueryState>
	)
}

function Loaded({ data, offering }: { data: RosterResponse; offering: string }) {
	const course = data.offering

	return (
		<>
			<PageHeader
				title={course.course_title || course.course}
				description={`${course.course} · ${course.term} · ${data.registrations.length} registered`}
				actions={
					<Button variant="outline" size="sm" asChild>
						<Link to="/staff/academic?tab=offerings">
							<ArrowLeft /> Offerings
						</Link>
					</Button>
				}
			/>

			{!data.can_grade && (
				<Card className="mb-4">
					<CardContent className="py-4 text-sm">
						You can see this roster but not enter marks. Grade fields are restricted to
						the Registrar, Academic Coordinator and Faculty.
					</CardContent>
				</Card>
			)}

			{data.registrations.length === 0 ? (
				<Card>
					<CardContent className="py-14 text-center">
						<div className="font-medium">Nobody has registered</div>
						<p className="text-muted-foreground mx-auto mt-1 max-w-sm text-sm">
							Marks can be entered once students register for this run.
						</p>
					</CardContent>
				</Card>
			) : (
				<div className="space-y-4">
					{data.registrations.map((registration) => (
						<StudentSheet
							key={registration.name}
							registration={registration}
							choices={data.components}
							statuses={data.statuses}
							canGrade={data.can_grade}
							offering={offering}
						/>
					))}
				</div>
			)}
		</>
	)
}

function StudentSheet({
	registration,
	choices,
	statuses,
	canGrade,
	offering,
}: {
	registration: RosterRegistration
	choices: string[]
	statuses: string[]
	canGrade: boolean
	offering: string
}) {
	const save = useSaveGrades(offering)
	const [rows, setRows] = useState<GradeComponentRow[]>(() => initial(registration))
	const [status, setStatus] = useState(registration.status)

	// A save refetches the roster; without this the inputs keep showing what was
	// typed rather than what the server computed from it.
	useEffect(() => {
		setRows(initial(registration))
		setStatus(registration.status)
	}, [registration])

	const weight = rows.reduce((total, row) => total + (Number(row.weight_pct) || 0), 0)
	const weightOff = rows.length > 0 && Math.abs(weight - 100) > 0.01

	function update(index: number, patch: Partial<GradeComponentRow>) {
		setRows((current) =>
			current.map((row, i) => (i === index ? { ...row, ...patch } : row)),
		)
	}

	function onSave() {
		save.mutate(
			{ registration: registration.name, components: rows, status },
			{
				onSuccess: (result) => {
					toast.success(
						result.marks_complete
							? `${registration.student_name}: ${result.grade} (${result.final_marks})`
							: `${registration.student_name}: marks saved, grade pending`,
					)
				},
				onError: (error) =>
					toast.error(
						error instanceof FrappeError ? error.message : 'Those marks were not saved.',
					),
			},
		)
	}

	return (
		<Card>
			<CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
				<div>
					<CardTitle className="text-base">{registration.student_name}</CardTitle>
					<div className="text-muted-foreground mt-0.5 text-xs">
						{registration.student} · {registration.credits} credits
					</div>
				</div>
				<div className="flex items-center gap-2">
					{/* "Not graded" rather than 0.0: compute_grade leaves final_marks
					    at its old value until every component is marked. */}
					{registration.marks_complete && registration.grade ? (
						<Badge variant={registration.passed ? 'success' : 'destructive'}>
							{registration.grade} · {registration.final_marks}
						</Badge>
					) : (
						<Badge variant="muted">Not graded</Badge>
					)}
					<Badge variant="muted">{registration.status}</Badge>
				</div>
			</CardHeader>

			<CardContent className="pt-3">
				<div className="space-y-2">
					{rows.map((row, index) => (
						<div key={index} className="flex flex-wrap items-end gap-2">
							<div className="min-w-40 flex-1">
								{index === 0 && <Label className="mb-1 text-xs">Component</Label>}
								<select
									value={row.component}
									disabled={!canGrade}
									onChange={(event) => update(index, { component: event.target.value })}
									className="border-input bg-card h-9 w-full rounded-md border px-2 text-sm disabled:opacity-50"
								>
									{choices.map((choice) => (
										<option key={choice} value={choice}>
											{choice}
										</option>
									))}
								</select>
							</div>
							<NumberField
								label={index === 0 ? 'Weight %' : undefined}
								value={row.weight_pct}
								disabled={!canGrade}
								onChange={(value) => update(index, { weight_pct: value ?? 0 })}
							/>
							<NumberField
								label={index === 0 ? 'Out of' : undefined}
								value={row.max_marks}
								disabled={!canGrade}
								onChange={(value) => update(index, { max_marks: value ?? 100 })}
							/>
							<NumberField
								label={index === 0 ? 'Marks' : undefined}
								value={row.obtained_marks}
								disabled={!canGrade}
								placeholder="—"
								onChange={(value) => update(index, { obtained_marks: value })}
							/>
							<div className="w-16 text-right">
								{index === 0 && <Label className="mb-1 block text-xs">Weighted</Label>}
								<div className="text-muted-foreground h-9 pt-2 text-sm tabular-nums">
									{row.obtained_marks == null
										? '—'
										: (
												((Number(row.obtained_marks) || 0) /
													(Number(row.max_marks) || 100)) *
												(Number(row.weight_pct) || 0)
											).toFixed(1)}
								</div>
							</div>
							{canGrade && (
								<Button
									variant="ghost"
									size="icon"
									className="mb-0.5"
									aria-label={`Remove ${row.component}`}
									onClick={() => setRows((current) => current.filter((_, i) => i !== index))}
								>
									<Trash2 />
								</Button>
							)}
						</div>
					))}
				</div>

				{canGrade && (
					<div className="mt-3 flex flex-wrap items-center gap-2">
						<Button
							variant="outline"
							size="sm"
							onClick={() =>
								setRows((current) => [
									...current,
									{
										component: choices[0] ?? 'Assignment',
										weight_pct: 0,
										max_marks: 100,
										obtained_marks: null,
										weighted_score: 0,
									},
								])
							}
						>
							<Plus /> Component
						</Button>

						<span
							className={cn(
								'text-xs',
								weightOff ? 'text-warning-foreground font-medium' : 'text-muted-foreground',
							)}
						>
							Weights total {weight}%{weightOff && ' — should be 100%'}
						</span>

						<select
							value={status}
							onChange={(event) => setStatus(event.target.value)}
							className="border-input bg-card ml-auto h-8 rounded-md border px-2 text-sm"
							aria-label="Registration status"
						>
							{statuses.map((choice) => (
								<option key={choice} value={choice}>
									{choice}
								</option>
							))}
						</select>

						<Button size="sm" onClick={onSave} disabled={save.isPending}>
							{save.isPending ? <LoaderCircle className="animate-spin" /> : <Save />}
							Save marks
						</Button>
					</div>
				)}
			</CardContent>
		</Card>
	)
}

function NumberField({
	label,
	value,
	onChange,
	disabled,
	placeholder,
}: {
	label?: string
	value: number | null
	onChange: (value: number | null) => void
	disabled?: boolean
	placeholder?: string
}) {
	return (
		<div className="w-20">
			{label && <Label className="mb-1 block text-xs">{label}</Label>}
			<Input
				type="number"
				inputMode="decimal"
				value={value ?? ''}
				disabled={disabled}
				placeholder={placeholder}
				aria-label={label}
				onChange={(event) =>
					// An empty box means "not marked yet", which is not a zero --
					// compute_grade holds the letter back on a blank and would
					// award a fail on a nought.
					onChange(event.target.value === '' ? null : Number(event.target.value))
				}
				className="text-right"
			/>
		</div>
	)
}

function initial(registration: RosterRegistration): GradeComponentRow[] {
	if (registration.components.length > 0) {
		return registration.components.map((row) => ({ ...row }))
	}
	return STARTER.map((row) => ({ ...row, weighted_score: 0 }))
}
