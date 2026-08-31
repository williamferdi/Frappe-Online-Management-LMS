import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
	ArrowLeft,
	CheckCircle2,
	Circle,
	FileCheck2,
	Lock,
	LoaderCircle,
	Send,
} from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { useApplication, useRunAction, useUpdateStep } from '@/hooks/useStaff'
import { FrappeError } from '@/lib/frappe'
import { cn, formatDate, money } from '@/lib/utils'
import type { ApplicationDetail as Detail, ChecklistRow } from '@/types'

/** What each checklist action does, in the officer's words. */
const ACTION_LABEL: Record<string, string> = {
	resend_requests: 'Resend requests',
	create_lms_account: 'Create LMS account',
	send_interview_invite: 'Send interview invite',
	send_scholarship_form: 'Send scholarship form',
	send_manuals: 'Send manuals',
	onboard_student: 'Onboard student',
}

export function ApplicationDetail() {
	const { name = null } = useParams()
	const query = useApplication(name)

	return (
		<QueryState query={query} title="Application">
			{(data) => <Loaded data={data} />}
		</QueryState>
	)
}

function Loaded({ data }: { data: Detail }) {
	const record = data.application
	const board = data.checklist
	const done = board.rows.filter((row) => row.done).length
	const percent = Math.round((done / board.rows.length) * 100)

	return (
		<>
			<PageHeader
				title={record.full_name}
				description={`${record.name} · ${record.program ?? 'No programme'} · ${record.workflow_state}`}
				actions={
					<Button variant="outline" size="sm" asChild>
						<Link to="/staff/admissions">
							<ArrowLeft /> Pipeline
						</Link>
					</Button>
				}
			/>

			<Card className="mb-4">
				<CardContent className="p-4">
					<div className="mb-2 flex items-center justify-between text-sm">
						<span className="font-medium">
							{done} of {board.rows.length} steps complete
						</span>
						<span className="text-muted-foreground tabular-nums">{percent}%</span>
					</div>
					<Progress value={percent} />
					{!board.can_write && (
						<p className="text-muted-foreground mt-3 text-xs">
							You have read-only access to this application.
						</p>
					)}
				</CardContent>
			</Card>

			<div className="grid gap-4 lg:grid-cols-3">
				<div className="lg:col-span-2">
					<Checklist board={board} application={record.name} />
				</div>
				<div className="space-y-4">
					<Candidate data={data} />
					<Evidence data={data} />
				</div>
			</div>
		</>
	)
}

function Checklist({
	board,
	application,
}: {
	board: Detail['checklist']
	application: string
}) {
	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Checklist</CardTitle>
			</CardHeader>
			<CardContent className="p-0 pb-2">
				<ul className="divide-y">
					{board.rows.map((row) => (
						<Step
							key={row.step_no}
							row={row}
							application={application}
							canWrite={board.can_write}
						/>
					))}
				</ul>
			</CardContent>
		</Card>
	)
}

function Step({
	row,
	application,
	canWrite,
}: {
	row: ChecklistRow
	application: string
	canWrite: boolean
}) {
	const update = useUpdateStep(application)
	const run = useRunAction(application)
	const [open, setOpen] = useState(false)

	const blocked = Boolean(row.blocked)
	const editable = canWrite && !blocked

	function setStatus(status: string) {
		update.mutate(
			{ step_no: row.step_no, status },
			{
				onSuccess: () => {
					setOpen(false)
					toast.success(`${row.step} → ${status}`)
				},
				onError: (error) =>
					toast.error(
						error instanceof FrappeError ? error.message : 'That change was refused.',
					),
			},
		)
	}

	function runAction() {
		if (!row.action) return
		run.mutate(row.action, {
			onSuccess: () => toast.success(ACTION_LABEL[row.action!] ?? 'Done'),
			onError: (error) =>
				toast.error(
					error instanceof FrappeError ? error.message : 'That action failed.',
				),
		})
	}

	return (
		<li className="px-4 py-3">
			<div className="flex flex-wrap items-start gap-3">
				<div className="mt-0.5 shrink-0">
					{row.done ? (
						<CheckCircle2 className="text-success size-4" />
					) : blocked ? (
						<Lock className="text-muted-foreground size-4" />
					) : (
						<Circle className="text-muted-foreground size-4" />
					)}
				</div>

				<div className="min-w-0 flex-1">
					<div className="flex flex-wrap items-center gap-2">
						<span className={cn('text-sm font-medium', blocked && 'text-muted-foreground')}>
							{row.step_no}. {row.step}
						</span>
						<Badge variant={row.done ? 'success' : blocked ? 'muted' : 'default'}>
							{row.status}
						</Badge>
						<Badge variant="muted">{row.owner_role}</Badge>
					</div>

					{/* The gate, in words. A greyed control with no reason is the
					    thing officers ring the Registrar about. */}
					{row.blocked && (
						<div className="text-muted-foreground mt-1 text-xs">{row.blocked}</div>
					)}
					{row.remarks && (
						<div className="text-muted-foreground mt-1 text-xs italic">{row.remarks}</div>
					)}
					{row.updated_on && (
						<div className="text-muted-foreground mt-1 text-xs">
							{formatDate(row.updated_on)}
							{row.updated_by && <> · {row.updated_by}</>}
						</div>
					)}

					{open && editable && (
						<div className="mt-2 flex flex-wrap gap-1">
							{row.statuses.map((status) => (
								<Button
									key={status}
									size="sm"
									variant={status === row.status ? 'default' : 'outline'}
									className="h-7 text-xs"
									disabled={update.isPending}
									onClick={() => setStatus(status)}
								>
									{status}
								</Button>
							))}
						</div>
					)}
				</div>

				<div className="flex shrink-0 items-center gap-1.5">
					{row.action && editable && (
						<Button size="sm" variant="outline" onClick={runAction} disabled={run.isPending}>
							{run.isPending ? <LoaderCircle className="animate-spin" /> : <Send />}
							{ACTION_LABEL[row.action] ?? row.action}
						</Button>
					)}
					{editable && (
						<Button size="sm" variant="ghost" onClick={() => setOpen((value) => !value)}>
							{open ? 'Close' : 'Change'}
						</Button>
					)}
				</div>
			</div>
		</li>
	)
}

function Candidate({ data }: { data: Detail }) {
	const record = data.application

	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Candidate</CardTitle>
			</CardHeader>
			<CardContent className="pt-3">
				<dl className="space-y-2.5">
					<Field label="Email" value={record.email} />
					<Field label="Mobile" value={record.mobile} />
					<Field label="Date of birth" value={formatDate(record.dob)} />
					<Field label="Gender" value={record.gender} />
					<Field label="Church" value={record.church_name} />
					<Field label="Role" value={record.current_role} />
					<Field
						label="Ministry"
						value={record.years_of_ministry ? `${record.years_of_ministry} years` : null}
					/>
					<Field label="Address" value={record.address} />
					{record.student && <Field label="Student" value={record.student} />}
				</dl>
			</CardContent>
		</Card>
	)
}

function Evidence({ data }: { data: Detail }) {
	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Evidence</CardTitle>
			</CardHeader>
			<CardContent className="space-y-4 pt-3 text-sm">
				<Group label="Documents" empty="None uploaded">
					{data.documents.map((doc) => (
						<Line
							key={doc.name}
							left={doc.document_type}
							right={
								doc.verified ? (
									<Badge variant="success">
										<FileCheck2 /> Verified
									</Badge>
								) : (
									<Badge variant="muted">Unverified</Badge>
								)
							}
							href={doc.file}
						/>
					))}
				</Group>

				<Group label="References" empty="None requested">
					{data.references.map((ref) => (
						<Line
							key={ref.name}
							left={ref.referee_name || ref.referee_email || 'Referee'}
							right={
								<Badge variant={ref.submitted_on ? 'success' : 'muted'}>
									{ref.submitted_on ? 'Received' : ref.sent_on ? 'Sent' : 'Not sent'}
								</Badge>
							}
						/>
					))}
				</Group>

				<Group label="Mentor" empty="None requested">
					{data.mentors.map((mentor) => (
						<Line
							key={mentor.name}
							left={mentor.mentor_name || mentor.mentor_email || 'Mentor'}
							right={
								<Badge variant={mentor.consented_on ? 'success' : 'muted'}>
									{mentor.consented_on ? 'Consented' : mentor.sent_on ? 'Sent' : 'Not sent'}
								</Badge>
							}
						/>
					))}
				</Group>

				{data.exam && (
					<Group label="Entrance exam">
						<Line
							left={`${data.exam.total}% (pass ${data.exam.pass_mark}%)`}
							right={
								<Badge variant={data.exam.result === 'Pass' ? 'success' : 'destructive'}>
									{data.exam.result}
								</Badge>
							}
						/>
					</Group>
				)}

				{data.interview && (
					<Group label="Interview">
						<Line
							left={formatDate(data.interview.scheduled_on)}
							right={<Badge variant="muted">{data.interview.outcome || 'Pending'}</Badge>}
						/>
					</Group>
				)}

				{data.scholarship && (
					<Group label="Scholarship">
						<Line
							left={money(data.scholarship.approved_amount || data.scholarship.requested_amount)}
							right={<Badge variant="muted">{data.scholarship.status}</Badge>}
						/>
					</Group>
				)}

				<Group label="Invoices" empty="None raised">
					{data.invoices.map((invoice) => (
						<Line
							key={invoice.name}
							left={invoice.fee_type || invoice.category || invoice.name}
							right={
								<span className="flex items-center gap-2">
									<span className="tabular-nums">{money(invoice.net_amount)}</span>
									<Badge variant={invoice.status === 'Paid' ? 'success' : 'warning'}>
										{invoice.status}
									</Badge>
								</span>
							}
						/>
					))}
				</Group>
			</CardContent>
		</Card>
	)
}

function Group({
	label,
	empty,
	children,
}: {
	label: string
	empty?: string
	children: React.ReactNode
}) {
	const rows = Array.isArray(children) ? children.filter(Boolean) : children
	const isEmpty = Array.isArray(rows) ? rows.length === 0 : !rows

	return (
		<div>
			<div className="text-muted-foreground mb-1.5 text-xs font-medium uppercase tracking-wider">
				{label}
			</div>
			{isEmpty ? (
				<p className="text-muted-foreground text-xs">{empty}</p>
			) : (
				<ul className="space-y-1">{rows}</ul>
			)}
		</div>
	)
}

function Line({
	left,
	right,
	href,
}: {
	left: string
	right: React.ReactNode
	href?: string | null
}) {
	return (
		<li className="flex items-center justify-between gap-2">
			{href ? (
				<a href={href} className="text-primary min-w-0 truncate underline underline-offset-2">
					{left}
				</a>
			) : (
				<span className="min-w-0 truncate">{left}</span>
			)}
			<span className="shrink-0">{right}</span>
		</li>
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
