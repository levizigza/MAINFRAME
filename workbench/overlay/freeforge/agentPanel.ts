/*---------------------------------------------------------------------------------------------
 *  FreeForge agent panel protocol (thin overlay types).
 *  Runtime UI lives in extensions/freeforge-editor webview until full vscode contrib lands.
 *  Events match mainframe.editor.agent NDJSON stream — do not reimplement patch/verify in TS.
 *--------------------------------------------------------------------------------------------*/

export type FreeForgeAgentEventType =
	| 'status'
	| 'ai_status'
	| 'completion_gate'
	| 'context_chips'
	| 'message_delta'
	| 'message_done'
	| 'tool_call'
	| 'tool_result'
	| 'propose_source'
	| 'proposal'
	| 'done'
	| 'cancelled'
	| 'error';

export interface FreeForgeAgentEvent {
	readonly id?: string;
	readonly ts?: number;
	readonly type: FreeForgeAgentEventType;
	readonly [key: string]: unknown;
}

export interface FreeForgeContextChip {
	readonly kind: 'selection' | 'active_file' | 'dirty_buffer' | 'diagnostic' | 'workspace' | string;
	readonly path?: string;
	readonly message?: string;
	readonly start_line?: number;
	readonly end_line?: number;
}

/** CLI twin for the panel — never call hosted LLM endpoints from the renderer. */
export const AGENT_CLI = {
	streamTurn: ['editor', 'agent-run', '--task', '<taskId>'],
	apply: ['editor', 'apply', '--task', '<taskId>'],
	reject: ['editor', 'reject', '--task', '<taskId>'],
	cancel: ['editor', 'cancel', '--task', '<taskId>'],
} as const;

export const AGENT_PANEL_ID = 'freeforge.agentPanel';
