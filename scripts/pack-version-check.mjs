#!/usr/bin/env node
// Verify that the packed npm tarball installs cleanly without devDependencies
// and that the installed CLI binary reports the exact package.json version.

import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

function run(command, args, cwd) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: process.platform === 'win32',
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    const output = `${result.stderr ?? ''}\n${result.stdout ?? ''}`.trim();
    throw new Error(`${command} ${args.join(' ')} exited with ${result.status}${output ? `: ${output}` : ''}`);
  }
  return result.stdout;
}

function packTarball() {
  const out = run('npm', ['pack', '--json', '--silent'], process.cwd());
  const parsed = JSON.parse(out);
  const entry = Array.isArray(parsed) ? parsed.at(-1) : parsed;
  const filename = typeof entry === 'string' ? entry : entry?.filename;
  if (!filename) throw new Error('npm pack --json did not return a tarball filename');
  return resolve(process.cwd(), filename);
}

const pkg = JSON.parse(readFileSync(join(process.cwd(), 'package.json'), 'utf8'));
const expected = pkg.version;

let workDir;
let tarballPath;

try {
  tarballPath = packTarball();
  workDir = mkdtempSync(join(tmpdir(), 'c4spec-pack-check-'));

  writeFileSync(
    join(workDir, 'package.json'),
    JSON.stringify({ name: 'c4spec-pack-check', private: true }, null, 2),
  );

  run('npm', ['install', '--omit=dev', '--no-audit', '--no-fund', '--silent', tarballPath], workDir);

  const binPath = join(workDir, 'node_modules', '@slowickip', 'c4spec', 'bin', 'c4spec.js');
  const flagVersion = run(process.execPath, [binPath, '--version'], workDir).trim();
  if (flagVersion !== expected) {
    throw new Error(`Packed CLI --version mismatch: expected ${expected}, got ${flagVersion}`);
  }

  const cmdVersion = JSON.parse(run(process.execPath, [binPath, 'version', '--json'], workDir));
  if (cmdVersion.c4spec !== expected) {
    throw new Error(`Packed CLI version --json mismatch: expected ${expected}, got ${cmdVersion.c4spec}`);
  }

  console.log(`pack-version-check: OK (${pkg.name}@${expected})`);
} finally {
  if (workDir) rmSync(workDir, { recursive: true, force: true });
  if (tarballPath) rmSync(tarballPath, { force: true });
}
