# Demo and Live are persistent parallel environments, not sequential phases

`Environment` (`demo` | `live`) is a property of each `Signal`, `Order`, and `Position` — not a one-time deployment setting or a phase a strategy graduates through. Both environments are always available; the dashboard has an explicit switch between them (comparable to an exchange's testnet/live toggle), so any strategy can be run against `demo` at any time regardless of its `live-enabled` status.

This was a direct correction of an earlier assumption (that promoting a strategy to Live would mean it "moves on" from Demo). The user wants to keep experimenting in Demo freely, indefinitely, in parallel with whatever is running for real — so `live-enabled` only ever adds Live access, it never removes Demo access.
