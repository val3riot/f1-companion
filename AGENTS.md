# Codex repository instructions

Before changing this repository, read `.agent/PROJECT.md`. It contains the
architecture, ownership map, development commands, validation matrix, and
project-specific constraints.

Keep `.agent/PROJECT.md` updated when a change materially alters architecture,
startup commands, external integrations, environment variables, or testing.

Never print, commit, or copy values from `backend/.env`. In particular,
`F1_SIGNALR_LOGIN_SESSION`, `F1_SIGNALR_AUTH_TOKEN`, and `OPENAI_API_KEY` are
secrets. Use `.env.example` and variable names when documenting configuration.
