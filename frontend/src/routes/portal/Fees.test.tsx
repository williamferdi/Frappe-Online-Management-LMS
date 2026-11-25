import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import type { FeesResponse } from '@/types'

const enrollment = {
	name: 'SIB-2026-0003-M.DIV.',
	student: 'SIB-2026-0003',
	student_name: 'Patricia Example',
	program: 'M.DIV.',
	program_name: 'Master of Divinity',
	current_level: '2',
	credits_earned: 0,
	cgpa: null,
	status: 'Active',
}

const invoice = (over: Partial<FeesResponse['invoices'][number]> = {}) => ({
	name: 'FEE-2026-00015',
	fee_type: 'Monthly Tuition',
	category: 'Recurring Tuition',
	term: '2026-T6',
	status: 'Unpaid',
	due_date: '2026-12-09',
	gross_amount: 4332,
	discount_amount: 1332,
	net_amount: 3000,
	paid_amount: 0,
	outstanding_amount: 3000,
	payment_link: null,
	overdue: false,
	...over,
})

const data: FeesResponse = {
	enrollment,
	summary: { billed: 3350, paid: 350, outstanding: 3000, overdue: 0, overdue_count: 0 },
	invoices: [
		invoice(),
		invoice({
			name: 'FEE-2026-00014',
			fee_type: 'Course Registration Fee',
			category: 'Per-Registration',
			term: null,
			status: 'Paid',
			due_date: '2026-11-27',
			gross_amount: 350,
			discount_amount: 0,
			net_amount: 350,
			paid_amount: 350,
			outstanding_amount: 0,
		}),
	],
	payments: [
		{
			name: 'PAY-2026-00001',
			received_on: '2026-11-21',
			amount: 350,
			mode: 'UPI',
			reference_no: 'UTR-998877',
			allocated_amount: 350,
			unallocated_amount: 0,
			applied_to: [
				{
					invoice: 'FEE-2026-00014',
					fee_type: 'Course Registration Fee',
					term: null,
					amount: 350,
				},
			],
		},
	],
	statement: {
		rows: [
			{
				date: '2026-11-27',
				kind: 'Invoice',
				reference: 'FEE-2026-00014',
				particulars: 'Course Registration Fee',
				charge: 350,
				credit: 0,
				balance: 350,
			},
			{
				date: '2026-11-21',
				kind: 'Payment',
				reference: 'PAY-2026-00001',
				particulars: 'UPI · UTR-998877',
				charge: 0,
				credit: 350,
				balance: 0,
			},
			{
				date: '2026-12-09',
				kind: 'Invoice',
				reference: 'FEE-2026-00015',
				particulars: 'Monthly Tuition · 2026-T6 (scholarship −1332)',
				charge: 3000,
				credit: 0,
				balance: 3000,
			},
		],
		charges: 3350,
		credits: 350,
		balance: 3000,
	},
}

let download: ReturnType<typeof vi.fn>
let toastError: ReturnType<typeof vi.fn>

async function renderFees(response: FeesResponse = data) {
	vi.resetModules()
	Object.assign(window, { user: 's@x.invalid', roles: ['Student'], csrf_token: 't' })

	download = vi.fn(async () => new Blob(['%PDF'], { type: 'application/pdf' }))
	toastError = vi.fn()

	vi.doMock('sonner', () => ({ toast: { error: toastError, success: vi.fn() } }))
	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: vi.fn(async () => response), frappeDownload: download }
	})

	URL.createObjectURL = vi.fn(() => 'blob:fake')
	URL.revokeObjectURL = vi.fn()
	vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

	const { Fees } = await import('./Fees')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
	render(
		<QueryClientProvider client={client}>
			<MemoryRouter>
				<Fees />
			</MemoryRouter>
		</QueryClientProvider>,
	)
	await waitFor(() => expect(document.querySelector('[data-slot="skeleton"]')).toBeNull())
}

afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.doUnmock('sonner')
	vi.restoreAllMocks()
})

describe('the fees page', () => {
	it('shows what was billed, what was paid and what is owed', async () => {
		await renderFees()

		// "Paid" is also a badge and a column; the stat labels are the small text.
		const stat = (label: string) =>
			screen.getByText(label, { selector: 'div.text-xs' }).nextSibling
		expect(stat('Billed')).toHaveTextContent('₹3,350')
		expect(stat('Paid')).toHaveTextContent('₹350')
		expect(stat('Outstanding')).toHaveTextContent('₹3,000')
	})

	it('keeps a paid invoice on the page, which it never used to', async () => {
		// Pay an invoice and it vanished from every screen.
		await renderFees()

		const row = screen.getByText('FEE-2026-00014').closest('tr') as HTMLElement
		expect(within(row).getByText('Paid')).toBeInTheDocument()
		expect(within(row).getByText('Course Registration Fee')).toBeInTheDocument()
	})

	it('shows the scholarship on the invoice it reduced', async () => {
		await renderFees()

		const row = screen.getByText('FEE-2026-00015').closest('tr') as HTMLElement
		expect(within(row).getByText(/Scholarship −₹1,332/)).toBeInTheDocument()
		expect(within(row).getByText('Unpaid')).toBeInTheDocument()
	})

	it('flags an overdue invoice and the total that is late', async () => {
		await renderFees({
			...data,
			summary: { ...data.summary, overdue: 3000, overdue_count: 1 },
			invoices: [invoice({ overdue: true, due_date: '2026-11-01' })],
		})

		expect(screen.getByText('Overdue', { selector: '[data-slot="badge"]' })).toBeInTheDocument()
		expect(screen.getByText('1 invoice')).toBeInTheDocument()
	})

	it('shows a waived invoice as waived, with nothing owed on it', async () => {
		await renderFees({
			...data,
			invoices: [
				invoice({ status: 'Waived', outstanding_amount: 0, paid_amount: 0, net_amount: 3000 }),
			],
		})

		const row = screen.getByText('FEE-2026-00015').closest('tr') as HTMLElement
		expect(within(row).getByText('Waived')).toBeInTheDocument()
		expect(within(row).queryByRole('link', { name: 'Pay' })).not.toBeInTheDocument()
	})

	it('offers Pay only where there is a link and something left to pay', async () => {
		await renderFees({
			...data,
			invoices: [invoice({ payment_link: 'https://pay.example.invalid/x' })],
		})

		expect(screen.getByRole('link', { name: 'Pay' })).toHaveAttribute(
			'href',
			'https://pay.example.invalid/x',
		)
	})

	it('says plainly when nothing has been billed yet', async () => {
		await renderFees({
			...data,
			invoices: [],
			payments: [],
			summary: { billed: 0, paid: 0, outstanding: 0, overdue: 0, overdue_count: 0 },
		})

		expect(screen.getByText('Nothing has been billed yet')).toBeInTheDocument()
	})
})

describe('payments and receipts', () => {
	async function openPayments() {
		await userEvent.click(screen.getByRole('tab', { name: /payments & receipts/i }))
	}

	it('lists a payment with what it was applied to', async () => {
		await renderFees()
		await openPayments()

		expect(screen.getByText('UTR-998877', { exact: false })).toBeInTheDocument()
		expect(screen.getByText(/₹350 towards Course Registration Fee/)).toBeInTheDocument()
		expect(screen.getByText('PAY-2026-00001')).toBeInTheDocument()
	})

	it('downloads that payment’s receipt, naming it', async () => {
		await renderFees()
		await openPayments()

		await userEvent.click(screen.getByRole('button', { name: /download receipt/i }))

		await waitFor(() =>
			expect(download).toHaveBeenCalledWith('sibbcs.api.student_fees.receipt', {
				payment: 'PAY-2026-00001',
			}),
		)
	})

	it('says what went wrong when the PDF cannot be made, and points at Print', async () => {
		await renderFees()
		await openPayments()
		download.mockRejectedValueOnce(new Error('The PDF could not be made just now. Use Print instead.'))

		await userEvent.click(screen.getByRole('button', { name: /download receipt/i }))

		await waitFor(() =>
			expect(toastError).toHaveBeenCalledWith(
				'The PDF could not be made just now. Use Print instead.',
			),
		)
	})

	it('says so when nothing has been paid yet', async () => {
		await renderFees({ ...data, payments: [] })
		await openPayments()

		expect(screen.getByText('No payments recorded yet')).toBeInTheDocument()
	})

	it('states money held as credit', async () => {
		await renderFees({
			...data,
			payments: [{ ...data.payments[0], amount: 500, unallocated_amount: 150 }],
		})
		await openPayments()

		expect(screen.getByText(/₹150 held as credit/)).toBeInTheDocument()
	})
})

describe('the statement', () => {
	async function openStatement() {
		await userEvent.click(screen.getByRole('tab', { name: /statement/i }))
	}

	it('runs a balance down the page and closes on what is owed', async () => {
		await renderFees()
		await openStatement()

		const rows = screen.getAllByRole('row').slice(1)
		expect(rows).toHaveLength(3)
		expect(within(rows[2]).getByText('₹3,000', { selector: 'td:last-child' })).toBeInTheDocument()
		expect(screen.getByText('Outstanding', { selector: '[data-slot="badge"]' })).toBeInTheDocument()
		expect(screen.getByText(/Charged ₹3,350 · Paid or waived ₹350/)).toBeInTheDocument()
	})

	it('prints from the browser, which needs no renderer on the server', async () => {
		await renderFees()
		await openStatement()
		const print = vi.spyOn(window, 'print').mockImplementation(() => {})

		await userEvent.click(screen.getByRole('button', { name: /print/i }))

		expect(print).toHaveBeenCalledOnce()
	})

	it('marks only the statement to be printed', async () => {
		await renderFees()
		await openStatement()

		const area = document.querySelector('.print-area') as HTMLElement
		expect(area).not.toBeNull()
		expect(within(area).getByText('Statement of account')).toBeInTheDocument()
		// The buttons are not part of the paper.
		expect(area.contains(screen.getByRole('button', { name: /download pdf/i }))).toBe(false)
	})

	it('downloads the statement as a PDF', async () => {
		await renderFees()
		await openStatement()

		await userEvent.click(screen.getByRole('button', { name: /download pdf/i }))

		await waitFor(() =>
			expect(download).toHaveBeenCalledWith('sibbcs.api.student_fees.statement', {}),
		)
	})

	it('shows a settled account as settled', async () => {
		await renderFees({
			...data,
			statement: { ...data.statement, balance: 0 },
		})
		await openStatement()

		expect(screen.getByText('Settled', { selector: '[data-slot="badge"]' })).toBeInTheDocument()
	})
})
