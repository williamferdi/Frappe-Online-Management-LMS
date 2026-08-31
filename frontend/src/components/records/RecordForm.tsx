import { useEffect, useState, type FormEvent } from 'react'
import { LoaderCircle, Plus, Save, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { RecordField, dependsOnMet, type Values } from '@/components/records/Field'
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
	// A child grid showing forty columns is unreadable; Frappe already marks
	// the ones worth seeing, and falls back to the first few.
	const shown = columns.filter((c) => c.in_list_view)
	const visible = shown.length ? shown : columns.slice(0, 4)

	return (
		<div>
			<div className="mb-2 flex items-center justify-between">
				<span className="text-sm font-medium">{field.label || field.fieldname}</span>
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

			{rows.length === 0 ? (
				<p className="text-muted-foreground text-sm">No rows.</p>
			) : (
				<div className="space-y-2">
					{rows.map((row, index) => (
						<div key={index} className="flex flex-wrap items-end gap-2 rounded-lg border p-3">
							{visible.map((column) => (
								<div key={column.fieldname} className="min-w-36 flex-1">
									<RecordField
										field={index === 0 ? column : { ...column, label: column.label }}
										value={row[column.fieldname]}
										values={row}
										disabled={disabled}
										onChange={(value) =>
											onChange(
												rows.map((r, i) =>
													i === index ? { ...r, [column.fieldname]: value } : r,
												),
											)
										}
									/>
								</div>
							))}
							{!disabled && (
								<Button
									type="button"
									variant="ghost"
									size="icon"
									aria-label="Remove row"
									onClick={() => onChange(rows.filter((_, i) => i !== index))}
								>
									<Trash2 />
								</Button>
							)}
						</div>
					))}
				</div>
			)}
		</div>
	)
}

export { dependsOnMet }
