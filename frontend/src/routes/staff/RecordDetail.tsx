import { useNavigate, useParams, Link } from 'react-router-dom'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { RecordForm } from '@/components/records/RecordForm'
import { Button } from '@/components/ui/button'
import { useDescribe, useRecord } from '@/hooks/useRecords'
import { ArrowLeft } from 'lucide-react'

export function RecordDetail() {
	const { doctype = '', name = '' } = useParams()
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
							initial={isNew ? defaults : (record.data?.values ?? {})}
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
