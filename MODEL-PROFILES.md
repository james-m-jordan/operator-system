# Model and provider profiles

Version 0.7.0 adds local agent CLI adapters for GPT-6 Astra and Claude Opus 5.5.
The kit supplies task packets, routing, validation, and run receipts. Codex or
Claude Code supplies authentication, tools, context management, and the model
conversation. This is not a raw Responses/Messages API client.

## Built-in profiles

| Profile | Provider / agent runtime | Requested model | Default effort |
| --- | --- | --- | --- |
| `gpt-6-astra` | OpenAI / Codex CLI | `gpt-6-astra` | `medium` |
| `claude-opus-5-5` | Anthropic / Claude Code | `claude-opus-5-5` | `medium` |

Both accept `low`, `medium`, `high`, `xhigh`, and `max`. Medium is the starter
setting; compare task quality, latency, and cost before raising it. An effort label
does not imply equal compute or cost across providers. No pricing or context-window
assumptions are used to route tasks.

Model IDs are explicit rather than floating `opus` or `latest` aliases. The
profile's model/provider/effort values record the **requested** configuration;
they are not independent proof of the server model, endpoint, or billed usage.
Provider-managed policies, gateways, built-in subagents, and safety fallbacks
remain under the installed runtime's control. Review that runtime's configuration
when exact infrastructure or model attestation is required.

## Check and select

From a generated workspace:

```bash
python3 hub/scripts/ops.py profiles
python3 hub/scripts/ops.py profiles --profile gpt-6-astra --check-runtime
python3 hub/scripts/ops.py profiles --profile claude-opus-5-5 --check-runtime
python3 hub/scripts/ops.py run morning-control-panel --profile gpt-6-astra --preview
python3 hub/scripts/ops.py run morning-control-panel --profile claude-opus-5-5 --print-prompt
python3 hub/scripts/ops.py run morning-control-panel --profile gpt-6-astra --invoke
```

Listing and preview create no packet and make no model request. The runtime check
executes only the local CLI help command, checking the flags this adapter needs.
Invocation repeats that check before starting a profiled worker. Old Codex versions
without `exec`, and Claude versions without `--permission-prompts`, fail with
update guidance. A passing help check does not establish account/model access,
credentials, MCP availability, or sufficient task permissions.

Install and authenticate the provider's current CLI using its official setup.
Authentication stays in that CLI or its supported environment; never place API
keys in profiles or command arguments. A custom executable can be an absolute
path (including spaces) or a path relative to the workspace. It is a single argv
element, not shell code. No shell expansion is performed.

Selection is deterministic:

1. The run's `--profile` override.
2. `runtime.automation_profiles[automation-id]`.
3. `runtime.default_profile`.
4. Existing `runtime.agent_command`, when the default is null or absent.

For example, merge these settings into `hub/config/org.json`'s existing `runtime`:

```json
{
  "default_profile": "gpt-6-astra",
  "automation_profiles": {
    "system-review-loop": "claude-opus-5-5"
  },
  "model_profiles": {
    "gpt-6-astra": {"effort": "high", "timeout_seconds": 3600},
    "claude-opus-5-5": {"effort": "medium", "timeout_seconds": 2400},
    "astra-deep": {
      "provider": "openai",
      "model": "gpt-6-astra",
      "effort": "xhigh",
      "timeout_seconds": 7200
    }
  }
}
```

Built-in entries allow partial overrides. New names need `provider`, `model`, and
`effort`; executable and permissions get that provider's defaults. Built-in
timeouts are 3600 seconds. New profiles without a timeout use
`runtime.agent_timeout_seconds` or 3600. Existing wrappers keep their global
timeout and `{packet}` substitution. Null `default_profile` preserves that wrapper.
Built-ins exist in code, so safe upgrades need not overwrite user configuration.

Unknown profiles, fields, model/provider combinations, and effort values are
errors. API-specific knobs such as `temperature`, `thinking`, and `budget_tokens`
are intentionally not accepted by these CLI profiles. No automatic provider retry,
fallback routing, continuation, or change to installed schedules is introduced.
Existing scheduler exports remain packet-only drafts; installed external prompt
bundles do not configure another application's model picker.

## Permissions and invocation

The Codex adapter runs `codex exec`, passes the model, OpenAI provider, and
`model_reasoning_effort` as explicit settings, and defaults to `workspace-write`
with `approval_policy="never"`. Requests requiring escalation fail instead of
waiting on a person. `--skip-git-repo-check` supports the starter's multi-repository
workspace root. A profile can choose `sandbox: "read-only"`, but then the worker
cannot normally write its output or closeout. Do not expect successful autonomous
completion in that mode without an independently configured permitted mechanism.

The Claude adapter uses print mode with explicit model and effort, and
`permission_mode: "dontAsk"` by default. It passes `--permission-prompts none`
so unavailable permissions are denied without hanging. Configure narrow, reviewed
Claude permission rules for the actual task, including output writes and the
closeout command. A profile can supply `allowed_tools` (Claude permission-rule
strings), or select `acceptEdits` or `auto`. Those modes retain Claude's permission
checks and are not equivalents of Codex's OS sandbox. Organization policy still
applies. The adapter clears the optional availability fallback chain with
`fallbackModel: []`; provider safety policies remain in force.

Neither profile adds permission-bypass flags or grants sending authority. CLI
configuration and connectors may differ from this desktop chat. A task needing
mail, Slack, a browser, or other tools must have them configured in the selected
runtime; their presence in a packet is not proof they are available.

Both adapters receive packet text on stdin and run from the workspace directory.
Alongside `OPERATOR_RUN_ID`, `OPERATOR_WORKSPACE`, and `OPERATOR_PACKET`, workers
receive `OPERATOR_MODEL_PROFILE`, `OPERATOR_PROVIDER`, `OPERATOR_MODEL`, and
`OPERATOR_REASONING_EFFORT`. Custom wrappers receive empty model/effort fields.
The shared task contract tells both runtimes to read `AGENTS.md`; it is not replaced
by a provider-specific prompt or duplicated into a separate policy file.

The selected configuration and argv are saved in `run.json`, `started.json`, and
`invoke.json`. A CLI preflight failure writes an invocation diagnostic without a
start record. Exit zero still requires a matching evidence-backed chained closeout;
without one the runner returns 3. Provider failures retain their nonzero status.
Timeout returns 124 and terminates the POSIX worker process group, including
ordinary child processes. Deliberately detached processes and remote jobs are
outside that process group and need their own lifecycle controls.

## Validation and source basis

The automated suite uses local executable fixtures for both provider interfaces,
including model/effort arguments, stdin, working directory, environment, completion,
errors, incompatible CLIs, and timeout cleanup. It does not send private workspace
content to models or claim to measure real model quality. Before unattended use,
run a small authorized fixture task in your own configured runtime and verify its
artifact and closeout. A real model response alone is not a successful task.

The adapters were checked against these official sources on 2026-10-14:

- [GPT-6 Astra model and supported effort values](https://developers.openai.com/api/docs/models/gpt-6-astra).
- [Codex non-interactive command flags](https://learn.chatgpt.com/docs/developer-commands?surface=cli).
- [Claude Opus 5.5 migration requirements](https://platform.claude.com/docs/en/models/opus-5-5/migration-guide).
- [Claude Code command-line flags](https://code.claude.com/docs/en/cli-reference).
- [Claude model selection and fallback settings](https://code.claude.com/docs/en/model-config).
