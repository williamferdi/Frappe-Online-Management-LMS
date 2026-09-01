import { useState } from 'react'
import { Check, ChevronsUpDown, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useLinkOptions, type FieldMeta } from '@/hooks/useRecords'
import { cn } from '@/lib/utils'

export type Values = Record<string, unknown>

/**
 * Frappe's `depends_on` is a JavaScript expression over `doc`.
 *
 * Evaluating arbitrary strings from the server is not something to do lightly,
 * but these come from our own DocType definitions and the alternative is
 * showing every conditional field at once -- the Announcement form would ask
 * for a programme, a level, a term and a course offering on every notice.
 *
 * The common shapes are handled directly and only `eval:` expressions fall
 * through to Function, which is scoped to `doc` and nothing else.
 */
export function dependsOnMet(expression: string | null, values: Values): boolean {
	if (!expression) return true

	const source = expression.startsWith('eval:') ? expression.slice(5) : null
	if (!source) {
		// A bare fieldname: shown when that field is truthy.
		return Boolean(values[expression])
	}

	try {
		// eslint-disable-next-line no-new-func
		return Boolean(new Function('doc', `"use strict"; return (${source});`)(values))
	} catch {
		// A condition we cannot read is not a reason to hide a field.
		return true
	}
}

interface FieldProps {
	field: FieldMeta
	value: unknown
	values: Values
	onChange: (value: unknown) => void
	disabled?: boolean
}

export function RecordField({ field, value, values, onChange, disabled }: FieldProps) {
	if (!dependsOnMet(field.depends_on, values)) return null

	const readOnly = disabled || field.read_only
	const required =
		Boolean(field.reqd) || dependsOnMet(field.mandatory_depends_on, values) === true
			? Boolean(field.reqd)
			: false

	const id = `f-${field.fieldname}`
	const label = field.label || field.fieldname

	if (field.fieldtype === 'Check') {
		return (
			<label className="flex items-center gap-2 py-1.5 text-sm">
				<input
					type="checkbox"
					id={id}
					className="size-3.5"
					checked={Boolean(value)}
					disabled={readOnly}
					onChange={(event) => onChange(event.target.checked ? 1 : 0)}
				/>
				{label}
			</label>
		)
	}

	return (
		<div className="space-y-1.5">
			<Label htmlFor={id}>
				{label}
				{required && <span className="text-destructive"> *</span>}
			</Label>
			<FieldControl
				field={field}
				id={id}
				value={value}
				onChange={onChange}
				readOnly={readOnly}
			/>
			{field.description && (
				<p className="text-muted-foreground text-xs">{field.description}</p>
			)}
		</div>
	)
}

/** The input on its own, with no label. The child-table grid puts the
 *  labels in a header row instead of repeating them on every line. */
export function FieldControl({
	field,
	id,
	value,
	onChange,
	readOnly,
}: {
	field: FieldMeta
	id: string
	value: unknown
	onChange: (value: unknown) => void
	readOnly: boolean
}) {
	const text = value == null ? '' : String(value)

	switch (field.fieldtype) {
		case 'Select': {
			const choices = (field.options || '').split('\n')
			return (
				<select
					id={id}
					value={text}
					disabled={readOnly}
					onChange={(event) => onChange(event.target.value)}
					className="border-input bg-card h-9 w-full rounded-md border px-2 text-sm disabled:opacity-60"
				>
					{choices.map((choice, index) => (
						<option key={`${choice}-${index}`} value={choice}>
							{choice || '— none —'}
						</option>
					))}
				</select>
			)
		}

		case 'Link':
			return (
				<LinkControl
					id={id}
					target={field.options}
					value={text}
					readOnly={readOnly}
					onChange={onChange}
				/>
			)

		case 'Text':
		case 'Small Text':
		case 'Long Text':
			return (
				<Textarea
					id={id}
					value={text}
					disabled={readOnly}
					onChange={(event) => onChange(event.target.value)}
				/>
			)

		case 'Text Editor':
			return (
				<>
					<Textarea
						id={id}
						value={text}
						disabled={readOnly}
						className="min-h-40 font-mono text-xs"
						onChange={(event) => onChange(event.target.value)}
					/>
					{/* Honest about what this is: the field stores HTML and this is a
					    textarea, not a rich editor. Desk has one; say so rather than
					    let somebody paste plain text and wonder why it runs together. */}
					<p className="text-muted-foreground text-xs">
						HTML. Use &lt;p&gt; for paragraphs, or edit this one in Frappe Desk.
					</p>
				</>
			)

		case 'Int':
		case 'Float':
		case 'Currency':
		case 'Percent':
			return (
				<Input
					id={id}
					type="number"
					inputMode="decimal"
					value={text}
					disabled={readOnly}
					onChange={(event) =>
						onChange(event.target.value === '' ? null : Number(event.target.value))
					}
				/>
			)

		case 'Date':
			return (
				<Input
					id={id}
					type="date"
					value={text.slice(0, 10)}
					disabled={readOnly}
					onChange={(event) => onChange(event.target.value || null)}
				/>
			)

		case 'Datetime':
			return (
				<Input
					id={id}
					type="datetime-local"
					// Frappe stores "YYYY-MM-DD HH:MM:SS"; the input wants a T.
					value={text ? text.replace(' ', 'T').slice(0, 16) : ''}
					disabled={readOnly}
					onChange={(event) =>
						onChange(event.target.value ? event.target.value.replace('T', ' ') : null)
					}
				/>
			)

		case 'Time':
			return (
				<Input
					id={id}
					type="time"
					value={text.slice(0, 5)}
					disabled={readOnly}
					onChange={(event) => onChange(event.target.value || null)}
				/>
			)

		case 'Attach':
		case 'Attach Image':
			return (
				<div className="flex items-center gap-2">
					<Input
						id={id}
						value={text}
						disabled={readOnly}
						placeholder="/files/…"
						onChange={(event) => onChange(event.target.value)}
					/>
					{text && (
						<Button variant="outline" size="sm" asChild>
							<a href={text} target="_blank" rel="noreferrer">
								Open
							</a>
						</Button>
					)}
				</div>
			)

		default:
			return (
				<Input
					id={id}
					value={text}
					disabled={readOnly}
					onChange={(event) => onChange(event.target.value)}
				/>
			)
	}
}

/** A Link field: type to search, permission-checked on the server. */
function LinkControl({
	id,
	target,
	value,
	readOnly,
	onChange,
}: {
	id: string
	target: string | null
	value: string
	readOnly: boolean
	onChange: (value: unknown) => void
}) {
	const [open, setOpen] = useState(false)
	const [txt, setTxt] = useState('')
	const options = useLinkOptions(open ? target : null, txt)

	if (readOnly) {
		return <Input id={id} value={value} disabled />
	}

	return (
		<div className="relative">
			<div className="flex items-center gap-1">
				<Input
					id={id}
					value={value}
					readOnly
					placeholder={`Choose a ${target ?? 'record'}`}
					onClick={() => setOpen((current) => !current)}
					className="cursor-pointer"
				/>
				{value ? (
					<Button
						variant="ghost"
						size="icon"
						aria-label="Clear"
						onClick={() => onChange(null)}
					>
						<X />
					</Button>
				) : (
					<Button
						variant="ghost"
						size="icon"
						aria-label="Choose"
						onClick={() => setOpen((current) => !current)}
					>
						<ChevronsUpDown />
					</Button>
				)}
			</div>

			{open && (
				<div className="bg-popover absolute z-20 mt-1 w-full rounded-lg border p-1 shadow-lg">
					<Input
						autoFocus
						value={txt}
						placeholder="Search"
						className="mb-1"
						onChange={(event) => setTxt(event.target.value)}
					/>
					<ul className="max-h-56 overflow-y-auto">
						{(options.data ?? []).map((option) => (
							<li key={option.value}>
								<button
									type="button"
									className="hover:bg-muted flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm"
									onClick={() => {
										onChange(option.value)
										setOpen(false)
										setTxt('')
									}}
								>
									<Check
										className={cn(
											'size-3.5',
											option.value === value ? 'opacity-100' : 'opacity-0',
										)}
									/>
									<span className="min-w-0 truncate">
										{option.label}
										{option.label !== option.value && (
											<span className="text-muted-foreground ml-2 text-xs">
												{option.value}
											</span>
										)}
									</span>
								</button>
							</li>
						))}
						{options.isSuccess && (options.data ?? []).length === 0 && (
							<li className="text-muted-foreground px-2 py-2 text-sm">Nothing found</li>
						)}
					</ul>
				</div>
			)}
		</div>
	)
}
