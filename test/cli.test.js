import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const bin = fileURLToPath(new URL('../bin/c4spec.js', import.meta.url));
const example = fileURLToPath(new URL('../examples/mini-project', import.meta.url));
const nativeProposal = `
diff addSupport 'Add a support system' {
  add {
    support = system 'Support' {
      description 'Receives requests for help.'
    }
    app -> support 'Requests help'
  }
}
`;

function run(command, args, cwd, expected = 0) {
  const result = spawnSync(command, args, { cwd, encoding: 'utf8', timeout: 180_000 });
  assert.ifError(result.error);
  assert.equal(result.status, expected, result.stderr + result.stdout);
  return result.stdout;
}

function cli(cwd, args, expected = 0) {
  return JSON.parse(run(process.execPath, [bin, '--json', ...args], cwd, expected));
}

function git(cwd, ...args) {
  return run('git', args, cwd).trim();
}

function setup(t) {
  const temp = mkdtempSync(join(tmpdir(), 'c4spec-cli-test-'));
  t.after(() => rmSync(temp, { recursive: true, force: true }));
  return temp;
}

function repo(t, modelDir = 'architecture') {
  const temp = setup(t);
  const root = join(temp, 'working tree');
  mkdirSync(root);
  git(root, 'init', '-q');
  git(root, 'config', 'user.email', 'test@example.invalid');
  git(root, 'config', 'user.name', 'C4Spec test');
  cli(root, ['init', '--model-dir', modelDir]);
  git(root, 'add', '.');
  git(root, 'commit', '-qm', 'Initial model');
  return { temp, root, base: git(root, 'rev-parse', 'HEAD'), model: join(root, modelDir, 'model.c4') };
}

test('version, argument diagnostics, and init preserve existing model input', t => {
  const temp = setup(t);
  const root = join(temp, 'new project');
  assert.equal(cli(temp, ['version']).likec4, '1.61.0');
  assert.match(cli(temp, ['diff'], 2).error, /--base/);
  assert.equal(cli(temp, ['init', root, '--dry-run']).modelAction, 'create');
  assert.equal(existsSync(root), false);
  assert.equal(cli(temp, ['doctor'], 1).checks.find(item => item.name === 'model').ok, false);
  assert.match(cli(temp, ['init', root, '--model-dir', '../outside'], 2).error, /inside/);
  assert.equal(cli(temp, ['init', root]).modelAction, 'create');
  const model = join(root, 'architecture', 'model.c4');
  const source = readFileSync(model, 'utf8');
  assert.equal(cli(temp, ['init', '--repo', root]).modelAction, 'preserve');
  assert.equal(readFileSync(model, 'utf8'), source);
  assert.equal(cli(root, ['doctor']).valid, true);
  assert.equal(cli(root, ['validate']).valid, true);
  writeFileSync(model, source + '\ninvalid!\n');
  const invalid = cli(root, ['validate', '--compile-only'], 1);
  assert.equal(invalid.compiler.valid, false);
  assert.ok(invalid.compiler.errors.length > 0);
});

test('init defaults to diagram skills and adds the extended skills on request', t => {
  const root = setup(t);
  const init = ['init', '--agent', 'codex', 'claude-code'];
  const basic = ['c4spec', 'c4spec-maintain'];
  const plan = cli(root, [...init, '--dry-run']);
  assert.equal(plan.profile, 'basic');
  assert.deepEqual(plan.skillsToInstall, basic);
  assert.equal(existsSync(join(root, '.agents')), false);
  assert.match(cli(root, [...init, '--profile', 'unknown'], 2).error, /basic.*extended/);
  assert.equal(existsSync(join(root, 'architecture')), false);

  const result = cli(root, init);
  assert.equal(result.profile, 'basic');
  assert.deepEqual(result.agents, ['codex', 'claude-code']);
  assert.deepEqual(result.skillsToInstall, basic);
  for (const folder of ['.agents', '.claude']) {
    assert.ok(existsSync(join(root, folder, 'skills', 'c4spec', 'SKILL.md')));
    assert.ok(existsSync(join(root, folder, 'skills', 'c4spec-maintain', 'SKILL.md')));
    assert.equal(existsSync(join(root, folder, 'skills', 'c4spec-propose')), false);
  }
  assert.deepEqual(cli(root, ['update', '--dry-run']).skills.map(skill => skill.name), basic);
  const shared = join(root, '.agents', 'skills', 'c4spec', 'SKILL.md');
  const edited = readFileSync(shared, 'utf8') + '\nProject-specific modeling guidance.\n';
  writeFileSync(shared, edited);
  const lock = join(root, 'skills-lock.json');
  const basicLock = JSON.parse(readFileSync(lock, 'utf8')).skills;
  const extended = [...init, '--profile', 'extended'];
  const upgrade = cli(root, [...extended, '--dry-run']);
  assert.equal(upgrade.profile, 'extended');
  assert.equal(upgrade.modelAction, 'preserve');
  assert.equal(upgrade.skillsToInstall.length, 7);
  assert.ok(!upgrade.skillsToInstall.some(name => basic.includes(name)));
  assert.deepEqual(cli(root, extended).skillsToInstall, upgrade.skillsToInstall);
  assert.equal(readFileSync(shared, 'utf8'), edited);
  const extendedLock = JSON.parse(readFileSync(lock, 'utf8')).skills;
  for (const name of basic) assert.deepEqual(extendedLock[name], basicLock[name]);
  for (const folder of ['.agents', '.claude']) {
    assert.ok(existsSync(join(root, folder, 'skills', 'c4spec-propose', 'references', 'model-first.md')));
    assert.ok(existsSync(join(root, folder, 'skills', 'c4spec-verify', 'SKILL.md')));
  }
  const lockAfterUpgrade = readFileSync(lock, 'utf8');
  assert.deepEqual(cli(root, extended).skillsToInstall, []);
  assert.deepEqual(cli(root, [...init, '--profile', 'basic']).skillsToInstall, []);
  assert.equal(readFileSync(lock, 'utf8'), lockAfterUpgrade);
  assert.equal(cli(root, ['doctor']).skills.entries.length, 9);
  assert.equal(cli(root, ['validate', '--compile-only']).valid, true);
});

test('init supports a fresh extended install and preserves occupied skill paths', t => {
  const root = setup(t);
  const args = ['init', '--agent', 'claude-code', '--profile', 'extended'];
  const occupied = join(root, '.claude', 'skills', 'c4spec-propose');
  mkdirSync(occupied, { recursive: true });
  writeFileSync(join(occupied, 'notes.md'), 'Existing project file\n');
  assert.match(cli(root, args, 2).error, /c4spec-propose is incomplete/);
  assert.equal(existsSync(join(root, 'architecture')), false);
  assert.equal(readFileSync(join(occupied, 'notes.md'), 'utf8'), 'Existing project file\n');

  const fresh = join(root, 'new-project');
  assert.equal(cli(root, ['init', fresh, ...args.slice(1)]).skillsToInstall.length, 9);
  const preview = cli(fresh, ['update', '--dry-run']);
  assert.equal(preview.skills.length, 9);
  assert.ok(preview.skills.every(skill => skill.state === 'tracked' && skill.changes.length === 0));
});

test('upgrade preview reports file changes and flags edits without touching project files', t => {
  const { root } = repo(t);
  const folder = join(root, '.agents', 'skills', 'c4spec');
  const skill = join(folder, 'SKILL.md');
  const lock = join(root, 'skills-lock.json');
  mkdirSync(join(folder, 'docs'), { recursive: true });
  writeFileSync(skill, 'a\r\n');
  writeFileSync(join(folder, 'docs', 'b.md'), 'b\n');
  const revision = 'c'.repeat(40);
  const manifest = JSON.stringify({ version: 2, skills: { c4spec: {
    source: 'slowickip/c4spec', ref: 'main', commit: revision,
    computedHash: 'b22c4d22aa319d2924312fa18fcbfedc88fa89c74dbd8f298c683e1caf7b7f24',
  } } });
  writeFileSync(lock, manifest);

  const doctor = cli(root, ['doctor']);
  assert.equal(doctor.versions.likec4, '1.61.0');
  assert.equal(doctor.versions.c4spec, cli(root, ['version']).c4spec);
  assert.deepEqual(doctor.skills.entries, [
    { name: 'c4spec', path: '.agents/skills/c4spec', revision, state: 'tracked' },
  ]);
  assert.match(cli(root, ['update'], 2).error, /--dry-run/);
  const preview = cli(root, ['update', '--dry-run']);
  assert.equal(preview.skills[0].state, 'tracked');
  assert.ok(preview.skills[0].changes.some(change => change.action === 'add'));
  assert.deepEqual(preview.skills[0].changes.find(change => change.action === 'update'),
    { action: 'update', path: '.agents/skills/c4spec/SKILL.md' });
  assert.deepEqual(preview.skills[0].changes.find(change => change.action === 'remove'),
    { action: 'remove', path: '.agents/skills/c4spec/docs/b.md' });
  assert.equal(readFileSync(skill, 'utf8'), 'a\r\n');

  writeFileSync(skill, 'a\nlocal edit\n');
  const dirty = cli(root, ['update', '--dry-run'], 1);
  assert.equal(dirty.skills[0].state, 'modified');
  assert.equal(readFileSync(skill, 'utf8'), 'a\nlocal edit\n');
  assert.equal(readFileSync(join(folder, 'docs', 'b.md'), 'utf8'), 'b\n');
  assert.equal(readFileSync(lock, 'utf8'), manifest);
  assert.equal(existsSync(join(folder, 'references')), false);
});

test('validate reads existing records and distinguishes planned work from completion', () => {
  const register = ['--constraints-file', 'c4spec/constraints.json'];
  const completed = cli(example, ['--repo', example, 'validate', '--change', 'c4spec/changes/add-cache.json',
    ...register, '--phase', 'completion']);
  assert.equal(completed.records.valid, true);
  assert.equal(completed.records.testsExecuted, false);
  const planned = ['--repo', example, 'validate', '--change', 'c4spec/changes/add-notification-worker.json'];
  assert.equal(cli(example, planned).valid, true);
  const rejected = cli(example, [...planned, '--phase', 'completion'], 1);
  assert.ok(rejected.records.findings.some(item => item.code === 'still_planned'));
});

test('diff uses committed root model sources and returns no architecture delta for behavior-only changes', t => {
  const { root, base, model } = repo(t, '.');
  writeFileSync(join(root, 'behavior.txt'), 'a code-only change\n');
  git(root, 'add', 'behavior.txt');
  git(root, 'commit', '-qm', 'Behavior-only change');
  const unchanged = cli(root, ['diff', '--base', base]);
  assert.equal(unchanged.sourceChanged, false);
  assert.equal(unchanged.semantic.changed, false);
  const initial = readFileSync(model, 'utf8');
  writeFileSync(model, initial.replace("'Application'", "'Customer Application'"));
  assert.equal(cli(root, ['diff', '--base', base]).semantic.changed, false);
  git(root, 'add', 'model.c4');
  git(root, 'commit', '-qm', 'Rename application');
  const changed = cli(root, ['diff', '--base', base]);
  assert.equal(changed.semantic.changed, true);
  assert.deepEqual(changed.semantic.elements.modified, ['app']);
  assert.match(changed.sourcePatch, /Customer Application/);
  assert.doesNotMatch(changed.sourcePatch, /behavior.txt/);
  assert.match(cli(root, ['diff', '--base', base, '--source']).sourcePatch, /Customer Application/);
  assert.match(run(process.execPath, [bin, 'diff', '--base', base], root), /Model source: changed/);
});

test('review builds both viewers for a direct C4 edit', t => {
  const { root, base, model, temp } = repo(t);
  writeFileSync(model, readFileSync(model, 'utf8').replace("'Application'", "'Customer Application'"));
  git(root, 'add', '.');
  git(root, 'commit', '-qm', 'Rename application');
  assert.match(cli(root, ['review', '--base', base, '--out', join(root, 'inside')], 2).error, /outside/);
  const bundle = join(temp, 'direct');
  const review = cli(root, ['review', '--base', base, '--out', bundle]);
  assert.equal(review.kind, 'c4spec-cli-direct-review');
  assert.ok(existsSync(review.viewer));
  assert.ok(existsSync(join(bundle, 'base-site', 'index.html')));
  const patch = join(bundle, 'source.patch');
  const originalPatch = readFileSync(patch, 'utf8');
  assert.match(originalPatch, /Customer Application/);
  assert.match(cli(root, ['review', '--base', base, '--out', bundle], 2).error, /already exists/);
  assert.equal(readFileSync(patch, 'utf8'), originalPatch);
  assert.equal(git(root, 'status', '--porcelain'), '');
});

test('diff finds the model directory in Git when a commit removes the last source', t => {
  const { root, base } = repo(t);
  git(root, 'rm', 'architecture/model.c4');
  git(root, 'commit', '-qm', 'Remove the model');
  const result = cli(root, ['diff', '--base', base]);
  assert.equal(result.modelDir, 'architecture');
  assert.equal(result.sourceChanged, true);
  assert.deepEqual(result.semantic.elements.removed, ['app', 'user']);
});

test('native review previews, applies in scratch, and verifies the exact committed result', t => {
  const { root, base, model, temp } = repo(t);
  const source = readFileSync(model, 'utf8') + nativeProposal;
  const bundle = join(temp, 'review');
  const reviewArgs = ['review', '--base', base, '--out', bundle, '--diff', 'addSupport'];
  writeFileSync(model, source);
  assert.match(cli(root, reviewArgs, 2).error, /uncommitted/);
  git(root, 'add', '.');
  git(root, 'commit', '-qm', 'Propose support');
  const review = cli(root, reviewArgs);
  assert.equal(review.kind, 'c4spec-cli-native-review');
  assert.ok(existsSync(review.viewer));
  assert.equal(readFileSync(model, 'utf8'), source);
  assert.equal(git(root, 'status', '--porcelain'), '');
  assert.equal(cli(root, ['review', '--check-proposal', review.review]).valid, true);
  const semantic = JSON.parse(readFileSync(join(bundle, 'semantic-diff.json'), 'utf8'));
  assert.deepEqual(semantic.elements.added, ['support']);
  cpSync(join(bundle, 'applied', 'model.c4'), model);
  git(root, 'add', '.');
  git(root, 'commit', '-qm', 'Apply support');
  assert.equal(cli(root, ['review', '--check-applied', review.review]).valid, true);
  writeFileSync(model, readFileSync(model, 'utf8').replace("'Support'", "'Changed Support'"));
  git(root, 'add', '.');
  git(root, 'commit', '-qm', 'Unreviewed model change');
  assert.match(cli(root, ['review', '--check-applied', review.review], 2).error, /differ from the reviewed result/);
  const packet = JSON.parse(readFileSync(review.review, 'utf8'));
  const digest = createHash('sha256').update(readFileSync(model)).digest('hex');
  packet.expectedAppliedSources = [{ path: 'model.c4', sha256: digest }];
  writeFileSync(review.review, JSON.stringify(packet));
  assert.match(cli(root, ['review', '--check-applied', review.review], 2).error, /differs from applying/);
});
