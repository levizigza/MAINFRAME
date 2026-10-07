/** Overlay sanity check — no full vscode build required. */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

function parseAiProbeJson(raw) {
  try {
    const data = JSON.parse(raw);
    const status = String(data.status || 'paused').toLowerCase();
    if (status === 'available' || status === 'ok') {
      return { state: 'available', freeOnly: true };
    }
    if (status === 'disabled') {
      return { state: 'disabled', freeOnly: true };
    }
    return { state: 'paused', freeOnly: true };
  } catch {
    return { state: 'paused', freeOnly: true };
  }
}

const paused = parseAiProbeJson(JSON.stringify({ status: 'paused' }));
const avail = parseAiProbeJson(JSON.stringify({ status: 'available' }));
if (paused.state !== 'paused' || avail.state !== 'available') {
  console.error('parse check failed', { paused, avail });
  process.exit(1);
}
const contrib = readFileSync(join(__dirname, 'freeforge.contribution.ts'), 'utf8');
if (!contrib.includes('FREEFORGE_CONTRIB_ID')) {
  console.error('missing FREEFORGE_CONTRIB_ID');
  process.exit(1);
}
console.log(JSON.stringify({ ok: true, overlay: 'freeforge' }));
