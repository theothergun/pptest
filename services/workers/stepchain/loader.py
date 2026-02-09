from __future__ import annotations

import sys
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Dict, List, Any

from loguru import logger


@dataclass
class ScriptInfo:
	"""Holds one loaded script module + resolved entry function."""
	name: str
	path: Path
	function: Callable
	last_modified: float
	module_name: str


class ScriptLoader:
	"""
	Loads python scripts from a directory, resolves an entry function, and supports hot reload.

	Behavior:
	- Discovers all *.py under scripts_dir (excluding anything starting with "_" in any path segment).
	- Loads scripts into uniquely named modules to avoid stale state.
	- Resolves a callable entry function by common naming conventions.
	- Optionally preloads all scripts on initialization.

	Entry function resolution (first match wins):
	1) chain
	2) main
	3) <basename>
	4) <basename>_chain
	5) <flattened_path>
	6) <flattened_path>_chain

	Examples:
	- scripts/cleanup.py              -> cleanup(), cleanup_chain(), chain(), main()
	- scripts/tools/cleanup.py        -> cleanup(), cleanup_chain(), tools_cleanup(), tools_cleanup_chain(), chain(), main()
	"""

	def __init__(self, scripts_dir: str | Path = "scripts", preload: bool = True):
		self.scripts_dir = Path(scripts_dir)
		self.scripts: Dict[str, ScriptInfo] = {}
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

		mtime = script_path.stat().st_mtime

		# Reload check
		if not force and script_name in self.scripts:
			info = self.scripts[script_name]
			if mtime <= info.last_modified:
				return info.function

		try:
			module_name = self._make_module_name(script_name, mtime)

			# Clean previous module (important for long sessions)
			old = self.scripts.get(script_name)
			if old and old.module_name in sys.modules:
				del sys.modules[old.module_name]

			spec = importlib.util.spec_from_file_location(module_name, script_path)
			if spec is None or spec.loader is None:
				raise ImportError("Failed creating import spec for %s" % str(script_path))

			module = importlib.util.module_from_spec(spec)
			spec.loader.exec_module(module)

			func = self._resolve_chain_func(module, script_name)
			if not func:
				msg = "No chain function in %s" % script_name
				self._log.error(msg)
				if raise_on_error:
					raise AttributeError(msg)
				return None

			self.scripts[script_name] = ScriptInfo(
				name=script_name,
				path=script_path,
				function=func,
				last_modified=mtime,
				module_name=module_name,
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

	def _make_module_name(self, script_name: str, mtime: float) -> str:
		flat = script_name.replace("\\", "/").strip("/")
		flat = flat.replace("/", "_").replace("-", "_").replace(".", "_")
		# int(mtime) is seconds; include fractional part for fewer collisions
		mtime_tag = ("%0.6f" % float(mtime)).replace(".", "_")
		return "stepchain_%s_%s" % (flat, mtime_tag)

	def _resolve_chain_func(self, module: Any, script_name: str) -> Optional[Callable]:
		base = script_name.replace("\\", "/").strip("/").split("/")[-1]
		flat = script_name.replace("\\", "/").strip("/").replace("/", "_")

		candidates = [
			"chain",
			"main",
			base,
			base + "_chain",
			flat,
			flat + "_chain",
		]

		for name in candidates:
			if hasattr(module, name):
				fn = getattr(module, name)
				if callable(fn):
					self._log.trace("Resolved entry for {}: {}", script_name, name)
					return fn

		self._log.error(
			"No chain function in {}. Expected one of: {}",
			script_name,
			candidates,
		)
		return None

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
