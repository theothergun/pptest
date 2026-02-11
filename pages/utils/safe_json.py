def safe_format_data(
	value: object,
	max_depth: int = 12,
	max_items: int = 500,
) -> object:
	"""
	Convert arbitrary Python objects into JSON-serializable structures (dict/list/str/num/bool/None),
	while being robust against:
	- recursive/self-referential objects (cycle detection by id)
	- very deep structures (max_depth)
	- huge containers (max_items per container)
	- non-serializable types (converted to compact repr/str)

	Returns a JSON-safe object you can pass to ui.json_editor({"content": {"json": ...}}).
	"""
	seen = set()

	def _to_json_safe(obj: object, depth: int) -> object:
		if obj is None:
			return None
		if isinstance(obj, (bool, int, float, str)):
			return obj

		obj_id = id(obj)
		if obj_id in seen:
			return "<recursion>"
		if depth >= max_depth:
			return "<max_depth>"

		# bytes-like
		if isinstance(obj, (bytes, bytearray, memoryview)):
			try:
				return bytes(obj).decode("utf-8", "replace")
			except Exception:
				return repr(obj)

		# dict-like
		if isinstance(obj, dict):
			seen.add(obj_id)
			out = {}
			i = 0
			for k, v in obj.items():
				if i >= max_items:
					out["<truncated>"] = "max_items=%s" % max_items
					break
				# JSON keys must be strings (or at least convertible)
				try:
					key_s = k if isinstance(k, str) else str(k)
				except Exception:
					key_s = "<unstringable_key>"
				out[key_s] = _to_json_safe(v, depth + 1)
				i += 1
			seen.discard(obj_id)
			return out

		# list/tuple/set
		if isinstance(obj, (list, tuple, set, frozenset)):
			seen.add(obj_id)
			out_list = []
			i = 0
			for item in obj:
				if i >= max_items:
					out_list.append("<truncated max_items=%s>" % max_items)
					break
				out_list.append(_to_json_safe(item, depth + 1))
				i += 1
			seen.discard(obj_id)
			return out_list

		# pathlib.Path
		try:
			from pathlib import Path
			if isinstance(obj, Path):
				return str(obj)
		except Exception:
			pass

		# datetime/date/time
		try:
			import datetime
			if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
				try:
					return obj.isoformat()
				except Exception:
					return str(obj)
		except Exception:
			pass

		# Enum
		try:
			import enum
			if isinstance(obj, enum.Enum):
				return str(getattr(obj, "value", obj))
		except Exception:
			pass

		# dataclasses
		try:
			import dataclasses
			if dataclasses.is_dataclass(obj):
				seen.add(obj_id)
				try:
					return _to_json_safe(dataclasses.asdict(obj), depth + 1)
				finally:
					seen.discard(obj_id)
		except Exception:
			pass

		# objects with __dict__
		try:
			d = getattr(obj, "__dict__", None)
			if isinstance(d, dict) and d:
				seen.add(obj_id)
				try:
					return {
						"__type__": obj.__class__.__name__,
						"__dict__": _to_json_safe(d, depth + 1),
					}
				finally:
					seen.discard(obj_id)
		except Exception:
			pass

		# last resort
		try:
			return str(obj)
		except Exception:
			return repr(obj)

	return _to_json_safe(value, 0)
