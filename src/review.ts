import { cpSync, existsSync, mkdirSync, readdirSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { assertCompiler, buildViewer, exportModel, likec4, listDiffs, validModel } from './likec4.js';
import type { NativeDiff } from './likec4.js';
import { canonical, compareModels, emptyModel } from './model.js';
import { compilerVersion, InputError, isObject, readJson } from './process.js';
import {
  commit, committedModelDirectory, git, hasModel, manifest, modelDirectory, modelPatch, modelSnapshot,
  relativeModel, requireClean, resolveWorkspace, scratch, sha256, within,
} from './workspace.js';

import type { ModelOptions } from './workspace.js';

interface RevisionOptions extends ModelOptions {
  base?: string;
  head?: string;
}

export interface DiffOptions extends RevisionOptions {
  source?: boolean;
}

export interface ReviewOptions extends RevisionOptions {
  out?: string;
  diff?: string;
  checkProposal?: string;
  checkApplied?: string;
}

const writeJson = (file: string, data: unknown) => writeFileSync(file, JSON.stringify(data, null, 2) + '\n');
const sameSources = (a: unknown, b: unknown) => canonical(a) === canonical(b);
const recordLimits = { humanApprovalVerified: false, testsExecuted: false, runtimeVerified: false };

function refs(options: RevisionOptions) {
  const { root } = resolveWorkspace(options.repo, true);
  const requestedBase = commit(root, options.base);
  const head = commit(root, options.head ?? 'HEAD');
  const base = git(root, ['merge-base', requestedBase, head]).trim();
  const dir = committedModelDirectory(root, base, head, options.modelDir);
  return { root, dir, base, head, modelDir: relativeModel(root, dir) };
}

function compareDirectories(base: string, head: string, temp: string, project?: string) {
  const left = hasModel(base) ? exportModel(base, join(temp, 'base.json'), project) : null;
  const right = hasModel(head) ? exportModel(head, join(temp, 'head.json'), project) : null;
  const projectId = left?.projectId ?? right?.projectId;
  if (projectId === undefined) throw new InputError('Neither commit contains a LikeC4 model at this path');
  return compareModels(left ?? emptyModel(projectId), right ?? emptyModel(projectId));
}

function snapshots(input: ReturnType<typeof refs>, temp: string) {
  const base = modelSnapshot(input.root, input.base, input.modelDir, join(temp, 'base'));
  const head = modelSnapshot(input.root, input.head, input.modelDir, join(temp, 'head'));
  if (hasModel(base)) validModel(base);
  if (hasModel(head)) validModel(head);
  return { base, head };
}

export function diffCommand(options: DiffOptions) {
  const input = refs(options);
  const { root, base, head, modelDir } = input;
  const sourcePatch = modelPatch(root, base, head, modelDir);
  if (options.source) return { base, head, modelDir, sourcePatch };
  return scratch(temp => {
    assertCompiler(root);
    const { base: left, head: right } = snapshots(input, temp);
    return {
      base, head, modelDir, sourcePatch, sourceChanged: sourcePatch.length > 0,
      semantic: compareDirectories(left, right, temp, options.project),
      pendingDiffs: hasModel(right) ? listDiffs(right).map(({ id, projectId }) => ({ id, projectId })) : [],
    };
  });
}

function outsideOutput(root: string, output?: string) {
  if (!output) throw new InputError('Pass --out with a new directory outside the repository');
  const absolute = resolve(output);
  if (!existsSync(dirname(absolute))) throw new InputError('Parent directory of --out must exist');
  const parent = realpathSync(dirname(absolute));
  const final = resolve(parent, basename(absolute));
  if (within(root, final) || within(final, root)) {
    throw new InputError('--out must be outside the repository and its ancestors');
  }
  if (existsSync(final)) throw new InputError('Output path already exists: ' + final);
  return final;
}

function publishBundle(bundle: string, destination: string) {
  mkdirSync(destination);
  try {
    for (const entry of readdirSync(bundle)) {
      cpSync(join(bundle, entry), join(destination, entry), {
        recursive: true, errorOnExist: true, force: false,
      });
    }
  } catch (error) {
    rmSync(destination, { recursive: true, force: true });
    throw error;
  }
}

function verifyHead(input: Pick<ReturnType<typeof refs>, 'root' | 'dir' | 'head'>) {
  requireClean(input.root, input.dir);
  if (commit(input.root, 'HEAD') !== input.head) throw new InputError('HEAD changed during review. Retry.');
}

function applyToScratch(proposed: string, name: string, applied: string) {
  if (name.startsWith('-')) throw new InputError('Invalid native diff name');
  cpSync(proposed, applied, { recursive: true });
  likec4(applied, ['diff', 'apply', name, '.']);
  validModel(applied);
  if (listDiffs(applied).length !== 0) throw new InputError('Scratch apply left a pending native proposal');
}

function nativeBundle(pending: NativeDiff[], proposed: string, temp: string, out: string, options: ReviewOptions) {
  if (pending.length !== 1 || (options.diff !== undefined && pending[0].id !== options.diff)) {
    throw new InputError('Review requires exactly one pending native proposal. Isolate the matching diff first.');
  }
  const name = pending[0].id;
  if (options.project !== undefined && options.project !== pending[0].projectId) {
    throw new InputError('The pending diff belongs to LikeC4 project ' + pending[0].projectId);
  }
  if (name.startsWith('-')) throw new InputError('Invalid native diff name');
  const original = manifest(proposed);
  const dry = likec4(proposed, ['diff', 'apply', name, '--dry-run', '.']).stdout;
  buildViewer(proposed, join(out, 'review-site'));
  if (!sameSources(manifest(proposed), original)) throw new InputError('Review changed the proposal during dry-run or build');
  const applied = join(temp, 'applied');
  applyToScratch(proposed, name, applied);
  const semantic = compareDirectories(proposed, applied, temp, options.project ?? pending[0].projectId);
  if (!semantic.changed) throw new InputError('Native proposal has no supported computed delta; inspect its source');
  writeJson(join(out, 'semantic-diff.json'), semantic);
  writeJson(join(out, 'diff-list.json'), pending);
  writeFileSync(join(out, 'dry-run.txt'), dry);
  cpSync(proposed, join(out, 'proposal'), { recursive: true });
  cpSync(applied, join(out, 'applied'), { recursive: true });
  return {
    kind: 'c4spec-cli-native-review', diff: name, projectId: semantic.projectId,
    sources: original, sourcesDigest: sha256(canonical(original)),
    expectedAppliedSources: manifest(applied), nativeImpact: pending[0],
  };
}

function directBundle(before: string, after: string, temp: string, out: string, project?: string) {
  const semantic = compareDirectories(before, after, temp, project);
  if (!hasModel(after)) throw new InputError('The head has no model preview. Use c4spec diff.');
  const sources = manifest(after);
  buildViewer(after, join(out, 'review-site'));
  if (hasModel(before)) buildViewer(before, join(out, 'base-site'));
  if (!sameSources(manifest(after), sources)) throw new InputError('Review build changed model inputs');
  writeJson(join(out, 'semantic-diff.json'), semantic);
  return { kind: 'c4spec-cli-direct-review', projectId: semantic.projectId, sources,
    sourcesDigest: sha256(canonical(sources)) };
}

export function reviewCommand(options: ReviewOptions) {
  const input = refs(options);
  verifyHead(input);
  const destination = outsideOutput(input.root, options.out);
  return scratch(temp => {
    assertCompiler(input.root);
    const { base, head } = snapshots(input, temp);
    if (!hasModel(head)) throw new InputError('The head has no model preview. Use c4spec diff.');
    const pending = listDiffs(head);
    const out = join(temp, 'bundle');
    mkdirSync(out);
    const review = pending.length > 0 || options.diff !== undefined
      ? nativeBundle(pending, head, temp, out, options)
      : directBundle(base, head, temp, out, options.project);
    writeFileSync(join(out, 'source.patch'), modelPatch(input.root, input.base, input.head, input.modelDir));
    const packet = {
      schemaVersion: 1, ...review, baseCommit: input.base, proposalCommit: input.head,
      modelDir: input.modelDir, likec4Version: compilerVersion, ...recordLimits,
      limitations: [
        'Local review evidence does not authenticate approval.',
        'Only committed files in the selected model directory are copied. Root models copy DSL and config files.',
        'Computed views can omit authored selectors. Inspect the Git source patch.',
      ],
    };
    writeJson(join(out, 'review.json'), packet);
    verifyHead(input);
    publishBundle(out, destination);
    return {
      valid: true, kind: review.kind, proposalCommit: input.head, ...recordLimits,
      review: join(destination, 'review.json'), viewer: join(destination, 'review-site', 'index.html'),
    };
  });
}

export function verifyReview(options: ReviewOptions, applied = false) {
  const filename = applied ? options.checkApplied : options.checkProposal;
  if (!filename) throw new InputError('Pass the path to the native review packet');
  const packet = readJson(resolve(filename));
  if (!isObject(packet) || packet.kind !== 'c4spec-cli-native-review' || packet.schemaVersion !== 1 ||
      typeof packet.modelDir !== 'string' || typeof packet.proposalCommit !== 'string' ||
      typeof packet.diff !== 'string' || !Array.isArray(packet.sources) ||
      !Array.isArray(packet.expectedAppliedSources) || packet.likec4Version !== compilerVersion ||
      sha256(canonical(packet.sources)) !== packet.sourcesDigest) {
    throw new InputError('Invalid or incompatible C4Spec CLI native review packet');
  }
  const { diff: name, sources, expectedAppliedSources } = packet;
  const { root } = resolveWorkspace(options.repo, true);
  const dir = modelDirectory(root, options.modelDir ?? packet.modelDir);
  const path = relativeModel(root, dir);
  if (path !== packet.modelDir) throw new InputError('Model directory differs from review');
  const head = commit(root, 'HEAD');
  const reviewed = commit(root, packet.proposalCommit);
  if (reviewed !== packet.proposalCommit || (applied && head === reviewed) || (!applied && head !== reviewed)) {
    throw new InputError(applied ? 'Applied verification needs a committed descendant of the proposal' :
      'Proposal HEAD changed since review');
  }
  if (applied) git(root, ['merge-base', '--is-ancestor', reviewed, head]);
  const input = { root, dir, head };
  verifyHead(input);
  return scratch(temp => {
    assertCompiler(root);
    const snapshot = modelSnapshot(root, reviewed, path, join(temp, 'reviewed'));
    if (!sameSources(manifest(snapshot), sources)) {
      throw new InputError('Reviewed sources do not match the proposal Git commit');
    }
    validModel(snapshot);
    const pending = listDiffs(snapshot);
    if (pending.length !== 1 || pending[0].id !== name) {
      throw new InputError('Pending proposals differ from the expected review state');
    }
    const current = applied ? modelSnapshot(root, head, path, join(temp, 'current')) : snapshot;
    if (applied) {
      if (!sameSources(manifest(current), expectedAppliedSources)) {
        throw new InputError('Applied sources differ from the reviewed result. Review the change again.');
      }
      const replay = join(temp, 'replay');
      applyToScratch(snapshot, name, replay);
      if (!sameSources(manifest(replay), expectedAppliedSources)) {
        throw new InputError('Review packet differs from applying the committed proposal in scratch');
      }
    }
    verifyHead(input);
    return { valid: true, mode: applied ? 'applied' : 'proposal', commit: head, ...recordLimits };
  });
}
