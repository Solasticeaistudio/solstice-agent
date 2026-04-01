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
import json
import logging
import os
import secrets

from flask import Flask, request, jsonify, Response, stream_with_context

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
            a.auto_track_tasks = True
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
        _agent.auto_track_tasks = True

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
                a.auto_track_tasks = True
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


@app.route("/tasks", methods=["GET", "DELETE"])
@_require_auth
def tasks():
    from .agent.tasks import task_list, task_clear

    if request.method == "DELETE":
        return jsonify({"result": task_clear()})
    return jsonify({"result": task_list(request.args.get("status", ""))})


@app.route("/subagents", methods=["GET"])
@_require_auth
def subagents():
    agent = _get_agent()
    if "subagent_list" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Sub-agent tools are unavailable."}), 400
    return jsonify({"result": agent._tools["subagent_list"]()})


@app.route("/subagents/graph", methods=["GET"])
@_require_auth
def subagent_graph():
    agent = _get_agent()
    if "subagent_graph" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Sub-agent tools are unavailable."}), 400
    return jsonify({"result": agent._tools["subagent_graph"](request.args.get("run_id", ""))})


@app.route("/subagents/workflows", methods=["POST"])
@_require_auth
def submit_subagent_workflow():
    agent = _get_agent()
    if "submit_workflow" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Sub-agent tools are unavailable."}), 400
    payload = request.get_json(silent=True) or {}
    return jsonify(
        {
            "result": agent._tools["submit_workflow"](
                payload.get("workflow_json", ""),
                payload.get("workflow_name", ""),
            )
        }
    )


@app.route("/workflows", methods=["GET"])
@_require_auth
def workflows():
    agent = _get_agent()
    if "workflow_list" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Workflow tools are unavailable."}), 400
    return jsonify({"result": agent._tools["workflow_list"]()})


@app.route("/workflows/<workflow_id>", methods=["GET"])
@_require_auth
def workflow_status(workflow_id: str):
    agent = _get_agent()
    if "workflow_status" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Workflow tools are unavailable."}), 400
    return jsonify({"result": agent._tools["workflow_status"](workflow_id)})


@app.route("/workflows/<workflow_id>/events", methods=["GET"])
@_require_auth
def workflow_events(workflow_id: str):
    agent = _get_agent()
    if "workflow_events" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Workflow tools are unavailable."}), 400

    from .agent.subagents import _get_manager

    manager = _get_manager()
    watcher = manager.subscribe_workflow(workflow_id)

    @stream_with_context
    def generate():
        try:
            while True:
                try:
                    event = watcher.get(timeout=15)
                    payload = json.dumps(event)
                    yield f"event: workflow\ndata: {payload}\n\n"
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            manager.unsubscribe_workflow(workflow_id, watcher)

    import queue
    return Response(generate(), mimetype="text/event-stream")


@app.route("/workflows/<workflow_id>/cancel", methods=["POST"])
@_require_auth
def workflow_cancel(workflow_id: str):
    agent = _get_agent()
    if "workflow_cancel" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Workflow tools are unavailable."}), 400
    return jsonify({"result": agent._tools["workflow_cancel"](workflow_id)})


@app.route("/workflows/<workflow_id>/resume", methods=["POST"])
@_require_auth
def workflow_resume(workflow_id: str):
    agent = _get_agent()
    if "workflow_resume" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Workflow tools are unavailable."}), 400
    return jsonify({"result": agent._tools["workflow_resume"](workflow_id)})


@app.route("/workflows/<workflow_id>/nodes/<node_id>/disable", methods=["POST"])
@_require_auth
def workflow_disable_node(workflow_id: str, node_id: str):
    agent = _get_agent()
    if "workflow_disable_node" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Workflow tools are unavailable."}), 400
    return jsonify({"result": agent._tools["workflow_disable_node"](workflow_id, node_id)})


@app.route("/workflows/<workflow_id>/nodes/<node_id>/enable", methods=["POST"])
@_require_auth
def workflow_enable_node(workflow_id: str, node_id: str):
    agent = _get_agent()
    if "workflow_enable_node" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Workflow tools are unavailable."}), 400
    return jsonify({"result": agent._tools["workflow_enable_node"](workflow_id, node_id)})


@app.route("/workflows/<workflow_id>/nodes/<node_id>", methods=["DELETE"])
@_require_auth
def workflow_remove_node(workflow_id: str, node_id: str):
    agent = _get_agent()
    if "workflow_remove_node" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Workflow tools are unavailable."}), 400
    return jsonify({"result": agent._tools["workflow_remove_node"](workflow_id, node_id)})


@app.route("/workflows/<workflow_id>/nodes/<node_id>/retry-branch", methods=["POST"])
@_require_auth
def workflow_retry_branch(workflow_id: str, node_id: str):
    agent = _get_agent()
    if "workflow_retry_branch" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Workflow tools are unavailable."}), 400
    return jsonify({"result": agent._tools["workflow_retry_branch"](workflow_id, node_id)})


@app.route("/workflows/<workflow_id>/snapshot", methods=["POST"])
@_require_auth
def workflow_snapshot(workflow_id: str):
    agent = _get_agent()
    if "workflow_snapshot" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Workflow tools are unavailable."}), 400
    payload = request.get_json(silent=True) or {}
    return jsonify({"result": agent._tools["workflow_snapshot"](workflow_id, payload.get("label", ""))})


@app.route("/workflows/<workflow_id>/export", methods=["GET"])
@_require_auth
def workflow_export(workflow_id: str):
    agent = _get_agent()
    if "workflow_export" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Workflow tools are unavailable."}), 400
    snapshot_id = request.args.get("snapshot_id", "")
    return jsonify({"result": agent._tools["workflow_export"](workflow_id, snapshot_id)})


@app.route("/workflows/<workflow_id>/nodes", methods=["POST"])
@_require_auth
def workflow_add_node(workflow_id: str):
    agent = _get_agent()
    if "workflow_add_node" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Workflow tools are unavailable."}), 400
    payload = request.get_json(silent=True) or {}
    return jsonify(
        {
            "result": agent._tools["workflow_add_node"](
                workflow_id,
                payload.get("node_id", ""),
                payload.get("prompt", ""),
                payload.get("depends_on_node_ids"),
                payload.get("dependency_policies_json", ""),
                payload.get("tools"),
                payload.get("extra_instructions", ""),
                payload.get("include_parent_history", False),
                payload.get("async_mode", True),
                payload.get("allowed_command_prefixes"),
                payload.get("denied_command_prefixes"),
                payload.get("workspace_root"),
                payload.get("workspace_required"),
                payload.get("model_override", ""),
                payload.get("max_tool_iterations"),
                payload.get("task_subject", ""),
                payload.get("priority", 0),
                payload.get("retry_policy", "never"),
                payload.get("max_retries", 0),
            )
        }
    )


@app.route("/workflows/<workflow_id>/nodes/<node_id>/retry", methods=["POST"])
@_require_auth
def workflow_retry_node(workflow_id: str, node_id: str):
    agent = _get_agent()
    if "workflow_retry_node" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Workflow tools are unavailable."}), 400
    return jsonify({"result": agent._tools["workflow_retry_node"](workflow_id, node_id)})


@app.route("/workflows/<workflow_id>/nodes/<node_id>/priority", methods=["POST"])
@_require_auth
def workflow_set_priority(workflow_id: str, node_id: str):
    agent = _get_agent()
    if "workflow_set_priority" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Workflow tools are unavailable."}), 400
    payload = request.get_json(silent=True) or {}
    return jsonify({"result": agent._tools["workflow_set_priority"](workflow_id, node_id, payload.get("priority", 0))})


@app.route("/workflows/<workflow_id>/edges", methods=["POST"])
@_require_auth
def workflow_update_edge_policy(workflow_id: str):
    agent = _get_agent()
    if "workflow_update_edge_policy" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Workflow tools are unavailable."}), 400
    payload = request.get_json(silent=True) or {}
    return jsonify(
        {
            "result": agent._tools["workflow_update_edge_policy"](
                workflow_id,
                payload.get("node_id", ""),
                payload.get("dependency_node_id", ""),
                payload.get("policy", ""),
            )
        }
    )


@app.route("/workflows/<workflow_id>/rewire", methods=["POST"])
@_require_auth
def workflow_rewire_dependency(workflow_id: str):
    agent = _get_agent()
    if "workflow_rewire_dependency" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Workflow tools are unavailable."}), 400
    payload = request.get_json(silent=True) or {}
    return jsonify(
        {
            "result": agent._tools["workflow_rewire_dependency"](
                workflow_id,
                payload.get("node_id", ""),
                payload.get("dependency_node_id", ""),
                payload.get("action", ""),
                payload.get("policy", "block"),
            )
        }
    )


@app.route("/subagents/<run_id>", methods=["GET"])
@_require_auth
def subagent_result(run_id: str):
    agent = _get_agent()
    if "subagent_result" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Sub-agent tools are unavailable."}), 400
    return jsonify(
        {
            "status": agent._tools["subagent_status"](run_id),
            "result": agent._tools["subagent_result"](run_id),
        }
    )


@app.route("/subagents/<run_id>/resume", methods=["POST"])
@_require_auth
def resume_subagent(run_id: str):
    agent = _get_agent()
    if "resume_subagent" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Sub-agent tools are unavailable."}), 400
    payload = request.get_json(silent=True) or {}
    return jsonify(
        {
            "result": agent._tools["resume_subagent"](
                run_id,
                payload.get("async_mode", True),
                payload.get("task_subject", ""),
            )
        }
    )


@app.route("/subagents/<run_id>/cancel", methods=["POST"])
@_require_auth
def cancel_subagent(run_id: str):
    agent = _get_agent()
    if "cancel_subagent" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Sub-agent tools are unavailable."}), 400
    return jsonify({"result": agent._tools["cancel_subagent"](run_id)})


@app.route("/subagents/<run_id>/progress", methods=["GET"])
@_require_auth
def subagent_progress(run_id: str):
    agent = _get_agent()
    if "subagent_progress" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Sub-agent tools are unavailable."}), 400
    return jsonify({"progress": agent._tools["subagent_progress"](run_id)})


@app.route("/subagents/<run_id>/events", methods=["GET"])
@_require_auth
def subagent_events(run_id: str):
    agent = _get_agent()
    if "subagent_progress" not in getattr(agent, "_tools", {}):
        return jsonify({"error": "Sub-agent tools are unavailable."}), 400

    from .agent.subagents import _get_manager

    manager = _get_manager()
    watcher = manager.subscribe(run_id)

    @stream_with_context
    def generate():
        try:
            while True:
                try:
                    event = watcher.get(timeout=15)
                    payload = json.dumps({"run_id": run_id, **event})
                    yield f"event: progress\ndata: {payload}\n\n"
                    run = manager.get(run_id)
                    if run and run.status in {"completed", "failed", "interrupted", "cancelled"} and run.events and run.events[-1] == event:
                        final_payload = json.dumps({"run_id": run_id, "status": run.status, "aggregate_status": run.aggregate_status})
                        yield f"event: done\ndata: {final_payload}\n\n"
                        break
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    run = manager.get(run_id)
                    if run and run.status in {"completed", "failed", "interrupted", "cancelled"}:
                        final_payload = json.dumps({"run_id": run_id, "status": run.status, "aggregate_status": run.aggregate_status})
                        yield f"event: done\ndata: {final_payload}\n\n"
                        break
        finally:
            manager.unsubscribe(run_id, watcher)

    import queue
    return Response(generate(), mimetype="text/event-stream")


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
