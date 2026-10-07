/*---------------------------------------------------------------------------------------------
 *  FreeForge AI status channel — workbench talks to MAINFRAME CLI (loopback policy).
 *--------------------------------------------------------------------------------------------*/

import { DEFAULT_PAUSED_STATUS, FreeForgeAiStatus } from './freeforge.contribution.js';

/**
 * Parse JSON from `python -m mainframe ai probe`.
 * Implementation in the built workbench will spawn MAINFRAME; this module stays pure for unit checks.
 */
export function parseAiProbeJson(raw: string): FreeForgeAiStatus {
	try {
		const data = JSON.parse(raw) as {
			status?: string;
			provider?: string | null;
			detail?: string;
		};
		const status = (data.status || 'paused').toLowerCase();
		if (status === 'available' || status === 'ok') {
			return {
				state: 'available',
				provider: data.provider ?? 'ollama_local',
				detail: data.detail || 'Local inference available',
				freeOnly: true,
			};
		}
		if (status === 'disabled') {
			return {
				state: 'disabled',
				provider: data.provider ?? null,
				detail: data.detail || 'Provider disabled by eligibility gate',
				freeOnly: true,
			};
		}
		return {
			state: 'paused',
			provider: data.provider ?? null,
			detail: data.detail || DEFAULT_PAUSED_STATUS.detail,
			freeOnly: true,
		};
	} catch {
		return { ...DEFAULT_PAUSED_STATUS, detail: 'Failed to parse ai probe JSON' };
	}
}
