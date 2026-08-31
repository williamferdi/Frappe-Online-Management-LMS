import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
	ArrowLeft,
	CheckCircle2,
	Circle,
	Eye,
	Lock,
	LoaderCircle,
	Send,
} from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import {
	DocumentLink,
	ResponseDialog,
	type ResponseKind,
} from '@/components/ResponseDialog'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from '@/components/ui/table'
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
					<Summary data={data} />
				</div>
			</div>

			<Documents data={data} />
			<Responses data={data} />
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

function Documents({ data }: { data: Detail }) {
	const verified = data.documents.filter((row) => row.verified).length

	return (
		<Card className="mt-4">
			<CardHeader className="flex-row items-center justify-between">
				<CardTitle className="text-base">Applicant documents</CardTitle>
				{data.documents.length > 0 && (
					<span className="text-muted-foreground text-xs">
						{verified} of {data.documents.length} verified
					</span>
				)}
			</CardHeader>
			<CardContent className="p-0 pb-2">
				{data.documents.length === 0 ? (
					<p className="text-muted-foreground px-5 pb-5 pt-1 text-sm">
						Nothing uploaded yet. The candidate uploads these through the link on
						their application; the upload page is at <code>/apply</code>.
					</p>
				) : (
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead className="pl-5">Document</TableHead>
								<TableHead>Status</TableHead>
								<TableHead>Verified by</TableHead>
								<TableHead className="pr-5 text-right">File</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{data.documents.map((doc) => (
								<TableRow key={doc.name}>
									<TableCell className="pl-5 font-medium">{doc.document_type}</TableCell>
									<TableCell>
										<Badge variant={doc.verified ? 'success' : 'muted'}>
											{doc.verified ? 'Verified' : 'Not verified'}
										</Badge>
									</TableCell>
									<TableCell className="text-muted-foreground text-xs">
										{doc.verified_by || '—'}
									</TableCell>
									<TableCell className="pr-5 text-right">
										<DocumentLink file={doc.file} label="Open" />
									</TableCell>
								</TableRow>
							))}
						</TableBody>
					</Table>
				)}
			</CardContent>
		</Card>
	)
}

function Responses({ data }: { data: Detail }) {
	const [open, setOpen] = useState<{ kind: ResponseKind; row: string; name: string } | null>(
		null,
	)
	const application = data.application.name

	const rows = [
		...data.references.map((ref, index) => ({
			kind: 'reference' as ResponseKind,
			row: ref.name,
			label: `Reference ${index + 1}`,
			who: ref.referee_name || ref.referee_email || 'Not named',
			detail: ref.referee_type,
			sent: ref.sent_on,
			received: ref.submitted_on,
			verdict: ref.recommendation,
		})),
		...data.mentors.map((mentor) => ({
			kind: 'mentor' as ResponseKind,
			row: mentor.name,
			label: 'Mentor form',
			who: mentor.mentor_name || mentor.mentor_email || 'Not named',
			detail: null,
			sent: mentor.sent_on,
			received: mentor.consented_on,
			verdict: null,
		})),
	]

	return (
		<>
			<Card className="mt-4">
				<CardHeader>
					<CardTitle className="text-base">References and mentor</CardTitle>
				</CardHeader>
				<CardContent className="p-0 pb-2">
					{rows.length === 0 ? (
						<p className="text-muted-foreground px-5 pb-5 pt-1 text-sm">
							No requests sent yet. Use <b>Resend requests</b> on the reference and
							mentor steps above to send them.
						</p>
					) : (
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead className="pl-5">Request</TableHead>
									<TableHead>Who</TableHead>
									<TableHead>Sent</TableHead>
									<TableHead>Received</TableHead>
									<TableHead className="pr-5 text-right">Response</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{rows.map((row) => (
									<TableRow key={row.row}>
										<TableCell className="pl-5 font-medium">{row.label}</TableCell>
										<TableCell>
											<div className="text-sm">{row.who}</div>
											{row.detail && (
												<div className="text-muted-foreground text-xs">{row.detail}</div>
											)}
										</TableCell>
										<TableCell className="text-muted-foreground text-xs">
											{row.sent ? formatDate(row.sent) : 'Not sent'}
										</TableCell>
										<TableCell>
											{row.received ? (
												<Badge variant="success">{formatDate(row.received)}</Badge>
											) : (
												<Badge variant="muted">Awaiting</Badge>
											)}
										</TableCell>
										<TableCell className="pr-5 text-right">
											{row.received ? (
												<Button
													size="sm"
													variant="outline"
													onClick={() =>
														setOpen({ kind: row.kind, row: row.row, name: row.who })
													}
												>
													<Eye /> Read
												</Button>
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

			<ResponseDialog
				kind={open?.kind ?? 'reference'}
				application={application}
				row={open?.row ?? null}
				name={open?.name ?? ''}
				onClose={() => setOpen(null)}
			/>
		</>
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
