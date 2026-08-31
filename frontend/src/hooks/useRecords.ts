import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { frappeGet, frappePost } from '@/lib/frappe'

export interface FieldMeta {
	fieldname: string
	label: string | null
	fieldtype: string
	options: string | null
	reqd: 0 | 1
	read_only: boolean
	hidden: 0 | 1
	depends_on: string | null
	mandatory_depends_on: string | null
	default: string | null
	description: string | null
	permlevel: number
	precision: string | null
	in_list_view: 0 | 1
}

export interface Describe {
	doctype: string
	label: string
	fields: FieldMeta[]
	children: Record<string, FieldMeta[]>
	title_field: string
	is_submittable: number
	autoname: string | null
	list_fields: string[]
	can_create: boolean
	can_write: boolean
	can_delete: boolean
}

export interface RecordsPage {
	doctype: string
	rows: Record<string, unknown>[]
	truncated: boolean
	columns: FieldMeta[]
	total: number
}

export interface SectionEntry {
	doctype: string
	label: string
	is_submittable: number
	can_create: boolean
	can_write: boolean
	can_delete: boolean
	count: number
}

export const recordKeys = {
	all: ['records'] as const,
	sections: ['records', 'sections'] as const,
	describe: (doctype: string) => ['records', 'describe', doctype] as const,
	list: (doctype: string, search: string) => ['records', 'list', doctype, search] as const,
	one: (doctype: string, name: string) => ['records', 'one', doctype, name] as const,
	options: (doctype: string, txt: string) => ['records', 'options', doctype, txt] as const,
}

export const useSections = () =>
	useQuery({
		queryKey: recordKeys.sections,
		queryFn: () => frappeGet<Record<string, SectionEntry[]>>('sibbcs.api.records.sections'),
	})

export const useDescribe = (doctype: string | null) =>
	useQuery({
		queryKey: recordKeys.describe(doctype ?? ''),
		queryFn: () => frappeGet<Describe>('sibbcs.api.records.describe', { doctype }),
		enabled: Boolean(doctype),
		// Field definitions change when somebody edits a DocType, which is not
		// something that happens between two clicks.
		staleTime: 5 * 60_000,
	})

export const useRecordList = (doctype: string | null, search: string) =>
	useQuery({
		queryKey: recordKeys.list(doctype ?? '', search),
		queryFn: () =>
			frappeGet<RecordsPage>('sibbcs.api.records.records', {
				doctype,
				search: search || undefined,
			}),
		enabled: Boolean(doctype),
		placeholderData: (previous) => previous,
	})

export const useRecord = (doctype: string | null, name: string | null) =>
	useQuery({
		queryKey: recordKeys.one(doctype ?? '', name ?? ''),
		queryFn: () =>
			frappeGet<{ doctype: string; name: string; values: Record<string, unknown> }>(
				'sibbcs.api.records.record',
				{ doctype, name },
			),
		enabled: Boolean(doctype && name),
	})

export function useSaveRecord(doctype: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (values: { name?: string; values: Record<string, unknown> }) =>
			frappePost<{ doctype: string; name: string }>('sibbcs.api.records.save', {
				doctype,
				name: values.name,
				values: values.values,
			}),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: recordKeys.all }),
	})
}

export function useDeleteRecord(doctype: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (name: string) =>
			frappePost('sibbcs.api.records.remove', { doctype, name }),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: recordKeys.all }),
	})
}

export const useLinkOptions = (doctype: string | null, txt: string) =>
	useQuery({
		queryKey: recordKeys.options(doctype ?? '', txt),
		queryFn: () =>
			frappeGet<{ value: string; label: string }[]>('sibbcs.api.records.options', {
				doctype,
				txt: txt || undefined,
			}),
		enabled: Boolean(doctype),
		staleTime: 30_000,
	})
