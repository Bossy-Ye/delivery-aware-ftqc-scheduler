"""Resource-aware compilation: the go/no-go study.

The rest of this package takes a circuit as given and asks how to schedule it.
This subpackage leaves the circuit open. A program is a graph of decision
sites, each site offers several semantically equivalent implementations that
differ in T-count, T-depth and the shape of the magic-state demand they place
on the machine, and the compiler must choose one per site.

See ``results/rac_pilot/GO_NO_GO_MEMO.md`` for what the study concluded.
"""

from .analysis import logical_depth, static_summary, t_count, t_depth
from .cost import estimate, sccp_bound
from .execution import execute, execute_fixed_schedule
from .supply import StochasticSupplyModel, SupplyModel
from .variants import Fragment, ProgramSpace, Site, Variant

__all__ = [
    "t_count",
    "t_depth",
    "logical_depth",
    "static_summary",
    "sccp_bound",
    "estimate",
    "execute",
    "execute_fixed_schedule",
    "SupplyModel",
    "StochasticSupplyModel",
    "Fragment",
    "Variant",
    "Site",
    "ProgramSpace",
]
