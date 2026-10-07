/*---------------------------------------------------------------------------------------------
 *  FreeForge ↔ MAINFRAME CLI bridge contracts (async; cancel-aware).
 *  Full Electron host spawns python; this module is pure for overlay checks.
 *--------------------------------------------------------------------------------------------*/

export interface BridgeRequest {
	readonly argv: string[];
	readonly cwd?: string;
	readonly cancelToken?: string;
}

export interface BridgeResult {
	readonly ok: boolean;
	readonly json?: unknown;
	readonly error?: string;
	readonly cancelled?: boolean;
}

export function buildAiProbeRequest(): BridgeRequest {
	return { argv: ['-m', 'mainframe', 'ai', 'probe'] };
}

export function buildWorkbenchStatusRequest(): BridgeRequest {
	return { argv: ['-m', 'mainframe', 'workbench', 'status'] };
}

export function buildSessionStartRequest(workspace: string, chat: string): BridgeRequest {
	return {
		argv: [
			'-m',
			'mainframe',
			'workbench',
			'session-start',
			'--workspace',
			workspace,
			'--chat',
			chat,
		],
	};
}

export function buildTurnRequest(sessionId: string, message: string): BridgeRequest {
	return {
		argv: [
			'-m',
			'mainframe',
			'workbench',
			'turn',
			'--session',
			sessionId,
			'--message',
			message,
		],
	};
}

export function buildApplyRequest(sessionId: string, accept: boolean): BridgeRequest {
	return {
		argv: [
			'-m',
			'mainframe',
			'workbench',
			'apply',
			'--session',
			sessionId,
			accept ? '--accept' : '--reject',
		],
	};
}

export function buildCancelRequest(sessionId: string): BridgeRequest {
	return {
		argv: ['-m', 'mainframe', 'workbench', 'cancel', '--session', sessionId],
		cancelToken: sessionId,
	};
}

/** Enforce loopback-only Ollama base URL in settings UI. */
export function isLoopbackOllamaUrl(url: string): boolean {
	try {
		const u = new URL(url);
		const host = (u.hostname || '').toLowerCase();
		return host === '127.0.0.1' || host === 'localhost' || host === '::1';
	} catch {
		return false;
	}
}
