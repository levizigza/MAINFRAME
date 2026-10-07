/*---------------------------------------------------------------------------------------------
 *  FreeForge Workbench contribution (thin overlay).
 *  Copied into microsoft/vscode at:
 *    src/vs/workbench/contrib/freeforge/
 *  Does NOT vendor Void editCodeService / voidModelService.
 *--------------------------------------------------------------------------------------------*/

export const FREEFORGE_CONTRIB_ID = 'freeforge';
export const FREEFORGE_PRODUCT_NAME = 'FreeForge Workbench';
export const FREEFORGE_VIEW_CONTAINER = 'workbench.view.extension.freeforge';
export const FREEFORGE_CHAT_VIEW = 'freeforge.chat';
export const FREEFORGE_ABOUT_BLURB =
	'FreeForge Workbench — VS Code-class shell + FreeForge local agent. Zero required paid APIs.';

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

/** Settings keys surfaced in workbench (loopback-only enforced in bridge). */
export const FREEFORGE_SETTINGS = {
	ollamaBaseUrl: 'freeforge.ollamaBaseUrl',
	python: 'freeforge.python',
} as const;

export const DEFAULT_OLLAMA_BASE_URL = 'http://127.0.0.1:11434';
