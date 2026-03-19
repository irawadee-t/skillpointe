"""Site-specific scraping adapters."""
from .ball import BallJobsAdapter
from .southwire import SouthwireAdapter
from .ford import FordAdapter
from .ge_vernova import GEVernovaAdapter
from .schneider import SchneiderAdapter
from .delta import DeltaAdapter

ADAPTERS = {
    "ball": BallJobsAdapter,
    "southwire": SouthwireAdapter,
    "ford": FordAdapter,
    "ge_vernova": GEVernovaAdapter,
    "schneider": SchneiderAdapter,
    "delta": DeltaAdapter,
}
