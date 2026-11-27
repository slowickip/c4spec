# LikeC4 guidance maintained by C4Spec

**Validated compiler: LikeC4 1.61.0.** This is an exact compatibility claim,
not a minimum version or an open-ended range. Newer versions are unverified
until C4Spec validates them and updates this contract. Use the consumer's
explicit pin; never silently upgrade it or fall back to `latest` or 1.53.0.
The existing 1.60.0 mini-project tests cover the legacy direct-edit path only;
they do not qualify these newer DSL features or native model diffs on 1.60.

These references are part of the shared `c4spec` skill. C4Spec owns their
accuracy and updates; no separate `likec4-dsl` skill or live upstream prompt is
required. Read only the relevant topic below. The compiler and executable
checks decide whether an example is valid; prose alone is not evidence.

## Core authoring rules

- Start from the repository's existing project configuration, vocabulary,
  sources and views. Files belong to the nearest LikeC4 project config.
  Files in one project share a model; `import` names another project, not a
  sibling source file. Use full qualified element names across files.
- Define element kinds and relationship kinds in `specification`; instantiate
  meaningful C4 elements in `model`. Tags appear before properties; children
  and relationships follow properties. Keep one canonical graph.
- A typed directed relationship is `source -[kind]-> target 'purpose'`.
  Choose kind, direction, protocol and label deliberately. Match the exact
  source/target/kind/title when removing or extending parallel relationships.
- `*` selects roots, `element.*` selects children, and `element.**` selects
  descendants. Bare `**` and bare `_` are invalid include predicates.
  `element._` is a connected-child expansion, not a synonym for descendants.
  Review selector source even when exported JSON looks unchanged.
- View titles are properties inside the body: `view overview { title 'L2 — …' }`.
  Structural scope and C4 level must remain meaningful; dynamic/deployment
  views are selective additions, not replacements for context/container views.
- Preserve logical identity. In 1.61.0, native `diff` can add/remove elements
  and relationships and extend existing tags/links/metadata. Existing element
  title/description/technology and authored views need direct Git edits.
- Always validate before `diff list`; list can exit zero for invalid syntax.
  Dry-run is not sufficient evidence that overlapping apply will succeed.
  Test apply/discard on scratch copies; real apply needs the user's existing
  authorization. Preserve rationale in Git because apply removes the diff.

## Pinned commands

Use the same explicit compiler for validation, review, export and apply:

```sh
npx --yes likec4@1.61.0 --version
npx --yes likec4@1.61.0 validate --json --no-layout architecture
npx --yes likec4@1.61.0 export json --skip-layout -o /tmp/model.json architecture
npx --yes likec4@1.61.0 diff list --json architecture
npx --yes likec4@1.61.0 diff apply CHANGE_NAME --dry-run architecture
npx --yes likec4@1.61.0 start architecture
```

Use `--file` once per edited source when filtering diagnostics; distinguish
filtered error counts from project-wide totals. Without `--max-warnings`,
warnings do not fail validation; add `--max-warnings 0` only when the project
requires that policy. A valid model does not establish C4 meaning or runtime
conformance. C4Spec's source-bound helper supports one pending native diff.

## Topic references

| Need | Reference |
| --- | --- |
| Project scope and configuration | [configuration.md](configuration.md) |
| Element kinds, tags and relationship kinds | [specification.md](specification.md) |
| Elements, properties, links and extension | [model.md](model.md) |
| Valid identifiers and qualified names | [identifier-validity.md](identifier-validity.md) |
| Relationships and exact matching | [relationships-bidirectional.md](relationships-bidirectional.md) |
| Structural views and styling | [views.md](views.md), [style-tokens-colors.md](style-tokens-colors.md) |
| Include/exclude and metadata filters | [predicates.md](predicates.md), [include-predicates-wildcards.md](include-predicates-wildcards.md) |
| Ordered interactions and flow control | [dynamic-views.md](dynamic-views.md) |
| Deployment instances and environments | [deployment.md](deployment.md) |
| Native proposal/apply/discard | [diffs.md](diffs.md) |
| CLI validation, exports and preview | [cli.md](cli.md) |
| Worked examples and diagnostics | [examples.md](examples.md), [troubleshooting.md](troubleshooting.md) |

The runnable [example project](example/) exercises model, typed relations,
selector projection, description files, Material icons, dynamic interactions and deployment mapping against the
exact supported compiler in CI. Existing native rehearsals exercise proposal,
dry-run, static review, scratch apply, stale references and overlap rejection.
CI also compiles complete fenced project examples (those containing both
`specification` and `model` blocks) from the installed topic references.
Fragments still need the surrounding project context. This is focused
compatibility coverage, not validation of every prose fragment.

## Upgrade procedure

1. On a C4Spec feature branch, inspect the candidate release notes and actual
   DSL/CLI behavior. Update these owned references for syntax, feature and
   semantic changes; upstream docs/skills are research inputs only.
2. Change candidate pins together: native helper, rehearsal, CI commands and
   this guide. Run the complete Python suites, JSON/Python checks, legacy 1.60
   checks where retained, this example project, native build/apply/negative
   rehearsals and standard one-/multi-agent installation checks.
3. Exercise the affected consumer model and inspect As-is/Changes/To-be plus
   original source selectors. Check CLI JSON/exit behavior, source immutability,
   exports, overlap/stale failures and unsupported property/view fallbacks.
4. Record the exact version, commands, results and gaps in the PR or release notes.
   Declare compatibility only after passing checks or explicitly adjusting
   skills/scripts to the candidate feature set. A release note or semver range
   cannot substitute for that evidence. Keep the old consumer pin until its
   deliberate upgrade is reviewed.

## Provenance

Initial reference adaptation: `likec4/likec4` release 1.61.0, commit
`9a57883c1022d7ee44a29d8f2f9b7e94025cb4a7`, `skills/likec4-dsl/references/`
and selected authoring guidance from `skills/likec4-dsl/SKILL.md`.
MIT copyright Denis Davydkov; [full license](LICENSE.txt).
C4Spec pins commands and adds its tested limits and upgrade policy. Upstream
benchmark instructions, evaluation files and the unused LeanIX bridge are
excluded. These references may be revised independently of upstream.
