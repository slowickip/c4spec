import { spawnSync } from 'node:child_process';
import type { SpawnSyncOptions, SpawnSyncReturns } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

interface PackageMetadata {
  version: string;
  engines: { node: string };
  dependencies: { likec4: string };
}

export interface ExecutionOptions {
  label?: string;
  accept?: number[];
}

const require = createRequire(import.meta.url);
export const packageRoot = fileURLToPath(new URL('../', import.meta.url));
export const pkg: PackageMetadata = require('../package.json');
export const compilerVersion = pkg.dependencies.likec4;

export class InputError extends Error {}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export type JsonObject = Record<string, unknown>;

export function isObject(value: unknown): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function checkedJson(value: string, label: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    throw new InputError(label + ' did not contain valid JSON');
  }
}

export function readJson(path: string): unknown {
  let text;
  try {
    text = readFileSync(path, 'utf8');
  } catch (error) {
    throw new InputError('Cannot read ' + path + ': ' + errorMessage(error));
  }
  return checkedJson(text, path);
}

export function execute(command: string, args: string[], cwd: string,
  options: ExecutionOptions & { binary: true }): SpawnSyncReturns<Buffer>;
export function execute(command: string, args: string[], cwd: string,
  options?: ExecutionOptions & { binary?: false }): SpawnSyncReturns<string>;
export function execute(command: string, args: string[], cwd: string,
  { label = command, accept = [0], binary = false }: ExecutionOptions & { binary?: boolean } = {}):
  SpawnSyncReturns<string | Buffer> {
  const spawnOptions: SpawnSyncOptions = {
    cwd, stdio: 'pipe', maxBuffer: 64 * 1024 * 1024, timeout: 300_000, windowsHide: true,
  };
  const result = binary
    ? spawnSync(command, args, { ...spawnOptions, encoding: 'buffer' })
    : spawnSync(command, args, { ...spawnOptions, encoding: 'utf8' });
  if (result.error) throw new InputError(label + ': ' + result.error.message);
  if (result.status === null || !accept.includes(result.status)) {
    const explanation = (String(result.stderr ?? '') + '\n' + String(result.stdout ?? '')).trim();
    throw new InputError(label + ' failed (' + (result.status ?? result.signal) + ')' +
      (explanation ? ': ' + explanation.slice(-1600) : ''));
  }
  return result;
}

export function runPackage(name: string, args: string[], cwd: string, options: ExecutionOptions = {}) {
  const manifest = require.resolve(name + '/package.json');
  const { bin }: { bin: string | Record<string, string> } = require(manifest);
  const entry = typeof bin === 'string' ? bin : bin[name];
  return execute(process.execPath, [resolve(dirname(manifest), entry), ...args], cwd, {
    ...options, label: name + ' ' + args[0],
  });
}
