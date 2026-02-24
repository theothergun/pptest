from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Dict, Any, Optional


@dataclass
class ResultsViewState:
	max_range_days: int = 31

	# filter inputs
	date_from: date = field(default_factory=lambda: date.today() - timedelta(days=7))
	date_to: date = field(default_factory=date.today)
	selected_set: str = "All"

	# loaded data
	records: List[Dict[str, Any]] = field(default_factory=list)
	selected_index: Optional[int] = None

	# display mode: "ui" or "raw"
	mode: str = "ui"