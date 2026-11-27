<!-- C4Spec-maintained adaptation of likec4/likec4 9a57883c1022d7ee44a29d8f2f9b7e94025cb4a7 / skills/likec4-dsl/references/diffs.md; MIT, see LICENSE.txt. -->

# Model diffs and safe delete

A `diff` is a named, planned change of the model (for example, an RFC).
The model does not change until the diff is applied.

```likec4
diff rfc1 'RFC-1: Payments service' {
  description 'Replace the SOAP gateway with a Payments service'

  remove {
    shop.legacyPayments                      // element, its descendants and their relationships
    shop.orders -> bank 'checks fraud score' // relationship: source, target, kind, title and direction must match
  }

  add {
    extend shop {
      payments = container 'Payments Service'
    }
    shop.orders -> shop.payments 'requests payments'
    extend shop.orders {
      #next // tags, links and metadata for an existing element
    }
  }
}
```

## C4Spec 1.61.0 boundaries

Validate before listing. An invalid extension can yield an empty, successful
`diff list` while validate/apply reject it. Existing element extensions support
tags, links and metadata, not title, description or technology. Views and those
properties use direct Git edits with source/computed review; preserve identity.
A successful dry-run alone does not establish overlap-free apply. Apply only
in scratch during verification; real model apply needs explicit authorization.

## Rules

- `remove` lists elements and relationships that exist in the model. Use full FQNs.
- `add` has the syntax of a `model` block: elements, relationships, `extend` of elements.
- A diff cannot extend relationships, cannot remove elements added by a diff, and cannot add an element that exists.
- Diffs that change the same elements or relationships, or use what another diff adds, overlap:
  both get a warning, and `diff apply` needs `--accept-overlaps` after the owners of the diffs agreed.
- Diffs with the same name in several files are merged.
- Views can reference elements added by a diff: the model "as is" ignores these references.

## Apply, discard, safe delete

```sh
bunx likec4@1.61.0 diff list [project-dir]
bunx likec4@1.61.0 diff apply rfc1 --dry-run [project-dir]  # print the changes of each file
bunx likec4@1.61.0 diff apply rfc1 [project-dir]            # merge `add` into the model, remove `remove` entries, delete the diff
bunx likec4@1.61.0 diff apply rfc1 --accept-overlaps [project-dir]  # only after the owners of overlapping diffs agreed
bunx likec4@1.61.0 diff discard rfc1 [project-dir]          # delete the diff, the model does not change
bunx likec4@1.61.0 safe-delete shop.legacyPayments --dry-run [project-dir]
bunx likec4@1.61.0 safe-delete shop.legacyPayments --orphans --scoped-views --dynamic-steps [project-dir]
```

If `likec4 diff --help` fails, the installed version predates model diffs.
`apply` and `safe-delete` never edit other diffs: they report the diffs they break (exit code 1).
`apply` keeps only the model changes: the title, description and comments of the diff are deleted with it.
Comments inside the braces of an added element move with the element. Put lasting notes in an element `description`.
