import pytest

from byom import toolfilter


def tool(name, desc=""):
    return {"type": "function", "function": {"name": name, "description": desc}}


@pytest.fixture
def cfg():
    return {**toolfilter.DEFAULTS, "max_tools": 5}


def names(tools):
    return [t["function"]["name"] for t in tools]


def test_under_limit_untouched(cfg):
    tools = [tool("view"), tool("pmx-list_projects")]
    kept, dropped = toolfilter.filter_tools(tools, [], cfg)
    assert kept is tools and dropped == []


def test_core_tools_survive_and_relevance_ranks_mcp(cfg):
    tools = [tool("view"), tool("edit"), tool("byom-byom_use")]
    tools += [tool(f"srv-noise_{i}", "unrelated") for i in range(5)]
    tools += [tool("pmx-list_projects", "list projects")]
    msgs = [{"role": "user", "content": "please list my projects"}]
    kept, dropped = toolfilter.filter_tools(tools, msgs, cfg)
    assert len(kept) == 5 and len(dropped) == 4
    assert {"view", "edit", "byom-byom_use", "pmx-list_projects"} <= set(names(kept))


def test_tools_used_in_history_are_kept(cfg):
    tools = [tool("view")] + [tool(f"srv-t{i}") for i in range(8)]
    msgs = [{"role": "assistant", "tool_calls": [{"function": {"name": "srv-t7"}}]}]
    kept, _ = toolfilter.filter_tools(tools, msgs, cfg)
    assert "srv-t7" in names(kept)


def test_deny_patterns(cfg):
    cfg = {**cfg, "deny": ["msxi-*"]}
    kept, dropped = toolfilter.filter_tools([tool("view"), tool("msxi-load")], [], cfg)
    assert names(kept) == ["view"] and dropped == ["msxi-load"]
