import { Link } from 'react-router-dom'
import { Database } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useSections } from '@/hooks/useRecords'

const SECTION_LABEL: Record<string, string> = {
	academic: 'Academic',
	admissions: 'Admissions',
	finance: 'Finance',
	portal: 'Portal',
}

export function RecordIndex() {
	const query = useSections()

	return (
		<QueryState query={query} title="Records">
			{(sections) => (
				<>
					<PageHeader
						title="Records"
						description="Create and edit the college's data directly"
					/>

					{Object.keys(sections).length === 0 ? (
						<Card>
							<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
								<Database className="text-muted-foreground size-6" />
								<div className="font-medium">Nothing you can edit</div>
								<p className="text-muted-foreground max-w-sm text-sm">
									Your roles do not give you write access to any of these records.
								</p>
							</CardContent>
						</Card>
					) : (
						<div className="space-y-4">
							{Object.entries(sections).map(([section, rows]) => (
								<Card key={section}>
									<CardHeader>
										<CardTitle className="text-base">
											{SECTION_LABEL[section] ?? section}
										</CardTitle>
									</CardHeader>
									<CardContent className="pt-3">
										<ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
											{rows.map((row) => (
												<li key={row.doctype}>
													<Link
														to={`/staff/data/${encodeURIComponent(row.doctype)}`}
														className="hover:border-primary/50 hover:bg-muted/40 flex items-center justify-between gap-2 rounded-lg border px-3 py-2.5 transition-colors"
													>
														<span className="min-w-0">
															<span className="block truncate text-sm font-medium">
																{row.label}
															</span>
															{!row.can_write && (
																<span className="text-muted-foreground text-xs">
																	read only
																</span>
															)}
														</span>
														<Badge variant="muted">{row.count}</Badge>
													</Link>
												</li>
											))}
										</ul>
									</CardContent>
								</Card>
							))}
						</div>
					)}
				</>
			)}
		</QueryState>
	)
}
