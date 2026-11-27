import { existsSync, lstatSync, mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { assertCompiler, compilerValidation, exportModel } from './likec4.js';
import { compilerVersion, errorMessage, execute, InputError, isObject, packageRoot, pkg, readJson, runPackage } from './process.js';
import { installedSkills, skillPaths, skillProfiles } from './skills.js';
import { hasModel, modelDirectory, relativeModel, resolveWorkspace, scratch, within } from './workspace.js';

import type { ModelOptions } from './workspace.js';
import type { SkillProfile } from './skills.js';
import type { Phase } from './validation.js';

export interface InitOptions extends ModelOptions {
  agent?: string[];
  profile: SkillProfile;
  dryRun?: boolean;
}

export interface ValidateOptions extends ModelOptions {
  change?: string;
  constraintsFile?: string;
  compileOnly?: boolean;
  phase: Phase;
}

const starter = `specification {
  element person
  element system
}

model {
  user = person 'User' {
    description 'Uses the application to complete a task.'
  }
  app = system 'Application' {
    description 'Provides the workflow the user needs.'
  }
  user -> app 'Uses'
}

views {
  view context {
    title 'L1 — Application context'
    include *
  }
}
`;

const supportedAgents = new Set(['codex', 'claude-code']);

export function version() {
  return { c4spec: pkg.version, likec4: compilerVersion, node: process.versions.node };
}

function pathExists(path: string) {
  try {
    lstatSync(path);
    return true;
  } catch (error) {
    if (isObject(error) && error.code === 'ENOENT') return false;
    throw error;
  }
}

function planSkillInstall(root: string, selectedSkills: string[], agentFolders: string[]) {
  const lock = join(root, 'skills-lock.json');
  for (const path of ['.agents', '.claude', ...skillPaths, 'skills-lock.json']) {
    const target = join(root, path);
    if (pathExists(target) && lstatSync(target).isSymbolicLink()) {
      throw new InputError('Resolve the existing symlink before installing skills: ' + path);
    }
  }
  const data = pathExists(lock) ? readJson(lock) : undefined;
  const existing = isObject(data) && isObject(data.skills) ? data.skills : {};
  return selectedSkills.filter(name => {
    const installed = Object.hasOwn(existing, name) ||
      skillPaths.some(folder => pathExists(join(root, folder, name)));
    if (!installed) return true;
    const missing = agentFolders.find(folder => !lstatSync(join(root, folder, name, 'SKILL.md'),
      { throwIfNoEntry: false })?.isFile());
    if (missing) {
      throw new InputError(`Existing C4Spec skill ${name} is incomplete for ${missing}. Review the skill paths before installing for this agent.`);
    }
    return false;
  });
}

export function init(dir: string | undefined, options: InitOptions) {
  if (dir !== undefined && options.repo !== undefined) {
    throw new InputError('Use either the init directory argument or --repo');
  }
  const agents = [...new Set(options.agent ?? [])];
  if (agents.some(agent => !supportedAgents.has(agent))) {
    throw new InputError('Supported init agents are codex and claude-code');
  }
  const { profile } = options;
  const target = resolve(dir ?? options.repo ?? process.cwd());
  const exists = existsSync(target);
  const root = exists ? resolveWorkspace(dir ?? options.repo).root : target;
  const model = exists ? modelDirectory(root, options.modelDir, true) : resolve(root, options.modelDir ?? 'architecture');
  if (!within(root, model)) throw new InputError('--model-dir must stay inside the project');
  const file = join(model, 'model.c4');
  const needsModel = !hasModel(model);
  if (needsModel && pathExists(file)) throw new InputError('Model path is already occupied: ' + file);
  const agentFolders = agents.map(agent => agent === 'codex' ? skillPaths[0] : skillPaths[1]);
  const skillsToInstall = agents.length ? planSkillInstall(root, skillProfiles[profile], agentFolders) : [];

  if (!options.dryRun) {
    if (needsModel) {
      mkdirSync(model, { recursive: true });
      writeFileSync(file, starter, { flag: 'wx' });
    }
    if (skillsToInstall.length) {
      runPackage('skills', ['add', packageRoot, '--skill', ...skillsToInstall, ...agents.flatMap(agent => ['-a', agent]), '-y'], root);
      for (const folder of agentFolders) {
        if (!skillsToInstall.every(name => existsSync(join(root, folder, name, 'SKILL.md')))) {
          throw new InputError('Skill installation did not produce the selected C4Spec skills in ' + folder);
        }
      }
    }
  }
  return {
    root, modelDir: relativeModel(root, model), dryRun: !!options.dryRun,
    modelAction: needsModel ? 'create' : 'preserve', agents, profile, skillsToInstall,
  };
}

export function doctor(options: ModelOptions) {
  const { root } = resolveWorkspace(options.repo);
  const checks: { name: string; ok: boolean; detail: string }[] = [];
  function check(name: string, run: () => string) {
    try {
      checks.push({ name, ok: true, detail: run() });
    } catch (error) {
      checks.push({ name, ok: false, detail: errorMessage(error) });
    }
  }
  check('node', () => {
    const [major, minor, patch] = process.versions.node.split('.').map(Number);
    if (major < 22 || (major === 22 && (minor < 23 || (minor === 23 && patch < 3)))) {
      throw new InputError('Install Node.js ' + pkg.engines.node);
    }
    return process.versions.node;
  });
  check('git', () => execute('git', ['--version'], root).stdout.trim());
  check('likec4', () => assertCompiler(root));
  check('model', () => {
    const model = modelDirectory(root, options.modelDir);
    if (!hasModel(model)) throw new InputError('No LikeC4 sources in ' + model);
    return relativeModel(root, model);
  });
  return { root, valid: checks.every(item => item.ok), checks, versions: version(), skills: installedSkills(root) };
}

export async function validate(options: ValidateOptions) {
  const { root } = resolveWorkspace(options.repo);
  const dir = modelDirectory(root, options.modelDir);
  assertCompiler(root);
  const compiler = compilerValidation(dir);
  const result = { valid: compiler.valid, modelDir: relativeModel(root, dir), likec4: compilerVersion, compiler };
  if (!compiler.valid || options.compileOnly) return result;
  const { validateRecords } = await import('./validation.js');
  const read = (path?: string) => path === undefined ? undefined : readJson(resolve(root, path));
  const records = scratch(temp => validateRecords(exportModel(dir, join(temp, 'model.json'), options.project), {
    root, change: read(options.change), register: read(options.constraintsFile), phase: options.phase, viewWarning: 12,
  }));
  return { ...result, valid: records.valid, records };
}
