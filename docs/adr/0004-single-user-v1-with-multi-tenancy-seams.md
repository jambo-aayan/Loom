# Single-user v1, with cheap seams for later multi-tenancy

v1 has no authentication and no per-user data isolation — it's built for one account (the founder's). This was a deliberate choice against building real multi-tenancy (auth, per-user isolation, billing-shaped data) now, since there's no second user yet and guessing at those requirements risks building the wrong thing.

To keep the door open cheaply: every table carries a nullable owner/account-scoping column from the start, and secrets stay in config/env rather than baked into business logic. This is treated as inexpensive insurance, not as partial multi-tenancy — real auth and isolation are out of scope until there's an actual second user.
