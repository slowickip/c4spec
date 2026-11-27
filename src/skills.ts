import { createHash } from 'node:crypto';
import { lstatSync, readFileSync, readdirSync, realpathSync } from 'node:fs';
import { join, posix } from 'node:path';
import { compilerVersion, errorMessage, InputError, isObject, packageRoot, pkg, readJson } from './process.js';
import { resolveWorkspace } from './workspace.js';

const basicSkills = ['c4spec', 'c4spec-maintain'];
export const skillProfiles = {
  basic: basicSkills,
  extended: [...basicSkills, 'c4spec-apply', 'c4spec-continue', 'c4spec-explore',
    'c4spec-finish', 'c4spec-propose', 'c4spec-review', 'c4spec-verify'].sort(),
};
export type SkillProfile = keyof typeof skillProfiles;
export const skillPaths = ['.agents/skills', '.claude/skills'];

const commitSha = /^[0-9a-f]{40}$/i;
const folderHash = /^[0-9a-f]{64}$/i;
const ignoredDirectories = new Set(['.git', '__pycache__', '__pypackages__']);
type Files = Map<string, Buffer>;
type SkillState = 'tracked' | 'modified' | 'unverified' | 'missing' | 'blocked';

interface SkillInstallation {
  name: string;
  path: string;
  state: SkillState;
  revision?: string;
  detail?: string;
}

function readSkillFiles(directory: string, prefix = '', files: Files = new Map()): Files {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (entry.name === 'metadata.json' || (entry.isDirectory() && ignoredDirectories.has(entry.name))) continue;
    const path = join(directory, entry.name);
    const name = posix.join(prefix, entry.name);
    if (entry.isDirectory()) readSkillFiles(path, name, files);
    else if (entry.isFile()) files.set(name, normalizeLineEndings(readFileSync(path)));
    else throw new InputError('Review the link or special file inside the skill: ' + name);
  }
  return files;
}

// Adapted from skills 1.8.1 src/skill-hash.ts (MIT, Vercel, Inc.).
function normalizeLineEndings(content: Buffer) {
  if (content.includes(0) || !content.includes('\r\n')) return content;
  return Buffer.from(content.toString('latin1').replaceAll('\r\n', '\n'), 'latin1');
}

function hashSkillFiles(files: Files) {
  const entries = [...files].map(([name, content]) => ({ path: Buffer.from(name), content }));
  entries.sort((a, b) => Buffer.compare(a.path, b.path));
  const hash = createHash('sha256');
  for (const { path, content } of entries) {
    hash.update(path);
    hash.update('\0');
    hash.update(String(content.length));
    hash.update('\0');
    hash.update(content);
  }
  return hash.digest('hex');
}

function readLock(root: string) {
  const path = join(root, 'skills-lock.json');
  const stat = lstatSync(path, { throwIfNoEntry: false });
  if (stat === undefined) return {};
  if (!stat.isFile()) throw new InputError('Expected a regular skills-lock.json file');
  const lock = readJson(path);
  if (!isObject(lock) || lock.version !== 2 || !isObject(lock.skills)) {
    throw new InputError('Expected a version 2 skills-lock.json for verifying installed skill content');
  }
  return lock.skills;
}

function inventory(root: string) {
  let lock: Record<string, unknown> = {};
  let lockIssue: string | undefined;
  try {
    lock = readLock(root);
  } catch (error) {
    lockIssue = errorMessage(error);
  }
  const installations: { info: SkillInstallation; files?: Files }[] = [];
  for (const name of skillProfiles.extended) {
    const candidate = lock[name];
    const entry = isObject(candidate) ? candidate : undefined;
    const revision = [entry?.commit, entry?.ref]
      .find((value): value is string => typeof value === 'string' && commitSha.test(value));
    const digest = typeof entry?.computedHash === 'string' && folderHash.test(entry.computedHash)
      ? entry.computedHash.toLowerCase() : undefined;
    const canonical = join(root, skillPaths[0], name);
    let found = false;
    for (const dir of skillPaths) {
      const path = posix.join(dir, name);
      const absolute = join(root, path);
      const identity = { name, path, revision };
      try {
        const stat = lstatSync(absolute, { throwIfNoEntry: false });
        if (stat === undefined) continue;
        found = true;
        const resolved = realpathSync(absolute);
        if (dir !== skillPaths[0] && resolved === canonical && lstatSync(canonical).isDirectory()) continue;
        if (!stat.isDirectory() || resolved !== absolute) {
          throw new InputError('Review the skill path before upgrading it');
        }
        const files = readSkillFiles(resolved);
        const state = !files.has('SKILL.md') ? 'missing'
          : !digest ? 'unverified' : hashSkillFiles(files) === digest ? 'tracked' : 'modified';
        installations.push({ info: { ...identity, state }, files });
      } catch (error) {
        found = true;
        installations.push({ info: { ...identity, state: 'blocked', detail: errorMessage(error) } });
      }
    }
    if (!found && entry) {
      installations.push({ info: { name, path: posix.join(skillPaths[0], name), revision, state: 'missing' } });
    }
  }
  return { lockIssue, installations };
}

export function installedSkills(root: string) {
  const { lockIssue, installations } = inventory(root);
  return { lockIssue, entries: installations.map(({ info }) => info) };
}

export function previewSkillUpdate(repo?: string) {
  const { root } = resolveWorkspace(repo);
  const { lockIssue, installations } = inventory(root);
  const skills = installations.map(({ info, files }) => {
    const changes: { path: string; action: 'add' | 'update' | 'remove' }[] = [];
    if (files) {
      const target = readSkillFiles(join(packageRoot, skillPaths[0], info.name));
      if (!target.has('SKILL.md')) throw new InputError('Missing skill in the CLI bundle: ' + info.name);
      for (const name of [...new Set([...files.keys(), ...target.keys()])].sort()) {
        const previous = files.get(name);
        const next = target.get(name);
        const path = posix.join(info.path, name);
        if (!previous) changes.push({ path, action: 'add' });
        else if (!next) changes.push({ path, action: 'remove' });
        else if (!previous.equals(next)) changes.push({ path, action: 'update' });
      }
    }
    return { ...info, changes };
  });
  return {
    root, dryRun: true, target: { c4spec: pkg.version, likec4: compilerVersion },
    valid: !lockIssue && skills.length > 0 && skills.every(skill => skill.state === 'tracked'),
    lockIssue, skills,
  };
}
