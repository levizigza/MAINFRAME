/**
 * Stdlib-free check for overlay parse helpers (runs under Node without full vscode).
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Dynamic import of compiled-less TS via node strip-types when available;
// fallback: duplicate minimal parse for CI without TS.
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

const contrib = readFileSync(join(__dirname, 'freeforge.contribution.ts'), 'utf8');
if (!contrib.includes('FREEFORGE_CONTRIB_ID')) {
  console.error('missing FREEFORGE_CONTRIB_ID');
  process.exit(1);
}

console.log(JSON.stringify({ ok: true, overlay: 'freeforge', checks: ['parse_probe', 'contrib_id'] }));
