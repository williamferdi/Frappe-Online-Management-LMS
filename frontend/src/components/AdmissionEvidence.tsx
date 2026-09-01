import { useState } from 'react'
import { Eye } from 'lucide-react'

import {
	DocumentLink,
	ResponseDialog,
	type ResponseKind,
} from '@/components/ResponseDialog'
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
 */
export function DocumentsCard({
	documents,
	title = 'Applicant documents',
	empty,
}: {
	documents: ApplicationDocumentRow[]
	title?: string
	empty: string
}) {
	const verified = documents.filter((row) => row.verified).length

	return (
		<Card>
			<CardHeader className="flex-row items-center justify-between">
				<CardTitle className="text-base">{title}</CardTitle>
				{documents.length > 0 && (
					<span className="text-muted-foreground text-xs">
						{verified} of {documents.length} verified
					</span>
				)}
			</CardHeader>
			<CardContent className="p-0 pb-2">
				{documents.length === 0 ? (
					<p className="text-muted-foreground px-5 pb-5 pt-1 text-sm">{empty}</p>
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
							{documents.map((doc) => (
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
			label: `Reference ${index + 1}`,
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
