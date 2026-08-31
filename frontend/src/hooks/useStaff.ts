import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { frappeGet, frappePost } from '@/lib/frappe'
import type { ApplicationDetail, ConsoleDashboard, PipelineResponse } from '@/types'

export const staffKeys = {
	all: ['staff'] as const,
	dashboard: ['staff', 'dashboard'] as const,
	pipeline: (filters: PipelineFilters) => ['staff', 'pipeline', filters] as const,
	application: (name: string) => ['staff', 'application', name] as const,
}

export interface PipelineFilters {
	state?: string
	program?: string
	search?: string
}

export const useConsoleDashboard = () =>
	useQuery({
		queryKey: staffKeys.dashboard,
		queryFn: () => frappeGet<ConsoleDashboard>('sibbcs.api.console.dashboard'),
	})

export const usePipeline = (filters: PipelineFilters) =>
	useQuery({
		queryKey: staffKeys.pipeline(filters),
		queryFn: () =>
			frappeGet<PipelineResponse>('sibbcs.api.admissions_api.pipeline', {
				state: filters.state || undefined,
				program: filters.program || undefined,
				search: filters.search || undefined,
			}),
		// A search box refetching on every keystroke is the caller's problem to
		// debounce; keeping the previous rows on screen while it does stops the
		// table flashing empty between them.
		placeholderData: (previous) => previous,
	})

export const useApplication = (name: string | null) =>
	useQuery({
		queryKey: staffKeys.application(name ?? ''),
		queryFn: () =>
			frappeGet<ApplicationDetail>('sibbcs.api.admissions_api.application', { name }),
		enabled: Boolean(name),
	})

/**
 * Advancing a step can change the application's overall state and unblock a
 * later step, so the whole detail is refetched rather than the one row patched.
 */
export function useUpdateStep(application: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (values: { step_no: number; status: string; remarks?: string }) =>
			frappePost('sibbcs.admissions.checklist.update_step', {
				application,
				step_no: values.step_no,
				status: values.status,
				remarks: values.remarks,
			}),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: staffKeys.application(application) })
			void queryClient.invalidateQueries({ queryKey: staffKeys.dashboard })
		},
	})
}

export function useRunAction(application: string) {
	const queryClient = useQueryClient()
	return useMutation({
		mutationFn: (action: string) =>
			frappePost<{ action: string; result: unknown }>(
				'sibbcs.api.admissions_api.run_action',
				{ application, action },
			),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: staffKeys.application(application) })
			void queryClient.invalidateQueries({ queryKey: staffKeys.dashboard })
		},
	})
}
