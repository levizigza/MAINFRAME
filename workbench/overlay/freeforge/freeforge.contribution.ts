/*---------------------------------------------------------------------------------------------
 *  FreeForge Workbench contribution (thin overlay).
 *  Copied into microsoft/vscode at:
 *    src/vs/workbench/contrib/freeforge/
 *  Does NOT vendor Void editCodeService / voidModelService.
 *--------------------------------------------------------------------------------------------*/

export const FREEFORGE_CONTRIB_ID = 'freeforge';
export const FREEFORGE_VIEW_CONTAINER = 'workbench.view.extension.freeforge';

export interface FreeForgeAiStatus {
	readonly state: 'available' | 'paused' | 'disabled';
	readonly provider: string | null;
	readonly detail: string;
	readonly freeOnly: true;
}

export const DEFAULT_PAUSED_STATUS: FreeForgeAiStatus = {
	state: 'paused',
	provider: null,
	detail: 'Local Ollama/llama.cpp unreachable. Deterministic editing continues; agent paused.',
	freeOnly: true,
};
