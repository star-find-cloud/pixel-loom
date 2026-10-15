# Local operation and issue reporting

Pixel Loom runs locally. The desktop/headless bridge binds to a random `127.0.0.1` port and requires a fresh local session token. MCP clients communicate over stdio. The application has no account system, model-key store or upload service.

The connected MCP host receives requested image/pixel results and may send them to its model provider according to that host's settings and data policies.

An MCP client intentionally gains the ability to read/write artwork files through the advertised tools. File paths may be absolute or relative to the configured workspace. Existing exports need `overwrite=true`; replacing unsaved artwork needs saving or explicit discard intent.

Runtime tokens, recovery copies, logs, personal client settings and artwork are not part of the release package. Do not post session tokens or private artwork in bug reports. Report the application version, operating system, minimal reproduction and relevant error code. If a repository with private reporting is configured later, use that channel for sensitive reports.

The current release is a public preview. Model-quality evaluation, untrusted network hosting and multi-user remote access are outside its current support scope.
