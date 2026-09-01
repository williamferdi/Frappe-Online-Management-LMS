import { useEffect, useState, type FormEvent } from 'react'
import { LoaderCircle, Plus, Save, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import {
	FieldControl,
	RecordField,
	dependsOnMet,
	type Values,
} from '@/components/records/Field'
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
import {
	useDeleteRecord,
	useSaveRecord,
	type Describe,
	type FieldMeta,
} from '@/hooks/useRecords'
import { FrappeError } from '@/lib/frappe'

const LAYOUT = new Set(['Section Break', 'Column Break', 'Tab Break', 'Fold', 'HTML'])
const CHILD = new Set(['Table', 'Table MultiSelect'])

interface Group {
	title: string | null
	fields: FieldMeta[]
}

/** Split the flat field list on Section Breaks, the way Desk lays it out. */
function grouped(fields: FieldMeta[]): Group[] {
	const groups: Group[] = []
	let current: Group = { title: null, fields: [] }

	for (const field of fields) {
		if (field.fieldtype === 'Section Break') {
			if (current.fields.length) groups.push(current)
			current = { title: field.label, fields: [] }
			continue
		}
		if (LAYOUT.has(field.fieldtype)) continue
		current.fields.push(field)
	}
	if (current.fields.length) groups.push(current)
	return groups
}

export function RecordForm({
	meta,
	name,
	initial,
	onSaved,
	onDeleted,
}: {
	meta: Describe
	name?: string
	initial: Values
	onSaved: (name: string) => void
	onDeleted?: () => void
}) {
	const [values, setValues] = useState<Values>(initial)
	const [confirmDelete, setConfirmDelete] = useState(false)
	const save = useSaveRecord(meta.doctype)
	const remove = useDeleteRecord(meta.doctype)

	// A save refetches the record; without this the form keeps showing what was
	// typed rather than what the server made of it.
	useEffect(() => setValues(initial), [initial])

	const editable = name ? meta.can_write : meta.can_create

	function set(fieldname: string, value: unknown) {
		setValues((current) => ({ ...current, [fieldname]: value }))
	}

	function onSubmit(event: FormEvent) {
		event.preventDefault()
		save.mutate(
			{ name, values },
			{
				onSuccess: (result) => {
					toast.success(name ? 'Saved' : `Created ${result.name}`)
					onSaved(result.name)
				},
				onError: (error) =>
					toast.error(
						error instanceof FrappeError ? error.message : 'That could not be saved.',
					),
			},
		)
	}

	return (
		<form onSubmit={onSubmit} className="space-y-4" noValidate>
			{grouped(meta.fields).map((group, index) => (
				<Card key={group.title ?? index}>
					{group.title && (
						<CardHeader>
							<CardTitle className="text-base">{group.title}</CardTitle>
						</CardHeader>
					)}
					<CardContent className={group.title ? 'pt-3' : ''}>
						<div className="grid gap-4 sm:grid-cols-2">
							{group.fields.map((field) =>
								CHILD.has(field.fieldtype) ? (
									<div key={field.fieldname} className="sm:col-span-2">
										<ChildTable
											field={field}
											columns={meta.children[field.fieldname] ?? []}
											rows={(values[field.fieldname] as Values[]) ?? []}
											disabled={!editable || field.read_only}
											onChange={(rows) => set(field.fieldname, rows)}
										/>
									</div>
								) : (
									<div
										key={field.fieldname}
										className={
											['Text Editor', 'Long Text', 'Text', 'Small Text'].includes(
												field.fieldtype,
											)
												? 'sm:col-span-2'
												: undefined
										}
									>
										<RecordField
											field={field}
											value={values[field.fieldname]}
											values={values}
											disabled={!editable}
											onChange={(value) => set(field.fieldname, value)}
										/>
									</div>
								),
							)}
						</div>
					</CardContent>
				</Card>
			))}

			<div className="flex flex-wrap items-center gap-2">
				<Button type="submit" disabled={!editable || save.isPending}>
					{save.isPending ? <LoaderCircle className="animate-spin" /> : <Save />}
					{name ? 'Save' : 'Create'}
				</Button>

				{name && meta.can_delete && (
					<Button
						type="button"
						variant="outline"
						className="ml-auto"
						onClick={() => setConfirmDelete(true)}
					>
						<Trash2 /> Delete
					</Button>
				)}

				{!editable && (
					<span className="text-muted-foreground text-sm">
						You have read-only access to {meta.label}.
					</span>
				)}
			</div>

			<Dialog open={confirmDelete} onOpenChange={(open) => !open && setConfirmDelete(false)}>
				<DialogContent>
					<DialogHeader>
						<DialogTitle>Delete {name}?</DialogTitle>
						<DialogDescription>
							This cannot be undone. If anything else points at this record the
							deletion is refused and the message will say what.
						</DialogDescription>
					</DialogHeader>
					<DialogFooter>
						<Button variant="outline" onClick={() => setConfirmDelete(false)}>
							Cancel
						</Button>
						<Button
							variant="destructive"
							disabled={remove.isPending}
							onClick={() =>
								remove.mutate(name!, {
									onSuccess: () => {
										setConfirmDelete(false)
										toast.success(`${name} deleted`)
										onDeleted?.()
									},
									onError: (error) =>
										toast.error(
											error instanceof FrappeError
												? error.message
												: 'That could not be deleted.',
										),
								})
							}
						>
							{remove.isPending && <LoaderCircle className="animate-spin" />}
							Delete
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</form>
	)
}

/**
 * A child table as a table.
 *
 * The first version rendered each row as a bordered card of labelled fields,
 * which for the thirteen-step admission checklist meant the word "Status" and
 * its help text thirteen times, four column labels repeated per row, and
 * nothing lining up between rows. A grid of records wants column headers once
 * and short rows underneath -- which is also how the same data reads in Desk.
 */
function ChildTable({
	field,
	columns,
	rows,
	disabled,
	onChange,
}: {
	field: FieldMeta
	columns: FieldMeta[]
	rows: Values[]
	disabled: boolean
	onChange: (rows: Values[]) => void
}) {
	// Frappe already marks the columns worth seeing in a grid; the fallback is
	// for child tables where nobody has said.
	const marked = columns.filter((column) => column.in_list_view)
	const visible = (marked.length ? marked : columns.slice(0, 5)).filter(
		(column) => !CHILD.has(column.fieldtype),
	)

	// Said once, under the table, rather than on every row.
	const notes = visible.filter((column) => column.description)

	return (
		<div>
			<div className="mb-2 flex items-center justify-between">
				<span className="text-sm font-medium">{field.label || field.fieldname}</span>
				<div className="flex items-center gap-2">
					<span className="text-muted-foreground text-xs">
						{rows.length} {rows.length === 1 ? 'row' : 'rows'}
					</span>
					{!disabled && (
						<Button
							type="button"
							size="sm"
							variant="outline"
							onClick={() => onChange([...rows, {}])}
						>
							<Plus /> Row
						</Button>
					)}
				</div>
			</div>

			{rows.length === 0 ? (
				<p className="text-muted-foreground rounded-lg border border-dashed px-4 py-6 text-center text-sm">
					No rows yet.
				</p>
			) : (
				<div className="overflow-x-auto rounded-lg border">
					<table className="w-full text-sm">
						<thead>
							<tr className="bg-muted/50 border-b">
								{visible.map((column) => (
									<th
										key={column.fieldname}
										title={column.description ?? undefined}
										className="text-muted-foreground px-2.5 py-2 text-left text-xs font-medium uppercase tracking-wider whitespace-nowrap"
									>
										{column.label || column.fieldname}
										{Boolean(column.reqd) && <span className="text-destructive"> *</span>}
									</th>
								))}
								{!disabled && <th className="w-10" />}
							</tr>
						</thead>
						<tbody>
							{rows.map((row, index) => (
								<tr key={index} className="border-b last:border-0">
									{visible.map((column) => (
										<td key={column.fieldname} className="px-2.5 py-1.5 align-middle">
											{column.read_only || disabled ? (
												// A disabled input for something nobody can change is a
												// box that looks broken; plain text says what it is.
												<span className="text-muted-foreground block truncate py-1.5">
													{row[column.fieldname] == null || row[column.fieldname] === ''
														? '—'
														: String(row[column.fieldname])}
												</span>
											) : (
												<div className="[&_input]:h-8 [&_select]:h-8 [&_textarea]:min-h-8 [&_textarea]:py-1.5 min-w-32">
													<FieldControl
														field={column}
														id={`${field.fieldname}-${index}-${column.fieldname}`}
														value={row[column.fieldname]}
														readOnly={false}
														onChange={(value) =>
															onChange(
																rows.map((current, i) =>
																	i === index
																		? { ...current, [column.fieldname]: value }
																		: current,
																),
															)
														}
													/>
												</div>
											)}
										</td>
									))}
									{!disabled && (
										<td className="px-1 py-1.5 align-middle">
											<Button
												type="button"
												variant="ghost"
												size="icon"
												className="size-8"
												aria-label={`Remove row ${index + 1}`}
												onClick={() => onChange(rows.filter((_, i) => i !== index))}
											>
												<Trash2 />
											</Button>
										</td>
									)}
								</tr>
							))}
						</tbody>
					</table>
				</div>
			)}

			{notes.length > 0 && (
				<ul className="text-muted-foreground mt-2 space-y-0.5 text-xs">
					{notes.map((column) => (
						<li key={column.fieldname}>
							<span className="font-medium">{column.label || column.fieldname}:</span>{' '}
							{column.description}
						</li>
					))}
				</ul>
			)}
		</div>
	)
}

export { dependsOnMet }
