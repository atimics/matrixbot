import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PORTABILITY_FILES = (
    "mailbox/swarm.json",
    "mailbox/tools/git-check.sh",
    "mailbox/tools/dispatch-worker.sh",
    "mailbox/signal_watchdog.sh",
    "chatbot/integrations/telegram/arweave_store.py",
    "chatbot/integrations/telegram/codex_bridge.py",
)
DEVELOPER_HOME = re.compile(r"/Users/[^/\s\"']+")


def test_local_integrations_do_not_embed_a_developer_home() -> None:
    offenders = [
        relative_path
        for relative_path in PORTABILITY_FILES
        if DEVELOPER_HOME.search((PROJECT_ROOT / relative_path).read_text())
    ]

    assert offenders == []


def test_swarm_registry_uses_paths_relative_to_its_location() -> None:
    registry = json.loads((PROJECT_ROOT / "mailbox" / "swarm.json").read_text())
    configured_paths = [
        registry["workspace_root"],
        registry["agents"][0]["workspace"],
        *(
            path
            for path in registry["key_repos"].values()
            if not path.startswith("github.com/")
        ),
    ]

    assert all(not Path(path).is_absolute() for path in configured_paths)
