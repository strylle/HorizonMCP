![HorizonMCP logo](horizonmcp.png)

A Model Context Protocol server for HOI4 modding, built & optimized for use by the Over the Horizon team for the mod... Over the Horizon. While other MCP solutions exist, HorizonMCP is specifically compatible with Over the Horizon's various mechanics such as the proxy war and space mechanic, and draws from some existing community tools (i.e using CWTools rather than a custom built linter).

### How is HorizonMCP different?

1. Lightweight, other implementations build their own custom linters when using HorizonMCP in the intended manner (thru an IDE), the agent should be able to pick up on any syntax or logic errors anyway.

2. Because Over the Horizon is highly complex & utlizes numerous custom mechanics (i.e space mechanic using a ton of math & scripted guis, a proxy mechanic utilizing an entirely custom pseudodecision gui and backend), not only are existing tools inefficient, but we needed a custom solution not at the whims of anyone else.

3. While yes, Mythos-class and even Opus-class models are incredibly good at figuring out what I'm trying to do and planning accordingly, at times it makes mistakes and frequently consumes a ton of tokens figuring out context.

### Setup

1. Install: `.venv/bin/pip install -e .`
2. Copy `.mcp.json.example` to `.mcp.json` and set `MOD_PATH` to your local othmod folder.
3. Restart Claude Code

