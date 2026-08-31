import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { frappeGet, frappePost } from '@/lib/frappe'
import type {
	InvoicesResponse,
	OutstandingInvoice,
	PaymentsResponse,
	RoleCount,
	ScholarshipsResponse,
	UsersResponse,
} from '@/types'

export const financeKeys = {
	all: ['finance'] as const,
	invoices: (filters: InvoiceFilters) => ['finance', 'invoices', filters] as const,
	payments: (search: string) => ['finance', 'payments', search] as const,
	outstanding: (student: string) => ['finance', 'outstanding', student] as const,
	scholarships: ['finance', 'scholarships'] as const,
	users: (filters: UserFilters) => ['finance', 'users', filters] as const,
	roleSummary: ['finance', 'role-summary'] as const,
}

export interface InvoiceFilters {
	status?: string
	category?: string
	search?: string
	overdue?: boolean
}

export interface UserFilters {
	search?: string
	role?: string
}

export const useInvoices = (filters: InvoiceFilters) =>
	useQuery({
		queryKey: financeKeys.invoices(filters),
		queryFn: () =>
			frappeGet<InvoicesResponse>('sibbcs.api.finance_api.invoices', {
				status: filters.status || undefined,
				category: filters.category || undefined,
				search: filters.search || undefined,
				overdue: filters.overdue ? 1 : undefined,
			}),
		placeholderData: (previous) => previous,
	})

export const usePayments = (search: string) =>
	useQuery({
		queryKey: financeKeys.payments(search),
		queryFn: () =>
			frappeGet<PaymentsResponse>('sibbcs.api.finance_api.payments', {
				search: search || undefined,
			}),
		placeholderData: (previous) => previous,
	})

export const useOutstandingFor = (student: string | null) =>
	useQuery({
		queryKey: financeKeys.outstanding(student ?? ''),
		queryFn: () =>
			frappeGet<OutstandingInvoice[]>('sibbcs.api.finance_api.outstanding_for', { student }),
		enabled: Boolean(student),
	})

export const useScholarships = () =>
	useQuery({
		queryKey: financeKeys.scholarships,
		queryFn: () => frappeGet<ScholarshipsResponse>('sibbcs.api.finance_api.scholarships'),
	})

export function useRecordPayment() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (values: {
			student: string
			amount: number
			mode: string
			received_on?: string
			reference_no?: string
			allocations?: { fee_invoice: string; allocated_amount: number }[]
		}) => frappePost('sibbcs.api.finance_api.record_payment', values),
		// A payment changes the invoice it settles, the totals and the student's
		// own screens, so the whole namespace is refetched.
		onSuccess: () => queryClient.invalidateQueries({ queryKey: financeKeys.all }),
	})
}

export function useDecideScholarship() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (values: {
			request: string
			outcome: 'Approved' | 'Rejected'
			approved_amount?: number
			monthly_discount?: number
			remarks?: string
		}) => frappePost('sibbcs.admissions.scholarship.decide', values),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: financeKeys.scholarships }),
	})
}

export const useUsers = (filters: UserFilters) =>
	useQuery({
		queryKey: financeKeys.users(filters),
		queryFn: () =>
			frappeGet<UsersResponse>('sibbcs.api.users_api.users', {
				search: filters.search || undefined,
				role: filters.role || undefined,
			}),
		placeholderData: (previous) => previous,
	})

export const useRoleSummary = () =>
	useQuery({
		queryKey: financeKeys.roleSummary,
		queryFn: () => frappeGet<RoleCount[]>('sibbcs.api.users_api.role_summary'),
	})

export function useSetRoles() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (values: { user: string; roles: string[] }) =>
			frappePost('sibbcs.api.users_api.set_roles', values),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: financeKeys.all }),
	})
}

export function useSetEnabled() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (values: { user: string; enabled: number }) =>
			frappePost('sibbcs.api.users_api.set_enabled', values),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: financeKeys.all }),
	})
}

export function useCreateUser() {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (values: {
			email: string
			first_name: string
			last_name?: string
			roles: string[]
		}) => frappePost('sibbcs.api.users_api.create_user', values),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: financeKeys.all }),
	})
}
