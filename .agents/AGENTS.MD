# Agent Instructions — Cop & Thief Final Project

You are working on an AI-agent game project containing separate implementations for the **Cop** and the **Thief**.

Your responsibility is to improve, validate, debug, and maintain the project while strictly following the official project specification.

## 1. Source of Truth

Before implementing anything substantial, inspect the available project documentation.

Priority order:

1. The official PDF specification in the `ref/` folder.
2. `TASKS.md`.
3. `TODO.md` or the current TODO list.
4. Existing README documentation.
5. Existing implementation and configuration files.

The PDF specification is the authoritative source.

If the code conflicts with the PDF, follow the PDF and update the implementation accordingly.

Pay special attention to pages **94–95**, which describe the JSON files required for email submission.

Do not assume requirements. Verify them from the documentation.

---

# 2. Repository Separation

The Cop and Thief must be treated as independent agents with separate repositories.

Example repositories:

Cop:

`C:\Users\Aisha\Desktop\AI\uoh-ay26-final-project-cop`

Thief:

`C:\Users\Aisha\Desktop\AI\uoh-ay26-final-project-thief`

Each repository must contain only the information that the corresponding agent is legitimately allowed to know.

## Cop Repository

The Cop repository must not contain private Thief information such as:

* Thief strategy implementation.
* Thief-specific configuration.
* Hidden Thief parameters.
* Private Thief state.
* Internal Thief prompts.
* Any information that would give the Cop unfair knowledge.

For example, a file such as:

`config/thief/game.toml`

should not remain in the Cop repository unless the project specification explicitly requires it.

When reviewing the repository:

* Delete unnecessary opponent-specific files.
* Replace files with Cop-specific equivalents when needed.
* Preserve genuinely shared game interfaces and protocols.
* Update imports, paths, scripts, tests, and documentation after restructuring.

Apply the same principle to the Thief repository.

---

# 3. Never Give an Agent Unauthorized Knowledge

An agent may use:

* Public board state.
* Legal actions.
* Shared game configuration.
* Information explicitly exposed through the official game protocol.
* Its own history and internal strategy.

An agent must not use:

* Opponent private configuration.
* Opponent hidden state.
* Opponent strategy implementation.
* Future actions.
* Files unavailable through the official protocol.

Do not improve an agent by giving it information it should not possess.

Improve the reasoning and strategy instead.

---

# 4. Cop Strategy

The Cop's primary objective is to **capture the Thief**.

The Cop should behave as an intelligent pursuer rather than simply reacting to the nearest local move.

The strategy should consider:

* Shortest valid path toward the Thief.
* Obstacles.
* Reachability.
* Alternative routes.
* Thief escape directions.
* Potential interception points.
* Dead ends.
* Recent movement history.
* Repeated states.
* Distance reduction.
* Capture opportunities.

The Cop should avoid:

* Random movement.
* Repeated left-right or forward-backward oscillation.
* Moving away from the Thief without strategic reason.
* Repeatedly visiting the same positions.
* Using fallback logic unnecessarily.

When useful, evaluate multiple legal actions and assign each one a score.

Possible Cop scoring factors include:

* Reduction in shortest-path distance to the Thief.
* Probability of interception.
* Number of Thief escape routes removed.
* Penalty for repeated positions.
* Penalty for reversing the previous action.
* Penalty for entering strategically poor locations.
* Bonus for forcing the Thief toward dead ends.

---

# 5. Thief Strategy

The Thief's primary objective is to **avoid capture while accomplishing its game objectives**.

The strategy should consider:

* Distance from the Cop.
* Shortest-path distance rather than only Euclidean distance.
* Nearby escape routes.
* Dead ends.
* Obstacles.
* Future Cop reachability.
* Recent movement history.
* Repeated states.
* Alternative paths.
* Objective locations such as gems when relevant.

The Thief should avoid:

* Moving predictably back and forth.
* Entering dead ends unnecessarily.
* Selecting actions that immediately reduce safety.
* Reusing the same route indefinitely.
* Falling back because of preventable reasoning failures.

When possible, evaluate several future states instead of considering only the immediate move.

Possible Thief scoring factors include:

* Distance from the Cop.
* Number of available escape routes.
* Risk of capture during the next few turns.
* Progress toward objectives.
* Penalty for recently visited positions.
* Penalty for reversing direction.
* Penalty for entering dead ends.
* Bonus for routes with several future alternatives.

---

# 6. Loop and Oscillation Detection

Both agents must detect repetitive behavior.

Maintain a short history of:

* Positions.
* Actions.
* Board states where appropriate.

Detect patterns such as:

`A -> B -> A -> B`

or repeated visits to the same small set of cells.

When a loop is detected:

1. Penalize recently repeated actions and positions.
2. Re-evaluate all legal alternatives.
3. Prefer a meaningfully different route.
4. Log that loop detection was activated.

Do not hard-code a fix for one specific game log.

Implement general anti-loop behavior.

---

# 7. Gemini / LLM Decision Handling

If Gemini is used for action selection, never execute its response directly.

The program must provide Gemini with sufficient structured context, including:

* Agent role.
* Agent objective.
* Current board state.
* Cop position.
* Thief position.
* Obstacles.
* Available legal actions.
* Recent actions.
* Recent positions.
* Important game constraints.
* Loop warnings when applicable.

Require a strict output format.

Prefer a small structured response such as JSON.

Example conceptual format:

{
"action": "UP",
"reason": "...",
"confidence": 0.84
}

Do not depend on free-form text parsing when it can be avoided.

---

# 8. Validate Every LLM Action

Every Gemini-generated action must pass local validation.

Validate that:

* The action exists.
* The action is syntactically valid.
* The action belongs to the allowed action set.
* The move is legal in the current board state.
* The destination is reachable.
* The action does not violate the game rules.

If Gemini returns an invalid action:

1. Reject it.
2. Log why it was rejected.
3. If appropriate, retry using a stricter prompt containing only legal actions.
4. If that still fails, use the deterministic local strategy.

Fallback should be the final recovery mechanism, not normal behavior.

---

# 9. Fallback Strategy

Fallback behavior must also be intelligent.

Never use a purely random legal action unless the specification explicitly requires randomness.

For the Cop, fallback should still attempt to pursue or intercept the Thief.

For the Thief, fallback should still maximize safety and avoid capture.

Track how often fallback is used.

Frequent fallback usage should be treated as a bug or strategy-quality problem that requires investigation.

---

# 10. Game Log Analysis

Use existing JSON logs to evaluate strategy quality.

Important examples include:

`results/network/log_G001_g01.json`

`results/network/log_G001_g02.json`

Analyze games step by step.

Look for:

* Oscillation.
* Repeated actions.
* Invalid Gemini outputs.
* Unnecessary fallback usage.
* Missed capture opportunities.
* Poor escape choices.
* Dead-end movement.
* Cases where a clearly better legal action existed.

After strategy changes, re-run comparable scenarios and compare the new logs with the previous results.

Do not conclude that a strategy improved simply because the program runs successfully.

Evaluate the actual behavior.

---

# 11. Logging

Decision logs should make debugging possible.

For every important turn, record useful information such as:

* Game ID.
* Turn number.
* Agent position.
* Opponent position.
* Legal actions.
* Candidate actions.
* Candidate scores when applicable.
* Selected action.
* Source of decision:

  * deterministic strategy,
  * Gemini,
  * retry,
  * fallback.
* Whether the action was valid.
* Why an action was rejected.
* Whether loop detection was triggered.
* Why fallback was activated.

Keep logs readable.

Do not flood the output with irrelevant implementation details.

---

# 12. Pre-Game Integrity Verification

Add a verification stage before gameplay begins.

Its purpose is to detect incompatible or unauthorized game configuration changes.

Validate shared/protected configuration such as:

* `game.json`
* `config/game.toml`
* Board dimensions.
* Map structure.
* Initial positions where defined by the official configuration.
* Available actions.
* Movement rules.
* Scoring rules.
* Capture conditions.
* Turn limits.
* Shared protocol configuration.

Use a trusted canonical configuration as the source of truth.

Do not simply compare two potentially modified files against each other.

When appropriate, use checksums for files that are expected to remain identical.

If validation fails:

1. Stop before gameplay.
2. Report the affected file.
3. Report the affected field.
4. Show the expected value.
5. Show the received value.
6. Store the validation failure in the logs.

The verifier must not inspect private opponent strategy code.

---

# 13. Required JSON Submission Files

Carefully review pages 94–95 of the official PDF.

Determine exactly which JSON files must be sent by email.

For every required JSON file, verify:

* Exact filename.
* Schema.
* Required fields.
* Optional fields.
* Data types.
* Allowed values.
* Naming convention.
* Relationship with other files.

Compare the specification with the files generated by the current implementation.

If necessary, update the generators.

Create an automatic submission validator that checks the generated files before submission.

Validation errors should clearly report:

* Filename.
* Field.
* Expected format/value.
* Actual format/value.

Do not include additional private information in submission files unless explicitly required.

---

# 14. README

Each repository should have a polished and accurate README.

The README should include, where applicable:

* Project overview.
* Agent objective.
* Architecture.
* Strategy explanation.
* Important algorithms.
* Gemini/LLM usage.
* Action validation.
* Fallback behavior.
* Installation.
* Configuration.
* Running instructions.
* Testing instructions.
* Game-log explanation.
* Results.
* Limitations.
* Required submission files.

Do not document capabilities that do not actually exist.

---

# 15. Game Replay Visualization

Support visualization of recorded JSON games.

Provide a reusable script that converts game-result JSON logs into an animated GIF and optionally an MP4.

The visualization should clearly display:

* Board.
* Cop.
* Thief.
* Obstacles.
* Gems/objectives when applicable.
* Current turn.
* Selected action.
* Agent movement.
* Score.
* Capture or important events.

Highlight movement between frames.

The resulting GIF should be suitable for embedding directly into GitHub README files.

Do not assume the JSON schema. Inspect the actual log structure first.

---

# 16. Code Quality

Prefer:

* Clear functions.
* Small modules.
* Explicit validation.
* Deterministic behavior where possible.
* Reusable strategy components.
* Type hints where useful.
* Focused comments.
* Meaningful names.
* Tests for important logic.

Avoid:

* Hard-coded game-specific fixes.
* Huge functions.
* Duplicated Cop/Thief logic when shared utilities are appropriate.
* Silent exceptions.
* Random fallback without justification.
* Hidden assumptions about file structure.

---

# 17. Testing

When modifying strategy code, test more than one scenario.

At minimum test:

* Normal pursuit.
* Normal escape.
* Obstacle-heavy map.
* Dead-end scenario.
* Loop/oscillation scenario.
* Invalid Gemini response.
* Gemini unavailable.
* No obvious direct route.
* Near-capture situation.
* Long-running game.

Verify that all produced actions remain valid.

---

# 18. Git Workflow

Before beginning a new independent feature, inspect the working tree.

Do not overwrite unrelated user changes.

When explicitly requested to commit existing work before continuing, commit it first with a clear message describing what was actually completed.

Use meaningful commit messages, for example:

`feat: improve database synchronization with live files`

`feat: add intelligent cop pursuit strategy`

`fix: validate Gemini actions before execution`

`feat: add pre-game configuration integrity checks`

`docs: update README with game results and replay`

Do not commit generated files, temporary logs, credentials, local environments, or unrelated artifacts unless they are intentionally part of the repository.

---

# 19. Safe Refactoring

Before changing existing architecture:

1. Understand how the current implementation works.
2. Identify dependencies.
3. Preserve working behavior.
4. Make the smallest coherent change.
5. Update affected tests.
6. Re-run the relevant flow.

Do not rewrite large parts of the project without evidence that it is necessary.

---

# 20. Working Style

For every task:

1. Inspect the relevant files first.
2. Read the related requirement in the PDF/TASKS/TODO when applicable.
3. Explain internally what is causing the current problem.
4. Implement a general solution.
5. Validate the result.
6. Run relevant tests.
7. Review generated logs/output.
8. Update documentation when behavior changed.

Do not report a task as completed merely because code was written.

A task is complete only when the implementation has been verified against the project requirements and tested.

---

# 21. Final Priority

The goal is not simply to make the agents move.

The final project should demonstrate intelligent, rule-compliant behavior:

**Cop**
→ actively pursues, predicts, intercepts, and catches the Thief.

**Thief**
→ intelligently escapes, avoids traps, progresses toward objectives, and does not behave predictably.

**Both**
→ make valid actions, avoid repetitive loops, expose only permitted information, comply with the official protocol, produce correct submission files, and generate clear logs that explain their behavior.

Always prefer a robust general solution over a patch that only fixes one recorded game.
