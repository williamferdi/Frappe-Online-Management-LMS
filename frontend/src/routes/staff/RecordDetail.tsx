import { useNavigate, useParams, useSearchParams, Link } from 'react-router-dom'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { RecordForm } from '@/components/records/RecordForm'
import { Button } from '@/components/ui/button'
import { useDescribe, useRecord } from '@/hooks/useRecords'
import { ArrowLeft } from 'lucide-react'

export function RecordDetail() {
	const { doctype = '', name = '' } = useParams()
	const [params] = useSearchParams()
	const navigate = useNavigate()
	const isNew = name === 'new'

	const meta = useDescribe(doctype)
	const record = useRecord(doctype, isNew ? null : name)

	const back = `/staff/data/${encodeURIComponent(doctype)}`

	return (
		<QueryState query={meta} title={doctype}>
			{(described) => {
				// A new document has no record to wait for; an existing one does.
				if (!isNew && record.isPending) {
					return (
						<>
							<PageHeader title={name} />
							<p className="text-muted-foreground text-sm">Loading…</p>
						</>
					)
				}

				const defaults = Object.fromEntries(
					described.fields
						.filter((field) => field.default != null && field.default !== '')
						.map((field) => [field.fieldname, field.default]),
				)

				// A link may seed a new record: "change this student's level" arrives as
				// ?program_enrollment=…&from_level=2, so the registrar lands on a form
				// that already knows who it is about. Only fieldnames this DocType
				// actually has are taken, and the server still decides what is writable,
				// so a crafted URL buys nothing that typing the value would not.
				const seeded = isNew
					? Object.fromEntries(
							described.fields
								.filter((field) => params.has(field.fieldname))
								.map((field) => [field.fieldname, params.get(field.fieldname)]),
						)
					: {}

				return (
					<>
						<PageHeader
							title={isNew ? `New ${described.label}` : name}
							description={described.label}
							actions={
								<Button variant="outline" size="sm" asChild>
									<Link to={back}>
										<ArrowLeft /> {described.label}
									</Link>
								</Button>
							}
						/>

						<RecordForm
							meta={described}
							name={isNew ? undefined : name}
							initial={isNew ? { ...defaults, ...seeded } : (record.data?.values ?? {})}
							onSaved={(saved) =>
								navigate(
									`/staff/data/${encodeURIComponent(doctype)}/${encodeURIComponent(saved)}`,
									{ replace: true },
								)
							}
							onDeleted={() => navigate(back)}
						/>
					</>
				)
			}}
		</QueryState>
	)
}
