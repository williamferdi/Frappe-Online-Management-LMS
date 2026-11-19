import { describe, expect, it } from 'vitest'

import { stateLabel } from './states'

describe('what an application state is called on screen', () => {
	it('calls Draft what it actually is', () => {
		// An application sitting at Draft is complete; the ₹350 fee is unpaid.
		// "Draft" reads as "the candidate never finished", which sent one
		// candidate a message asking them to apply again.
		expect(stateLabel('Draft')).toBe('Awaiting Application Fee')
	})

	it('leaves every other state exactly as the server named it', () => {
		for (const state of ['In Review', 'Admitted', 'Onboarded', 'Rejected', 'Withdrawn']) {
			expect(stateLabel(state)).toBe(state)
		}
	})

	it('treats an empty state as the same thing', () => {
		// `workflow_state` is blank on an application typed into Desk and never
		// saved through the checklist; it means the same as Draft.
		expect(stateLabel('')).toBe('Awaiting Application Fee')
		expect(stateLabel(null)).toBe('Awaiting Application Fee')
		expect(stateLabel(undefined)).toBe('Awaiting Application Fee')
	})

	it('passes an unknown state through rather than inventing one', () => {
		expect(stateLabel('Something New')).toBe('Something New')
	})
})
