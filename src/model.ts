import { InputError, isObject } from './process.js';
import type { JsonObject } from './process.js';
import { sha256 } from './workspace.js';

// Ported from C4Spec's Python comparator. Keep computed semantics and drop
// generated relationship IDs and layout geometry.
const elements = ['id', 'kind', 'title', 'summary', 'description', 'technology', 'tags', 'metadata', 'parent', 'links'];
const relations = [
  'source', 'target', 'kind', 'title', 'summary', 'description', 'technology', 'tags',
  'metadata', 'direction', 'isBidirectional',
];
const identity = ['source', 'target', 'kind', 'direction', 'isBidirectional'];
const views = [
  'id', 'title', 'description', '_type', 'viewOf', 'variant', 'tags',
  'metadata', 'links', 'rules', 'notation',
];
const edges = ['source', 'target', 'title', 'description', 'technology', 'kind', 'direction'];
type ModelRecords = Record<string, JsonObject>;

export interface ComputedModel {
  projectId: string;
  elements: ModelRecords;
  relations: ModelRecords;
  views: ModelRecords;
}

function isModelRecords(value: unknown): value is ModelRecords {
  return isObject(value) && Object.values(value).every(isObject);
}

function isComputedModel(value: unknown): value is ComputedModel {
  return isObject(value) && typeof value.projectId === 'string' &&
    isModelRecords(value.elements) && isModelRecords(value.relations) && isModelRecords(value.views);
}

function viewRecords(value: unknown): JsonObject[] {
  if (!Array.isArray(value) || !value.every(isObject)) {
    throw new InputError('Unexpected computed LikeC4 view records');
  }
  return value;
}
const pick = (value: JsonObject, keys: string[]): JsonObject => Object.fromEntries(keys.filter(key => Object.hasOwn(value, key)).map(key => [key, value[key]]));
const sortPairs = <T>(pairs: [string, T][]) => pairs.sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0);

function ordered(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(ordered);
  if (isObject(value)) return Object.fromEntries(Object.keys(value).sort().map(key => [key, ordered(value[key])]));
  return value;
}

export const canonical = (value: unknown) => JSON.stringify(ordered(value));
const sorted = <T>(items: T[]) => sortPairs(items.map(item => [canonical(item), item])).map(([, item]) => item);

export function selectProject(data: unknown, project?: string): ComputedModel {
  const entries: unknown[] = Array.isArray(data) ? data : [data];
  if (!entries.every(isComputedModel)) {
    throw new InputError('Unexpected computed LikeC4 model export');
  }
  const selected = entries.filter(entry => project === undefined || entry.projectId === project);
  if (!selected.length) throw new InputError('No LikeC4 project matches ' + (project ?? 'the input'));
  if (new Set(selected.map(entry => entry.projectId)).size > 1) {
    throw new InputError('Multiple LikeC4 projects found. Pass --project with the exact project ID.');
  }
  const first = canonical(selected[0]);
  if (selected.some(entry => canonical(entry) !== first)) {
    throw new InputError('Conflicting duplicate LikeC4 project entries');
  }
  return selected[0];
}

export function emptyModel(projectId: string): ComputedModel {
  return { projectId, elements: {}, relations: {}, views: {} };
}

function fieldChanges(before: JsonObject, after: JsonObject) {
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])].sort();
  return Object.fromEntries(keys.filter(key => canonical(before[key]) !== canonical(after[key])).map(key => [
    key, { beforePresent: Object.hasOwn(before, key), afterPresent: Object.hasOwn(after, key),
      before: before[key] ?? null, after: after[key] ?? null },
  ]));
}

function namedChanges(before: ModelRecords, after: ModelRecords) {
  const added = Object.keys(after).filter(id => !Object.hasOwn(before, id)).sort();
  const removed = Object.keys(before).filter(id => !Object.hasOwn(after, id)).sort();
  const modified = Object.keys(after).filter(id => Object.hasOwn(before, id) &&
    canonical(before[id]) !== canonical(after[id])).sort();
  return {
    added, removed, modified,
    fieldChanges: Object.fromEntries(modified.map(id => [id, fieldChanges(before[id], after[id])])),
    addedDetails: Object.fromEntries(added.map(id => [id, after[id]])),
    removedDetails: Object.fromEntries(removed.map(id => [id, before[id]])),
  };
}

function viewSemantics(view: JsonObject, lookup: ModelRecords): JsonObject {
  const edgeIds = new Map<string, JsonObject>();
  const normalizedEdges = viewRecords(view.edges ?? []).map(edge => {
    if (typeof edge.id !== 'string' || edgeIds.has(edge.id)) {
      throw new InputError('Computed view has an invalid or duplicate edge ID');
    }
    const refs = edge.relations ?? [];
    if (!Array.isArray(refs) || !refs.every(id => typeof id === 'string')) {
      throw new InputError('Unexpected computed view relation references');
    }
    const relationKeys = refs.map(id => {
      if (!Object.hasOwn(lookup, id)) throw new InputError('View references an absent relation: ' + id);
      return canonical(pick(lookup[id], relations));
    }).sort();
    const value = { ...pick(edge, edges), relations: relationKeys };
    edgeIds.set(edge.id, value);
    return value;
  });
  const out: JsonObject = {
    ...pick(view, views),
    nodes: sorted(viewRecords(view.nodes ?? []).map(node => {
      const children = node.children ?? [];
      if (!Array.isArray(children)) throw new InputError('Unexpected computed view node children');
      return { ...pick(node, ['id', 'modelRef', 'parent']), children: sorted(children) };
    })),
    edges: sorted(normalizedEdges),
  };
  function flow(items: unknown): JsonObject[] {
    if (!Array.isArray(items)) throw new InputError('Unexpected dynamic view flow');
    return items.map(item => {
      if (typeof item === 'string') return edgeIds.get(item) ?? { unresolvedStep: item };
      if (isObject(item) && Object.hasOwn(item, 'flow')) {
        return { ...pick(item, ['_type', 'title', 'description']), flow: flow(item.flow) };
      }
      throw new InputError('Unexpected dynamic view flow item');
    });
  }
  if (Object.hasOwn(view, 'flow')) out.flow = flow(view.flow);
  return out;
}

function groupedRelations(relationsById: ModelRecords) {
  const groups = new Map<string, string[]>();
  for (const rel of Object.values(relationsById)) {
    const key = canonical(pick(rel, identity));
    const group = groups.get(key) ?? [];
    group.push(canonical(pick(rel, relations)));
    groups.set(key, group);
  }
  return groups;
}

function multisetDifference(left: string[], right: string[]) {
  const remaining = new Map<string, number>();
  for (const item of right) remaining.set(item, (remaining.get(item) ?? 0) + 1);
  const changed = new Map<string, number>();
  for (const item of left) {
    const count = remaining.get(item) ?? 0;
    if (count > 0) remaining.set(item, count - 1);
    else changed.set(item, (changed.get(item) ?? 0) + 1);
  }
  return sortPairs([...changed]).map(([value, count]) => ({ relationship: parseFields(value), count }));
}

// Group keys and values originate from canonicalized field selections above.
function parseFields(value: string): JsonObject {
  return JSON.parse(value);
}

function relationshipChanges(before: ModelRecords, after: ModelRecords) {
  const left = groupedRelations(before);
  const right = groupedRelations(after);
  const added: ReturnType<typeof multisetDifference> = [];
  const removed: ReturnType<typeof multisetDifference> = [];
  const modified: { identity: JsonObject; fieldChanges: ReturnType<typeof fieldChanges> }[] = [];
  for (const key of [...new Set([...left.keys(), ...right.keys()])].sort()) {
    const b = left.get(key) ?? [];
    const h = right.get(key) ?? [];
    if (b.length === 1 && h.length === 1 && b[0] !== h[0]) {
      modified.push({ identity: parseFields(key), fieldChanges: fieldChanges(parseFields(b[0]), parseFields(h[0])) });
    } else {
      added.push(...multisetDifference(h, b));
      removed.push(...multisetDifference(b, h));
    }
  }
  return { added, removed, modified };
}

function snapshot(model: ComputedModel) {
  return {
    projectId: model.projectId,
    elements: Object.fromEntries(Object.entries(model.elements).map(([id, item]) => [id, pick(item, elements)])),
    views: Object.fromEntries(Object.entries(model.views).map(([id, item]) => [id, viewSemantics(item, model.relations)])),
    relations: Object.values(model.relations).map(item => canonical(pick(item, relations))).sort(),
  };
}

export function compareModels(base: ComputedModel, head: ComputedModel) {
  if (base.projectId !== head.projectId) throw new InputError('Cannot compare different LikeC4 project IDs');
  const before = snapshot(base);
  const after = snapshot(head);
  const result = {
    projectId: head.projectId,
    elements: namedChanges(before.elements, after.elements),
    relationships: relationshipChanges(base.relations, head.relations),
    views: namedChanges(before.views, after.views),
    fingerprint: 'sha256:' + sha256(canonical({ before, after })),
  };
  const kinds = ['added', 'removed', 'modified'] as const;
  const changed = (['elements', 'relationships', 'views'] as const).some(section =>
    kinds.some(change => result[section][change].length));
  const indexChanged = kinds.some(change => result.views[change].includes('index'));
  const reviewHints = indexChanged
    ? ['The index view may be generated. Inspect the Git patch before treating it as an authored view edit.']
    : [];
  const limitations = [
    'The computed export can omit authored view selectors. Review the Git source patch.',
    'Renamed element IDs appear as removals and additions.',
    'Ambiguous edits to parallel relationships appear as removals and additions.',
  ];
  return { ...result, changed, reviewHints, limitations };
}
