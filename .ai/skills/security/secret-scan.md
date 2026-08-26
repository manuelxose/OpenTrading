---
name: secret-scan
description: "Scan for exposed secrets. Use before commits and in reviews; check git, Obsidian, Graphiti, Langfuse, and logs paths."
---

# Secret Scan

## Purpose
Secrets never appear in git, Obsidian, Graphiti, Langfuse prompts, or logs (§29).

## Trigger conditions
Pre-commit, review, dependency or config changes.

## Inputs
Changed files.

## Outputs
Findings with remediation.

## Related agents
`security` (owner), `infra-sre`.

## Procedure
1. Scan diffs for keys, tokens, passwords, connection strings.
2. Confirm `.env` excluded (`.gitignore`); production uses SOPS + age or
   Vault/Docker secrets.
3. Check logs/observability paths do not serialize credentials.
4. Confirm `vault-trading/` and Langfuse prompts contain no secrets.
5. Rotate anything found; never "just delete and move on" without evidence.
