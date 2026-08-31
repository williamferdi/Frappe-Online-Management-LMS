import { QueryClient } from '@tanstack/react-query'

import { FrappeError } from './frappe'

export const queryClient = new QueryClient({
	defaultOptions: {
		queries: {
			staleTime: 30_000,
			refetchOnWindowFocus: false,
			retry(failureCount, error) {
				// Retrying a refusal just repeats it. Only transient failures
				// deserve a second attempt.
				if (error instanceof FrappeError) {
					if (error.isAuthError || error.isPermissionError) return false
					if (error.status >= 400 && error.status < 500) return false
				}
				return failureCount < 2
			},
		},
	},
})
