import os
import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

class SkillRegistry:
    def __init__(self, skills_dir: str | None = None):
        if skills_dir is None:
            # Resolve to root skills/ directory
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.skills_dir = os.path.join(base_dir, "skills")
        else:
            self.skills_dir = skills_dir
        self._skills: dict[str, dict[str, Any]] = {}
        self._built = False

    def reset(self) -> "SkillRegistry":
        """Clear discovered skills and allow discovery to run again."""
        self._skills.clear()
        self._built = False
        return self

    def discover(self) -> "SkillRegistry":
        """Discovers all skills in the subdirectories of the skills folder."""
        if self._built:
            return self

        if not os.path.exists(self.skills_dir):
            logger.warning("Skills directory %s does not exist", self.skills_dir)
            self._built = True
            return self

        try:
            for entry in sorted(os.listdir(self.skills_dir)):
                entry_path = os.path.join(self.skills_dir, entry)
                if not os.path.isdir(entry_path) or entry.startswith(".") or entry.startswith("_"):
                    continue

                # Look for the markdown file in skills/{entry}/{entry}.md or skills/{entry}/instructions.md
                md_filename = f"{entry}.md"
                md_path = os.path.join(entry_path, md_filename)
                if not os.path.exists(md_path):
                    md_path = os.path.join(entry_path, "instructions.md")

                if not os.path.exists(md_path):
                    # Check if there is any md file at all
                    md_files = [f for f in os.listdir(entry_path) if f.endswith(".md")]
                    if md_files:
                        md_path = os.path.join(entry_path, md_files[0])
                    else:
                        logger.warning("Skill folder %s has no markdown instruction file", entry)
                        continue

                title = entry.replace("-", " ").title()
                content = ""
                try:
                    with open(md_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    # Try to parse title from first heading
                    match = re.match(r"^#+\s+(.+)$", content.splitlines()[0]) if content else None
                    if match:
                        title = match.group(1).strip()
                except Exception as e:
                    logger.warning("Failed to read markdown for skill %s: %s", entry, e)

                self._skills[entry] = {
                    "name": entry,
                    "title": title,
                    "content": content,
                    "path": md_path,
                }
        except Exception as e:
            logger.exception("Failed to scan skills directory: %s", e)

        self._built = True
        return self

    def list_skills(self) -> list[dict[str, str]]:
        """Returns a list of all discovered skills with basic metadata."""
        if not self._built:
            self.discover()
        return [
            {"name": s["name"], "title": s["title"]}
            for s in self._skills.values()
        ]

    def get_skill(self, name: str) -> dict[str, Any] | None:
        """Returns the full data of a specific skill."""
        if not self._built:
            self.discover()
        safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).lower()
        return self._skills.get(safe_name)

    def generate_index_md(self) -> None:
        """Auto-generates the INDEX.md file under the skills/ directory."""
        if not self._built:
            self.discover()
        
        lines = [
            "# Kairos Skills Index",
            "",
            "This is the catalog of skill specifications and guides for the agent.",
            "",
            "Available skills:"
        ]
        
        for skill in self._skills.values():
            # Extract first sentence or brief description if possible
            desc = ""
            for line in skill["content"].splitlines():
                clean = line.strip()
                if clean and not clean.startswith("#"):
                    # Use first non-empty heading or paragraph as a brief description
                    desc = clean[:120] + "..." if len(clean) > 120 else clean
                    break
            lines.append(f"- **{skill['name']}**: {desc or 'Guide and standards for ' + skill['title']}.")
        
        lines.append("")
        index_path = os.path.join(self.skills_dir, "INDEX.md")
        try:
            with open(index_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            logger.debug("Auto-generated INDEX.md at %s", index_path)
        except Exception as e:
            logger.error("Failed to generate INDEX.md: %s", e)

    def discover_tools(self) -> dict[str, tuple[Any, dict[str, Any]]]:
        """Discovers and imports python tools (tool.py) inside each skill directory.
        Returns a dictionary mapping tool_name -> (run_function, definition_dict).
        """
        import importlib.util
        tools = {}
        if not os.path.exists(self.skills_dir):
            return tools

        try:
            for entry in sorted(os.listdir(self.skills_dir)):
                entry_path = os.path.join(self.skills_dir, entry)
                if not os.path.isdir(entry_path) or entry.startswith(".") or entry.startswith("_"):
                    continue
                tool_py = os.path.join(entry_path, "tool.py")
                if os.path.exists(tool_py):
                    try:
                        spec = importlib.util.spec_from_file_location(f"skills_{entry}_tool", tool_py)
                        if spec and spec.loader:
                            mod = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(mod)
                            if hasattr(mod, 'DEFINITION') and hasattr(mod, 'run'):
                                tool_name = mod.DEFINITION['function']['name']
                                tools[tool_name] = (mod.run, mod.DEFINITION)
                                logger.debug("Discovered skill tool: %s from %s", tool_name, entry)
                    except Exception as e:
                        logger.warning("Skill tool %s: error loading (%s), ignored", entry, e)
        except Exception as e:
            logger.warning("Error scanning skills folder for tools: %s", e)

        return tools

