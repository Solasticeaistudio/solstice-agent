import sys
import time
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class StaticProvider:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0
        self.received = []

    def chat(self, messages, tools=None, temperature=0.7, max_tokens=4096):
        self.received.append({"messages": messages, "tools": tools})
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[index]

    def name(self):
        return "static"

    def supports_tools(self):
        return True


class FlakyProvider(StaticProvider):
    def __init__(self, failures_before_success, success_text):
        super().__init__([])
        self.failures_before_success = failures_before_success
        self.success_text = success_text

    def chat(self, messages, tools=None, temperature=0.7, max_tokens=4096):
        self.received.append({"messages": messages, "tools": tools})
        if self.calls < self.failures_before_success:
            self.calls += 1
            raise RuntimeError("provider boom")
        self.calls += 1
        from solstice_agent.agent.providers.base import LLMResponse

        return LLMResponse(text=self.success_text)


class DummyChannel:
    def __init__(self):
        self.sent = []

    def is_configured(self):
        return True

    def send_message(self, recipient_id, text, metadata=None):
        self.sent.append((recipient_id, text, metadata or {}))
        return {"success": True}


@pytest.fixture(autouse=True)
def isolated_subagent_manager(tmp_path):
    from solstice_agent.agent.subagents import init_subagent_manager

    init_subagent_manager(root=str(tmp_path / "subagents"))
    yield


def test_read_file_context_returns_line_offset(tmp_path):
    from solstice_agent.tools.file_ops import read_file_context
    from solstice_agent.tools.security import set_workspace_root

    sample = tmp_path / "sample.py"
    sample.write_text(
        "one\n"
        "two\n"
        "needle start\n"
        "needle middle\n"
        "three\n"
        "four\n",
        encoding="utf-8",
    )
    set_workspace_root(str(tmp_path))
    try:
        result = read_file_context(str(sample), "needle start\nneedle middle", context_lines=1)
        assert "starting at line 2" in result
        assert "   2 | two" in result
        assert "   3 | needle start" in result
    finally:
        set_workspace_root(None)


def test_task_board_persists_updates(tmp_path):
    from solstice_agent.agent.tasks import TaskBoard

    board = TaskBoard(root=str(tmp_path))
    created = board.upsert(subject="Audit repo", status="pending")
    board.upsert(
        subject="Audit repo",
        status="in_progress",
        task_id=created.id,
        details="Reading the core modules",
        blocked_by=["t-prereq"],
    )

    reloaded = TaskBoard(root=str(tmp_path))
    task = reloaded.get(created.id)
    assert task is not None
    assert task.status == "in_progress"
    assert task.details == "Reading the core modules"
    assert task.blocked_by == ["t-prereq"]


def test_subagent_manager_persists_completed_runs(tmp_path):
    from solstice_agent.agent.subagents import SubagentManager

    root = tmp_path / "subagents-store"
    manager = SubagentManager(root=str(root))
    run = manager.create(
        prompt="persist this",
        tools=["echo"],
        execution_config={"prompt": "persist this", "tools": ["echo"]},
    )
    manager.append_progress(run.run_id, "Started")
    manager.update(
        run.run_id,
        status="completed",
        result="done",
        finished_at="2026-03-31T00:00:00+00:00",
        details="Completed",
    )

    reloaded = SubagentManager(root=str(root))
    restored = reloaded.get(run.run_id)
    assert restored is not None
    assert restored.status == "completed"
    assert restored.result == "done"
    assert restored.progress[-1] == "Started"
    assert restored.execution_config["tools"] == ["echo"]


def test_subagent_manager_marks_stale_runs_interrupted(tmp_path):
    from solstice_agent.agent.subagents import SubagentManager

    root = tmp_path / "subagents-store"
    manager = SubagentManager(root=str(root))
    run = manager.create(
        prompt="long running",
        tools=["echo"],
        execution_config={"prompt": "long running", "tools": ["echo"]},
    )
    manager.update(run.run_id, status="running", details="Still going")
    manager.append_progress(run.run_id, "Still going")

    reloaded = SubagentManager(root=str(root))
    restored = reloaded.get(run.run_id)
    assert restored is not None
    assert restored.status == "interrupted"
    assert "restarted" in restored.error.lower()
    assert restored.finished_at
    assert restored.progress[-1] == "Interrupted by restart"


def test_subagent_manager_prunes_old_terminal_runs(tmp_path):
    from solstice_agent.agent.subagents import SubagentManager

    manager = SubagentManager(root=str(tmp_path / "subagents-store"), max_runs=2)
    for index in range(4):
        run = manager.create(
            prompt=f"run {index}",
            execution_config={"prompt": f"run {index}"},
        )
        manager.update(run.run_id, status="completed", result=f"done {index}")

    runs = manager.list()
    assert len(runs) == 2
    assert [run.prompt for run in runs] == ["run 3", "run 2"]


def test_skill_loader_parses_extended_frontmatter(tmp_path):
    from solstice_agent.agent.skills import SkillLoader

    skill_dir = tmp_path / "skills" / "deploy"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\n"
        "name: deploy-flow\n"
        "description: Ship the app safely\n"
        "tools: [read_file, run_command]\n"
        "allowed-tools: [run_command]\n"
        "when-to-use: deploying or releasing\n"
        "paths: [services/api, services/web]\n"
        "argument-hint: <environment>\n"
        "arguments: [environment]\n"
        "context: fork\n"
        "---\n"
        "Check the deploy checklist.\n",
        encoding="utf-8",
    )

    loader = SkillLoader(extra_dirs=[str(tmp_path / "skills")])
    skill = loader.get_skill("deploy-flow")
    assert skill is not None
    assert skill.allowed_tools == ["run_command"]
    assert skill.paths == ["services/api", "services/web"]
    assert skill.argument_names == ["environment"]
    assert skill.execution_context == "fork"
    assert loader.skills_for_path("services/api/app.py")[0].name == "deploy-flow"


def test_registry_registers_subagent_and_tasks():
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.tools.registry import ToolRegistry

    provider = StaticProvider([LLMResponse(text="done")])
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.load_builtins(enable_terminal=False, enable_web=False, enable_browser=False, enable_voice=False)
    registry.apply(agent)

    tools = set(agent.list_tool_names())
    assert "run_subagent" in tools
    assert "resume_subagent" in tools
    assert "cancel_subagent" in tools
    assert "workflow_list" in tools
    assert "workflow_status" in tools
    assert "subagent_status" in tools
    assert "subagent_result" in tools
    assert "task_upsert" in tools
    assert "task_list" in tools


def test_subagent_runs_with_filtered_toolset():
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.tools.registry import ToolRegistry

    provider = StaticProvider([LLMResponse(text="child answer")])
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.register("echo", lambda text="": text or "ok", {
        "name": "echo",
        "description": "Echo text",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
    })
    registry.apply(agent)

    result = agent._tools["run_subagent"](
        prompt="do the thing",
        tools=["echo"],
        extra_instructions="Be brief",
        async_mode=False,
    )
    assert "child answer" in result
    assert "echo" in result


def test_subagent_async_status_and_result():
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.tools.registry import ToolRegistry

    provider = StaticProvider([LLMResponse(text="async child")])
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.register("echo", lambda text="": text or "ok", {
        "name": "echo",
        "description": "Echo text",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
    })
    registry.apply(agent)

    started = agent._tools["run_subagent"](prompt="async work", tools=["echo"], async_mode=True)
    run_id = started.split("Run ID: ", 1)[1].splitlines()[0].strip()
    status = agent._tools["subagent_status"](run_id)
    assert run_id in status

    for _ in range(50):
        result = agent._tools["subagent_result"](run_id)
        if "async child" in result:
            break
        time.sleep(0.02)
    else:
        raise AssertionError("Sub-agent result did not complete in time")
    progress = agent._tools["subagent_progress"](run_id)
    assert "Request started" in progress or "Child agent running" in progress
    assert "Request completed" in progress or "Completed" in progress


def test_resume_subagent_reuses_saved_execution_config():
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.agent.subagents import _get_manager
    from solstice_agent.tools.registry import ToolRegistry

    provider = StaticProvider([LLMResponse(text="resumed child")])
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.register("echo", lambda text="": text or "ok", {
        "name": "echo",
        "description": "Echo text",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
    })
    registry.apply(agent)

    manager = _get_manager()
    original = manager.create(
        prompt="resume me",
        tools=["echo"],
        details="saved config",
        execution_config={
            "prompt": "resume me",
            "tools": ["echo"],
            "extra_instructions": "saved config",
            "include_parent_history": False,
            "allowed_command_prefixes": [],
            "denied_command_prefixes": [],
            "workspace_root": "",
            "workspace_required": None,
            "model_override": "",
            "max_tool_iterations": None,
            "task_subject": "",
        },
    )
    manager.update(original.run_id, status="interrupted", error="Process restarted before the sub-agent finished.")

    result = agent._tools["resume_subagent"](original.run_id, False, "")
    assert "resumed child" in result

    runs = manager.list()
    resumed = next(run for run in runs if run.parent_run_id == original.run_id)
    assert resumed.parent_run_id == original.run_id
    assert resumed.resume_count == 1
    assert resumed.tools == ["echo"]


def test_subagent_graph_tracks_parent_and_dependencies():
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.tools.registry import ToolRegistry

    provider = StaticProvider([LLMResponse(text="child one"), LLMResponse(text="child two")])
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.register("echo", lambda text="": text or "ok", {
        "name": "echo",
        "description": "Echo text",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
    })
    registry.apply(agent)

    parent_started = agent._tools["run_subagent"](prompt="parent", tools=["echo"], async_mode=True)
    parent_run_id = parent_started.split("Run ID: ", 1)[1].splitlines()[0].strip()
    child_started = agent._tools["run_subagent"](
        prompt="child",
        tools=["echo"],
        async_mode=False,
        spawned_by_run_id=parent_run_id,
        depends_on_run_ids=[parent_run_id],
    )
    assert "child two" in child_started

    graph = agent._tools["subagent_graph"](parent_run_id)
    assert parent_run_id in graph
    assert "children=" in graph or "aggregate=" in graph
    assert "Scheduler:" in graph
    status = agent._tools["subagent_status"](parent_run_id)
    assert "Children:" in status


def test_subagent_dependencies_block_until_ready():
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.agent.subagents import _get_manager
    from solstice_agent.tools.registry import ToolRegistry

    provider = StaticProvider([LLMResponse(text="dep child")])
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.register("echo", lambda text="": text or "ok", {
        "name": "echo",
        "description": "Echo text",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
    })
    registry.apply(agent)

    manager = _get_manager()
    dependency = manager.create(
        prompt="dependency",
        execution_config={"prompt": "dependency"},
    )
    started = agent._tools["run_subagent"](
        prompt="blocked child",
        tools=["echo"],
        async_mode=True,
        depends_on_run_ids=[dependency.run_id],
    )
    run_id = started.split("Run ID: ", 1)[1].splitlines()[0].strip()

    for _ in range(20):
        progress = agent._tools["subagent_progress"](run_id)
        if "Waiting on dependencies" in progress:
            break
        time.sleep(0.02)
    else:
        raise AssertionError("Dependent run did not report blocked state")

    manager.update(dependency.run_id, status="completed", result="done")
    for _ in range(50):
        result = agent._tools["subagent_result"](run_id)
        if "dep child" in result:
            break
        time.sleep(0.02)
    else:
        raise AssertionError("Dependent run did not complete after dependency resolved")


def test_dependency_ignore_failure_allows_downstream_run():
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.agent.subagents import _get_manager
    from solstice_agent.tools.registry import ToolRegistry

    provider = StaticProvider([LLMResponse(text="downstream child")])
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.register("echo", lambda text="": text or "ok", {
        "name": "echo",
        "description": "Echo text",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
    })
    registry.apply(agent)

    manager = _get_manager()
    dependency = manager.create(
        prompt="dependency",
        execution_config={"prompt": "dependency"},
    )
    manager.update(dependency.run_id, status="failed", error="boom")

    started = agent._tools["run_subagent"](
        prompt="downstream",
        tools=["echo"],
        async_mode=True,
        depends_on_run_ids=[dependency.run_id],
        dependency_policies_json=f'{{"{dependency.run_id}":"ignore_failure"}}',
    )
    run_id = started.split("Run ID: ", 1)[1].splitlines()[0].strip()

    for _ in range(50):
        result = agent._tools["subagent_result"](run_id)
        if "downstream child" in result:
            break
        time.sleep(0.02)
    else:
        raise AssertionError("Ignored dependency failure still blocked downstream run")

    status = agent._tools["subagent_status"](run_id)
    assert "Dependency policies:" in status


def test_submit_workflow_creates_dag_runs():
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.tools.registry import ToolRegistry

    provider = StaticProvider([LLMResponse(text="first"), LLMResponse(text="second")])
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.register("echo", lambda text="": text or "ok", {
        "name": "echo",
        "description": "Echo text",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
    })
    registry.apply(agent)

    workflow_json = (
        '{"nodes": ['
        '{"id": "root", "prompt": "root prompt", "tools": ["echo"], "priority": 1},'
        '{"id": "child", "prompt": "child prompt", "tools": ["echo"], "depends_on": ["root"]}'
        ']}'
    )
    response = agent._tools["submit_workflow"](workflow_json, "demo-flow")
    assert "Workflow submitted." in response
    assert "root -> sa-" in response
    assert "child -> sa-" in response

    graph = agent._tools["subagent_graph"]("")
    assert "workflow=" in graph


def test_workflow_list_status_cancel_and_resume():
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.agent.subagents import _get_manager
    from solstice_agent.tools.registry import ToolRegistry

    provider = StaticProvider([LLMResponse(text="first"), LLMResponse(text="resumed")])
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.register("echo", lambda text="": text or "ok", {
        "name": "echo",
        "description": "Echo text",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
    })
    registry.apply(agent)

    workflow_json = '{"nodes": [{"id": "a", "prompt": "node a", "tools": ["echo"]}]}'
    response = agent._tools["submit_workflow"](workflow_json, "ops-flow")
    workflow_id = response.split("(", 1)[1].split(")", 1)[0]
    run_id = response.split("->", 1)[1].strip()

    workflow_list = agent._tools["workflow_list"]()
    assert workflow_id in workflow_list
    assert "ops-flow" in workflow_list

    status = agent._tools["workflow_status"](workflow_id)
    assert workflow_id in status
    assert "Nodes:" in status

    cancel_message = agent._tools["workflow_cancel"](workflow_id)
    assert workflow_id in cancel_message

    manager = _get_manager()
    run = manager.get(run_id)
    assert run is not None
    manager.update(run.run_id, status="interrupted", error="restart")

    resume_message = agent._tools["workflow_resume"](workflow_id)
    assert workflow_id in resume_message

    workflow = manager.get_workflow(workflow_id)
    assert workflow is not None
    assert workflow.node_run_ids["a"] != run_id
    updated_status = agent._tools["workflow_status"](workflow_id)
    assert workflow.node_run_ids["a"] in updated_status


def test_workflow_mutation_add_node_update_policy_set_priority_and_retry():
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.agent.subagents import _get_manager
    from solstice_agent.tools.registry import ToolRegistry

    provider = StaticProvider([LLMResponse(text="root done"), LLMResponse(text="child done"), LLMResponse(text="child retried")])
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.register("echo", lambda text="": text or "ok", {
        "name": "echo",
        "description": "Echo text",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
    })
    registry.apply(agent)

    submit = agent._tools["submit_workflow"](
        '{"nodes":[{"id":"root","prompt":"root prompt","tools":["echo"]}]}',
        "mut-flow",
    )
    workflow_id = submit.split("(", 1)[1].split(")", 1)[0]

    added = agent._tools["workflow_add_node"](
        workflow_id,
        "child",
        "child prompt",
        ["root"],
        '{"root":"block"}',
        ["echo"],
        "",
        False,
        True,
        None,
        None,
        None,
        None,
        "",
        None,
        "",
        3,
        "never",
        0,
    )
    assert "Workflow node added." in added
    child_run_id = added.split("Run ID: ", 1)[1].strip()

    priority_message = agent._tools["workflow_set_priority"](workflow_id, "child", 7)
    assert "priority set to 7" in priority_message

    edge_message = agent._tools["workflow_update_edge_policy"](workflow_id, "child", "root", "ignore_failure")
    assert "ignore_failure" in edge_message

    manager = _get_manager()
    child_run = manager.get(child_run_id)
    assert child_run is not None
    assert child_run.priority == 7
    assert "ignore_failure" in child_run.dependency_policies.values()

    manager.update(child_run.run_id, status="failed", error="boom")
    retry_message = agent._tools["workflow_retry_node"](workflow_id, "child")
    assert "Workflow node retried." in retry_message

    workflow = manager.get_workflow(workflow_id)
    assert workflow is not None
    assert workflow.node_run_ids["child"] != child_run_id


def test_workflow_disable_remove_branch_retry_and_events():
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.agent.subagents import _get_manager
    from solstice_agent.tools.registry import ToolRegistry

    provider = StaticProvider(
        [
            LLMResponse(text="root done"),
            LLMResponse(text="branch retry root"),
            LLMResponse(text="branch retry child"),
        ]
    )
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.register("echo", lambda text="": text or "ok", {
        "name": "echo",
        "description": "Echo text",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
    })
    registry.apply(agent)

    submit = agent._tools["submit_workflow"](
        (
            '{"nodes":['
            '{"id":"root","prompt":"root prompt","tools":["echo"]},'
            '{"id":"child","prompt":"child prompt","tools":["echo"],"depends_on":["root"]}'
            ']}'
        ),
        "event-flow",
    )
    workflow_id = submit.split("(", 1)[1].split(")", 1)[0]
    manager = _get_manager()
    workflow = manager.get_workflow(workflow_id)
    assert workflow is not None

    add_leaf = agent._tools["workflow_add_node"](
        workflow_id,
        "leaf",
        "leaf prompt",
        ["root"],
        '{"root":"block"}',
        ["echo"],
        "",
        False,
        True,
        None,
        None,
        None,
        None,
        "",
        None,
        "",
        0,
        "never",
        0,
    )
    assert "Workflow node added." in add_leaf

    disable_message = agent._tools["workflow_disable_node"](workflow_id, "leaf")
    assert "disabled" in disable_message.lower()

    status = agent._tools["workflow_status"](workflow_id)
    assert "Disabled nodes: leaf" in status

    remove_message = agent._tools["workflow_remove_node"](workflow_id, "leaf")
    assert "removed" in remove_message.lower()

    status = agent._tools["workflow_status"](workflow_id)
    assert "Removed nodes: leaf" in status

    root_run_id = workflow.node_run_ids["root"]
    child_run_id = workflow.node_run_ids["child"]
    manager.update(root_run_id, status="failed", error="boom")
    manager.update(child_run_id, status="failed", error="downstream boom")

    branch_retry = agent._tools["workflow_retry_branch"](workflow_id, "root")
    assert "Workflow branch retried." in branch_retry

    updated_workflow = manager.get_workflow(workflow_id)
    assert updated_workflow is not None
    assert updated_workflow.node_run_ids["root"] != root_run_id
    assert updated_workflow.node_run_ids["child"] != child_run_id

    child_run = manager.get(updated_workflow.node_run_ids["child"])
    assert child_run is not None
    assert updated_workflow.node_run_ids["root"] in child_run.dependency_run_ids

    events = agent._tools["workflow_events"](workflow_id)
    assert "workflow_submitted" in events
    assert "node_disabled" in events
    assert "node_removed" in events
    assert "branch_retried" in events


def test_workflow_enable_rewire_snapshot_and_export():
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.agent.subagents import _get_manager
    from solstice_agent.tools.registry import ToolRegistry

    provider = StaticProvider([LLMResponse(text="root done")])
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.register("echo", lambda text="": text or "ok", {
        "name": "echo",
        "description": "Echo text",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
    })
    registry.apply(agent)

    submit = agent._tools["submit_workflow"](
        (
            '{"nodes":['
            '{"id":"root","prompt":"root prompt","tools":["echo"]},'
            '{"id":"leaf","prompt":"leaf prompt","tools":["echo"]}'
            ']}'
        ),
        "export-flow",
    )
    workflow_id = submit.split("(", 1)[1].split(")", 1)[0]

    disable_message = agent._tools["workflow_disable_node"](workflow_id, "leaf")
    assert "disabled" in disable_message.lower()

    enable_message = agent._tools["workflow_enable_node"](workflow_id, "leaf")
    assert "enabled" in enable_message.lower()

    rewire_message = agent._tools["workflow_rewire_dependency"](workflow_id, "leaf", "root", "add", "block")
    assert "dependency added" in rewire_message.lower()

    manager = _get_manager()
    workflow = manager.get_workflow(workflow_id)
    assert workflow is not None
    leaf_run = manager.get(workflow.node_run_ids["leaf"])
    root_run_id = workflow.node_run_ids["root"]
    assert leaf_run is not None
    assert root_run_id in leaf_run.dependency_run_ids

    snapshot_message = agent._tools["workflow_snapshot"](workflow_id, "before-export")
    assert "Workflow snapshot created." in snapshot_message
    snapshot_id = snapshot_message.split("Snapshot ID: ", 1)[1].splitlines()[0].strip()

    exported = json.loads(agent._tools["workflow_export"](workflow_id))
    assert exported["workflow_id"] == workflow_id
    assert exported["revision"] >= 4
    assert exported["snapshots"]
    assert any(node["id"] == "leaf" for node in exported["current"]["nodes"])

    snapshot_export = json.loads(agent._tools["workflow_export"](workflow_id, snapshot_id))
    assert snapshot_export["snapshot"]["snapshot_id"] == snapshot_id


def test_cancel_subagent_marks_run_cancelled():
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.agent.subagents import _get_manager
    from solstice_agent.tools.registry import ToolRegistry

    agent = Agent(provider=StaticProvider([LLMResponse(text="unused")]))
    registry = ToolRegistry()
    registry.apply(agent)

    run = _get_manager().create(
        prompt="cancel me",
        execution_config={"prompt": "cancel me"},
    )
    message = agent._tools["cancel_subagent"](run.run_id)
    assert "cancelled" in message.lower()
    assert "was cancelled" in agent._tools["subagent_result"](run.run_id).lower()


def test_retry_policy_requeues_failed_run_until_success():
    from solstice_agent.agent.core import Agent
    from solstice_agent.tools.registry import ToolRegistry

    agent = Agent(provider=FlakyProvider(1, "recovered"))
    registry = ToolRegistry()
    registry.apply(agent)

    started = agent._tools["run_subagent"](
        prompt="retry me",
        async_mode=True,
        retry_policy="on_failure",
        max_retries=1,
    )
    run_id = started.split("Run ID: ", 1)[1].splitlines()[0].strip()

    for _ in range(100):
        result = agent._tools["subagent_result"](run_id)
        if "recovered" in result:
            break
        time.sleep(0.03)
    else:
        raise AssertionError("Retried sub-agent did not complete successfully")

    status = agent._tools["subagent_status"](run_id)
    assert "Retry policy: on_failure (1/1)" in status


def test_cancel_subagent_cascades_to_descendants():
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.subagents import _get_manager
    from solstice_agent.tools.registry import ToolRegistry

    agent = Agent(provider=StaticProvider([]))
    registry = ToolRegistry()
    registry.apply(agent)

    manager = _get_manager()
    parent = manager.create(prompt="parent", execution_config={"prompt": "parent"})
    child = manager.create(
        prompt="child",
        execution_config={"prompt": "child"},
        spawned_by_run_id=parent.run_id,
    )

    message = agent._tools["cancel_subagent"](parent.run_id)
    assert "descendants" in message.lower()
    assert manager.get(parent.run_id).status == "cancelled"
    assert manager.get(child.run_id).status == "cancelled"


def test_command_policy_context_blocks_denied_prefix():
    from solstice_agent.tools.terminal import check_command_safety, command_policy_context

    with command_policy_context(denied_prefixes=["git push"]):
        warning = check_command_safety("git push origin main")
        assert warning is not None
        assert "git push" in warning


def test_agent_prompt_includes_task_board(tmp_path):
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.tasks import init_task_board, task_upsert

    init_task_board(root=str(tmp_path))
    task_upsert(subject="Map the repo", status="in_progress", details="Reading core modules")
    agent = Agent(provider=StaticProvider([]))
    messages = agent._build_messages("continue")
    system_prompt = messages[0]["content"]
    assert "Task Tracking" in system_prompt
    assert "Map the repo" in system_prompt


def test_subagent_workspace_isolation(tmp_path):
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.tools.registry import ToolRegistry
    from solstice_agent.tools.security import set_workspace_root

    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    allowed = root_a / "allowed.txt"
    blocked = root_b / "blocked.txt"
    allowed.write_text("allowed", encoding="utf-8")
    blocked.write_text("blocked", encoding="utf-8")

    provider = StaticProvider([LLMResponse(text="ok")])
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.load_builtins(enable_terminal=False, enable_web=False, enable_browser=False, enable_voice=False)
    registry.apply(agent)

    set_workspace_root(str(tmp_path))
    try:
        child = agent.clone_with_tools(
            tool_names=["read_file"],
            workspace_root=str(root_a),
            workspace_required=True,
        )
        ok = child._execute_tool({"name": "read_file", "arguments": {"path": str(allowed)}})
        nope = child._execute_tool({"name": "read_file", "arguments": {"path": str(blocked)}})
    finally:
        set_workspace_root(None)

    assert "allowed" in ok
    assert "outside the workspace" in nope


def test_auto_task_tracking_marks_completion(tmp_path):
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.agent.tasks import init_task_board, TaskBoard

    init_task_board(root=str(tmp_path))
    agent = Agent(provider=StaticProvider([LLMResponse(text="done")]))
    agent.auto_track_tasks = True
    response = agent.chat("Please investigate the failing test suite")

    board = TaskBoard(root=str(tmp_path))
    tasks = board.list()
    assert response == "done"
    assert tasks
    assert tasks[0].status == "completed"
    assert "Please investigate the failing test suite" in tasks[0].subject


def test_gateway_shortcuts_surface_tasks_and_subagents(tmp_path):
    from datetime import datetime
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.agent.tasks import init_task_board, task_upsert
    from solstice_agent.gateway.manager import GatewayManager
    from solstice_agent.gateway.models import GatewayMessage, ChannelType, MessageDirection
    from solstice_agent.tools.registry import ToolRegistry

    init_task_board(root=str(tmp_path))
    task_upsert(subject="Inspect gateway", status="in_progress")
    agent = Agent(provider=StaticProvider([LLMResponse(text="gateway reply")]))
    registry = ToolRegistry()
    registry.load_builtins(enable_terminal=False, enable_web=False, enable_browser=False, enable_voice=False)
    registry.apply(agent)
    manager = GatewayManager(agent=agent)

    msg = GatewayMessage(
        id="gw-1",
        channel=ChannelType.WEBCHAT,
        direction=MessageDirection.INBOUND,
        sender_id="user-1",
        text="/tasks",
        timestamp=datetime.now(),
    )
    result = manager._process_message(msg)
    assert "Inspect gateway" in result

    started = agent._tools["run_subagent"](prompt="gateway async", tools=[], async_mode=True)
    run_id = started.split("Run ID: ", 1)[1].splitlines()[0].strip()
    for _ in range(50):
        progress = manager._process_message(
            GatewayMessage(
                id="gw-2",
                channel=ChannelType.WEBCHAT,
                direction=MessageDirection.INBOUND,
                sender_id="user-1",
                text=f"/subagent-progress {run_id}",
                timestamp=datetime.now(),
            )
        )
        if "Progress for" in progress:
            break
        time.sleep(0.02)
    else:
        raise AssertionError("Gateway progress shortcut did not return progress")


def test_gateway_start_shortcut_surfaces_guided_onboarding():
    from datetime import datetime
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.gateway.manager import GatewayManager
    from solstice_agent.gateway.models import GatewayMessage, ChannelType, MessageDirection

    agent = Agent(provider=StaticProvider([LLMResponse(text="gateway reply")]))
    manager = GatewayManager(agent=agent)
    result = manager._process_message(
        GatewayMessage(
            id="gw-start",
            channel=ChannelType.WEBCHAT,
            direction=MessageDirection.INBOUND,
            sender_id="user-1",
            text="/start",
            timestamp=datetime.now(),
        )
    )

    assert "Let’s get started." in result
    assert "Help around my files" in result
    assert "Reply with a number or a word like `files`, `reminders`, or `learn`." in result


def test_gateway_start_keyword_launches_guided_prompt():
    from datetime import datetime
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.gateway.manager import GatewayManager
    from solstice_agent.gateway.models import GatewayMessage, ChannelType, MessageDirection

    provider = StaticProvider([LLMResponse(text="guided gateway reply")])
    agent = Agent(provider=provider)
    manager = GatewayManager(agent=agent)
    result = manager._process_message(
        GatewayMessage(
            id="gw-reminders",
            channel=ChannelType.WEBCHAT,
            direction=MessageDirection.INBOUND,
            sender_id="user-1",
            text="reminders",
            timestamp=datetime.now(),
        )
    )

    assert result == "guided gateway reply"
    assert provider.received
    assert provider.received[-1]["messages"][-1]["content"] == "Help me set up a daily reminder or recurring check."


def test_gateway_start_fuzzy_reply_launches_guided_prompt():
    from datetime import datetime
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.gateway.manager import GatewayManager
    from solstice_agent.gateway.models import GatewayMessage, ChannelType, MessageDirection

    provider = StaticProvider([LLMResponse(text="guided fuzzy reply")])
    agent = Agent(provider=provider)
    manager = GatewayManager(agent=agent)
    manager._process_message(
        GatewayMessage(
            id="gw-start-fuzzy-1",
            channel=ChannelType.WEBCHAT,
            direction=MessageDirection.INBOUND,
            sender_id="user-1",
            text="/start",
            timestamp=datetime.now(),
        )
    )
    result = manager._process_message(
        GatewayMessage(
            id="gw-start-fuzzy-2",
            channel=ChannelType.WEBCHAT,
            direction=MessageDirection.INBOUND,
            sender_id="user-1",
            text="can you help me with my files?",
            timestamp=datetime.now(),
        )
    )

    assert result == "guided fuzzy reply"
    assert provider.received[-1]["messages"][-1]["content"] == "Look through my workspace and explain what is here in simple terms."


def test_gateway_start_unmatched_reply_falls_back_to_normal_chat():
    from datetime import datetime
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.gateway.manager import GatewayManager
    from solstice_agent.gateway.models import GatewayMessage, ChannelType, MessageDirection

    provider = StaticProvider([LLMResponse(text="normal reply")])
    agent = Agent(provider=provider)
    manager = GatewayManager(agent=agent)
    manager._process_message(
        GatewayMessage(
            id="gw-start-normal-1",
            channel=ChannelType.WEBCHAT,
            direction=MessageDirection.INBOUND,
            sender_id="user-1",
            text="/start",
            timestamp=datetime.now(),
        )
    )
    result = manager._process_message(
        GatewayMessage(
            id="gw-start-normal-2",
            channel=ChannelType.WEBCHAT,
            direction=MessageDirection.INBOUND,
            sender_id="user-1",
            text="tell me a joke",
            timestamp=datetime.now(),
        )
    )

    assert result == "normal reply"
    assert provider.received[-1]["messages"][-1]["content"] == "tell me a joke"


def test_gateway_start_calendar_reply_maps_to_reminders_prompt():
    from datetime import datetime
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.gateway.manager import GatewayManager
    from solstice_agent.gateway.models import GatewayMessage, ChannelType, MessageDirection

    provider = StaticProvider([LLMResponse(text="calendar reply")])
    agent = Agent(provider=provider)
    manager = GatewayManager(agent=agent)
    manager._process_message(
        GatewayMessage(
            id="gw-start-calendar-1",
            channel=ChannelType.WEBCHAT,
            direction=MessageDirection.INBOUND,
            sender_id="user-1",
            text="/start",
            timestamp=datetime.now(),
        )
    )
    result = manager._process_message(
        GatewayMessage(
            id="gw-start-calendar-2",
            channel=ChannelType.WEBCHAT,
            direction=MessageDirection.INBOUND,
            sender_id="user-1",
            text="can you help with my calendar and appointments?",
            timestamp=datetime.now(),
        )
    )

    assert result == "calendar reply"
    assert provider.received[-1]["messages"][-1]["content"] == "Help me set up a daily reminder or recurring check."


def test_gateway_start_email_reply_maps_to_connect_or_organize_prompt():
    from datetime import datetime
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.gateway.manager import GatewayManager
    from solstice_agent.gateway.models import GatewayMessage, ChannelType, MessageDirection

    provider = StaticProvider([LLMResponse(text="email reply")])
    agent = Agent(provider=provider)
    manager = GatewayManager(agent=agent)
    manager._process_message(
        GatewayMessage(
            id="gw-start-email-1",
            channel=ChannelType.WEBCHAT,
            direction=MessageDirection.INBOUND,
            sender_id="user-1",
            text="/start",
            timestamp=datetime.now(),
        )
    )
    result = manager._process_message(
        GatewayMessage(
            id="gw-start-email-2",
            channel=ChannelType.WEBCHAT,
            direction=MessageDirection.INBOUND,
            sender_id="user-1",
            text="I want help connecting my email and messages",
            timestamp=datetime.now(),
        )
    )

    assert result == "email reply"
    assert provider.received[-1]["messages"][-1]["content"] == "Help me connect email or messaging apps, or get organized and suggest a useful first task."


def test_end_to_end_parent_delegation_updates_task_and_returns_result(tmp_path):
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.agent.tasks import init_task_board, TaskBoard
    from solstice_agent.tools.registry import ToolRegistry

    init_task_board(root=str(tmp_path))
    provider = StaticProvider([LLMResponse(text="delegated answer")])
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.register("echo", lambda text="": text or "ok", {
        "name": "echo",
        "description": "Echo text",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
    })
    registry.apply(agent)

    started = agent._tools["run_subagent"](
        prompt="investigate",
        tools=["echo"],
        async_mode=True,
        task_subject="Investigate delegated issue",
    )
    run_id = started.split("Run ID: ", 1)[1].splitlines()[0].strip()

    for _ in range(50):
        result = agent._tools["subagent_result"](run_id)
        if "delegated answer" in result:
            break
        time.sleep(0.02)
    else:
        raise AssertionError("Delegated sub-agent did not finish in time")

    board = TaskBoard(root=str(tmp_path))
    tasks = [task for task in board.list() if task.subject == "Investigate delegated issue"]
    assert tasks
    assert tasks[0].status == "completed"


def test_server_sse_streams_subagent_events():
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.tools.registry import ToolRegistry
    import solstice_agent.server as server

    provider = StaticProvider([LLMResponse(text="sse child")])
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.register("echo", lambda text="": text or "ok", {
        "name": "echo",
        "description": "Echo text",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
    })
    registry.apply(agent)
    old_agent = server._agent
    server._agent = agent
    try:
        started = agent._tools["run_subagent"](prompt="sse work", tools=["echo"], async_mode=True)
        run_id = started.split("Run ID: ", 1)[1].splitlines()[0].strip()
        client = server.app.test_client()
        response = client.get(f"/subagents/{run_id}/events")
        payload = b"".join(response.response)
    finally:
        server._agent = old_agent

    assert b"event: progress" in payload
    assert b"event: done" in payload
    assert b"\"type\": \"lifecycle\"" in payload or b"\"type\": \"request_started\"" in payload


def test_server_sse_streams_workflow_events():
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.tools.registry import ToolRegistry
    import solstice_agent.server as server

    provider = StaticProvider([LLMResponse(text="workflow child")])
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.register("echo", lambda text="": text or "ok", {
        "name": "echo",
        "description": "Echo text",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
    })
    registry.apply(agent)
    old_agent = server._agent
    server._agent = agent
    try:
        submit = agent._tools["submit_workflow"](
            '{"nodes": [{"id": "a", "prompt": "node a", "tools": ["echo"]}]}',
            "sse-flow",
        )
        workflow_id = submit.split("(", 1)[1].split(")", 1)[0]
        client = server.app.test_client()
        response = client.get(f"/workflows/{workflow_id}/events")
        chunks = []
        for index, chunk in enumerate(response.response):
            chunks.append(chunk)
            if index >= 1:
                break
        payload = b"".join(chunks)
    finally:
        server._agent = old_agent

    assert b"event: workflow" in payload
    assert b"workflow_submitted" in payload or b"workflow_registered" in payload


def test_gateway_follow_subagent_pushes_updates():
    from datetime import datetime
    from solstice_agent.agent.core import Agent
    from solstice_agent.agent.providers.base import LLMResponse
    from solstice_agent.gateway.manager import GatewayManager
    from solstice_agent.gateway.models import GatewayMessage, ChannelType, MessageDirection
    from solstice_agent.tools.registry import ToolRegistry

    provider = StaticProvider([LLMResponse(text="follow child")])
    agent = Agent(provider=provider)
    registry = ToolRegistry()
    registry.register("echo", lambda text="": text or "ok", {
        "name": "echo",
        "description": "Echo text",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
    })
    registry.apply(agent)
    manager = GatewayManager(agent=agent)
    channel = DummyChannel()
    manager.channels[ChannelType.WEBCHAT] = channel

    started = agent._tools["run_subagent"](prompt="follow work", tools=["echo"], async_mode=True)
    run_id = started.split("Run ID: ", 1)[1].splitlines()[0].strip()
    msg = GatewayMessage(
        id="gw-follow",
        channel=ChannelType.WEBCHAT,
        direction=MessageDirection.INBOUND,
        sender_id="user-1",
        text=f"/follow-subagent {run_id}",
        timestamp=datetime.now(),
        channel_metadata={"chat_id": "chat-1"},
    )
    result = manager._process_message(msg)
    assert "Following sub-agent" in result

    for _ in range(100):
        if any(run_id in text for _, text, _ in channel.sent):
            break
        time.sleep(0.02)
    else:
        raise AssertionError("Gateway did not push sub-agent progress")
