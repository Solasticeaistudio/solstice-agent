import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_memory_resume_reuses_same_session_id(tmp_path):
    from solstice_agent.agent.memory import Memory

    memory = Memory(root=str(tmp_path))
    original_session = memory.session_id
    history = [
        {"role": "user", "content": "Plan the release"},
        {"role": "assistant", "content": "Working on it."},
    ]
    memory.save_conversation(history)

    resumed = Memory(root=str(tmp_path))
    loaded = resumed.resume_conversation()

    assert resumed.session_id == original_session
    assert loaded == history

    loaded.append({"role": "user", "content": "Add the follow-up tasks"})
    resumed.save_conversation(loaded)

    sessions = list((tmp_path / "conversations").glob("s-*.json"))
    assert len(sessions) == 1


def test_memory_search_matches_notes_and_conversations(tmp_path):
    from solstice_agent.agent.memory import Memory

    memory = Memory(root=str(tmp_path))
    memory.remember("preferred_language", "Python", category="preferences", tags=["dev"])
    memory.save_conversation(
        [
            {"role": "user", "content": "Investigate the gateway workspace root issue"},
            {"role": "assistant", "content": "I will audit the gateway startup path."},
        ]
    )

    notes_result = memory.search("python", scope="notes")
    assert "preferred_language [preferences]: Python" in notes_result

    convo_result = memory.search("workspace root", scope="conversations")
    assert "gateway workspace root issue" in convo_result.lower()


def test_memory_recall_filters_by_category_and_lists_tags(tmp_path):
    from solstice_agent.agent.memory import Memory

    memory = Memory(root=str(tmp_path))
    memory.remember("preferred_editor", "Neovim", category="preferences", tags=["editor", "dev"])
    memory.remember("launch_goal", "Ship a safe local agent", category="project")

    filtered = memory.recall(category="preferences")
    assert "preferred_editor (preferences) [dev, editor]: Neovim" in filtered
    assert "launch_goal" not in filtered

    exact = memory.recall("preferred_editor")
    assert "tags=dev, editor" in exact


def test_memory_list_conversations_includes_preview(tmp_path):
    from solstice_agent.agent.memory import Memory

    memory = Memory(root=str(tmp_path))
    memory.save_conversation(
        [
            {"role": "user", "content": "Summarize the repo and tell me what to fix before launch."},
            {"role": "assistant", "content": "Starting the audit."},
        ]
    )

    listing = memory.list_conversations()
    assert "Summarize the repo and tell me what to fix before launch." in listing
