# Chat trace modes

Chat uses two intentionally separate streams.

- `public_trace` is the normal user experience. It contains only fixed copy
  generated from allowlisted application events. It is persisted with the
  assistant message as `chat_messages.public_trace`.
- `debug_trace` is short-lived developer execution telemetry. It is not a chat
  message and is never stored as chat history.

`APP_ENV` (or the legacy `APP_ENVIRONMENT`) and `CHAT_TRACE_MODE` are evaluated
by the server. Production never sends `debug_trace`; development may send it
when `CHAT_TRACE_MODE=debug`; staging additionally requires an authenticated
JWT principal with `developer` or `admin` role. A client field such as
`debug: true` has no effect.

Developer trace payloads are recursively redacted for credentials, tokens,
passwords, service credentials, email, phone, and precise location. Provider
scratchpads (`analysis`, `thinking`, `reasoning_content`) are classified as
internal-only, discarded, and never become a public or developer UI surface.

The Flutter debug panel and its copy-transcript button are enabled automatically
in Flutter debug builds. They can be explicitly disabled or enabled with
`--dart-define=CHAT_DEBUG_TRACE=false|true`. That compile-time switch is not an
authorization boundary; the server-side gate remains authoritative. The copied
transcript contains the prior user message, the allowlisted public trace, and
only the already-redacted developer telemetry received by the client.

## Confirmed action lifecycle

When a suggested dish is awaiting confirmation, the server retains a
process-local, session- and authenticated-owner-bound action for 20 minutes.
The stored payload includes the catalogue dish reference and a stable write
request identifier; a websocket reconnect can continue that same pending
action. A confirmation atomically changes it from `PENDING_CONFIRMATION` to
`EXECUTING`; terminal state is retained for one hour so a second device receives
`ALREADY_EXECUTED` rather than creating a duplicate write. A later suggestion
of the same action type supersedes the earlier one, and a bare confirmation is
rejected as ambiguous if different pending action types coexist.

For a recommended dish, the Flutter write result must return the same
`catalog_dish_id` as both its persisted and read-back reference before the
assistant reports success. The normal UI receives only a human-readable action
state and allowlisted public trace; action IDs, tool arguments, and debug
telemetry are never added to chat history.
