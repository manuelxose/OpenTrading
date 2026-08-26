---
name: threat-model
description: "Model threats against trust zones and the LLM→Core→Broker boundary. Use for security-sensitive designs, execution paths, and zone changes."
---

# Threat Model

## Purpose
Make attack paths explicit for zones 1/2/3 (architecture §29) and the broker boundary.

## Trigger conditions
New components, network changes, execution paths, LLM integrations, authn/z.

## Inputs
Component/design + data flows.

## Outputs
Threat list with mitigations, stored in `docs/threat-model/`.

## Related agents
`security` (owner), `principal-architect`, `execution-mt4`, `ai-trading-systems`.

## Procedure
1. Draw data flows across zones 1/2/3.
2. Enumerate threats: prompt injection → order intent, bridge compromise, secret
   exposure, replay/duplicate commands, insider misuse.
3. Verify mitigations exist (EA defense-in-depth, idempotency, SAFE_MODE, kill switch).
4. Confirm LLMs have no broker credentials/execution sockets/secret-store access (INV-9).
5. Update the stored threat model; review at each phase boundary.
