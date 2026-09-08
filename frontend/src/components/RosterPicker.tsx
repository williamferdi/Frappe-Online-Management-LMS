import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { Check, ChevronDown } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * Whose view of a course to look at.
 *
 * A native `<select>` was fine for a demo course with one student on it. A
 * cohort of two hundred is a list nobody scrolls, and the browser's own
 * type-ahead only matches from the start of a name -- no use to anybody who
 * knows the surname.
 *
 * So: type to filter. Hand-written rather than a combobox package, for the
 * same reason `tabs.tsx` and `useDragOrder` are -- the built bundle is
 * committed to git, so a dependency is a permanent addition to what every
 * student downloads. What this owes a keyboard is the ARIA 1.2 combobox
 * pattern: arrows to move, Enter to take, Escape to leave it as it was.
 *
 * Shared by the Student view tab and the assignment preview. Two roster
 * pickers would be two things to keep in step, and this project has spent
 * long enough removing pairs like that.
 */

/** Rendered at most, however long the cohort is. A list past this is not
 *  being read, it is being scrolled past -- the answer is more typing, and
 *  the count says so. */
const SHOWN = 50

export interface RosterEntry {
	name: string
	/** Null happens: a registration can exist before anybody has typed a name
	 *  on the student record behind it. */
	student_name: string | null
}

/** What to call somebody. A blank row is one you cannot tell from the next
 *  blank row, so an unnamed registration shows the thing that identifies it. */
function nameOf(person: RosterEntry) {
	return person.student_name || person.name
}

export function RosterPicker({
	roster,
	value,
	onChange,
	label = 'Seen as',
	anyone = 'A student who has just arrived',
	placeholder,
	allowAnyone = true,
}: {
	roster: RosterEntry[]
	value: string | null
	onChange: (registration: string | null) => void
	label?: string
	/** What the empty choice is called: nobody in particular. */
	anyone?: string
	/** Shown in the empty box. Defaults to whatever the empty choice is
	 *  called, which is the right words wherever there is one. */
	placeholder?: string
	/** Whether there is an empty choice at all. Marking is a walk through a
	 *  class rather than a view of one: there is always somebody in hand, so
	 *  a row meaning nobody would be a row that does nothing. */
	allowAnyone?: boolean
}) {
	const id = useId()
	const [open, setOpen] = useState(false)
	const [query, setQuery] = useState('')
	const [active, setActive] = useState(0)
	const box = useRef<HTMLDivElement>(null)

	const chosen = roster.find((person) => person.name === value)
	const shownValue = open ? query : chosen ? nameOf(chosen) : ''

	const matches = useMemo(() => {
		const needle = query.trim().toLowerCase()
		const people = needle
			? roster.filter((person) => nameOf(person).toLowerCase().includes(needle))
			: roster
		return people.slice(0, SHOWN)
	}, [roster, query])

	// Where there is a reset it is always offered and never filtered away:
	// somebody who has typed a name still has to be able to get back to nobody
	// in particular.
	const options: (RosterEntry | null)[] = allowAnyone ? [null, ...matches] : matches
	const hidden = Math.max(
		0,
		(query.trim()
			? roster.filter((person) =>
					nameOf(person).toLowerCase().includes(query.trim().toLowerCase()),
				).length
			: roster.length) - matches.length,
	)

	useEffect(() => setActive(0), [query, open])

	// Closing on an outside click rather than on blur: blur fires before the
	// click that caused it lands, so choosing with the mouse would close the
	// list out from under the pointer.
	useEffect(() => {
		if (!open) return
		const away = (event: MouseEvent) => {
			if (!box.current?.contains(event.target as Node)) setOpen(false)
		}
		document.addEventListener('mousedown', away)
		return () => document.removeEventListener('mousedown', away)
	}, [open])

	const take = (person: RosterEntry | null) => {
		onChange(person ? person.name : null)
		setQuery('')
		setOpen(false)
	}

	const onKeyDown = (event: React.KeyboardEvent) => {
		if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
			event.preventDefault()
			if (!open) return setOpen(true)
			const step = event.key === 'ArrowDown' ? 1 : -1
			setActive((current) => (current + step + options.length) % options.length)
			return
		}

		if (event.key === 'Enter' && open) {
			event.preventDefault()
			// Nothing to take when a search has matched nobody, and with no
			// reset row there is not even a null to fall back on.
			if (options.length) take(options[active] ?? null)
			return
		}

		if (event.key === 'Escape' && open) {
			event.preventDefault()
			setQuery('')
			setOpen(false)
		}
	}

	return (
		<div
			className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm"
			ref={box}
		>
			<label
				id={`${id}-label`}
				className="text-muted-foreground shrink-0"
				htmlFor={`${id}-input`}
			>
				{label}
			</label>

			{/* Takes what is left, down to a floor and up to a ceiling: this sits
			    in a 260px column on one screen and a full-width row on another. */}
			<div className="relative min-w-44 max-w-72 flex-1">
				<input
					id={`${id}-input`}
					role="combobox"
					aria-expanded={open}
					aria-controls={`${id}-list`}
					aria-autocomplete="list"
					aria-labelledby={`${id}-label`}
					aria-activedescendant={open ? `${id}-option-${active}` : undefined}
					className="border-input bg-background h-9 w-full rounded-md border px-3 pr-8 text-sm"
					placeholder={placeholder ?? anyone}
					value={shownValue}
					onChange={(event) => {
						setQuery(event.target.value)
						setOpen(true)
					}}
					onFocus={() => setOpen(true)}
					onKeyDown={onKeyDown}
				/>
				<ChevronDown className="text-muted-foreground pointer-events-none absolute top-2.5 right-2.5 size-4" />

				{open && (
					<ul
						id={`${id}-list`}
						role="listbox"
						aria-labelledby={`${id}-label`}
						className="bg-popover absolute z-50 mt-1 max-h-72 w-full min-w-52 overflow-y-auto rounded-md border p-1 shadow-md"
					>
						{options.map((person, index) => (
							<li
								key={person?.name ?? '__anyone'}
								id={`${id}-option-${index}`}
								role="option"
								aria-selected={(person?.name ?? null) === value}
								className={cn(
									'flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-sm',
									index === active && 'bg-accent text-accent-foreground',
								)}
								onMouseEnter={() => setActive(index)}
								onClick={() => take(person)}
							>
								<Check
									className={cn(
										'size-3.5 shrink-0',
										(person?.name ?? null) === value ? 'opacity-100' : 'opacity-0',
									)}
								/>
								<span className={cn('truncate', !person && 'text-muted-foreground')}>
									{person ? nameOf(person) : anyone}
								</span>
							</li>
						))}

						{matches.length === 0 && query.trim() && (
							<li className="text-muted-foreground px-2 py-1.5 text-sm">
								Nobody on this course by that name.
							</li>
						)}

						{hidden > 0 && (
							<li className="text-muted-foreground border-t px-2 py-1.5 text-xs">
								{hidden} more — keep typing to narrow it.
							</li>
						)}
					</ul>
				)}
			</div>
		</div>
	)
}
