import { useQuery } from '@tanstack/react-query'
import { ExternalLink, LoaderCircle } from 'lucide-react'

import { RichText } from '@/components/RichText'
import { Button } from '@/components/ui/button'
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from '@/components/ui/dialog'
import { frappeGet, FrappeError } from '@/lib/frappe'
import { formatDate } from '@/lib/utils'

interface Response {
	referee?: string
	mentor?: string
	email?: string
	type?: string
	recommendation?: string
	submitted_on?: string | null
	consented_on?: string | null
	html: string
}

export type ResponseKind = 'reference' | 'mentor'

const ENDPOINT: Record<ResponseKind, string> = {
	reference: 'sibbcs.admissions.reference_form.view',
	mentor: 'sibbcs.admissions.mentor_form.view',
}

/**
 * Shows what a referee or mentor actually wrote.
 *
 * `reference_form.view` and `mentor_form.view` already render the answers as a
 * table and already check permissions, so this asks them rather than
 * re-deriving the questions on this side -- the two would drift the first time
 * the form changed.
 */
export function ResponseDialog({
	kind,
	application,
	row,
	name,
	onClose,
}: {
	kind: ResponseKind
	application: string
	row: string | null
	name: string
	onClose: () => void
}) {
	const query = useQuery({
		queryKey: ['response', kind, application, row],
		queryFn: () => frappeGet<Response>(ENDPOINT[kind], { application, row }),
		enabled: Boolean(row),
	})

	const data = query.data
	const submitted = data?.submitted_on ?? data?.consented_on ?? null

	return (
		<Dialog open={Boolean(row)} onOpenChange={(open) => !open && onClose()}>
			<DialogContent className="max-h-[85svh] max-w-2xl overflow-y-auto">
				<DialogHeader>
					<DialogTitle>{data?.referee || data?.mentor || name}</DialogTitle>
					<DialogDescription>
						{data?.email}
						{data?.type && <> · {data.type}</>}
						{submitted && <> · submitted {formatDate(submitted)}</>}
					</DialogDescription>
				</DialogHeader>

				{query.isPending && (
					<div className="text-muted-foreground flex items-center gap-2 py-8 text-sm">
						<LoaderCircle className="size-4 animate-spin" /> Loading the response
					</div>
				)}

				{query.error && (
					<p className="text-destructive py-6 text-sm">
						{query.error instanceof FrappeError
							? query.error.message
							: 'That response could not be loaded.'}
					</p>
				)}

				{data && !query.isPending && (
					<>
						{data.recommendation && (
							<div className="bg-muted/60 rounded-lg px-3 py-2 text-sm">
								<span className="text-muted-foreground">Recommendation: </span>
								<span className="font-medium">{data.recommendation}</span>
							</div>
						)}

						{data.html ? (
							<RichText
								html={data.html}
								className="[&_td]:border-b [&_td]:py-2 [&_table]:w-full"
							/>
						) : (
							<p className="text-muted-foreground py-6 text-sm">
								Nothing has been submitted yet.
							</p>
						)}
					</>
				)}
			</DialogContent>
		</Dialog>
	)
}

/** A file the candidate uploaded. Private files need the session, so a link. */
export function DocumentLink({ file, label }: { file: string | null; label: string }) {
	if (!file) return <span className="text-muted-foreground text-xs">No file</span>
	return (
		<Button variant="ghost" size="sm" className="h-7 px-2 text-xs" asChild>
			<a href={file} target="_blank" rel="noreferrer">
				{label} <ExternalLink />
			</a>
		</Button>
	)
}
