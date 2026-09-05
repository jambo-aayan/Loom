# Every strategy defaults to manual approval; auto-execution is opt-in per strategy

Every `Strategy` is created with `Approval mode: manual`, meaning every `Signal` it proposes needs an explicit human approval before it becomes an `Order` — regardless of how confident the strategy is. `auto-above-threshold` and `auto` exist as `Approval mode` values a specific strategy can be switched to, but only as a deliberate choice made after reviewing that strategy's track record; nothing is auto-approved by default.

This was a real trade-off: the user explicitly wanted the option of full automation for high-confidence signals, and the architecture supports it. But given real money is eventually involved and trust in any given strategy has to be earned, the safer default was chosen over the more automated one — a future reader should not assume "confidence exists, so it must already be driving automatic trades."
