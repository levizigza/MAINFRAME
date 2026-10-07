/*---------------------------------------------------------------------------------------------
 *  Reviewable apply — unified diff → Accept / Reject (never silent overwrite).
 *  Inspired by Void DiffZones UX; does not vendor Void services.
 *--------------------------------------------------------------------------------------------*/

export interface ReviewableEdit {
	readonly path: string;
	readonly old: string;
	readonly new: string;
}

export interface DiffHunk {
	readonly path: string;
	readonly unified: string;
}

export function editsToUnified(edits: ReviewableEdit[]): DiffHunk[] {
	return edits.map((e) => {
		const oldLines = e.old.split('\n');
		const newLines = e.new.split('\n');
		const body = [
			`--- a/${e.path}`,
			`+++ b/${e.path}`,
			`@@`,
			...oldLines.map((l) => `-${l}`),
			...newLines.map((l) => `+${l}`),
		].join('\n');
		return { path: e.path, unified: body };
	});
}

export type DiffDecision = 'accept' | 'reject';

export interface DiffReviewState {
	readonly hunks: DiffHunk[];
	readonly decision: DiffDecision | null;
}

export function decideDiff(
	state: DiffReviewState,
	decision: DiffDecision
): DiffReviewState {
	return { ...state, decision };
}

export function silentOverwriteForbidden(): true {
	return true;
}
