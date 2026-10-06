# Hosted provider investigation (candidates ≠ entitlements)

Investigated **2026-09-29** against official docs. MAINFRAME does **not** preapprove marketing free tiers.

| Provider | Live | Label | Why disabled |
|----------|------|-------|--------------|
| `groq_cloud` | disabled | `unverified_live` | Rate limits + Developer upgrade; published prices; recurring free without billing not verified |
| `google_gemini_api` | disabled | `unverified_live` | Free unpaid quota uses Unpaid Services data terms; billing unlocks Paid Tier / auto upgrades |
| `mistral_api` | disabled | `unverified_live` | Free mode for eval; pay-as-you-go extends usage and unlocks tiers |

Protocol fixtures exercise native roles, tools, streaming, cancellation, and usage reporting. Credentials stay in `.mainframe/credentials/` via the broker. Exhausting free access **pauses** — no billing activation, no paid endpoint switch.

```powershell
python -m mainframe providers investigate
python -m mainframe providers fixture groq_cloud --tools
python -m mainframe providers accept
```
