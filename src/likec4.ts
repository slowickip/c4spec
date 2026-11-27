import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { checkedJson, compilerVersion, InputError, isObject, readJson, runPackage } from './process.js';
import type { ExecutionOptions, JsonObject } from './process.js';
import { selectProject } from './model.js';
import { hasModel } from './workspace.js';

interface Diagnostic {
  message: string;
  file?: string;
}

interface CompilerReport extends JsonObject {
  valid: boolean;
  errors?: Diagnostic[];
  warnings?: Diagnostic[];
}

export interface NativeDiff extends JsonObject {
  id: string;
  projectId?: string;
}

function isDiagnostic(value: unknown): value is Diagnostic {
  return isObject(value) && typeof value.message === 'string' &&
    (value.file === undefined || typeof value.file === 'string');
}

function isCompilerReport(value: unknown): value is CompilerReport {
  return isObject(value) && typeof value.valid === 'boolean' &&
    [value.errors, value.warnings].every(items => items === undefined ||
      (Array.isArray(items) && items.every(isDiagnostic)));
}

function isNativeDiff(value: unknown): value is NativeDiff {
  return isObject(value) && typeof value.id === 'string' &&
    (value.projectId === undefined || typeof value.projectId === 'string');
}

export function likec4(dir: string, args: string[], options?: ExecutionOptions) {
  return runPackage('likec4', args, dir, options);
}

export function assertCompiler(dir: string) {
  const version = likec4(dir, ['--version']).stdout.trim();
  if (version !== compilerVersion) {
    throw new InputError('Expected LikeC4 ' + compilerVersion + ', got ' + version);
  }
  return version;
}

export function compilerValidation(dir: string): CompilerReport {
  if (!hasModel(dir)) throw new InputError('No LikeC4 sources in ' + dir);
  const result = likec4(dir, ['validate', '--json', '--no-layout', '.'], { accept: [0, 1] });
  const report = checkedJson(result.stdout, 'LikeC4 validate');
  if (!isCompilerReport(report)) throw new InputError('Unexpected LikeC4 validation result');
  return { ...report, valid: report.valid && result.status === 0 };
}

export function validModel(dir: string) {
  const report = compilerValidation(dir);
  if (!report.valid) {
    const messages = (report.errors ?? []).slice(0, 5).map(item => item.message).join('; ');
    throw new InputError('LikeC4 validation failed' + (messages ? ': ' + messages : ''));
  }
}

export function exportModel(dir: string, output: string, project?: string) {
  likec4(dir, ['export', 'json', '--skip-layout', '-o', output, '.']);
  return selectProject(readJson(output), project);
}

export function listDiffs(dir: string): NativeDiff[] {
  const data = checkedJson(likec4(dir, ['diff', 'list', '--json', '.']).stdout, 'LikeC4 diff list');
  if (!Array.isArray(data) || !data.every(isNativeDiff)) {
    throw new InputError('Unexpected LikeC4 native diff list');
  }
  return data;
}

export function buildViewer(dir: string, destination: string) {
  likec4(dir, ['build', '--output', destination, '--output-single-file', '.']);
  if (!existsSync(join(destination, 'index.html'))) {
    throw new InputError('LikeC4 did not produce a review viewer');
  }
}
