import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { Toaster } from 'sonner'

import { queryClient } from '@/lib/query'
import { router } from '@/router'

import './index.css'

const root = document.getElementById('root')
if (!root) throw new Error('#root is missing from the page')

createRoot(root).render(
	<StrictMode>
		<QueryClientProvider client={queryClient}>
			<RouterProvider router={router} />
			<Toaster
				position="bottom-right"
				closeButton
				toastOptions={{
					classNames: {
						toast: 'bg-card text-card-foreground border-border shadow-lg',
						description: 'text-muted-foreground',
					},
				}}
			/>
		</QueryClientProvider>
	</StrictMode>,
)
