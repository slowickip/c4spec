#!/usr/bin/env node
// Reconcile a partially completed npm release by verifying the published npm
// commit (`gitHead`), ensuring the single-package `v<version>` Git tag exists
// on `origin`, and ensuring the corresponding GitHub Release exists.

import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

function defaultRun(command, args, cwd) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: process.platform === 'win32' && command === 'npm',
  });
  if (result.error) throw result.error;
  return {
    status: result.status ?? 1,
    stdout: result.stdout ?? '',
    stderr: result.stderr ?? '',
  };
}

function runChecked(run, command, args, cwd) {
  const result = run(command, args, cwd);
  if (result.status !== 0) {
    const detail = `${result.stderr}\n${result.stdout}`.trim();
    throw new Error(`${command} ${args.join(' ')} exited with ${result.status}${detail ? `: ${detail}` : ''}`);
  }
  return result.stdout;
}

export function extractChangelogNotes(changelog, version) {
  if (!changelog) return '';
  const lines = changelog.split(/\r?\n/);
  const start = lines.indexOf(`## ${version}`);
  if (start === -1) return '';
  let end = lines.findIndex((line, index) => index > start && line.startsWith('## '));
  if (end === -1) end = lines.length;
  return lines.slice(start + 1, end).join('\n').trim();
}

function parsePublishedMetadata(result, spec) {
  if (result.status !== 0) {
    const combined = `${result.stdout}\n${result.stderr}`;
    try {
      const parsed = JSON.parse(result.stdout);
      if (parsed?.error?.code === 'E404') return null;
    } catch {
      // Fall through to text check below.
    }
    if (/\bE404\b|404 Not Found/i.test(combined)) return null;
    throw new Error(`npm view ${spec} failed (${result.status}): ${combined.trim()}`);
  }
  const stdout = result.stdout.trim();
  if (!stdout) return null;
  const parsed = JSON.parse(stdout);
  const entry = Array.isArray(parsed) ? parsed[0] : parsed;
  if (!entry || typeof entry !== 'object') return null;
  return entry;
}

function parseRemoteTagSha(lsRemoteOutput, tag) {
  const lines = lsRemoteOutput.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  const peeled = lines.find(line => line.endsWith(`\trefs/tags/${tag}^{}`));
  if (peeled) return peeled.split(/\s+/)[0];
  const direct = lines.find(line => line.endsWith(`\trefs/tags/${tag}`));
  return direct ? direct.split(/\s+/)[0] : null;
}

function verifyCommitPackage(run, cwd, sha, expectedName, expectedVersion) {
  const exists = run('git', ['cat-file', '-e', `${sha}^{commit}`], cwd);
  if (exists.status !== 0) {
    throw new Error(`Published commit ${sha} does not exist in local Git history`);
  }
  const raw = runChecked(run, 'git', ['show', `${sha}:package.json`], cwd);
  const pkgAtSha = JSON.parse(raw);
  if (pkgAtSha.name !== expectedName || pkgAtSha.version !== expectedVersion) {
    throw new Error(
      `Commit ${sha} has ${pkgAtSha.name}@${pkgAtSha.version}, expected ${expectedName}@${expectedVersion}`,
    );
  }
}

export function reconcileRelease({
  cwd = process.cwd(),
  remote = 'origin',
  run = defaultRun,
  log = console.log,
} = {}) {
  const pkg = JSON.parse(readFileSync(join(cwd, 'package.json'), 'utf8'));
  const { name, version } = pkg;
  if (!name || !version) {
    throw new Error('package.json must define name and version');
  }
  const tag = `v${version}`;
  const spec = `${name}@${version}`;

  const npmMeta = parsePublishedMetadata(run('npm', ['view', spec, '--json'], cwd), spec);
  if (!npmMeta) {
    log(`${spec} is not published on npm; skipping tag and release reconciliation.`);
    return { status: 'not-published', tag, spec };
  }

  const gitHead = typeof npmMeta.gitHead === 'string' && /^[0-9a-f]{40}$/i.test(npmMeta.gitHead)
    ? npmMeta.gitHead
    : null;

  const remoteTagSha = parseRemoteTagSha(
    runChecked(run, 'git', ['ls-remote', '--tags', remote, `refs/tags/${tag}`, `refs/tags/${tag}^{}`], cwd),
    tag,
  );

  let targetSha;
  let tagAction = 'existing';

  if (remoteTagSha) {
    if (gitHead && remoteTagSha !== gitHead) {
      throw new Error(
        `Existing remote tag ${tag} points to ${remoteTagSha}, which does not match published npm gitHead ${gitHead}`,
      );
    }
    targetSha = gitHead ?? remoteTagSha;
    verifyCommitPackage(run, cwd, targetSha, name, version);
  } else {
    if (!gitHead) {
      throw new Error(
        `Cannot reconcile missing tag ${tag}: published npm metadata for ${spec} has no valid gitHead`,
      );
    }
    targetSha = gitHead;
    verifyCommitPackage(run, cwd, targetSha, name, version);

    const localTag = run('git', ['rev-parse', '-q', '--verify', `refs/tags/${tag}^{commit}`], cwd);
    if (localTag.status === 0) {
      const localSha = localTag.stdout.trim();
      if (localSha !== targetSha) {
        throw new Error(
          `Local tag ${tag} points to ${localSha}, which does not match published npm gitHead ${targetSha}`,
        );
      }
    } else {
      runChecked(run, 'git', ['tag', '-a', tag, targetSha, '-m', tag], cwd);
    }
    runChecked(run, 'git', ['push', remote, `refs/tags/${tag}`], cwd);
    tagAction = 'created';
  }

  const releaseView = run('gh', ['release', 'view', tag], cwd);
  if (releaseView.status === 0) {
    return { status: 'up-to-date', tag, spec, targetSha, tagAction, releaseAction: 'existing' };
  }
  const releaseErr = `${releaseView.stderr}\n${releaseView.stdout}`.trim();
  if (!/release not found/i.test(releaseErr)) {
    throw new Error(`gh release view ${tag} failed (${releaseView.status})${releaseErr ? `: ${releaseErr}` : ''}`);
  }

  let changelog = '';
  const changelogAtCommit = run('git', ['show', `${targetSha}:CHANGELOG.md`], cwd);
  if (changelogAtCommit.status === 0) {
    changelog = changelogAtCommit.stdout;
  }
  const notes = extractChangelogNotes(changelog, version);

  const releaseArgs = ['release', 'create', tag, '--title', tag];
  if (version.includes('-')) releaseArgs.push('--prerelease');

  let tempDir;
  try {
    if (notes) {
      tempDir = mkdtempSync(join(tmpdir(), 'c4spec-release-notes-'));
      const notesFile = join(tempDir, 'notes.md');
      writeFileSync(notesFile, `${notes}\n`);
      releaseArgs.push('--notes-file', notesFile);
    } else {
      releaseArgs.push('--generate-notes');
    }
    runChecked(run, 'gh', releaseArgs, cwd);
  } finally {
    if (tempDir) rmSync(tempDir, { recursive: true, force: true });
  }

  return { status: 'reconciled', tag, spec, targetSha, tagAction, releaseAction: 'created' };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const result = reconcileRelease();
    console.log(JSON.stringify(result));
  } catch (error) {
    console.error(`reconcile-release: ${error instanceof Error ? error.message : String(error)}`);
    process.exit(1);
  }
}
