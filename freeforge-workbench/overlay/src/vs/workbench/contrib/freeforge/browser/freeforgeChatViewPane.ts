/*---------------------------------------------------------------------------------------------
 *  FreeForge Chat view — streams agent turns via Python bridge (async + cancel).
 *--------------------------------------------------------------------------------------------*/

import { IViewPaneOptions, ViewPane } from '../../../browser/parts/views/viewPane.js';
import { IKeybindingService } from '../../../../platform/keybinding/common/keybinding.js';
import { IContextMenuService } from '../../../../platform/contextview/browser/contextView.js';
import { IConfigurationService } from '../../../../platform/configuration/common/configuration.js';
import { IContextKeyService } from '../../../../platform/contextkey/common/contextkey.js';
import { IViewDescriptorService } from '../../../common/views.js';
import { IInstantiationService } from '../../../../platform/instantiation/common/instantiation.js';
import { IOpenerService } from '../../../../platform/opener/common/opener.js';
import { IThemeService } from '../../../../platform/theme/common/themeService.js';
import { IHoverService } from '../../../../platform/hover/browser/hover.js';
import { ICommandService } from '../../../../platform/commands/common/commands.js';
import { localize } from '../../../../nls.js';

export class FreeforgeChatViewPane extends ViewPane {
	private _taskId: string | undefined;
	private _log: HTMLElement | undefined;
	private _input: HTMLTextAreaElement | undefined;
	private _chips: HTMLElement | undefined;
	private _cancelled = false;

	constructor(
		options: IViewPaneOptions,
		@IKeybindingService keybindingService: IKeybindingService,
		@IContextMenuService contextMenuService: IContextMenuService,
		@IConfigurationService configurationService: IConfigurationService,
		@IContextKeyService contextKeyService: IContextKeyService,
		@IViewDescriptorService viewDescriptorService: IViewDescriptorService,
		@IInstantiationService instantiationService: IInstantiationService,
		@IOpenerService openerService: IOpenerService,
		@IThemeService themeService: IThemeService,
		@IHoverService hoverService: IHoverService,
		@ICommandService private readonly commandService: ICommandService
	) {
		super(
			options,
			keybindingService,
			contextMenuService,
			configurationService,
			contextKeyService,
			viewDescriptorService,
			instantiationService,
			openerService,
			themeService,
			hoverService
		);
	}

	protected override renderBody(container: HTMLElement): void {
		super.renderBody(container);
		container.classList.add('freeforge-chat');

		this._chips = document.createElement('div');
		this._chips.className = 'freeforge-chips';
		this._chips.setAttribute('aria-label', localize('freeforge.chips', 'Context chips'));
		container.appendChild(this._chips);

		this._log = document.createElement('div');
		this._log.className = 'freeforge-log';
		this._log.setAttribute('role', 'log');
		container.appendChild(this._log);

		const actions = document.createElement('div');
		actions.className = 'freeforge-actions';

		const send = document.createElement('button');
		send.textContent = localize('freeforge.send', 'Send');
		send.onclick = () => void this._send();

		const cancel = document.createElement('button');
		cancel.textContent = localize('freeforge.cancel', 'Cancel');
		cancel.onclick = () => void this._cancel();

		const apply = document.createElement('button');
		apply.textContent = localize('freeforge.apply', 'Apply diff');
		apply.onclick = () => void this._apply(true);

		const reject = document.createElement('button');
		reject.textContent = localize('freeforge.reject', 'Reject diff');
		reject.onclick = () => void this._apply(false);

		actions.append(send, cancel, apply, reject);
		container.appendChild(actions);

		this._input = document.createElement('textarea');
		this._input.placeholder = localize(
			'freeforge.placeholder',
			'Ask FreeForge (local Mode B)…'
		);
		this._input.rows = 3;
		container.appendChild(this._input);

		this._append(
			'assistant',
			'FreeForge Workbench — AI paused until Ollama is available. Editing still works.'
		);
	}

	private _append(role: string, text: string): void {
		if (!this._log) {
			return;
		}
		const row = document.createElement('div');
		row.className = `freeforge-msg freeforge-msg-${role}`;
		row.textContent = text;
		this._log.appendChild(row);
		this._log.scrollTop = this._log.scrollHeight;
	}

	private _renderChips(chips: Array<{ kind: string; path?: string; message?: string }>): void {
		if (!this._chips) {
			return;
		}
		this._chips.replaceChildren();
		for (const c of chips || []) {
			const el = document.createElement('span');
			el.className = 'freeforge-chip';
			el.textContent = c.kind + (c.path ? `: ${c.path}` : '') + (c.message ? ` — ${c.message}` : '');
			this._chips.appendChild(el);
		}
	}

	private async _send(): Promise<void> {
		const text = (this._input?.value || '').trim();
		if (!text) {
			return;
		}
		this._cancelled = false;
		this._append('user', text);
		if (this._input) {
			this._input.value = '';
		}
		try {
			const result = (await this.commandService.executeCommand('freeforge.agentTurn', {
				message: text,
				taskId: this._taskId,
			})) as {
				task_id?: string;
				assistant?: string;
				chips?: Array<{ kind: string; path?: string; message?: string }>;
				events?: Array<{ type: string; text?: string }>;
				ai?: { status?: string };
				proposal?: { edits?: unknown[] };
			};
			if (this._cancelled) {
				this._append('assistant', localize('freeforge.cancelled', 'Cancelled.'));
				return;
			}
			this._taskId = result?.task_id || this._taskId;
			this._renderChips(result?.chips || []);
			if (result?.ai?.status === 'paused') {
				this._append('system', localize('freeforge.paused', 'AI paused — deterministic tools only.'));
			}
			// Stream deltas if bridge provided events; else one shot
			const deltas = (result?.events || []).filter((e) => e.type === 'assistant_delta');
			if (deltas.length) {
				let acc = '';
				for (const d of deltas) {
					if (this._cancelled) {
						break;
					}
					acc += d.text || '';
				}
				this._append('assistant', acc || result?.assistant || '');
			} else {
				this._append('assistant', result?.assistant || '');
			}
			const n = result?.proposal?.edits?.length || 0;
			if (n > 0) {
				this._append(
					'system',
					localize('freeforge.proposalReady', '{0} edit(s) ready — Apply or Reject.', n)
				);
			}
		} catch (err) {
			this._append('assistant', `Bridge error: ${String(err)}`);
		}
	}

	private async _cancel(): Promise<void> {
		this._cancelled = true;
		if (this._taskId) {
			await this.commandService.executeCommand('freeforge.cancel', { taskId: this._taskId });
		}
		this._append('system', localize('freeforge.cancelNote', 'Cancel requested.'));
	}

	private async _apply(accept: boolean): Promise<void> {
		if (!this._taskId) {
			return;
		}
		const result = (await this.commandService.executeCommand('freeforge.applyOrReject', {
			taskId: this._taskId,
			accept,
		})) as { ok?: boolean; rejected?: boolean };
		this._append(
			'system',
			accept
				? localize('freeforge.applied', 'Apply finished ok={0}', String(!!result?.ok))
				: localize('freeforge.rejected', 'Diff rejected — no silent overwrite.')
		);
	}
}
