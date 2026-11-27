# Bundled third-party material

C4Spec's original work uses Apache 2.0. The remaining bundled material and
its source revisions are listed below. [C4Spec license](../LICENSE)

## Skill upgrade preview

`src/skills.ts` adapts line-ending normalization and byte-ordered SHA-256
hashing to compare installed skill content against the installer lock.
The CLI package includes its MIT notice.
[skills 1.8.1 source](https://github.com/vercel-labs/skills/blob/e781cb4d07433dfe1d19e924ed45cc61738c55ec/src/skill-hash.ts) ·
[MIT license](../licenses/Skills-MIT.txt)

## Owned LikeC4 instruction bundle (2026-11-17)

Source: [`likec4/likec4` 1.61.0, `9a57883c1022d7ee44a29d8f2f9b7e94025cb4a7`](https://github.com/likec4/likec4/tree/9a57883c1022d7ee44a29d8f2f9b7e94025cb4a7/skills/likec4-dsl).
MIT copyright 2023–2026 Denis Davydkov; full notice is preserved in
`licenses/LikeC4-MIT.txt` and the installed bundle's `references/likec4/LICENSE.txt`.

| Source | Destination / adaptation |
| --- | --- |
| `skills/likec4-dsl/references/*.md`, except `bridge-leanix-drawio.md` | Shared `c4spec/references/likec4/` topic references; pinned commands, local paths, corrected example declarations/icons, 1.61 description-file/Material guidance, own compatibility policy and measured limitations |
| Selected project/model/view/validation rules from `skills/likec4-dsl/SKILL.md` | Curated `references/likec4/README.md`; no second discoverable DSL skill |
| `LICENSE` | Unchanged notices in repository and installed shared skill |

Excluded: upstream benchmark-oriented command/snippet formatting instructions,
1.53 fallback advice, evaluation files, unused LeanIX bridge and bridge CLI
instructions. The runnable example and compatibility/upgrade procedure are
C4Spec-owned. The imported references are a starting point maintained here;
upstream changes are reviewed as research, never pulled automatically.
