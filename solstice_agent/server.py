"""
Gateway Server
==============
Flask server that exposes the messaging gateway endpoints.
Run alongside or instead of the CLI for channel-based messaging.

Usage:
    solstice-gateway                     # Start gateway server
    solstice-gateway --port 8000         # Custom port

Security:
    - Binds to 127.0.0.1 by default (localhost only)
    - Token-based authentication required on all endpoints
    - Use --host 0.0.0.0 and --auth-token for network-accessible deployments
"""

import argparse
import functools
import logging
import os
import secrets

from flask import Flask, request, jsonify

from .config import Config, RUNTIME_PROFILE_NAMES
from .agent.core import Agent
from .agent.personality import DEFAULT
from .tools.registry import ToolRegistry
from .tools.security import set_workspace_root

log = logging.getLogger("solstice.server")

app = Flask(__name__)

# Auth token — set at startup
_auth_token: str = ""


def _require_auth(f):
    """Decorator: require Bearer token authentication on endpoints."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not _auth_token:
            # No token configured — allow (localhost-only deployments)
            return f(*args, **kwargs)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authentication required. Pass 'Authorization: Bearer <token>' header."}), 401

        provided = auth_header[7:]
        if not secrets.compare_digest(provided, _auth_token):
            return jsonify({"error": "Invalid authentication token."}), 403

        return f(*args, **kwargs)
    return decorated

# Singletons
_agent = None
_pool = None
_router = None
_config = None


def _get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.load()
    return _config


def _server_tool_flags(config: Config) -> dict:
    """Gateway/server tool exposure must be explicit and safe by default."""
    return config.resolve_tool_flags(default_profile="gateway")


def _configure_gateway_workspace(config: Config, cli_workspace_root: str | None = None):
    """Gateway file access must fail closed when no workspace is configured."""
    workspace_root = cli_workspace_root or os.environ.get("SOLSTICE_WORKSPACE_ROOT") or config.workspace_root
    set_workspace_root(workspace_root or None, required=True)


def _get_pool():
    """Get AgentPool (multi-agent mode) or None."""
    global _pool
    if _pool is not None:
        return _pool

    config = _get_config()
    if not config.has_multi_agent():
        return None

    from .agent.skills import init_skills
    if _server_tool_flags(config)["enable_skills"]:
        init_skills()

    from .agent.router import AgentPool
    agent_configs = config.get_agent_configs()
    _pool = AgentPool(agent_configs, global_config=config)

    # Scheduler
    if _server_tool_flags(config)["enable_cron"]:
        from .agent.scheduler import init_scheduler

        def _factory():
            p = config.create_provider()
            a = Agent(provider=p, personality=DEFAULT,
                      temperature=config.temperature)
            r = ToolRegistry()
            flags = _server_tool_flags(config)
            flags["enable_cron"] = False
            r.load_builtins(**flags)
            r.apply(a)
            return a

        init_scheduler(_factory)

    log.info(f"Multi-agent pool initialized: {_pool.list_agents()}")
    return _pool


def _get_router():
    """Get AgentRouter (multi-agent mode) or None."""
    global _router
    if _router is not None:
        return _router

    config = _get_config()
    if not config.has_multi_agent():
        return None

    from .agent.router import AgentRouter
    routing_config = config.get_routing_config()
    if routing_config:
        _router = AgentRouter.from_config(routing_config)
    else:
        _router = AgentRouter(strategy="channel", default="default")

    log.info(f"Router initialized: strategy={_router.strategy}")
    return _router


def _get_agent() -> Agent:
    """Get single agent (legacy mode)."""
    global _agent
    if _agent is None:
        config = _get_config()
        provider = config.create_provider()

        # Skills
        skill_loader = None
        if _server_tool_flags(config)["enable_skills"]:
            from .agent.skills import init_skills, _get_loader
            init_skills()
            skill_loader = _get_loader()

        # Compactor
        from .agent.compactor import ContextCompactor, CompactorConfig
        compactor = ContextCompactor(provider, CompactorConfig(model_name=config.model))

        _agent = Agent(
            provider=provider, personality=DEFAULT,
            temperature=config.temperature,
            skill_loader=skill_loader, compactor=compactor,
        )

        registry = ToolRegistry()
        registry.load_builtins(**_server_tool_flags(config))
        registry.apply(_agent)

        # Scheduler
        if _server_tool_flags(config)["enable_cron"]:
            from .agent.scheduler import init_scheduler

            def _factory():
                p = config.create_provider()
                a = Agent(provider=p, personality=DEFAULT,
                          temperature=config.temperature, skill_loader=skill_loader)
                r = ToolRegistry()
                flags = _server_tool_flags(config)
                flags["enable_cron"] = False
                r.load_builtins(**flags)
                r.apply(a)
                return a

            init_scheduler(_factory)

        log.info(f"Agent initialized: {provider.name()}")
    return _agent


@app.route("/chat", methods=["POST"])
@_require_auth
def chat():
    """Chat endpoint. Supports multi-agent via 'agent' and 'sender_id' fields."""
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    if not message:
        return jsonify({"error": "Missing 'message'"}), 400

    agent_name = data.get("agent", "default")
    sender_id = data.get("sender_id", "")

    pool = _get_pool()
    if pool:
        agent = pool.get_agent(agent_name, sender_id=sender_id)
    else:
        agent = _get_agent()

    response = agent.chat(message)
    return jsonify({"response": response, "agent": agent_name})


@app.route("/agents", methods=["GET"])
@_require_auth
def agents():
    """List available agents and routing config."""
    pool = _get_pool()
    router = _get_router()
    if pool:
        return jsonify({
            "agents": pool.list_agents(),
            "active_instances": pool.active_count(),
            "routing": {
                "strategy": router.strategy if router else "none",
                "default": router.default if router else "default",
                "rules": router.rules if router else {},
            },
        })
    else:
        _get_agent()
        return jsonify({
            "agents": ["default"],
            "active_instances": 1,
            "routing": {"strategy": "single", "default": "default"},
        })


@app.route("/health", methods=["GET"])
def health():
    """Health check. Returns minimal info (no internal state leakage)."""
    return jsonify({"status": "ok"})


def main():
    global _auth_token, _config

    parser = argparse.ArgumentParser(prog="solstice-gateway", description="Solstice Agent Gateway Server")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind address (default: 127.0.0.1 — localhost only)")
    parser.add_argument("--config", "-c", help="Path to config file")
    parser.add_argument("--profile", choices=RUNTIME_PROFILE_NAMES,
                        help="Runtime profile for gateway/server tool defaults")
    parser.add_argument("--workspace-root",
                        help="Workspace root for gateway file tools. If omitted, file access fails closed.")
    parser.add_argument("--auth-token", default=None,
                        help="Bearer token for API authentication (or set SOL_GATEWAY_TOKEN env var)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(name)s: %(message)s")
    _config = Config.load(args.config)
    _config.runtime_profile = args.profile or _config.runtime_profile or "gateway"
    _configure_gateway_workspace(_config, cli_workspace_root=args.workspace_root)

    # Auth token from flag, env var, or auto-generated
    _auth_token = args.auth_token or os.environ.get("SOL_GATEWAY_TOKEN", "")

    if args.host != "127.0.0.1" and not _auth_token:
        # Generate and display a token for network-accessible deployments
        _auth_token = secrets.token_urlsafe(32)
        print(f"WARNING: Binding to {args.host} with auto-generated auth token.")
        print(f"  Token: {_auth_token}")
        print(f"  Pass via: Authorization: Bearer {_auth_token}")
        print()

    print(f"Solstice Gateway starting on {args.host}:{args.port}")
    if _auth_token:
        print("  Authentication: enabled")
    else:
        print("  Authentication: disabled (localhost only)")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
