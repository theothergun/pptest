from __future__ import annotations

import sys
import inspect
import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Dict, List, Any

from loguru import logger


@dataclass
class AutomationProgramInfo:
	"""Holds one loaded script module + resolved entry function."""
	name: str
	path: Path
	function: Callable
	last_modified: float
	module_name: str
	metadata: dict[str, Any] = field(default_factory=dict)


class AutomationScriptLoader:
	"""
	Loads python scripts from a directory, resolves an entry function, and supports hot reload.

	Behavior:
	- Discovers all *.py under scripts_dir (excluding anything starting with "_" in any path segment).
	- Loads scripts into uniquely named modules to avoid stale state.
	- Resolves a callable `main(ctx)` entry function.
	- Optionally preloads all scripts on initialization.
	"""

	def __init__(self, scripts_dir: str | Path = "scripts", preload: bool = True):
		self.scripts_dir = Path(scripts_dir)
		self.scripts: Dict[str, AutomationProgramInfo] = {}
		self._log = logger.bind(component="ScriptLoader")

		self.scripts_dir.mkdir(parents=True, exist_ok=True)

		if preload:
			self.load_all(raise_on_error=False)

	# ------------------------------------------------------------------ discovery

	def list_available_scripts(self) -> List[str]:
		"""
		Return script names relative to scripts_dir without suffix, using POSIX separators.
		Example: scripts/tools/cleanup.py -> "tools/cleanup"
		"""
		scripts: List[str] = []

		for file in self.scripts_dir.rglob("*.py"):
			if file.name.startswith("_"):
				continue

			rel = file.relative_to(self.scripts_dir).with_suffix("")
			if any(part.startswith("_") for part in rel.parts):
				continue

			scripts.append(rel.as_posix())

		return sorted(scripts)

	# ------------------------------------------------------------------ load / reload

	def load_all(self, raise_on_error: bool = False) -> List[str]:
		"""
		Load all discoverable scripts.

		Returns list of successfully loaded script names.
		If raise_on_error is True, raises on first failure.
		"""
		loaded: List[str] = []
		for name in self.list_available_scripts():
			fn = self.load_script(name, force=True, raise_on_error=raise_on_error)
			if fn:
				loaded.append(name)

		self._log.info("Preload completed: loaded={}", len(loaded))
		return loaded

	def load_script(
		self,
		script_name: str,
		force: bool = False,
		raise_on_error: bool = False,
	) -> Optional[Callable]:
		"""
		Load or reload one script by name (relative path without .py).
		Returns the resolved callable, or None on failure (unless raise_on_error=True).
		"""
		script_path = self.scripts_dir / (script_name + ".py")

		if not script_path.exists():
			self._log.error("Script not found: {}", str(script_path))
			if raise_on_error:
				raise FileNotFoundError(str(script_path))
			return None

		stats = script_path.stat()
		mtime = stats.st_mtime
		mtime_ns = stats.st_mtime_ns

		# Reload check
		if not force and script_name in self.scripts:
			info = self.scripts[script_name]
			if mtime <= info.last_modified:
				return info.function

		try:
			module_name = self._make_module_name(script_name, mtime_ns)

			# Clean previous module (important for long sessions)
			old = self.scripts.get(script_name)
			if old and old.module_name in sys.modules:
				del sys.modules[old.module_name]

			spec = importlib.util.spec_from_file_location(module_name, script_path)
			if spec is None or spec.loader is None:
				raise ImportError("Failed creating import spec for %s" % str(script_path))

			module = importlib.util.module_from_spec(spec)
			spec.loader.exec_module(module)

			func = self._resolve_main_func(module, script_name)
			if not func:
				msg = "No valid main(ctx) entry point in %s" % script_name
				self._log.error(msg)
				if raise_on_error:
					raise AttributeError(msg)
				return None

			self.scripts[script_name] = AutomationProgramInfo(
				name=script_name,
				path=script_path,
				function=func,
				last_modified=mtime,
				module_name=module_name,
				metadata=self._resolve_metadata(module, script_name, script_path),
			)

			self._log.trace("Loaded script: {} (module={})", script_name, module_name)
			return func

		except Exception as ex:
			# Keep message + full trace
			self._log.exception("Failed loading script: {} - error={}", script_name, str(ex))
			if raise_on_error:
				raise
			return None

	# ------------------------------------------------------------------ helpers

	def _make_module_name(self, script_name: str, mtime_tag_value: float | int) -> str:
		flat = script_name.replace("\\", "/").strip("/")
		flat = flat.replace("/", "_").replace("-", "_").replace(".", "_")
		# int(mtime) is seconds; include fractional part for fewer collisions
		mtime_tag = str(mtime_tag_value).replace(".", "_")
		return "automation_runtime_%s_%s" % (flat, mtime_tag)

	def _resolve_main_func(self, module: Any, script_name: str) -> Optional[Callable]:
		fn = getattr(module, "main", None)
		if not callable(fn):
			self._log.error("No main(ctx) entry point in {}", script_name)
			return None

		try:
			signature = inspect.signature(fn)
		except (TypeError, ValueError):
			self._log.error("Unable to inspect main(ctx) signature in {}", script_name)
			return None

		params = list(signature.parameters.values())
		if not params:
			self._log.error("main(ctx) missing context parameter in {}", script_name)
			return None

		first_param = params[0]
		if first_param.kind not in (
			inspect.Parameter.POSITIONAL_ONLY,
			inspect.Parameter.POSITIONAL_OR_KEYWORD,
		):
			self._log.error("main(ctx) must accept ctx as first positional parameter in {}", script_name)
			return None

		required_positionals = [
			param for param in params
			if param.kind in (
				inspect.Parameter.POSITIONAL_ONLY,
				inspect.Parameter.POSITIONAL_OR_KEYWORD,
			)
			and param.default is inspect.Parameter.empty
		]
		if len(required_positionals) > 1:
			self._log.error("main(ctx) must not require more than one positional parameter in {}", script_name)
			return None

		self._log.trace("Resolved entry for {}: main", script_name)
		return fn

	def _resolve_metadata(self, module: Any, script_name: str, script_path: Path) -> dict[str, Any]:
		meta = getattr(module, "SCRIPT_META", None)
		if not isinstance(meta, dict):
			meta = {}
		data = dict(meta)
		data.setdefault("name", script_name)
		data.setdefault("title", script_name.split("/")[-1].replace("_", " ").title())
		data.setdefault("path", script_path.as_posix())
		data.setdefault("description", "")
		data.setdefault("buttons", [])
		return data

	def get_script_metadata(self, script_name: str, *, load_if_missing: bool = True) -> dict[str, Any]:
		info = self.scripts.get(script_name)
		if info is None and load_if_missing:
			self.load_script(script_name, force=False, raise_on_error=False)
			info = self.scripts.get(script_name)
		return dict(getattr(info, "metadata", {}) or {})

	def list_script_metadata(self) -> list[dict[str, Any]]:
		items: list[dict[str, Any]] = []
		for name in self.list_available_scripts():
			items.append(self.get_script_metadata(name))
		return items

	# ------------------------------------------------------------------ hot reload

	def check_for_updates(self) -> List[str]:
		"""
		Reloads any already-loaded script whose file mtime changed.
		Returns list of reloaded script names.
		"""
		reloaded: List[str] = []

		for name, info in list(self.scripts.items()):
			if not info.path.exists():
				self._log.warn("Script removed from disk, unloading: {}", name)
				self.unload_script(name)
				continue

			new_mtime = info.path.stat().st_mtime
			if new_mtime > info.last_modified:
				if self.load_script(name, force=True):
					reloaded.append(name)

		if reloaded:
			self._log.info("Hot reload: reloaded={}", reloaded)

		return reloaded

	def reload_all(self) -> List[str]:
		"""
		Force reload all currently loaded scripts.
		Returns list of successfully reloaded names.
		"""
		reloaded: List[str] = []
		for name in list(self.scripts.keys()):
			if self.load_script(name, force=True):
				reloaded.append(name)
		return reloaded

	def unload_script(self, script_name: str) -> None:
		"""
		Unload a script module (best-effort) and remove it from the registry.
		"""
		info = self.scripts.pop(script_name, None)
		if not info:
			return

		if info.module_name in sys.modules:
			del sys.modules[info.module_name]

		self._log.info("Unloaded script: {} (module={})", script_name, info.module_name)
