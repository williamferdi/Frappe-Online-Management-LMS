import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Eye, EyeOff, LoaderCircle, Plus, Save, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Content } from '@/routes/staff/Content'
import { Gradebook } from '@/routes/staff/Gradebook'
import { Groups } from '@/routes/staff/Groups'
import { Modules } from '@/routes/staff/Modules'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import {
	useCourse,
	useDeleteAssignment,
	useDeleteScheme,
	useSaveAssignment,
	useSaveScheme,
	useSetPublished,
} from '@/hooks/useCourses'
import { FrappeError } from '@/lib/frappe'
import { cn } from '@/lib/utils'
import type {
	CourseAssignment,
	CourseDetail as CourseDetailData,
	GradeSchemeRow,
} from '@/types'

/** What a course is weighted by before anyone has said otherwise. */
const STARTER: GradeSchemeRow[] = [
	{ component: 'Assignment', weight_pct: 40, drop_lowest: 0, posting_policy: 'Manual' },
	{ component: 'Exam', weight_pct: 40, drop_lowest: 0, posting_policy: 'Manual' },
	{ component: 'Attendance', weight_pct: 20, drop_lowest: 0, posting_policy: 'Manual' },
]

function message(error: unknown) {
	return error instanceof FrappeError ? error.message : 'Something went wrong.'
}

export function CourseDetail() {
	const { name = null } = useParams()
	const offering = name ? decodeURIComponent(name) : null
	const query = useCourse(offering)

	return (
		<QueryState query={query} title="Course">
			{(data) => <Loaded data={data} offering={offering!} />}
		</QueryState>
	)
}

function Loaded({ data, offering }: { data: CourseDetailData; offering: string }) {
	const course = data.offering

	// The tab lives in the address, so "set one on the Assignments tab" can be
	// a link to the Assignments tab rather than a description of where it is.
	const [params, setParams] = useSearchParams()
	const tab = params.get('tab') || 'scheme'
	const setTab = (next: string) =>
		setParams(next === 'scheme' ? {} : { tab: next }, { replace: true })

	return (
		<>
			<PageHeader
				title={course.course_title || course.course}
				description={`${course.course} · ${course.term} · ${course.enrolled_count ?? 0} registered`}
				actions={
					<Button variant="outline" size="sm" asChild>
						<Link to="/staff/courses">
							<ArrowLeft /> Courses
						</Link>
					</Button>
				}
			/>

			<Tabs value={tab} onValueChange={setTab} defaultValue="scheme">
				<TabsList>
					<TabsTrigger value="scheme">Grade scheme</TabsTrigger>
					<TabsTrigger value="assignments">
						Assignments{data.assignments.length ? ` (${data.assignments.length})` : ''}
					</TabsTrigger>
					<TabsTrigger value="content">Content</TabsTrigger>
					<TabsTrigger value="modules">Modules</TabsTrigger>
					<TabsTrigger value="gradebook">Gradebook</TabsTrigger>
					<TabsTrigger value="groups">Groups</TabsTrigger>
				</TabsList>

				<TabsContent value="scheme">
					<SchemeEditor data={data} offering={offering} />
				</TabsContent>

				<TabsContent value="assignments">
					<Assignments data={data} offering={offering} />
				</TabsContent>

				<TabsContent value="content">
					<Content offering={offering} />
				</TabsContent>

				<TabsContent value="modules">
					<Modules offering={offering} />
				</TabsContent>

				<TabsContent value="gradebook">
					<Gradebook offering={offering} />
				</TabsContent>

				<TabsContent value="groups">
					<Groups offering={offering} />
				</TabsContent>
			</Tabs>
		</>
	)
}

// ---------------------------------------------------------------------------
// the scheme
// ---------------------------------------------------------------------------

function SchemeEditor({ data, offering }: { data: CourseDetailData; offering: string }) {
	const [rows, setRows] = useState<GradeSchemeRow[]>(data.scheme?.rows ?? STARTER)
	const save = useSaveScheme(offering)
	const remove = useDeleteScheme(offering)

	const total = rows.reduce((sum, row) => sum + (Number(row.weight_pct) || 0), 0)
	const balanced = Math.abs(total - 100) < 0.01

	const update = (index: number, patch: Partial<GradeSchemeRow>) =>
		setRows(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)))

	const onSave = () =>
		save.mutate(rows, {
			onSuccess: () => toast.success('Grade scheme saved'),
			onError: (error) => toast.error(message(error)),
		})

	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">How this course is weighted</CardTitle>
				<p className="text-muted-foreground text-sm">
					Every student on this run gets these columns. An assignment counts towards one
					of them, and the weights have to add up to 100.
				</p>
			</CardHeader>

			<CardContent>
				<div className="space-y-2">
					{rows.map((row, index) => (
						<div key={index} className="flex flex-wrap items-end gap-2">
							<div className="min-w-40 flex-1">
								<Label htmlFor={`component-${index}`} className="text-xs">
									Component
								</Label>
								<select
									id={`component-${index}`}
									className="border-input bg-background mt-1 h-9 w-full rounded-md border px-3 text-sm"
									value={row.component}
									onChange={(event) => update(index, { component: event.target.value })}
								>
									{data.choices.components.map((option) => (
										<option key={option} value={option}>
											{option}
										</option>
									))}
								</select>
							</div>

							<div className="w-24">
								<Label htmlFor={`weight-${index}`} className="text-xs">
									Weight %
								</Label>
								<Input
									id={`weight-${index}`}
									type="number"
									className="mt-1"
									value={row.weight_pct}
									onChange={(event) =>
										update(index, { weight_pct: Number(event.target.value) })
									}
								/>
							</div>

							<div className="w-32">
								<Label htmlFor={`posting-${index}`} className="text-xs">
									Posting
								</Label>
								<select
									id={`posting-${index}`}
									className="border-input bg-background mt-1 h-9 w-full rounded-md border px-3 text-sm"
									value={row.posting_policy}
									onChange={(event) =>
										update(index, { posting_policy: event.target.value })
									}
								>
									{data.choices.posting_policies.map((option) => (
										<option key={option} value={option}>
											{option}
										</option>
									))}
								</select>
							</div>

							<Button
								variant="ghost"
								size="icon"
								aria-label={`Remove ${row.component}`}
								onClick={() => setRows(rows.filter((_, i) => i !== index))}
							>
								<Trash2 className="size-4" />
							</Button>
						</div>
					))}
				</div>

				<div className="mt-4 flex flex-wrap items-center gap-3">
					<Button
						variant="outline"
						size="sm"
						onClick={() =>
							setRows([
								...rows,
								{
									component: data.choices.components[0] ?? 'Assignment',
									weight_pct: 0,
									drop_lowest: 0,
									posting_policy: 'Manual',
								},
							])
						}
					>
						<Plus /> Add component
					</Button>

					<span
						className={cn(
							'text-sm font-medium tabular-nums',
							balanced ? 'text-emerald-600' : 'text-destructive',
						)}
					>
						{total}% of 100
					</span>

					<div className="ml-auto flex gap-2">
						{data.scheme && (
							<Button
								variant="outline"
								size="sm"
								onClick={() =>
									remove.mutate(undefined, {
										onSuccess: () => toast.success('Scheme removed'),
										onError: (error) => toast.error(message(error)),
									})
								}
								disabled={remove.isPending}
							>
								Remove scheme
							</Button>
						)}
						<Button size="sm" onClick={onSave} disabled={save.isPending || !balanced}>
							{save.isPending ? <LoaderCircle className="animate-spin" /> : <Save />}
							Save scheme
						</Button>
					</div>
				</div>

				{!balanced && (
					<p className="text-muted-foreground mt-2 text-xs">
						The weights have to total 100 before this can be saved — otherwise the
						final mark would not mean anything.
					</p>
				)}
			</CardContent>
		</Card>
	)
}

// ---------------------------------------------------------------------------
// the work
// ---------------------------------------------------------------------------

const BLANK: Partial<CourseAssignment> = {
	title: '',
	component: 'Assignment',
	points_possible: 100,
	submission_type: 'Text Entry',
	grading_type: 'Points',
	late_policy: 'Accept',
	late_penalty_pct_per_day: 0,
	allowed_attempts: 1,
	due_date: null,
	description: '',
}

function Assignments({ data, offering }: { data: CourseDetailData; offering: string }) {
	const [editing, setEditing] = useState<Partial<CourseAssignment> | null>(null)

	if (!data.scheme) {
		return (
			<Card>
				<CardContent className="py-14 text-center">
					<div className="font-medium">Set the grade scheme first</div>
					<p className="text-muted-foreground mx-auto mt-1 max-w-md text-sm">
						An assignment counts towards one component of the scheme. Without a scheme
						there is nothing for a score to count towards.
					</p>
				</CardContent>
			</Card>
		)
	}

	return (
		<div className="space-y-4">
			{editing ? (
				<AssignmentEditor
					data={data}
					offering={offering}
					initial={editing}
					onDone={() => setEditing(null)}
				/>
			) : (
				<div className="flex justify-end">
					<Button size="sm" onClick={() => setEditing({ ...BLANK })}>
						<Plus /> New assignment
					</Button>
				</div>
			)}

			{data.assignments.length === 0 ? (
				<Card>
					<CardContent className="py-14 text-center">
						<div className="font-medium">Nothing set yet</div>
						<p className="text-muted-foreground mx-auto mt-1 max-w-md text-sm">
							Work you create stays unpublished until you publish it, so students see
							nothing while you draft.
						</p>
					</CardContent>
				</Card>
			) : (
				<div className="space-y-2">
					{data.assignments.map((row) => (
						<AssignmentRow
							key={row.name}
							row={row}
							offering={offering}
							onEdit={() => setEditing(row)}
						/>
					))}
				</div>
			)}
		</div>
	)
}

function AssignmentRow({
	row,
	offering,
	onEdit,
}: {
	row: CourseAssignment
	offering: string
	onEdit: () => void
}) {
	const publish = useSetPublished(offering)
	const remove = useDeleteAssignment(offering)

	return (
		<Card>
			<CardContent className="flex flex-wrap items-center gap-3 p-4">
				<div className="min-w-0 flex-1">
					<div className="flex items-center gap-2">
						<span className="truncate font-medium">{row.title}</span>
						<Badge variant={row.published ? 'default' : 'secondary'}>
							{row.published ? 'Published' : 'Draft'}
						</Badge>
					</div>
					<div className="text-muted-foreground mt-0.5 text-xs">
						{row.component} · {row.points_possible} points · {row.submission_type}
						{row.due_date ? ` · due ${row.due_date.slice(0, 16).replace('T', ' ')}` : ' · no due date'}
					</div>
				</div>

				<div className="flex gap-1">
					<Button
						variant="ghost"
						size="sm"
						onClick={() =>
							publish.mutate(
								{ assignment: row.name, published: !row.published },
								{ onError: (error) => toast.error(message(error)) },
							)
						}
						disabled={publish.isPending}
					>
						{row.published ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
						{row.published ? 'Unpublish' : 'Publish'}
					</Button>
					<Button variant="ghost" size="sm" asChild>
						<Link
							to={`/staff/courses/${encodeURIComponent(offering)}/grade/${encodeURIComponent(row.name)}`}
						>
							Mark
						</Link>
					</Button>
					<Button variant="ghost" size="sm" onClick={onEdit}>
						Edit
					</Button>
					<Button
						variant="ghost"
						size="icon"
						aria-label={`Delete ${row.title}`}
						onClick={() =>
							remove.mutate(row.name, {
								onSuccess: () => toast.success('Assignment deleted'),
								onError: (error) => toast.error(message(error)),
							})
						}
						disabled={remove.isPending}
					>
						<Trash2 className="size-4" />
					</Button>
				</div>
			</CardContent>
		</Card>
	)
}

function AssignmentEditor({
	data,
	offering,
	initial,
	onDone,
}: {
	data: CourseDetailData
	offering: string
	initial: Partial<CourseAssignment>
	onDone: () => void
}) {
	const [values, setValues] = useState<Partial<CourseAssignment>>(initial)
	const save = useSaveAssignment(offering)

	// Only the components the scheme actually has: a score counting towards a
	// bucket that does not exist reaches nobody's grade, and the server
	// refuses it anyway.
	const components = data.scheme?.rows.map((row) => row.component) ?? []

	const set = (patch: Partial<CourseAssignment>) => setValues({ ...values, ...patch })

	const onSave = () =>
		save.mutate(
			{ values, assignment: initial.name },
			{
				onSuccess: () => {
					toast.success(initial.name ? 'Assignment saved' : 'Assignment created')
					onDone()
				},
				onError: (error) => toast.error(message(error)),
			},
		)

	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">
					{initial.name ? 'Edit assignment' : 'New assignment'}
				</CardTitle>
			</CardHeader>
			<CardContent className="space-y-4">
				<div>
					<Label htmlFor="title">Title</Label>
					<Input
						id="title"
						className="mt-1"
						value={values.title ?? ''}
						onChange={(event) => set({ title: event.target.value })}
					/>
				</div>

				<div className="grid gap-3 sm:grid-cols-3">
					<Field label="Counts towards">
						<select
							className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
							value={values.component ?? ''}
							onChange={(event) => set({ component: event.target.value })}
						>
							{components.map((option) => (
								<option key={option} value={option}>
									{option}
								</option>
							))}
						</select>
					</Field>

					<Field label="Points possible">
						<Input
							type="number"
							value={values.points_possible ?? 100}
							onChange={(event) => set({ points_possible: Number(event.target.value) })}
						/>
					</Field>

					<Field label="Grading">
						<select
							className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
							value={values.grading_type ?? 'Points'}
							onChange={(event) => set({ grading_type: event.target.value })}
						>
							{data.choices.grading_types.map((option) => (
								<option key={option} value={option}>
									{option}
								</option>
							))}
						</select>
					</Field>
				</div>

				<div className="grid gap-3 sm:grid-cols-3">
					<Field label="Available from">
						<Input
							type="datetime-local"
							value={(values.available_from ?? '').slice(0, 16)}
							onChange={(event) => set({ available_from: event.target.value || null })}
						/>
					</Field>
					<Field label="Due">
						<Input
							type="datetime-local"
							value={(values.due_date ?? '').slice(0, 16)}
							onChange={(event) => set({ due_date: event.target.value || null })}
						/>
					</Field>
					<Field label="Closes">
						<Input
							type="datetime-local"
							value={(values.available_until ?? '').slice(0, 16)}
							onChange={(event) => set({ available_until: event.target.value || null })}
						/>
					</Field>
				</div>

				<div className="grid gap-3 sm:grid-cols-3">
					<Field label="Submission type">
						<select
							className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
							value={values.submission_type ?? ''}
							onChange={(event) => set({ submission_type: event.target.value })}
						>
							{data.choices.submission_types.map((option) => (
								<option key={option} value={option}>
									{option}
								</option>
							))}
						</select>
					</Field>

					<Field label="Late policy">
						<select
							className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
							value={values.late_policy ?? ''}
							onChange={(event) => set({ late_policy: event.target.value })}
						>
							{data.choices.late_policies.map((option) => (
								<option key={option} value={option}>
									{option}
								</option>
							))}
						</select>
					</Field>

					{values.late_policy === 'Accept with penalty' && (
						<Field label="Penalty % per day">
							<Input
								type="number"
								value={values.late_penalty_pct_per_day ?? 0}
								onChange={(event) =>
									set({ late_penalty_pct_per_day: Number(event.target.value) })
								}
							/>
						</Field>
					)}
				</div>

				<div>
					<Label htmlFor="description">Brief</Label>
					<Textarea
						id="description"
						className="mt-1 font-mono text-xs"
						rows={5}
						value={values.description ?? ''}
						onChange={(event) => set({ description: event.target.value })}
					/>
					<p className="text-muted-foreground mt-1 text-xs">
						HTML, shown to students as written. There is no rich-text editor here yet.
					</p>
				</div>

				<div className="flex justify-end gap-2">
					<Button variant="outline" size="sm" onClick={onDone}>
						Cancel
					</Button>
					<Button size="sm" onClick={onSave} disabled={save.isPending || !values.title}>
						{save.isPending ? <LoaderCircle className="animate-spin" /> : <Save />}
						Save
					</Button>
				</div>
			</CardContent>
		</Card>
	)
}

/**
 * A labelled control.
 *
 * A native <label> wrapping its control, rather than a <Label> beside one: the
 * association is then implicit and needs no id, which matters because several
 * of these render more than once on the page.
 */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
	return (
		<label className="block">
			<span className="text-xs font-medium">{label}</span>
			<div className="mt-1">{children}</div>
		</label>
	)
}
