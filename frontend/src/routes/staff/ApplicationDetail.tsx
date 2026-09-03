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
import { ExamCard } from '@/components/ExamCard'
import { Face } from '@/components/Face'
import { InterviewCard } from '@/components/InterviewCard'
import { ScholarshipCard } from '@/components/ScholarshipCard'
import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from '@/components/ui/dialog'
import { Progress } from '@/components/ui/progress'
import { Textarea } from '@/components/ui/textarea'
import {
	useApplication,
	useRequestResubmit,
	useReviewDocument,
	useRunAction,
	useUpdateStep,
} from '@/hooks/useStaff'
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
			{(data) => <Loaded data={data} onChanged={() => void query.refetch()} />}
		</QueryState>
	)
}

function Loaded({ data, onChanged }: { data: Detail; onChanged: () => void }) {
	const record = data.application
	const board = data.checklist
	const done = board.rows.filter((row) => row.done).length
	const percent = Math.round((done / board.rows.length) * 100)

	return (
		<>
			<PageHeader
				title={record.full_name}
				avatar={
					<Face name={record.full_name} photo={record.photo} className="size-12" />
				}
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
				<Documents data={data} />
				<ResponsesCard
					application={data.application.name}
					references={data.references}
					mentors={data.mentors}
					empty="No requests sent yet. Use Resend requests on the reference and mentor steps above to send them."
				/>
			</div>

			<div className="mt-4 grid gap-4 xl:grid-cols-2">
				<ExamCard
					application={record.name}
					exam={data.exam}
					canWrite={board.can_write}
				/>
				<InterviewCard
					application={record.name}
					interview={data.interview}
					outcomes={data.interview_outcomes}
					canWrite={board.can_write}
				/>
			</div>

			{data.scholarship && (
				<div className="mt-4">
					<ScholarshipCard
						scholarship={data.scholarship}
						onDecided={onChanged}
					/>
				</div>
			)}
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

/**
 * The officer's working copy of the documents table.
 *
 * Two things happen here that do not happen on the student profile: a tick box
 * per row, and one button that asks the candidate for whatever is still
 * outstanding. Neither decides the checklist step -- ticking the last required
 * document moves it server-side, and this screen simply refetches and shows
 * where it landed.
 */
function Documents({ data }: { data: Detail }) {
	const application = data.application.name
	const [asking, setAsking] = useState(false)
	const [message, setMessage] = useState('')
	const [busyRow, setBusyRow] = useState<string | null>(null)

	const review = useReviewDocument(application)
	const resubmit = useRequestResubmit(application)

	// The same two cases the server distinguishes: never arrived, and
	// arrived but not accepted. A row with no file behind it is the first
	// of those, whatever the table shows.
	const outstanding = [
		...data.required_documents
			.filter(
				(type) =>
					!data.documents.some((row) => row.document_type === type && row.file),
			)
			.map((type) => ({ type, missing: true })),
		...data.documents
			.filter((row) => row.file && !row.verified)
			.map((row) => ({ type: row.document_type, missing: false })),
	]

	function save(row: string, values: { verified?: boolean; remarks?: string }) {
		setBusyRow(row)
		review.mutate(
			{ row, ...values },
			{
				onError: (error) =>
					toast.error(
						error instanceof FrappeError ? error.message : 'That change was not saved.',
					),
				onSettled: () => setBusyRow(null),
			},
		)
	}

	return (
		<>
			<DocumentsCard
				documents={data.documents}
				required={data.required_documents}
				requestedOn={data.application.docs_resubmit_requested_on}
				busyRow={busyRow}
				empty="Nothing uploaded yet. The candidate uploads these through the link on their application; the upload page is at /apply."
				onVerify={
					data.checklist.can_write
						? (row, verified) => save(row, { verified })
						: undefined
				}
				onRemarks={
					data.checklist.can_write ? (row, remarks) => save(row, { remarks }) : undefined
				}
				onResubmit={
					data.checklist.can_write && outstanding.length > 0
						? () => setAsking(true)
						: undefined
				}
			/>

			<Dialog open={asking} onOpenChange={(open) => !open && setAsking(false)}>
				<DialogContent>
					<DialogHeader>
						<DialogTitle>Ask for these documents again</DialogTitle>
						<DialogDescription>
							One email to {data.application.email}, with a link that lets them upload
							without logging in. The step moves to Resubmit Requested until something
							new arrives.
						</DialogDescription>
					</DialogHeader>

					<ul className="text-sm">
						{outstanding.map((item) => (
							<li key={item.type} className="flex items-center justify-between gap-2 py-1">
								<span>{item.type}</span>
								<Badge variant={item.missing ? 'destructive' : 'warning'}>
									{item.missing ? 'Never received' : 'Not accepted'}
								</Badge>
							</li>
						))}
					</ul>

					<Textarea
						value={message}
						onChange={(event) => setMessage(event.target.value)}
						placeholder="Anything else you want to say (optional)"
						rows={3}
					/>
					<p className="text-muted-foreground text-xs">
						Your remarks on each document are quoted in the email, so the candidate knows
						what was wrong with each one.
					</p>

					<DialogFooter>
						<Button variant="outline" onClick={() => setAsking(false)}>
							Cancel
						</Button>
						<Button
							disabled={resubmit.isPending}
							onClick={() =>
								resubmit.mutate(message.trim() || undefined, {
									onSuccess: (result) => {
										toast.success(`Asked ${result.sent_to} for ${result.items.length} documents`)
										setAsking(false)
										setMessage('')
									},
									onError: (error) =>
										toast.error(
											error instanceof FrappeError
												? error.message
												: 'The request could not be sent.',
										),
								})
							}
						>
							{resubmit.isPending ? <LoaderCircle className="animate-spin" /> : <Send />}
							Send the request
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</>
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
						data.exam.result ? (
							<Badge
								variant={data.exam.result.result === 'Pass' ? 'success' : 'destructive'}
							>
								{data.exam.result.total}% {data.exam.result.result}
							</Badge>
						) : data.exam.submission ? (
							// Sat and waiting to be read is not the same as never sat,
							// and only one of the two is anybody's job to finish.
							<Badge variant="warning">Sat, not marked</Badge>
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
