import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Toaster } from 'sonner'

import './preview.css'
import { Modules } from '@/routes/staff/Modules'

const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

createRoot(document.getElementById('root')!).render(
	<StrictMode>
		<QueryClientProvider client={client}>
			<MemoryRouter>
				<div className="mx-auto max-w-4xl p-6">
					<Modules offering="DEMO GEST501-DEMO-TERM-B" />
				</div>
				<Toaster />
			</MemoryRouter>
		</QueryClientProvider>
	</StrictMode>,
)
