import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'

import './preview.css'
import { RichText } from '@/components/RichText'
import { RichTextEditor } from '@/components/RichTextEditor'

const START =
	'<h2>Week one</h2><p>Read <strong>Genesis 1–3</strong> before the first lecture.</p><ul><li>Creation</li><li>The fall</li></ul><p>Office hours are on Thursday.</p>'

function Preview() {
	const [value, setValue] = useState(START)

	return (
		<div className="mx-auto max-w-3xl space-y-6 p-6">
			<div>
				<label id="body-label" className="text-sm font-medium">
					Body
				</label>
				<RichTextEditor
					id="body"
					labelledBy="body-label"
					className="mt-1"
					value={value}
					onChange={setValue}
					placeholder="Write the page, or paste it from Word or Google Docs."
				/>
			</div>

			<section className="space-y-2">
				<h2 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
					Stored body
				</h2>
				<pre
					id="stored"
					className="bg-muted overflow-x-auto rounded-md p-3 text-xs whitespace-pre-wrap"
				>
					{value}
				</pre>
			</section>

			<section className="space-y-2">
				<h2 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
					As a student sees it
				</h2>
				<div className="rounded-md border p-3">
					<RichText html={value} />
				</div>
			</section>
		</div>
	)
}

createRoot(document.getElementById('root')!).render(
	<StrictMode>
		<Preview />
	</StrictMode>,
)
