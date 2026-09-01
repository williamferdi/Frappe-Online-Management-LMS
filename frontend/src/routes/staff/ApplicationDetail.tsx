import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
	ArrowLeft,
	CheckCircle2,
	Circle,
	Lock,
	LoaderCircle,
	Pencil,
	Send,
} from 'lucide-react'
import { toast } from 'sonner'

import { DocumentsCard, ResponsesCard } from '@/components/AdmissionEvidence'
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
					<div className="flex gap-2">
						<Button variant="outline" size="sm" asChild>
							<Link to="/staff/admissions">
								<ArrowLeft /> Pipeline
							</Link>
						</Button>
						{/* The checklist below drives the workflow; this opens the
						    record itself, every field of it. */}
						<Button size="sm" asChild>
							<Link
								to={`/staff/data/Admission%20Application/${encodeURIComponent(record.name)}`}
							>
								<Pencil /> Edit application
							</Link>
						</Button>
					</div>
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
					<Summary data={data} />
				</div>
			</div>

			<div className="mt-4 space-y-4">
				<DocumentsCard
					documents={data.documents}
					empty="Nothing uploaded yet. The candidate uploads these through the link on their application; the upload page is at /apply."
				/>
				<ResponsesCard
					application={data.application.name}
					references={data.references}
					mentors={data.mentors}
					empty="No requests sent yet. Use Resend requests on the reference and mentor steps above to send them."
				/>
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
					<Field label="Mother tongue" value={record.mother_tongue} />
					<Field label="Nationality" value={record.nationality} />
					<Field label="Church" value={record.church_name} />
					<Field label="Denomination" value={record.church_denomination} />
					<Field label="Role" value={record.current_role} />
					<Field
						label="Ministry"
						value={record.years_of_ministry ? `${record.years_of_ministry} years` : null}
					/>
					<Field label="Salvation" value={record.salvation_status} />
					<Field label="Baptism" value={record.baptism_status} />
					<Field label="Sense of call" value={record.sense_of_call} />
					<Field label="Address" value={record.address} />
					{record.student && <Field label="Student" value={record.student} />}
				</dl>

				{/* Shown only when true: an unticked box is not a finding. */}
				<div className="mt-3 flex flex-wrap gap-1.5">
					{Boolean(record.ata_eligible) && <Badge variant="success">ATA eligible</Badge>}
					{Boolean(record.mature_candidate) && <Badge>Mature candidate</Badge>}
					{Boolean(record.transfer_student) && <Badge>Transfer student</Badge>}
					{Boolean(record.education_sequence_mismatch) && (
						<Badge variant="warning">Educational sequence mismatch</Badge>
					)}
				</div>
			</CardContent>
		</Card>
	)
}

/** Exam, interview, scholarship and money -- the short facts, in the sidebar. */
function Summary({ data }: { data: Detail }) {
	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Assessment</CardTitle>
			</CardHeader>
			<CardContent className="space-y-3 pt-3 text-sm">
				<Line
					left="Entrance exam"
					right={
						data.exam ? (
							<Badge variant={data.exam.result === 'Pass' ? 'success' : 'destructive'}>
								{data.exam.total}% {data.exam.result}
							</Badge>
						) : (
							<span className="text-muted-foreground text-xs">Not sat</span>
						)
					}
				/>
				<Line
					left="Interview"
					right={
						data.interview ? (
							<Badge variant="muted">{data.interview.outcome || 'Pending'}</Badge>
						) : (
							<span className="text-muted-foreground text-xs">Not held</span>
						)
					}
				/>
				<Line
					left="Scholarship"
					right={
						data.scholarship ? (
							<Badge variant="muted">{data.scholarship.status}</Badge>
						) : (
							<span className="text-muted-foreground text-xs">None</span>
						)
					}
				/>

				{data.invoices.length > 0 && (
					<div className="border-t pt-3">
						<div className="text-muted-foreground mb-1.5 text-xs font-medium uppercase tracking-wider">
							Invoices
						</div>
						<ul className="space-y-1">
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
						</ul>
					</div>
				)}
			</CardContent>
		</Card>
	)
}

function Line({ left, right }: { left: string; right: React.ReactNode }) {
	return (
		<div className="flex items-center justify-between gap-2">
			<span className="min-w-0 truncate">{left}</span>
			<span className="shrink-0">{right}</span>
		</div>
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
