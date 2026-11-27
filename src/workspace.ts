import { createHash } from 'node:crypto';
import {
  existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync,
  realpathSync, rmSync, writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, dirname, isAbsolute, join, posix, relative, resolve, sep } from 'node:path';
import { errorMessage, execute, InputError } from './process.js';

const ignored = new Set(['.git', 'node_modules', '.agents', '.claude', '.codex', '.likec4', 'dist', 'build']);
export interface ModelOptions {
  repo?: string;
  modelDir?: string;
  project?: string;
}

interface SourceEntry {
  path: string;
  sha256: string;
}

export const isModel = (path: string) => /\.(?:c4|likec4)$/i.test(path);
const configName = (path: string) => /^(?:\.likec4rc(?:\..*)?|\.?likec4\.config\.(?:json5?|ya?ml|[cm]?[jt]s))$/.test(basename(path));
const order = (left: string, right: string) => left < right ? -1 : left > right ? 1 : 0;

export function git(cwd: string, args: string[]) {
  return execute('git', ['-C', cwd, ...args], cwd).stdout;
}

function gitBytes(cwd: string, args: string[]) {
  return execute('git', ['-C', cwd, ...args], cwd, { binary: true }).stdout;
}

export function within(parent: string, child: string) {
  const rel = relative(parent, child);
  return !isAbsolute(rel) && rel !== '..' && !rel.startsWith('..' + sep);
}

export function resolveWorkspace(input?: string, requireGit = false) {
  const start = resolve(input ?? process.cwd());
  if (!existsSync(start) || !lstatSync(start).isDirectory()) {
    throw new InputError('Project directory does not exist: ' + start);
  }
  let root: string;
  try {
    root = realpathSync(git(start, ['rev-parse', '--show-toplevel']).trim());
  } catch (error) {
    if (requireGit) throw new InputError('Run this command in a Git working tree. ' + errorMessage(error));
    return { root: realpathSync(start), git: false };
  }
  if (input && root !== realpathSync(start)) {
    if (requireGit) throw new InputError('--repo must name the root of the Git working tree: ' + root);
    return { root: realpathSync(start), git: false };
  }
  return { root, git: true };
}

function checkModelPath(root: string, input: string) {
  const dir = resolve(root, input);
  if (!within(root, dir)) throw new InputError('--model-dir must stay inside the project');
  for (let parent = dir; parent !== root; parent = dirname(parent)) {
    if (existsSync(parent) && !within(root, realpathSync(parent))) {
      throw new InputError('--model-dir resolves outside the project');
    }
  }
  if (existsSync(dir) && !lstatSync(dir).isDirectory()) throw new InputError('Model path is not a directory: ' + input);
  return dir;
}

function findModelDirectories(dir: string, matches = new Set<string>()) {
  if (!existsSync(dir) || !lstatSync(dir).isDirectory()) return matches;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory() && !ignored.has(entry.name) && !entry.name.startsWith('.')) {
      findModelDirectories(join(dir, entry.name), matches);
    } else if (entry.isFile() && isModel(entry.name)) {
      matches.add(dir);
    }
  }
  return matches;
}

function chooseModelDirectory(folders: string[]): string | undefined {
  const candidates = [...new Set(folders)];
  const conventional = ['architecture', 'docs/architecture'].filter(path =>
    candidates.some(folder => folder === path || folder.startsWith(path + '/')));
  if (conventional.length === 1) return conventional[0];
  if (conventional.length > 1) throw new InputError('Multiple model directories found. Pass --model-dir.');
  if (candidates.includes('.')) return '.';
  if (candidates.length > 1) throw new InputError('Multiple model directories found. Pass --model-dir.');
  return candidates[0];
}

export function modelDirectory(root: string, explicit?: string, scaffold = false) {
  if (explicit !== undefined) return checkModelPath(root, explicit);
  const path = chooseModelDirectory([...findModelDirectories(root)].map(dir => relativeModel(root, dir)));
  if (!path && !scaffold) throw new InputError('No LikeC4 sources found. Run c4spec init or pass --model-dir.');
  return checkModelPath(root, path ?? 'architecture');
}

export function committedModelDirectory(root: string, base: string, head: string, explicit?: string) {
  if (explicit !== undefined) return checkModelPath(root, explicit);
  function find(commitId: string) {
    const files = git(root, ['ls-tree', '--full-tree', '--name-only', '-r', '-z', commitId]).split('\0');
    const folders = files.filter(isModel).map(file => posix.dirname(file)).filter(folder =>
      folder === '.' || !folder.split('/').some(name => ignored.has(name) || name.startsWith('.')));
    return chooseModelDirectory(folders);
  }
  const before = find(base);
  const after = find(head);
  if (before && after && before !== after) {
    throw new InputError('Model directory moved between commits. Pass --model-dir . to compare both paths.');
  }
  const path = after ?? before;
  if (!path) throw new InputError('No committed LikeC4 sources found. Pass --model-dir.');
  return checkModelPath(root, path);
}

export function hasModel(dir: string) {
  return findModelDirectories(dir).size > 0;
}

export function relativeModel(root: string, dir: string) {
  return relative(root, dir).split(sep).join('/') || '.';
}

export function commit(root: string, ref?: string) {
  if (!ref) throw new InputError('Pass --base with the Git base ref.');
  const id = git(root, ['rev-parse', '--verify', '--end-of-options', ref + '^{commit}']).trim();
  if (!/^[a-f0-9]{40}$|^[a-f0-9]{64}$/.test(id)) throw new InputError('Expected a Git commit ID');
  return id;
}

export function requireClean(root: string, dir: string) {
  if (git(root, ['--literal-pathspecs', 'status', '--porcelain=v1', '-z', '--untracked-files=all',
    '--', relativeModel(root, dir)])) {
    throw new InputError('Model input has uncommitted files. Commit the model before reviewing it.');
  }
}

export function modelPatch(root: string, base: string, head: string, path: string) {
  if (path !== '.') {
    return git(root, ['--literal-pathspecs', 'diff', '--no-ext-diff', '--no-textconv', '--no-color',
      base, head, '--', path]);
  }
  return git(root, ['diff', '--no-ext-diff', '--no-textconv', '--no-color', base, head, '--',
    ':(icase,glob)**/*.c4', ':(icase,glob)**/*.likec4', ':(glob)**/*likec4.config.*', ':(glob)**/.likec4rc*']);
}

export function modelSnapshot(root: string, id: string, modelPath: string, dest: string) {
  mkdirSync(dest);
  const entries = gitBytes(root, ['--literal-pathspecs', 'ls-tree', '-r', '-z', '--full-tree', id, '--', modelPath])
    .toString('utf8').split('\0').filter(Boolean);
  // Root models may share a directory with the application. Limit root
  // snapshots to model and config files; set a model directory for assets.
  for (const entry of entries) {
    const tab = entry.indexOf('\t');
    const path = entry.slice(tab + 1);
    if (modelPath === '.' && !isModel(path) && !configName(path)) continue;
    const [mode, type, blob] = entry.slice(0, tab).split(' ');
    if (type !== 'blob' || !['100644', '100755'].includes(mode)) {
      throw new InputError('Committed model input must be a regular file: ' + path);
    }
    const local = modelPath === '.' ? path : path.slice(modelPath.length + 1);
    const target = resolve(dest, local);
    if (!local || local.includes('\\') || !within(dest, target) || target === dest) {
      throw new InputError('Unsafe path in Git model snapshot: ' + path);
    }
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, gitBytes(root, ['cat-file', 'blob', blob]), { flag: 'wx' });
  }
  return dest;
}

export function sha256(value: string | Buffer) {
  return createHash('sha256').update(value).digest('hex');
}

export function manifest(dir: string): SourceEntry[] {
  function walk(folder: string): SourceEntry[] {
    return readdirSync(folder, { withFileTypes: true }).flatMap(entry => {
      const path = join(folder, entry.name);
      if (entry.isDirectory()) return walk(path);
      if (!entry.isFile()) throw new InputError('Model input contains a nonregular file: ' + path);
      return [{ path: relativeModel(dir, path), sha256: sha256(readFileSync(path)) }];
    });
  }
  return walk(dir).sort((a, b) => order(a.path, b.path));
}

export function scratch<T>(action: (dir: string) => T): T {
  const dir = mkdtempSync(join(tmpdir(), 'c4spec-'));
  try {
    return action(dir);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

export function evidenceFile(root: string, ref: string) {
  if (typeof ref !== 'string' || !ref || /[\\:*?\[\]#\0\n\r]/.test(ref) ||
      ref.startsWith('~') || isAbsolute(ref) || ref.split('/').includes('..')) {
    throw new InputError('Evidence reference must be a literal repository-relative path');
  }
  const full = resolve(root, ref);
  if (!within(root, full) || full === root) throw new InputError('Evidence path escapes the project');
  for (let parent = full; parent !== root; parent = dirname(parent)) {
    if (existsSync(parent) && !within(root, realpathSync(parent))) {
      throw new InputError('Evidence path resolves outside the project');
    }
  }
  return existsSync(full) && lstatSync(realpathSync(full)).isFile();
}
