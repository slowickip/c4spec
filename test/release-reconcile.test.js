import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { extractChangelogNotes, reconcileRelease } from '../scripts/reconcile-release.mjs';

function runReal(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, encoding: 'utf8' });
  assert.ifError(result.error);
  return {
    status: result.status ?? 1,
    stdout: result.stdout ?? '',
    stderr: result.stderr ?? '',
  };
}

function git(cwd, ...args) {
  const result = runReal('git', args, cwd);
  assert.equal(result.status, 0, result.stderr + result.stdout);
  return result.stdout.trim();
}

function setupRepo(t, { version = '0.1.0-alpha.4', changelog } = {}) {
  const temp = mkdtempSync(join(tmpdir(), 'c4spec-reconcile-test-'));
  t.after(() => rmSync(temp, { recursive: true, force: true }));

  const origin = join(temp, 'origin.git');
  const work = join(temp, 'work');
  mkdirSync(origin);
  mkdirSync(work);
  git(origin, 'init', '--bare', '-q');
  git(work, 'init', '-q', '-b', 'main');
  git(work, 'config', 'user.email', 'test@example.invalid');
  git(work, 'config', 'user.name', 'C4Spec test');
  git(work, 'remote', 'add', 'origin', origin);

  writeFileSync(join(work, 'package.json'), JSON.stringify({
    name: '@slowickip/c4spec',
    version,
  }, null, 2));
  writeFileSync(join(work, 'CHANGELOG.md'), changelog ?? [
    '# Changelog',
    '',
    `## ${version}`,
    '',
    '### Patch Changes',
    '',
    '- Release test entry',
    '',
    '## 0.1.0-alpha.3',
    '',
    '- Previous release',
    '',
  ].join('\n'));
  git(work, 'add', '.');
  git(work, 'commit', '-qm', `Release ${version}`);
  git(work, 'push', '-u', 'origin', 'main', '-q');

  return { origin, work, commitA: git(work, 'rev-parse', 'HEAD') };
}

function makeRunner({ npmResult, ghReleaseExists = false, onReleaseCreate }) {
  const calls = [];
  const run = (command, args, cwd) => {
    calls.push({ command, args });
    if (command === 'git') return runReal(command, args, cwd);
    if (command === 'npm') {
      assert.equal(args[0], 'view');
      return npmResult;
    }
    if (command === 'gh') {
      if (args[0] === 'release' && args[1] === 'view') {
        return ghReleaseExists
          ? { status: 0, stdout: '{}', stderr: '' }
          : { status: 1, stdout: '', stderr: 'release not found' };
      }
      if (args[0] === 'release' && args[1] === 'create') {
        const notesIdx = args.indexOf('--notes-file');
        const notes = notesIdx !== -1 ? readFileSync(args[notesIdx + 1], 'utf8') : '';
        onReleaseCreate?.(args, notes);
        return { status: 0, stdout: '', stderr: '' };
      }
    }
    throw new Error(`Unexpected command: ${command} ${args.join(' ')}`);
  };
  return { run, calls };
}

test('skips reconciliation when package version is not published on npm', t => {
  const { work, origin } = setupRepo(t);
  const { run, calls } = makeRunner({
    npmResult: { status: 1, stdout: JSON.stringify({ error: { code: 'E404' } }), stderr: '' },
  });

  const result = reconcileRelease({ cwd: work, run, log: () => {} });
  assert.equal(result.status, 'not-published');
  assert.equal(result.tag, 'v0.1.0-alpha.4');
  assert.equal(git(origin, 'tag', '--list'), '');
  assert.equal(calls.some(c => c.command === 'gh'), false);
});

test('reconciles missing v<version> tag on published gitHead rather than subsequent HEAD', t => {
  const { work, origin, commitA } = setupRepo(t, { version: '0.1.0-alpha.4' });

  // Unrelated commit B lands on main without bumping package.json.
  writeFileSync(join(work, 'README.md'), 'Subsequent doc update\n');
  writeFileSync(join(work, 'CHANGELOG.md'), '# Changelog\n\n## 0.1.0-alpha.4\n\n- Mutated later\n');
  git(work, 'add', '.');
  git(work, 'commit', '-qm', 'Unrelated follow-up commit');
  git(work, 'push', 'origin', 'main', '-q');
  const commitB = git(work, 'rev-parse', 'HEAD');
  assert.notEqual(commitA, commitB);

  let created;
  const { run } = makeRunner({
    npmResult: { status: 0, stdout: JSON.stringify({ version: '0.1.0-alpha.4', gitHead: commitA }), stderr: '' },
    onReleaseCreate: (args, notes) => { created = { args, notes }; },
  });

  const result = reconcileRelease({ cwd: work, run, log: () => {} });
  assert.equal(result.status, 'reconciled');
  assert.equal(result.tag, 'v0.1.0-alpha.4');
  assert.equal(result.targetSha, commitA);
  assert.equal(result.tagAction, 'created');
  assert.equal(result.releaseAction, 'created');

  // Remote tag must point to commitA, not commitB, and use Changesets v<version> format.
  assert.equal(git(origin, 'tag', '--list'), 'v0.1.0-alpha.4');
  assert.equal(git(origin, 'rev-parse', 'v0.1.0-alpha.4^{commit}'), commitA);
  assert.ok(created);
  assert.equal(created.args.includes('v0.1.0-alpha.4'), true);
  assert.equal(created.args.includes('--prerelease'), true);
  assert.match(created.notes, /Release test entry/);
  assert.doesNotMatch(created.notes, /Mutated later/);
});

test('creates missing GitHub release when remote v<version> tag already matches gitHead', t => {
  const { work, origin, commitA } = setupRepo(t, { version: '0.1.0' });
  git(work, 'tag', '-a', 'v0.1.0', commitA, '-m', 'v0.1.0');
  git(work, 'push', 'origin', 'refs/tags/v0.1.0', '-q');

  let created;
  const { run } = makeRunner({
    npmResult: { status: 0, stdout: JSON.stringify({ version: '0.1.0', gitHead: commitA }), stderr: '' },
    onReleaseCreate: (args, notes) => { created = { args, notes }; },
  });

  const result = reconcileRelease({ cwd: work, run, log: () => {} });
  assert.equal(result.status, 'reconciled');
  assert.equal(result.tagAction, 'existing');
  assert.equal(result.releaseAction, 'created');
  assert.equal(git(origin, 'rev-parse', 'v0.1.0^{commit}'), commitA);
  assert.equal(created.args.includes('--prerelease'), false);
  assert.match(created.notes, /Release test entry/);
});

test('returns up-to-date when both tag and GitHub release already exist', t => {
  const { work, commitA } = setupRepo(t, { version: '0.1.0-alpha.4' });
  git(work, 'tag', '-a', 'v0.1.0-alpha.4', commitA, '-m', 'v0.1.0-alpha.4');
  git(work, 'push', 'origin', 'refs/tags/v0.1.0-alpha.4', '-q');

  const { run } = makeRunner({
    npmResult: { status: 0, stdout: JSON.stringify({ version: '0.1.0-alpha.4', gitHead: commitA }), stderr: '' },
    ghReleaseExists: true,
  });

  const result = reconcileRelease({ cwd: work, run, log: () => {} });
  assert.equal(result.status, 'up-to-date');
  assert.equal(result.tagAction, 'existing');
  assert.equal(result.releaseAction, 'existing');
});

test('rejects missing tag recovery when npm metadata lacks gitHead', t => {
  const { work, origin } = setupRepo(t, { version: '0.1.0-alpha.4' });
  const { run } = makeRunner({
    npmResult: { status: 0, stdout: JSON.stringify({ version: '0.1.0-alpha.4' }), stderr: '' },
  });

  assert.throws(
    () => reconcileRelease({ cwd: work, run, log: () => {} }),
    /no valid gitHead/,
  );
  assert.equal(git(origin, 'tag', '--list'), '');
});

test('rejects existing remote tag that diverges from npm gitHead', t => {
  const { work, commitA } = setupRepo(t, { version: '0.1.0-alpha.4' });
  writeFileSync(join(work, 'other.txt'), 'other\n');
  git(work, 'add', '.');
  git(work, 'commit', '-qm', 'Other commit');
  const commitB = git(work, 'rev-parse', 'HEAD');
  git(work, 'tag', '-a', 'v0.1.0-alpha.4', commitB, '-m', 'wrong tag');
  git(work, 'push', 'origin', 'refs/tags/v0.1.0-alpha.4', '-q');

  const { run } = makeRunner({
    npmResult: { status: 0, stdout: JSON.stringify({ version: '0.1.0-alpha.4', gitHead: commitA }), stderr: '' },
  });

  assert.throws(
    () => reconcileRelease({ cwd: work, run, log: () => {} }),
    /does not match published npm gitHead/,
  );
});

test('rejects npm gitHead whose package.json version does not match', t => {
  const { work, commitA } = setupRepo(t, { version: '0.1.0-alpha.3' });
  writeFileSync(join(work, 'package.json'), JSON.stringify({ name: '@slowickip/c4spec', version: '0.1.0-alpha.4' }));
  git(work, 'add', '.');
  git(work, 'commit', '-qm', 'Bump to 0.1.0-alpha.4');

  const { run } = makeRunner({
    npmResult: { status: 0, stdout: JSON.stringify({ version: '0.1.0-alpha.4', gitHead: commitA }), stderr: '' },
  });

  assert.throws(
    () => reconcileRelease({ cwd: work, run, log: () => {} }),
    /expected @slowickip\/c4spec@0\.1\.0-alpha\.4/,
  );
});

test('extractChangelogNotes isolates only the requested version section', () => {
  const md = '# Changelog\n\n## 0.1.0-alpha.4\n\n- New\n\n## 0.1.0-alpha.3\n\n- Old\n';
  assert.equal(extractChangelogNotes(md, '0.1.0-alpha.4'), '- New');
  assert.equal(extractChangelogNotes(md, '0.1.0-alpha.3'), '- Old');
  assert.equal(extractChangelogNotes(md, '0.9.9'), '');
});
