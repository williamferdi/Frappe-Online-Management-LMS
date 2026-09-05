import { describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'

import { useDragOrder } from './useDragOrder'

/** A DragEvent with just the parts the hook touches. */
function dragEvent(held?: string) {
	const data = new Map<string, string>()
	if (held) data.set('text/plain', held)
	return {
		preventDefault: vi.fn(),
		dataTransfer: {
			effectAllowed: '',
			dropEffect: '',
			setData: (key: string, value: string) => data.set(key, value),
			getData: (key: string) => data.get(key) ?? '',
		},
	} as unknown as React.DragEvent
}

describe('reordering by dragging', () => {
	it('sends the whole new order, not a swap', () => {
		// A half-applied reorder would leave two things claiming one position,
		// which is why the server rewrites positions from the list it is given.
		const onReorder = vi.fn()
		const { result } = renderHook(() =>
			useDragOrder(['a', 'b', 'c', 'd'], onReorder),
		)

		act(() => result.current.handlers('a').onDragStart(dragEvent()))
		act(() => result.current.handlers('c').onDrop(dragEvent('a')))

		expect(onReorder).toHaveBeenCalledWith(['b', 'c', 'a', 'd'])
	})

	it('moves an item backwards as well as forwards', () => {
		const onReorder = vi.fn()
		const { result } = renderHook(() => useDragOrder(['a', 'b', 'c'], onReorder))

		act(() => result.current.handlers('c').onDragStart(dragEvent()))
		act(() => result.current.handlers('a').onDrop(dragEvent('c')))

		expect(onReorder).toHaveBeenCalledWith(['c', 'a', 'b'])
	})

	it('does nothing when something is dropped on itself', () => {
		const onReorder = vi.fn()
		const { result } = renderHook(() => useDragOrder(['a', 'b'], onReorder))

		act(() => result.current.handlers('a').onDragStart(dragEvent()))
		act(() => result.current.handlers('a').onDrop(dragEvent('a')))

		expect(onReorder).not.toHaveBeenCalled()
	})

	it('lets a keyboard do what dragging cannot', () => {
		// Native drag and drop cannot be driven from a keyboard at all, so the
		// move buttons are not decoration.
		const onReorder = vi.fn()
		const { result } = renderHook(() => useDragOrder(['a', 'b', 'c'], onReorder))

		act(() => result.current.moveBy('c', -1))

		expect(onReorder).toHaveBeenCalledWith(['a', 'c', 'b'])
	})

	it('refuses to move past either end', () => {
		const onReorder = vi.fn()
		const { result } = renderHook(() => useDragOrder(['a', 'b'], onReorder))

		act(() => result.current.moveBy('a', -1))
		act(() => result.current.moveBy('b', 1))

		expect(onReorder).not.toHaveBeenCalled()
	})

	it('lets the drop be accepted at all', () => {
		// Without preventDefault on dragover the browser refuses the drop and
		// nothing ever happens — the commonest way this silently fails.
		const { result } = renderHook(() => useDragOrder(['a', 'b'], vi.fn()))
		const event = dragEvent()

		act(() => result.current.handlers('b').onDragOver(event))

		expect(event.preventDefault).toHaveBeenCalled()
	})

	it('reports what is being dragged and what it is over, for the styling', () => {
		const { result } = renderHook(() => useDragOrder(['a', 'b'], vi.fn()))

		act(() => result.current.handlers('a').onDragStart(dragEvent()))
		act(() => result.current.handlers('b').onDragOver(dragEvent()))

		expect(result.current.dragging).toBe('a')
		expect(result.current.over).toBe('b')

		act(() => result.current.handlers('a').onDragEnd())
		expect(result.current.dragging).toBeNull()
		expect(result.current.over).toBeNull()
	})
})
