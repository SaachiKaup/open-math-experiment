# Danus × Open Math OS

We want a team of agents to work on mathematical problems and keep their work in files. A local Codex coordinator follows Danus's approach: split the problem, check submissions, and build on accepted facts. Workers use Open Math OS for remote compute and project files. We watch and steer the work through tmux.

![Proposed Danus workflow, with local coordination and remote workers](docs/danus.svg)

## The approach

1. **Set the goal.** Agree on the problem and what counts as done.
2. **Split the work.** Assign focused tasks: a lemma, an example, a computation, or another line of attack.
3. **Run the workers.** An adapter uses the platform API and WebSocket. Each worker gets a session and output directory in the shared Open Math OS project.
4. **Check the results.** A fresh verifier reviews claims and supporting files. Accepted results enter Danus's fact graph; rejected submissions return for revision.
5. **Bring it together.** The coordinator uses accepted facts to choose the next tasks and assemble the final explanation and files.

The fact graph is our source of accepted mathematical results. Progress notes and promising ideas stay separate from verified facts.

## Watching and steering with tmux

We plan three windows: **coordinator**, **report**, and **control**. The reporter shows published progress, obstacles, and accepted results every three minutes. We can stop, reassign, and restart workers from the control window.

Remote workers do not need a pane each. Stopping the coordinator does not automatically stop them; local coordination needs its host awake.

## Where we are

**Verified:** our platform key can list teams and projects, read chat history, open a VM connection, authenticate over WebSocket, and list files in **AI Mathathon 2026**.

**Next:** connect Danus's worker execution to that runtime, submit and monitor tasks, transfer files, and add the reporter. The diagram shows this intended integration, not a completed deployment.

Use the **platform key** for agents and project files. The separate **model key** is for direct model inference. Keys stay in the local `.env`.

The probes and captured evidence are in [`experiments/`](experiments/). The reference Danus implementation is alongside this repo at `../Danus`.
