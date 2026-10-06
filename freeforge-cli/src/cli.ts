#!/usr/bin/env node
import { Command, CommanderError } from "commander";
import {
  cmdDoctor,
  cmdEval,
  cmdResume,
  cmdRun,
  cmdServeStatus,
  cmdStatus,
  cmdWorkflows,
  unsupported,
} from "./commands.js";

const program = new Command();
program
  .name("freeforge")
  .description("FreeForge CLI — cost policy, workflows, OpenClaw adapter (loopback)")
  .version("0.1.0")
  .showSuggestionAfterError(false);

program
  .command("doctor")
  .description("Probe policy, SQLite, OpenClaw supported interfaces (no private DB writes)")
  .action(async () => {
    process.exitCode = await cmdDoctor();
  });

program
  .command("run")
  .description("Execute a local command through the adapter; record FreeForge receipts")
  .argument("[argv...]", "command and args (use -- to stop option parsing)")
  .allowUnknownOption(true)
  .action(async (argv: string[]) => {
    const raw = process.argv;
    const dash = raw.indexOf("--");
    const cmdArgv = dash >= 0 ? raw.slice(dash + 1) : argv;
    process.exitCode = await cmdRun(cmdArgv);
  });

program
  .command("workflows")
  .description("List or invoke named workflows")
  .argument("[action]", "list | run", "list")
  .argument("[name]", "workflow name")
  .action(async (action: string, name?: string) => {
    try {
      process.exitCode = await cmdWorkflows(action, name);
    } catch {
      process.exitCode = 2;
    }
  });

program
  .command("status")
  .description("Show task status from FreeForge SQLite (survives restart)")
  .argument("[taskId]", "optional task id")
  .action(async (taskId?: string) => {
    process.exitCode = await cmdStatus(taskId);
  });

program
  .command("resume")
  .description("Recover task status after restart; re-run if incomplete")
  .argument("<taskId>", "task id")
  .action(async (taskId: string) => {
    process.exitCode = await cmdResume(taskId);
  });

program
  .command("eval")
  .description("Run built-in FreeForge CLI evaluation")
  .action(async () => {
    process.exitCode = await cmdEval();
  });

program
  .command("serve-status")
  .description("Loopback HTTP status listener with bearer auth")
  .option("-p, --port <n>", "port", "18791")
  .action(async (opts: { port: string }) => {
    process.exitCode = await cmdServeStatus(Number(opts.port));
  });

program.exitOverride();

try {
  await program.parseAsync(process.argv);
} catch (err) {
  if (err instanceof CommanderError) {
    if (err.code === "commander.helpDisplayed" || err.code === "commander.versionDisplayed") {
      process.exitCode = 0;
    } else if (err.code === "commander.unknownCommand") {
      const name = (err.message.match(/unknown command ['"]([^'"]+)/i) || [])[1] || "unknown";
      try {
        unsupported(name);
      } catch {
        process.exitCode = 2;
      }
    } else {
      process.exitCode = err.exitCode ?? 1;
    }
  } else {
    throw err;
  }
}
