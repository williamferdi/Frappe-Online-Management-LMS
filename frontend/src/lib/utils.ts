import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs))
}

const INR = new Intl.NumberFormat('en-IN', {
	style: 'currency',
	currency: 'INR',
	maximumFractionDigits: 0,
})

export function money(value: number | string | null | undefined): string {
	const amount = typeof value === 'string' ? Number(value) : (value ?? 0)
	return INR.format(Number.isFinite(amount) ? amount : 0)
}

export function initials(name: string): string {
	return name
		.split(/\s+/)
		.filter(Boolean)
		.slice(0, 2)
		.map((part) => part[0]?.toUpperCase() ?? '')
		.join('')
}

const DATE = new Intl.DateTimeFormat('en-IN', {
	day: 'numeric',
	month: 'short',
	year: 'numeric',
})

export function formatDate(value: string | null | undefined): string {
	if (!value) return '—'
	const parsed = new Date(value)
	return Number.isNaN(parsed.valueOf()) ? '—' : DATE.format(parsed)
}

/** Frappe stores a Time as "HH:MM:SS"; students read "6:30 pm". */
export function formatTime(value: string | null | undefined): string {
	if (!value) return ''
	const [hours, minutes] = value.split(':').map(Number)
	if (Number.isNaN(hours)) return ''
	const suffix = hours >= 12 ? 'pm' : 'am'
	const hour = hours % 12 === 0 ? 12 : hours % 12
	return `${hour}:${String(minutes ?? 0).padStart(2, '0')} ${suffix}`
}
