import { useEffect, useState } from 'react'

/**
 * Holds a value still for a moment.
 *
 * A search box that refetches on every keystroke asks the server for five
 * answers nobody reads on the way to the sixth.
 */
export function useDebounced<T>(value: T, delay = 300): T {
	const [settled, setSettled] = useState(value)

	useEffect(() => {
		const timer = setTimeout(() => setSettled(value), delay)
		return () => clearTimeout(timer)
	}, [value, delay])

	return settled
}
