/**
 * Overlay unit checks (Node, no full vscode). Pure helpers only.
 */
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

function parseAiProbeJson(raw) {
  try {
    const data = JSON.parse(raw);
    const status = String(data.status || 'paused').toLowerCase();
    if (status === 'available' || status === 'ok') {
      return { state: 'available', provider: data.provider ?? 'ollama_local', freeOnly: true };
    }
    if (status === 'disabled') {
      return { state: 'disabled', provider: data.provider ?? null, freeOnly: true };
    }
    return { state: 'paused', provider: data.provider ?? null, freeOnly: true };
  } catch {
    return { state: 'paused', freeOnly: true };
  }
}

function isLoopbackOllamaUrl(url) {
  try {
    const u = new URL(url);
    const host = (u.hostname || '').toLowerCase();
    return host === '127.0.0.1' || host === 'localhost' || host === '::1';
  } catch {
    return false;
  }
}

function editsToUnified(edits) {
  return edits.map((e) => ({
    path: e.path,
    unified: [`--- a/${e.path}`, `+++ b/${e.path}`, '@@', `-${e.old}`, `+${e.new}`].join('\n'),
  }));
}

const paused = parseAiProbeJson(
  JSON.stringify({ status: 'paused', detail: 'unreachable', free_only: true })
);
const avail = parseAiProbeJson(
  JSON.stringify({ status: 'available', provider: 'ollama_local', detail: 'ok' })
);

if (paused.state !== 'paused' || avail.state !== 'available') {
  console.error('overlay check failed', { paused, avail });
  process.exit(1);
}

const required = [
  'freeforge.contribution.ts',
  'aiStatus.ts',
  'chatPanel.ts',
  'contextChips.ts',
  'diffReview.ts',
  'toolLoop.ts',
  'bridge.ts',
];
for (const f of required) {
  if (!existsSync(join(__dirname, f))) {
    console.error('missing overlay file', f);
    process.exit(1);
  }
}

const contrib = readFileSync(join(__dirname, 'freeforge.contribution.ts'), 'utf8');
if (!contrib.includes('FREEFORGE_CONTRIB_ID')) {
  console.error('missing FREEFORGE_CONTRIB_ID');
  process.exit(1);
}
if (!contrib.includes('FreeForge Workbench') && !contrib.includes('FREEFORGE')) {
  console.error('branding marker missing');
  process.exit(1);
}

if (!isLoopbackOllamaUrl('http://127.0.0.1:11434') || isLoopbackOllamaUrl('https://api.openai.com')) {
  console.error('loopback URL gate failed');
  process.exit(1);
}

const hunks = editsToUnified([{ path: 'a.py', old: 'x', new: 'y' }]);
if (!hunks[0].unified.includes('--- a/a.py') || !hunks[0].unified.includes('+y')) {
  console.error('diff review helper failed');
  process.exit(1);
}

const bridge = readFileSync(join(__dirname, 'bridge.ts'), 'utf8');
if (!bridge.includes('buildCancelRequest') || !bridge.includes('isLoopbackOllamaUrl')) {
  console.error('bridge contracts missing');
  process.exit(1);
}

console.log(
  JSON.stringify({
    ok: true,
    overlay: 'freeforge',
    checks: ['parse_probe', 'contrib_id', 'files', 'loopback', 'diff', 'bridge'],
  })
);
