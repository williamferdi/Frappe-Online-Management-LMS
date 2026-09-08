import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import './preview.css'
import { CourseDetail } from '../src/routes/staff/CourseDetail'

const OFFERING = 'TEST COURSE-DEMO-TERM-B'
const tab = new URLSearchParams(window.location.search).get('tab') ?? 'modules'

const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

createRoot(document.getElementById('root')!).render(
	<QueryClientProvider client={client}>
		<MemoryRouter
			initialEntries={[`/staff/courses/${encodeURIComponent(OFFERING)}?tab=${tab}`]}
		>
			{/* The padding the app shell puts round a staff page. */}
			<div className="bg-background text-foreground min-h-screen px-6 py-5">
				<Routes>
					<Route path="/staff/courses/:name" element={<CourseDetail />} />
				</Routes>
			</div>
		</MemoryRouter>
	</QueryClientProvider>,
)
