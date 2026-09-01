import { useState } from 'react'
import { Eye, LoaderCircle, MailWarning } from 'lucide-react'

import {
	DocumentLink,
	ResponseDialog,
	type ResponseKind,
} from '@/components/ResponseDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from '@/components/ui/table'
import { formatDate } from '@/lib/utils'
import type {
	ApplicationDocumentRow,
	MentorConsentRow,
	ReferenceRequestRow,
} from '@/types'

/**
 * What a candidate sent in, and what the people who vouched for them wrote.
 *
 * Shared between the application under review and the student it became: the
 * evidence does not change when the person's status does, and the registrar
 * looking up a current student wants the same certificates and the same
 * reference answers the admissions officer read.
 *
 * Passing `onVerify` turns it into the officer's working screen. Without it --
 * on the student profile -- it stays what it was, a record.
 */
/** What the two references are called, everywhere a person reads them. */
const REFERENCE_LABEL: Record<string, string> = {
	'Pastor-Mentor': 'Spiritual & Ministerial Reference',
	'Professor-Employer': 'Academic & Professional Reference',
}

export function DocumentsCard({
	documents,
	title = 'Applicant documents',
	empty,
	required,
	onVerify,
	onRemarks,
	onResubmit,
	busyRow = null,
	requestedOn = null,
}: {
	documents: ApplicationDocumentRow[]
	title?: string
	empty: string
	/** The document types that gate the checklist step. */
	required?: string[]
	onVerify?: (row: string, verified: boolean) => void
	onRemarks?: (row: string, remarks: string) => void
	onResubmit?: () => void
	busyRow?: string | null
	requestedOn?: string | null
}) {
	const reviewing = Boolean(onVerify)
	const verified = documents.filter((row) => row.verified).length
	const outstanding = documents.filter((row) => !row.verified)

	// The step turns on the required documents, not on all of them, so the
	// officer is told how many of *those* are left rather than being left to
	// wonder why ticking an optional one changed nothing.
	const requiredHeld = required
		? required.filter((type) =>
				documents.some((row) => row.document_type === type && row.verified),
			).length
		: 0

	return (
		<Card>
			<CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
				<CardTitle className="text-base">{title}</CardTitle>
				<div className="flex flex-wrap items-center gap-3">
					{documents.length > 0 && (
						<span className="text-muted-foreground text-xs">
							{verified} of {documents.length} verified
							{required && (
								<>
									{' · '}
									<span
										className={
											requiredHeld === required.length ? 'text-success' : undefined
										}
									>
										{requiredHeld} of {required.length} required
									</span>
								</>
							)}
						</span>
					)}
					{onResubmit && (
						<Button size="sm" variant="outline" onClick={onResubmit}>
							<MailWarning /> Request resubmit
						</Button>
					)}
				</div>
			</CardHeader>
			<CardContent className="p-0 pb-2">
				{requestedOn && outstanding.length > 0 && (
					<p className="text-muted-foreground border-b px-5 pb-3 text-xs">
						Documents were last requested on {formatDate(requestedOn)}. The step stays at{' '}
						<b>Resubmit Requested</b> until the candidate sends something new.
					</p>
				)}

				{documents.length === 0 ? (
					<p className="text-muted-foreground px-5 pb-5 pt-1 text-sm">{empty}</p>
				) : (
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead className="pl-5">Document</TableHead>
								{reviewing ? (
									<>
										<TableHead className="w-24 text-center">Verified</TableHead>
										<TableHead>Remarks</TableHead>
									</>
								) : (
									<>
										<TableHead>Status</TableHead>
										<TableHead>Verified by</TableHead>
									</>
								)}
								<TableHead className="pr-5 text-right">File</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{documents.map((doc) => (
								<TableRow key={doc.name}>
									<TableCell className="pl-5 font-medium">
										{doc.document_type}
										{required?.includes(doc.document_type) && (
											<span className="text-destructive" title="Required">
												{' *'}
											</span>
										)}
									</TableCell>

									{reviewing ? (
										<>
											<TableCell className="text-center">
												{busyRow === doc.name ? (
													<LoaderCircle className="text-muted-foreground mx-auto size-4 animate-spin" />
												) : (
													<Checkbox
														checked={Boolean(doc.verified)}
														disabled={!doc.file}
														aria-label={`${doc.document_type} verified`}
														onChange={(event) => onVerify?.(doc.name, event.target.checked)}
													/>
												)}
											</TableCell>
											<TableCell>
												<Input
													// Keyed on the stored value, so a refetch or a
													// rejected save puts the box back in step.
													key={`${doc.name}:${doc.remarks ?? ''}`}
													defaultValue={doc.remarks ?? ''}
													placeholder="Why it was not accepted"
													className="h-8"
													maxLength={500}
													aria-label={`${doc.document_type} remarks`}
													onBlur={(event) => {
														const value = event.target.value.trim()
														if (value !== (doc.remarks ?? '')) {
															onRemarks?.(doc.name, value)
														}
													}}
												/>
											</TableCell>
										</>
									) : (
										<>
											<TableCell>
												<Badge variant={doc.verified ? 'success' : 'muted'}>
													{doc.verified ? 'Verified' : 'Not verified'}
												</Badge>
											</TableCell>
											<TableCell className="text-muted-foreground text-xs">
												{doc.verified_by || '—'}
											</TableCell>
										</>
									)}

									<TableCell className="pr-5 text-right">
										<DocumentLink file={doc.file} label="Open" />
									</TableCell>
								</TableRow>
							))}
						</TableBody>
					</Table>
				)}

				{reviewing && documents.length > 0 && (
					<p className="text-muted-foreground px-5 pb-1 pt-3 text-xs">
						Ticking every required document moves <b>Applicant Documents Review</b> to
						Verified on its own. Remarks are quoted back to the candidate in the resubmit
						email, so write them to be read.
					</p>
				)}
			</CardContent>
		</Card>
	)
}

export function ResponsesCard({
	application,
	references,
	mentors,
	title = 'References and mentor',
	empty,
}: {
	application: string
	references: ReferenceRequestRow[]
	mentors: MentorConsentRow[]
	title?: string
	empty: string
}) {
	const [open, setOpen] = useState<{ kind: ResponseKind; row: string; name: string } | null>(
		null,
	)

	const rows = [
		...references.map((ref, index) => ({
			kind: 'reference' as ResponseKind,
			row: ref.name,
			// Named for what each one is, the way the apply form asks for them
			// and the way the referee sees their own form titled. The index is
			// the fallback for a row typed in before the type was set.
			label: REFERENCE_LABEL[ref.referee_type ?? ''] ?? `Reference ${index + 1}`,
			who: ref.referee_name || ref.referee_email || 'Not named',
			detail: ref.referee_type,
			sent: ref.sent_on,
			received: ref.submitted_on,
		})),
		...mentors.map((mentor) => ({
			kind: 'mentor' as ResponseKind,
			row: mentor.name,
			label: 'Mentor form',
			who: mentor.mentor_name || mentor.mentor_email || 'Not named',
			detail: mentor.current_position ?? null,
			sent: mentor.sent_on,
			received: mentor.consented_on,
		})),
	]

	return (
		<>
			<Card>
				<CardHeader>
					<CardTitle className="text-base">{title}</CardTitle>
				</CardHeader>
				<CardContent className="p-0 pb-2">
					{rows.length === 0 ? (
						<p className="text-muted-foreground px-5 pb-5 pt-1 text-sm">{empty}</p>
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
