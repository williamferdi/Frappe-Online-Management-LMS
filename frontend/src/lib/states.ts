/**
 * What an application's stored state is called on screen.
 *
 * `workflow_state` is derived by `checklist.derive_state` and stored, and
 * `Draft` is what it holds for an application that is complete in every
 * respect except the ₹350 application fee. To an officer that reads as "the
 * candidate never finished", which is the opposite of the truth and sent one
 * straight back to the candidate asking them to apply again.
 *
 * Relabelled here rather than renamed in the database: the value is stored on
 * every application, is a Select option, and is what the filter chips send
 * back as `state`. A rename is a patch plus a DocType change plus every
 * stored row; a label is a label.
 */
const LABELS: Record<string, string> = {
	Draft: 'Awaiting Application Fee',
}

export function stateLabel(state?: string | null): string {
	if (!state) return 'Awaiting Application Fee'
	return LABELS[state] ?? state
}
