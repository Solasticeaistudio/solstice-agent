# Connectors

Sol supports external tool connectors that extend its capabilities without modifying the core package.

## Installing a Connector

Connectors are separate Python packages installed into the same environment as Sol:

```bash
# pipx install (recommended)
pipx inject solstice-agent artemis-camunda

# pip install (if using pip directly)
pip install artemis-camunda
```

Sol auto-discovers connectors at startup via Python entry points — no config required.

## How Auto-Discovery Works

Connectors register themselves under the `solstice_agent.connectors` entry point group in their `pyproject.toml`:

```toml
[project.entry-points."solstice_agent.connectors"]
my-connector = "my_package.connector:register"
```

The `register` function receives a `ToolRegistry` instance and calls `registry.register(name, handler, schema)` for each tool it provides.

Sol calls `ToolRegistry.list_connectors()` at startup to log which connectors were loaded.

## Writing a Connector

```python
# my_package/connector.py

def register(registry):
    registry.register(
        "my_tool",
        my_tool_handler,
        {
            "name": "my_tool",
            "description": "Does something useful.",
            "parameters": {
                "type": "object",
                "properties": {
                    "input": {"type": "string", "description": "Input value"},
                },
                "required": ["input"],
            },
        },
    )

def my_tool_handler(input: str) -> str:
    return f"Processed: {input}"
```

## Listing Loaded Connectors

In Python:

```python
from solstice_agent.tools.registry import ToolRegistry

registry = ToolRegistry()
registry.load_builtins()
print(registry.list_connectors())
```

Or check the startup logs when running `sol --verbose`.

## Security Notes

Connectors run with the same permissions as Sol. Only install connectors from sources you trust. Review connector code before installation, especially for gateway deployments.
