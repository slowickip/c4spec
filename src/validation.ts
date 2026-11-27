import { join } from 'node:path';
import { Ajv2020 } from 'ajv/dist/2020.js';
import type { ValidateFunction } from 'ajv/dist/2020.js';
import formats = require('ajv-formats');
import { canonical } from './model.js';
import type { ComputedModel } from './model.js';
import { errorMessage, InputError, isObject, packageRoot, readJson } from './process.js';
import { evidenceFile } from './workspace.js';

export type Phase = 'proposal' | 'completion';
type Severity = 'error' | 'warning';

interface Finding {
  severity: Severity;
  code: string;
  location: string;
  message: string;
}

type EmitFinding = (severity: Severity, code: string, location: string, message: string) => void;

interface Constraint {
  id: string;
  statement: string;
  verificationRefs?: string[];
  appliesTo?: string[];
}

interface ChangeRecord {
  constraints?: (Constraint & { durability: 'persistent' | 'change-only' })[];
  alternatives?: { id: string }[];
  decision?: string;
  scope?: string[];
  evidence?: { element: string; path: string; state: 'planned' | 'declared' | 'inferred' | 'observed' }[];
}

interface ConstraintRegister {
  constraints: (Constraint & { supersedes?: string[] })[];
}

interface RecordOptions {
  root: string;
  change?: unknown;
  register?: unknown;
  phase: Phase;
  viewWarning: number;
}

const schemas = join(packageRoot, '.agents', 'skills', 'c4spec', 'schemas');
const ajv = new Ajv2020({ allErrors: true, strict: false });
formats.default(ajv);

function compileSchema<T>(filename: string): ValidateFunction<T> {
  const schema = readJson(join(schemas, filename));
  if (!isObject(schema)) throw new InputError('Invalid bundled schema: ' + filename);
  return ajv.compile<T>(schema);
}

const changeSchema = compileSchema<ChangeRecord>('change.schema.json');
const registerSchema = compileSchema<ConstraintRegister>('constraints.schema.json');
const detailName = /(?:\.ya?ml$|\.json$|(?:Controller|Repository|DTO)$|^(?:helmrelease|externalsecret)[-_.])/i;

function checkSchema<T>(value: unknown, validate: ValidateFunction<T>, label: string,
  emit: EmitFinding): value is T | undefined {
  if (value === undefined || validate(value)) return true;
  for (const error of validate.errors ?? []) {
    emit('error', 'schema', label + error.instancePath, 'JSON Schema rule ' + error.keyword + ' failed');
  }
  return false;
}

function uniqueIds(items: { id: string }[], at: string, emit: EmitFinding) {
  if (new Set(items.map(item => item.id)).size !== items.length) {
    emit('error', 'duplicate_id', at, 'IDs in this collection must be unique');
  }
}

function referencedPath(root: string, ref: string, at: string, planned: boolean, emit: EmitFinding) {
  try {
    if (!evidenceFile(root, ref)) {
      emit(planned ? 'warning' : 'error', planned ? 'planned_path' : 'missing_path', at,
        planned ? 'Planned reference does not exist yet' : 'Evidence or verification file does not exist');
    }
  } catch (error) {
    emit('error', 'unsafe_path', at, errorMessage(error));
  }
}

function mapped(model: ComputedModel, id: string, at: string, level: Severity, kind: string, emit: EmitFinding) {
  if (!Object.hasOwn(model.elements, id)) emit(level, 'unmapped_' + kind, at, 'Unknown model element: ' + id);
}

function checkConstraint(model: ComputedModel, root: string, constraint: Constraint, at: string,
  persistent: boolean, planned: Set<string>, severity: Severity, emit: EmitFinding) {
  const refs = constraint.verificationRefs ?? [];
  if (persistent && refs.length === 0) emit('error', 'verification_required', at, 'Persistent constraints require verification references');
  if (refs.length !== new Set(refs).size) emit('error', 'duplicate_ref', at, 'Duplicate verification reference');
  for (const ref of refs) referencedPath(root, ref, at, planned.has(ref), emit);
  for (const id of constraint.appliesTo ?? []) mapped(model, id, at, severity, 'constraint', emit);
}

function sameConstraint(a: Constraint, b: Constraint) {
  const set = (values?: string[]) => [...new Set(values ?? [])].sort();
  return a.statement === b.statement && canonical(set(a.appliesTo)) === canonical(set(b.appliesTo)) &&
    canonical(set(a.verificationRefs)) === canonical(set(b.verificationRefs));
}

function checkRecords(model: ComputedModel, root: string, change: ChangeRecord,
  register: ConstraintRegister | undefined, phase: Phase, emit: EmitFinding) {
  const level = phase === 'proposal' ? 'warning' : 'error';
  const items = change.constraints ?? [];
  const alternatives = change.alternatives ?? [];
  const evidence = change.evidence ?? [];
  const planned = new Set<string>();
  uniqueIds(items, 'change.constraints', emit);
  uniqueIds(alternatives, 'change.alternatives', emit);
  if (change.decision && !alternatives.some(item => item.id === change.decision)) {
    emit('error', 'unknown_decision', 'change.decision', 'Decision must reference an existing alternative');
  }
  for (const [i, id] of (change.scope ?? []).entries()) mapped(model, id, 'change.scope.' + i, level, 'scope', emit);
  for (const [i, item] of evidence.entries()) {
    const at = 'change.evidence.' + i;
    const future = item.state === 'planned';
    if (future && phase === 'proposal') planned.add(item.path);
    if (future && phase === 'completion') emit('error', 'still_planned', at, 'Completion requires actual evidence');
    mapped(model, item.element, at, level, 'evidence', emit);
    referencedPath(root, item.path, at, future && phase === 'proposal', emit);
  }
  const persistent = items.filter(item => item.durability === 'persistent');
  for (const [i, item] of items.entries()) {
    const at = 'change.constraints.' + i;
    const durable = item.durability === 'persistent';
    checkConstraint(model, root, item, at, durable, planned, level, emit);
    if (durable) {
      for (const ref of item.verificationRefs ?? []) {
        if (!evidence.some(e => e.path === ref && (!item.appliesTo?.length || item.appliesTo.includes(e.element)))) {
          emit(level, 'unlinked_verification_ref', at, 'Verification reference needs matching change evidence');
        }
      }
    }
  }
  if (!register) {
    if (persistent.length && phase === 'completion') {
      emit('warning', 'register_not_checked', 'constraints', 'No durable register supplied');
    }
    return;
  }
  uniqueIds(register.constraints, 'constraints.constraints', emit);
  const byId = new Map(register.constraints.map(item => [item.id, item]));
  for (const item of persistent) {
    const saved = byId.get(item.id);
    const at = 'change.constraints.' + item.id;
    if (!saved) emit(level, 'unpromoted_constraint', at, 'Persistent constraint is missing from the register');
    else if (!sameConstraint(item, saved)) {
      emit(level, 'constraint_register_mismatch', at, 'Registered constraint differs from the change');
    }
  }
  for (const [i, item] of register.constraints.entries()) {
    const at = 'constraints.constraints.' + i;
    checkConstraint(model, root, item, at, true, planned, 'error', emit);
    for (const id of item.supersedes ?? []) {
      if (id === item.id) emit('error', 'self_supersession', at, 'A constraint cannot supersede itself');
      else if (!byId.has(id)) emit('warning', 'unknown_supersession', at, 'Superseded ID is absent from the register');
    }
  }
}

function adviseModel(model: ComputedModel, viewWarning: number, emit: EmitFinding) {
  for (const [id, element] of Object.entries(model.elements)) {
    const at = 'model.elements.' + id;
    const description = element.description;
    const text = isObject(description) ? description.txt ?? description.md : description;
    const title = typeof element.title === 'string' ? element.title : '';
    if (!title.trim()) emit('warning', 'missing_name', at, 'Give the element a meaningful name');
    if (typeof text !== 'string' || !text.trim()) emit('warning', 'missing_responsibility', at, 'Describe the element responsibility');
    if ((element.kind === 'container' || element.kind === 'component') && !element.technology) {
      emit('warning', 'missing_technology', at, 'Identify the technology when it helps explain this element');
    }
    if (detailName.test(title)) {
      emit('warning', 'implementation_detail', at, 'Check that this detail matters to architecture');
    }
  }
  for (const [id, relation] of Object.entries(model.relations)) {
    const at = 'model.relations.' + id;
    if (!relation.title && !relation.description) emit('warning', 'unlabeled_relationship', at, 'Describe the relationship purpose');
    for (const endpoint of [relation.source, relation.target]) {
      const ref = isObject(endpoint) ? endpoint.model : endpoint;
      if (typeof ref === 'string' && ref && !Object.hasOwn(model.elements, ref)) emit('error', 'dangling_relation', at, 'Unknown endpoint: ' + ref);
    }
  }
  for (const [id, view] of Object.entries(model.views)) {
    if ((Array.isArray(view.nodes) || isObject(view.nodes)) && Object.keys(view.nodes).length > viewWarning) {
      emit('warning', 'large_view', 'model.views.' + id, 'Prefer a more focused view');
    }
  }
}

export function validateRecords(model: ComputedModel, { root, change, register, phase, viewWarning }: RecordOptions) {
  const findings: Finding[] = [];
  const emit: EmitFinding = (severity, code, location, message) => {
    findings.push({ severity, code, location, message });
  };
  const changeValid = checkSchema(change, changeSchema, 'change', emit);
  const registerValid = checkSchema(register, registerSchema, 'constraints', emit);
  if (changeValid && registerValid) {
    checkRecords(model, root, change ?? {}, register, phase, emit);
    adviseModel(model, viewWarning, emit);
  }
  const errors = findings.filter(item => item.severity === 'error').length;
  return {
    schemaVersion: 1, valid: errors === 0, phase, errors, warnings: findings.length - errors,
    findings, testsExecuted: false, runtimeVerified: false, implementationConformanceVerified: false,
  };
}
