# The per-update context stays a literal; `bind()` is not adopted

**Decision:** the middleware keeps building its child-container context as a hand-written dict —
`{Update: event, TelegramObject: cast("Update", event).event}` at a hardcoded `Scope.REQUEST` — and
does not route it through `modern_di.integrations.bind` / `classify_connection`. Layer 2 of the
integration kit (`from_di`, `parse_markers`, `resolve_markers`, `is_injected`, `mark_injected`) is
adopted; Layer 1 is not.

When `modern-di` 2.28 shipped `modern_di.integrations`, this package converted every hand-rolled
primitive it had — except this one. `bind(provider, connection)` classifies a *single* connection
object and produces the context entry for it. Here one incoming `event` seeds **two** aiogram types,
and asymmetrically: `Update` is bound to the event itself, `TelegramObject` to `event.event`,
aiogram's resolved inner object for that update. There is no isinstance dispatch to delegate either,
because the scope is fixed. So `bind` cannot derive this dict; it would have to be called twice and
the results merged, which is longer than the literal and hides where the asymmetry lives.

`modern-di`'s own kit design records aiogram as the documented Layer-1 outlier for exactly this
reason, so the literal is the upstream-sanctioned shape, not a conversion this repo skipped.

**Revisit trigger:** the kit grows a multi-provider or merge-shaped `bind`, or aiogram's update
model changes so the context becomes a single-connection classification — the shape `bind` is built
for.
