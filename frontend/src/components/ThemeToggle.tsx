import { useEffect, useState } from 'react'
import { Moon, Sun } from 'lucide-react'

import { Button } from '@/components/ui/button'

type Theme = 'light' | 'dark'

const KEY = 'sibbcs-theme'

function preferred(): Theme {
	try {
		const stored = localStorage.getItem(KEY)
		if (stored === 'light' || stored === 'dark') return stored
	} catch {
		// Private mode. The system preference is a fine answer.
	}
	return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function ThemeToggle() {
	const [theme, setTheme] = useState<Theme>(preferred)

	useEffect(() => {
		document.documentElement.classList.toggle('dark', theme === 'dark')
		try {
			localStorage.setItem(KEY, theme)
		} catch {
			// Nothing to do -- the class is already applied for this session.
		}
	}, [theme])

	return (
		<Button
			variant="ghost"
			size="icon"
			onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
			aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
		>
			{theme === 'dark' ? <Sun /> : <Moon />}
		</Button>
	)
}
