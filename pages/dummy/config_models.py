# -----------------------------
# Data models (dummy data)
# -----------------------------
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import json
from pathlib import Path
from typing import List, Any

CONFIG_FILE = Path("config/dummy_config.json")


@dataclass
class Inspection:
	id: int
	name: str
	state_field_name: str
	expected_value: str
	type_of_value: str
	is_checked: bool = False


@dataclass
class DummyTest:
	id: int
	name: str
	is_checked: bool = False
	inspections: List[Inspection] = field(default_factory=list)


@dataclass
class DummySet:
	id: int
	name: str
	dummies: List[DummyTest] = field(default_factory=list)


@dataclass
class DummySchedulerSettings:
	is_dummy_activated: bool = True

	on_machine_start: bool = False
	on_program_change: bool = False
	on_interval: bool = True
	interval_value: int = 12
	interval_unit: str = "hour"  # "Minute(s)", "Hour(s)", "Day(s)"

	is_predetermined: bool = False

	clean_enabled: bool = True
	clean_older_value: int = 1
	clean_older_unit: str = "year"  # "Day(s)", "Month(s)", "Year(s)"


TYPE_LIST = ["Bool", "Int", "Float", "String", "Range"]


def build_demo_sets() -> List[DummySet]:
	def inspections(seed: int) -> List[Inspection]:
		return [
			Inspection(id=seed * 10 + 1, name="Inspection A", state_field_name="PLC.Var.A", expected_value="1",
					   type_of_value="Int"),
			Inspection(id=seed * 10 + 2, name="Inspection B", state_field_name="PLC.Var.B", expected_value="True",
					   type_of_value="Bool"),
			Inspection(id=seed * 10 + 3, name="Inspection C", state_field_name="ltc_result", expected_value="3.14",
					   type_of_value="Float"),
			Inspection(id=seed * 10 + 3, name="Inspection C", state_field_name="PLC.Var.D", expected_value="]0,1]",
					   type_of_value="Range"),
		]

	return [
		DummySet(
			id=1,
			name="Set 1",
			dummies=[
				DummyTest(id=1, name="Dummy 001", inspections=inspections(1)),
				DummyTest(id=2, name="Dummy 002", inspections=inspections(2)),
				DummyTest(id=3, name="Dummy 003", inspections=inspections(3)),
			],
		),
		DummySet(
			id=2,
			name="Set 2",
			dummies=[
				DummyTest(id=4, name="Dummy A", inspections=inspections(4)),
				DummyTest(id=5, name="Dummy B", inspections=inspections(5)),
			],
		),
	]


# -----------------------------
# View / State
# -----------------------------

def _deserialize_sets(data) -> List[DummySet]:
	# data is list[dict]
	sets: List[DummySet] = []
	for s in data:
		dummies: List[DummyTest] = []
		for d in s["dummies"]:
			inspections = [Inspection(**i) for i in d["inspections"]]
			dummies.append(DummyTest(id=d["id"], name=d["name"], is_checked=d.get("is_checked", False),
									 inspections=inspections))
		sets.append(DummySet(id=s["id"], name=s["name"], dummies=dummies))
	return sets


def _get_previous_selected(previous_selected_id: int, data:list):
	data = data or []
	return next((elem for elem in data if elem.id == previous_selected_id),
						data[0] if data else None)


def sets_to_dict(sets: List["DummySet"]) -> list[dict]:
	return [
		{
			"id": s.id,
			"name": s.name,
			"dummies": [
				{
					"id": d.id,
					"name": d.name,
					"inspections": [
						{
							"id": i.id,
							"name": i.name,
							"state_field_name": i.state_field_name,
							"expected_value": i.expected_value,
							"type_of_value": i.type_of_value,
						}
						for i in (d.inspections or [])
					],
				}
				for d in (s.dummies or [])
			],
		}
		for s in sets
	]


def dict_to_sets(data: Any) -> List["DummySet"]:
	# supports either {"sets":[...]} or just [...]
	sets_data = data["sets"] if isinstance(data, dict) and "sets" in data else data
	if not isinstance(sets_data, list):
		raise ValueError("Invalid format: expected list of sets or {sets:[...]}")

	sets: List[DummySet] = []
	for s in sets_data:
		dummies: List[DummyTest] = []
		for d in s.get("dummies", []):
			inspections = [Inspection(**i) for i in d.get("inspections", [])]
			dummies.append(DummyTest(id=d["id"], name=d["name"], inspections=inspections))
		sets.append(DummySet(id=s["id"], name=s["name"], dummies=dummies))
	return sets


def save_config_file(state: DummyEditionState, path: Path = CONFIG_FILE) -> None:
	payload = get_state_payload(state)
	path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

def get_state_payload(state: DummyEditionState) -> dict:
	return {"version": 1, "sets": sets_to_dict(state.sets), "scheduler": asdict(state.scheduler)}


def load_config_file(state) -> None:
	if not CONFIG_FILE.exists():
		return
	data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
	#sets
	state.sets =dict_to_sets(data)
	state.selected_set = state.sets[0] if state.sets else None
	state.selected_dummy_id = None
	state.selected_inspection_id = None

	# scheduler (optional)
	sched = data.get("scheduler")
	if isinstance(sched, dict):
		# only set known fields (safe if file is older/newer)
		for k, v in sched.items():
			if hasattr(state.scheduler, k):
				setattr(state.scheduler, k, v)

class DummyEditionState:
	def __init__(self) -> None:
		self.scheduler = DummySchedulerSettings()
		self.sets = []
		self.selected_set = self.sets[0] if self.sets else None
		self.selected_dummy_id = None
		self.selected_inspection_id = None
		self.service_enabled = True

		self._baseline_json = self._serialize_state()
		self._dirty = False  # cached flag

	def _serialize_state(self) -> str:
		# IMPORTANT: exclude UI-only fields like is_checked
		clean_sets = []
		for s in self.sets:
			clean_dummies = []
			for d in s.dummies:
				clean_inspections = [{
					"id": i.id,
					"name": i.name,
					"state_field_name": i.state_field_name,
					"expected_value": i.expected_value,
					"type_of_value": i.type_of_value,
				} for i in (d.inspections or [])]
				clean_dummies.append({
					"id": d.id,
					"name": d.name,
					"inspections": clean_inspections,
				})
			clean_sets.append({"id": s.id, "name": s.name, "dummies": clean_dummies})

		payload = {
			"version": 1,
			"scheduler": asdict(self.scheduler),
			"sets": clean_sets,
		}
		return json.dumps(payload, sort_keys=True)

	@property
	def has_changes(self) -> bool:
		return self._dirty

	def recompute_dirty(self) -> None:
		"""Call after *any* mutation that should affect dirty state."""
		self._dirty = (self._serialize_state() != self._baseline_json)
		print(f"recompute_dirty: {self._dirty}")

	def commit(self) -> None:
		"""Call after successful save/load."""
		self._baseline_json = self._serialize_state()
		self._dirty = False

	def rollback(self) -> None:
		"""Revert to baseline."""
		baseline_data = json.loads(self._baseline_json)
		# easiest: rebuild dataclasses from dicts (see note below)
		self.sets = _deserialize_sets(baseline_data) or []
		self.selected_set = _get_previous_selected(self.selected_set.id, self.sets)
		dummies = self.selected_set.dummies if self.selected_set else []
		selected_dummy = _get_previous_selected(self.selected_dummy_id, dummies)
		self.selected_dummy_id = selected_dummy.id if selected_dummy else None
		inspections = selected_dummy.inspections if selected_dummy else []
		selected_inspection = _get_previous_selected(self.selected_inspection_id, inspections)
		self.selected_inspection_id = selected_inspection.id if selected_inspection else None
		self._dirty = False

	# ---- convenience ----
	@property
	def dummies(self) -> List[DummyTest]:
		return self.selected_set.dummies if self.selected_set else []

	def is_exportable(self):
		if len(self.dummies) == 0:
			return False
		else:
			return all(len(d.inspections or []) > 0 for d in self.dummies)

	def selected_dummy(self) -> Optional[DummyTest]:
		if self.selected_dummy_id is None:
			return None
		return next((d for d in self.dummies if d.id == self.selected_dummy_id), None)

	def inspections(self) -> List[Inspection]:
		d = self.selected_dummy()
		return d.inspections if d else []

	# ---- selection handlers (similar to your SelectionHandler) ----
	def any_dummy_selected(self) -> bool:
		return any(d.is_checked for d in self.dummies)

	def all_dummy_selected(self) -> bool:
		return len(self.dummies) > 0 and all(d.is_checked for d in self.dummies)

	def any_inspection_selected(self) -> bool:
		return any(s.is_checked for s in self.inspections())

	def all_inspection_selected(self) -> bool:
		st = self.inspections()
		return len(st) > 0 and all(s.is_checked for s in st)
