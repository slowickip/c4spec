import { Command, CommanderError, Option } from 'commander';
import { errorMessage, InputError, pkg } from './process.js';
import { skillProfiles } from './skills.js';

import type { InitOptions, ValidateOptions, validate } from './commands.js';
import type { DiffOptions, ReviewOptions, diffCommand } from './review.js';
import type { ModelOptions } from './workspace.js';

function output<T extends object>(result: T, json: boolean, human: (result: T) => void) {
  if (json) console.log(JSON.stringify(result, null, 2));
  else human(result);
  if ('valid' in result && result.valid === false) process.exitCode = 1;
}

function showValidation(report: Awaited<ReturnType<typeof validate>>) {
  console.log(report.valid ? 'C4Spec validation passed' : 'C4Spec validation failed');
  for (const level of ['errors', 'warnings'] as const) {
    for (const item of report.compiler[level] ?? []) {
      console.log(level.slice(0, -1) + ': ' + [item.file, item.message].filter(Boolean).join(' '));
    }
  }
  for (const item of 'records' in report ? report.records.findings : []) {
    console.log(item.severity + ': ' + item.location + ' — ' + item.message);
  }
}

function showDiff(report: ReturnType<typeof diffCommand>) {
  if (!('semantic' in report)) {
    process.stdout.write(report.sourcePatch);
    return;
  }
  for (const key of ['elements', 'relationships', 'views'] as const) {
    const { added, removed, modified } = report.semantic[key];
    console.log(key + ': +' + added.length + ' −' + removed.length + ' ~' + modified.length);
  }
  console.log('Model source: ' + (report.sourceChanged ? 'changed' : 'unchanged'));
  for (const item of report.pendingDiffs) console.log('Pending native diff: ' + item.id);
  for (const hint of report.semantic.reviewHints) console.log('Review: ' + hint);
}

export async function runCli(argv: string[] = process.argv) {
  const json = argv.slice(2, argv.indexOf('--') === -1 ? undefined : argv.indexOf('--')).includes('--json');
  const program = new Command()
    .name('c4spec')
    .description('Work with LikeC4 architecture models and Git reviews')
    .version(pkg.version)
    .option('--repo <path>', 'project or Git root')
    .option('--model-dir <path>', 'model directory inside the project')
    .option('--project <id>', 'LikeC4 project ID for multi-project exports')
    .option('--json', 'emit a machine-readable result')
    .showHelpAfterError()
    .exitOverride();

  if (json) program.configureOutput({ writeErr: () => {} });

  program.command('init [directory]')
    .description('Scaffold a model and optionally install C4Spec skills')
    .option('--agent <ids...>', 'install skills for codex and/or claude-code')
    .addOption(new Option('--profile <name>', 'diagram maintenance (basic) or model-first workflow (extended)')
      .choices(Object.keys(skillProfiles)).default('basic'))
    .option('--dry-run', 'show intended changes')
    .action(async (dir: string | undefined, _: unknown, command: Command) => {
      const { init } = await import('./commands.js');
      output(init(dir, command.optsWithGlobals<InitOptions>()), json, result => {
        const verb = result.modelAction === 'create' ? 'Create' : 'Keep';
        console.log((result.dryRun ? 'Would ' + verb.toLowerCase() : verb) +
          ' model in ' + result.modelDir + ' (' + result.root + ')');
        if (!result.agents.length) return;
        console.log('C4Spec profile ' + result.profile + ' for ' + result.agents.join(', '));
        if (result.skillsToInstall.length) {
          console.log((result.dryRun ? 'Would install ' : 'Installed ') + result.skillsToInstall.join(', '));
        } else console.log('All selected C4Spec skills are present');
      });
    });
  program.command('doctor')
    .description('Check tool versions, installed skills and model discovery')
    .action(async (_: unknown, command: Command) => {
      const { doctor } = await import('./commands.js');
      output(doctor(command.optsWithGlobals<ModelOptions>()), json, result => {
        console.log('C4Spec ' + result.versions.c4spec + ' / validated LikeC4 ' + result.versions.likec4);
        for (const check of result.checks) console.log((check.ok ? 'OK ' : 'FAIL ') + check.name + ' — ' + check.detail);
        const { entries, lockIssue } = result.skills;
        const revisions = new Set(entries.map(skill => skill.revision ?? 'no recorded commit'));
        console.log('C4Spec skills — ' + ([...revisions].join(', ') || 'no project skills found'));
        if (lockIssue) console.log('Review skills lock — ' + lockIssue);
        for (const skill of entries.filter(entry => entry.state !== 'tracked')) {
          console.log('Review ' + skill.path + ' — ' + (skill.detail ?? skill.state));
        }
      });
    });
  program.command('update')
    .description('Preview updating installed project skills to the running CLI bundle')
    .requiredOption('--dry-run', 'preview file changes and report installation drift')
    .action(async (_: unknown, command: Command) => {
      const { previewSkillUpdate } = await import('./skills.js');
      output(previewSkillUpdate(command.optsWithGlobals<ModelOptions>().repo), json, result => {
        console.log('Preview C4Spec ' + result.target.c4spec + ' skills / LikeC4 ' + result.target.likec4);
        if (result.lockIssue) console.log('Review skills lock — ' + result.lockIssue);
        if (!result.skills.length) console.log('No C4Spec project skills found');
        for (const skill of result.skills) {
          console.log(skill.path + ' — ' + (skill.detail ?? skill.state));
          for (const change of skill.changes) console.log('  ' + change.action + ' ' + change.path);
        }
      });
    });
  program.command('validate')
    .description('Compile the model and check architectural structure and optional records')
    .option('--change <file>', 'existing change record relative to the project')
    .option('--constraints-file <file>', 'existing durable constraint register')
    .addOption(new Option('--phase <phase>', 'record validation phase').choices(['proposal', 'completion']).default('proposal'))
    .addOption(new Option('--compile-only', 'only run the pinned LikeC4 compiler').conflicts(['change', 'constraintsFile']))
    .action(async (_: unknown, command: Command) => {
      const { validate } = await import('./commands.js');
      output(await validate(command.optsWithGlobals<ValidateOptions>()), json, showValidation);
    });
  program.command('diff')
    .description('Compare committed source and computed models from the Git merge base')
    .requiredOption('--base <ref>', 'Git base ref')
    .option('--head <ref>', 'Git head ref', 'HEAD')
    .option('--source', 'emit only the Git source patch')
    .action(async (_: unknown, command: Command) => {
      const { diffCommand } = await import('./review.js');
      output(diffCommand(command.optsWithGlobals<DiffOptions>()), json, showDiff);
    });
  program.command('review')
    .description('Build a review bundle or verify a native proposal or its applied result')
    .option('--base <ref>', 'Git base ref')
    .option('--out <dir>', 'new output directory outside the Git repository')
    .option('--diff <name>', 'expected pending native diff name')
    .addOption(new Option('--check-proposal <file>', 'verify HEAD and the reviewed proposal sources')
      .conflicts(['base', 'out', 'diff', 'checkApplied']))
    .addOption(new Option('--check-applied <file>', 'verify the committed result against the native review')
      .conflicts(['base', 'out', 'diff', 'checkProposal']))
    .action(async (_: unknown, command: Command) => {
      const { reviewCommand, verifyReview } = await import('./review.js');
      const args = command.optsWithGlobals<ReviewOptions>();
      const check = args.checkApplied !== undefined || args.checkProposal !== undefined;
      output(check ? verifyReview(args, args.checkApplied !== undefined) : reviewCommand(args), json, result => {
        if ('mode' in result) console.log('Verified ' + result.mode + ' model at ' + result.commit);
        else {
          console.log('Review packet ' + result.review);
          console.log('LikeC4 viewer ' + result.viewer);
        }
      });
    });
  program.command('version')
    .description('Show C4Spec, LikeC4 and Node versions')
    .action(async () => {
      const { version } = await import('./commands.js');
      output(version(), json, result => console.log('C4Spec ' + result.c4spec + ' / LikeC4 ' + result.likec4 + ' / Node ' + result.node));
    });

  try {
    await program.parseAsync(argv);
  } catch (error) {
    if (error instanceof CommanderError && error.exitCode === 0) return;
    if (json) {
      console.log(JSON.stringify({ valid: false, error: errorMessage(error) }));
    } else if (!(error instanceof CommanderError)) {
      console.error('c4spec: ' + errorMessage(error));
    }
    process.exitCode = error instanceof CommanderError || error instanceof InputError ? 2 : 1;
  }
}
