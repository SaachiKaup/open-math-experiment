# Danus × Open Math OS

A local Codex coordinator uses Danus to organise mathematical work. Workers run in Open Math OS, with project files and remote compute. We supervise them through tmux.

## Agents and knowledge

![Danus agents, verifier, and memory](docs/danus.svg)

Exploratory subagents suggest directions. Proof workers develop claims. A fresh verifier checks each submission; only accepted results enter the fact graph. Shared notes and dead ends remain separate from verified facts.

## How we want to run it

![Planned tmux controls, worker creation, interruption, and checkpoints](docs/danus-control.svg)

Three tmux windows hold the **coordinator**, **report**, and **control** views. The coordinator can create workers as tasks branch. Each remote worker gets its own session and output folder; the reporter summarises published progress every three minutes.

At round boundaries and before a graceful stop, save the assignment, progress, output paths, and accepted fact references. Resume from that checkpoint, or change the assignment and start again. A forced interruption may lose unsaved work.

Stopping the coordinator does not stop remote workers. Local supervision still needs its host awake.

## Current status

**Verified:** platform-key authentication, project discovery, chat history, VM connection, and file listing in AI Mathathon 2026.

**To build:** the Danus worker adapter, task submission, file transfers, checkpoints, and reporter. The control diagram describes this plan.

Keys stay in `.env`. Reference harness: `../Danus`. Probes and evidence: [`experiments/`](experiments/).
