"""Jinja2-based prompt loader with version resolution and shared-boilerplate injection.

Convention: prompts live at `prompts/<agent_name>/v<N>.jinja`. The loader resolves the
latest version by default, or the requested explicit version. The shared system boilerplate
is auto-prepended unless `inject_boilerplate=False`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, Template, select_autoescape

# Project root (campaign_mgr/) is two levels up from this file.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS_DIR = _PROJECT_ROOT / "prompts"
_VERSION_RE = re.compile(r"^v(\d+)\.jinja$")


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    agent_name: str
    version: str  # "v1", "v2", ...
    text: str  # the rendered prompt with shared boilerplate prepended


class PromptLoader:
    def __init__(self, prompts_dir: Path | None = None):
        self._prompts_dir = prompts_dir or _PROMPTS_DIR
        self._env = Environment(
            loader=FileSystemLoader(self._prompts_dir),
            autoescape=select_autoescape(disabled_extensions=("jinja",), default_for_string=False),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    # ------------------------------------------------------------------ versioning

    def latest_version(self, agent_name: str) -> str:
        agent_dir = self._prompts_dir / agent_name
        if not agent_dir.is_dir():
            raise FileNotFoundError(f"Prompt directory does not exist: {agent_dir}")
        versions: list[int] = []
        for p in agent_dir.iterdir():
            m = _VERSION_RE.match(p.name)
            if m:
                versions.append(int(m.group(1)))
        if not versions:
            raise FileNotFoundError(f"No vN.jinja files found in {agent_dir}")
        return f"v{max(versions)}"

    # ------------------------------------------------------------------ rendering

    def render(
        self,
        agent_name: str,
        variables: dict | None = None,
        version: str | None = None,
        inject_boilerplate: bool = True,
    ) -> RenderedPrompt:
        version = version or self.latest_version(agent_name)
        relpath = f"{agent_name}/{version}.jinja"
        template: Template = self._env.get_template(relpath)
        body = template.render(**(variables or {}))

        if inject_boilerplate:
            boilerplate = self._env.get_template("shared/system_boilerplate.jinja").render()
            text = f"{boilerplate.strip()}\n\n---\n\n{body.strip()}"
        else:
            text = body.strip()

        return RenderedPrompt(agent_name=agent_name, version=version, text=text)


_default_loader: PromptLoader | None = None


def get_prompt_loader() -> PromptLoader:
    """Module-level singleton for convenience."""
    global _default_loader
    if _default_loader is None:
        _default_loader = PromptLoader()
    return _default_loader
