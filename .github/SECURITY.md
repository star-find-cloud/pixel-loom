# Security policy

Pixel Loom is a local public-preview application. It uses a token-authenticated loopback bridge and standard MCP/stdio. It is not intended for untrusted network hosting or multi-user remote access.

A connected MCP client intentionally gains the ability to read and write artwork files through the advertised tools. Image results may be processed by the client's model provider. See [the local-operation policy](../project/SECURITY.md).

For a report, include the version, operating system, minimal reproduction and error code. Never include passwords, model credentials, session tokens, private artwork or client configuration in a public issue. If GitHub offers private vulnerability reporting for this repository, use it for sensitive details; otherwise share only a redacted description publicly.
