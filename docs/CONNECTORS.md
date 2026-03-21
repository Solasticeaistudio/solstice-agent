# Connectors

Solstice Agent supports external connectors through Python entry points.

## OSS Boundary

Open-source Sol provides:

- the core agent loop
- built-in tools
- the tool registry
- runtime profiles and security policy
- the connector loading interface

External connectors can add tools without modifying core.

That means the boundary is intentionally simple:

- OSS core owns runtime, safety policy, tool registration, and profile defaults
- Connector packages own service-specific auth, API logic, and any risky actions
- Paid Artemis connectors use the same public loading contract as third-party packages

## Loading Mechanism

Connectors are discovered from the `solstice_agent.connectors` entry-point group.

Each entry point should resolve to a callable that accepts a `ToolRegistry` and registers tools on it.

Example package metadata:

```toml
[project.entry-points."solstice_agent.connectors"]
my_connector = "my_package.connector:register"
```

Example implementation:

```python
def register(registry):
    registry.register(
        "my_tool",
        my_handler,
        {
            "name": "my_tool",
            "description": "Example connector tool",
            "parameters": {"type": "object", "properties": {}},
        },
    )
```

## Runtime Behavior

- Built-in tools load first
- Installed connectors are discovered afterward
- Failed connector imports are logged and do not stop Sol from starting
- Loaded connector names are available from `ToolRegistry.list_connectors()`

## Commercial Boundary

The OSS core is designed to stay boring here:

- core runtime and built-in tools stay in the open repository
- the plugin interface stays public
- premium Artemis connectors can live in separate packages and install into the same environment

That keeps the boundary clean:

- OSS core: runtime, safety, tool system, plugin interface
- external connector packages: deep platform integrations

In practice:

- `solstice-agent` remains installable and useful on its own
- connector packages extend the tool surface without forking core
- commercial connectors compete on integration depth, not on private runtime hooks

## Operational Guidance

- Install connector packages into the same environment as `sol`
- Keep connector tools subject to the same runtime-profile and policy expectations as built-in tools
- Prefer explicit docs for auth, network scope, and dangerous actions inside each connector package

Minimal packaging example:

```bash
pip install solstice-agent
pip install my-connector-package
sol
```
