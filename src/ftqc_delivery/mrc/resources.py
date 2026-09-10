"""Machine model: several kinds of magic state, produced by separate factories.

Time is measured in *logical cycles*, one logical cycle being the ``d`` surface
code rounds that a lattice-surgery operation takes. Space is measured in
*tiles*, one tile being a ``d x d`` patch.

The literature anchors used for the default factory parameters are:

* a ``|CCZ>`` factory occupying ``12d x 6d`` and producing one state every
  ``5.5d`` code cycles, i.e. 72 tiles and 5.5 logical cycles per state
  (Gidney and Fowler, *Efficient magic state factories with a catalyzed
  |CCZ> to 2|T> transformation*, Quantum 3, 135 (2019), arXiv:1812.01238);
* a 15-to-1 ``|T>`` factory occupying 11 tiles and producing one state every
  11 logical cycles (Litinski, *A Game of Surface Codes*, Quantum 3, 128
  (2019), arXiv:1808.02892).

These two are not drawn from a single calibrated design point -- they target
different output fidelities -- so no claim is made that their ratio is the
"correct" one for any machine. They fix the *scale*; the number of factories of
each kind is the architectural parameter this study sweeps.

Two conversions between the resources are real and are modelled explicitly,
because they are what makes the resources only *partly* non-fungible:

* one ``|CCZ>`` plus a catalyst yields exactly two ``|T>`` states
  (Gidney and Fowler 2019);
* eight ``|T>`` states yield one ``|CCZ>`` state through the 8T-to-CCZ
  distillation used by current factory designs.

The round trip loses a factor of four, so the exchange is asymmetric and lossy.
Enabling conversion is the study's main falsification control.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from functools import lru_cache
from math import ceil


T = "T"
CCZ = "CCZ"
RESOURCES = (T, CCZ)

UNBOUNDED = -1

#: Tiles occupied by one factory, and logical cycles between its outputs.
FACTORY_REFERENCE = {
    T: {
        "tiles": 11,
        "period": 11,
        "source": "Litinski 2019 (arXiv:1808.02892), 15-to-1 block, 11 tiles, 11 cycles",
    },
    CCZ: {
        "tiles": 72,
        "period": 6,
        "source": (
            "Gidney & Fowler 2019 (arXiv:1812.01238), 12d x 6d footprint, "
            "one state per 5.5d code cycles; the period is rounded up to 6 "
            "integral logical cycles, which is conservative for CCZ"
        ),
    },
}


@dataclass(frozen=True)
class FactoryBank:
    """A bank of identical factories producing one kind of magic state.

    Attributes:
        resource: Which state the bank produces.
        count: How many factories the bank contains.
        period: Logical cycles between successive outputs of one factory.
        latency: Logical cycles before a factory yields its first state.
        buffer_capacity: Storage for produced states, or ``UNBOUNDED``.
            Production arriving at a full buffer is lost.
        tiles_per_factory: Space charged for each factory.
        p_success: Probability that a production attempt yields a usable
            state. Distillation post-selects, so failures cost throughput.
        stagger: Whether factory phases are spread over one period.
    """

    resource: str
    count: int
    period: int
    latency: int = 0
    buffer_capacity: int = UNBOUNDED
    tiles_per_factory: int = 0
    p_success: float = 1.0
    stagger: bool = True

    def __post_init__(self) -> None:
        if self.resource not in RESOURCES:
            raise ValueError(f"unknown resource {self.resource!r}")
        if self.count <= 0:
            raise ValueError("count must be positive")
        if self.period <= 0:
            raise ValueError("period must be positive")
        if self.latency < 0:
            raise ValueError("latency must be nonnegative")
        if not 0.0 < self.p_success <= 1.0:
            raise ValueError("p_success must lie in (0, 1]")
        if self.buffer_capacity < 0 and self.buffer_capacity != UNBOUNDED:
            raise ValueError("buffer_capacity must be nonnegative or UNBOUNDED")

    @property
    def first_output(self) -> int:
        """Return the cycle at which the bank's first state can appear."""

        return self.latency + self.period

    @property
    def nominal_rate(self) -> float:
        """Return states per logical cycle ignoring distillation failures."""

        return self.count / self.period

    @property
    def rate(self) -> float:
        """Return the expected states per logical cycle."""

        return self.nominal_rate * self.p_success

    @property
    def tiles(self) -> int:
        """Return the total space the bank occupies."""

        return self.count * self.tiles_per_factory

    @property
    def unbounded_buffer(self) -> bool:
        """Return whether stored states are uncapped."""

        return self.buffer_capacity == UNBOUNDED

    def arrival_series(self, horizon: int, seed: int | None = None) -> list[int]:
        """Return the states delivered at each cycle ``1..horizon``.

        With ``p_success < 1`` the series is a sample, drawn from ``seed`` so
        that every policy sees the identical machine.
        """

        horizon = max(1, int(horizon))
        series = [0] * (horizon + 1)
        rng = random.Random(f"{seed}|{self.resource}|{self.count}|{self.period}|{self.p_success}")
        for index in range(self.count):
            offset = (index * self.period) // self.count if self.stagger else 0
            cycle = self.first_output + offset
            while cycle <= horizon:
                if self.p_success >= 1.0 or rng.random() < self.p_success:
                    series[cycle] += 1
                cycle += self.period
        return series

    def earliest_cycle_for(self, count: int, seed: int | None = None) -> int:
        """Return the first cycle by which ``count`` states have been produced.

        Read off the arrival process itself rather than from ``count / rate``,
        which overstates the wait by up to one production period and would make
        any bound built on it invalid.
        """

        if count <= 0:
            return 0
        return _earliest_cycle(
            self.count,
            self.period,
            self.latency,
            self.stagger,
            self.p_success,
            self.resource,
            int(count),
            seed,
        )

    def describe(self) -> str:
        """Return a compact identifier for tables."""

        buffer_text = "inf" if self.unbounded_buffer else str(self.buffer_capacity)
        return (
            f"{self.resource}x{self.count}/p{self.period}"
            f"/l{self.latency}/b{buffer_text}/s{self.p_success:g}"
        )


@dataclass(frozen=True)
class Conversion:
    """A protocol that turns states of one resource into another.

    ``inputs`` states of ``source`` become ``outputs`` states of ``target``
    after ``latency`` logical cycles, and at most ``concurrency`` conversions
    may be in flight at once.
    """

    source: str
    target: str
    inputs: int
    outputs: int
    latency: int
    concurrency: int = 1
    tiles: int = 0
    source_note: str = ""


#: One |CCZ> plus a catalyst becomes two |T> states (Gidney & Fowler 2019).
CATALYZED_CCZ_TO_T = Conversion(
    source=CCZ,
    target=T,
    inputs=1,
    outputs=2,
    latency=2,
    concurrency=2,
    tiles=4,
    source_note="Gidney & Fowler 2019 (arXiv:1812.01238), catalyzed |CCZ> -> 2|T>",
)

#: Eight |T> states distil into one |CCZ> state, as used by current factories.
T_TO_CCZ_DISTILLATION = Conversion(
    source=T,
    target=CCZ,
    inputs=8,
    outputs=1,
    latency=6,
    concurrency=1,
    tiles=12,
    source_note="8T -> 1 CCZ distillation used in current CCZ factory designs",
)


@dataclass(frozen=True)
class Machine:
    """A fault-tolerant machine: factory banks plus optional conversions."""

    banks: tuple[FactoryBank, ...]
    conversions: tuple[Conversion, ...] = ()
    name: str = ""
    seed: int = 0
    extra_tiles: int = 0

    def __post_init__(self) -> None:
        seen = [bank.resource for bank in self.banks]
        if len(set(seen)) != len(seen):
            raise ValueError("each resource may have at most one bank")

    def bank(self, resource: str) -> FactoryBank | None:
        """Return the bank producing ``resource``, if the machine has one."""

        for bank in self.banks:
            if bank.resource == resource:
                return bank
        return None

    @property
    def resources(self) -> tuple[str, ...]:
        """Return the resources this machine can produce, in a fixed order."""

        return tuple(resource for resource in RESOURCES if self.bank(resource))

    def rate(self, resource: str) -> float:
        """Return the expected production rate of ``resource``."""

        bank = self.bank(resource)
        return bank.rate if bank else 0.0

    @property
    def factory_tiles(self) -> int:
        """Return the space occupied by factories and conversion units."""

        return (
            sum(bank.tiles for bank in self.banks)
            + sum(conversion.tiles * conversion.concurrency for conversion in self.conversions)
            + self.extra_tiles
        )

    @property
    def imbalance(self) -> float:
        """Return the ratio of the faster to the slower resource, in T-equivalents.

        One ``|CCZ>`` is worth two ``|T>`` states through the catalyzed
        transformation, so rates are compared after that conversion. A value of
        1 means the two banks deliver equal value per cycle.
        """

        t_value = self.rate(T)
        ccz_value = 2.0 * self.rate(CCZ)
        if t_value <= 0 or ccz_value <= 0:
            return float("inf")
        return max(t_value, ccz_value) / min(t_value, ccz_value)

    def describe(self) -> str:
        """Return a compact identifier for tables and plot labels."""

        parts = [bank.describe() for bank in self.banks]
        if self.conversions:
            parts.append("conv:" + "+".join(
                f"{c.inputs}{c.source}->{c.outputs}{c.target}" for c in self.conversions
            ))
        return self.name or "|".join(parts)


def build_machine(
    t_factories: int,
    ccz_factories: int,
    buffer_capacity: int = 32,
    latency: int = 0,
    p_success: float = 1.0,
    conversions: tuple[Conversion, ...] = (),
    name: str = "",
    seed: int = 0,
) -> Machine:
    """Return a machine with the reference factory designs at the given counts."""

    banks = []
    for resource, count in ((T, t_factories), (CCZ, ccz_factories)):
        if count <= 0:
            continue
        reference = FACTORY_REFERENCE[resource]
        banks.append(
            FactoryBank(
                resource=resource,
                count=count,
                period=int(reference["period"]),
                latency=latency,
                buffer_capacity=buffer_capacity,
                tiles_per_factory=int(reference["tiles"]),
                p_success=p_success,
            )
        )
    if not banks:
        raise ValueError("a machine needs at least one factory bank")
    return Machine(banks=tuple(banks), conversions=conversions, name=name, seed=seed)


def machine_for_rates(
    t_rate: float,
    ccz_rate: float,
    buffer_capacity: int = 32,
    latency: int = 0,
    p_success: float = 1.0,
    conversions: tuple[Conversion, ...] = (),
    seed: int = 0,
) -> Machine:
    """Return a machine whose banks deliver approximately the requested rates."""

    t_period = int(FACTORY_REFERENCE[T]["period"])
    ccz_period = int(FACTORY_REFERENCE[CCZ]["period"])
    return build_machine(
        t_factories=ceil(t_rate * t_period) if t_rate > 0 else 0,
        ccz_factories=ceil(ccz_rate * ccz_period) if ccz_rate > 0 else 0,
        buffer_capacity=buffer_capacity,
        latency=latency,
        p_success=p_success,
        conversions=conversions,
        name=f"T{t_rate:g}_CCZ{ccz_rate:g}",
        seed=seed,
    )


def machine_for_capacity(
    capacity: float,
    ccz_share: float,
    buffer_capacity: int = 32,
    latency: int = 0,
    p_success: float = 1.0,
    conversions: tuple[Conversion, ...] = (),
    seed: int = 0,
) -> Machine:
    """Return a machine with a given total capacity split between the banks.

    ``capacity`` is the total production rate in T-equivalent states per
    logical cycle, and ``ccz_share`` is the fraction of that capacity held by
    the CCZ bank. Holding ``capacity`` fixed while sweeping ``ccz_share``
    separates the effect of *splitting* the supply from the effect of having
    more or less of it, which is the comparison this study needs: any advantage
    that survives at constant capacity is about the resources being
    non-fungible, not about total throughput.

    Factory counts are integral, so the achieved rates only approximate the
    request; callers should report ``Machine.rate`` rather than the target.
    """

    if capacity <= 0:
        raise ValueError("capacity must be positive")
    if not 0.0 <= ccz_share <= 1.0:
        raise ValueError("ccz_share must lie in [0, 1]")

    t_target = capacity * (1.0 - ccz_share)
    ccz_target = capacity * ccz_share / 2.0

    t_period = int(FACTORY_REFERENCE[T]["period"])
    ccz_period = int(FACTORY_REFERENCE[CCZ]["period"])
    t_count = max(1, round(t_target * t_period)) if t_target > 0 else 0
    ccz_count = max(1, round(ccz_target * ccz_period)) if ccz_target > 0 else 0
    if t_count == 0 and ccz_count == 0:
        t_count = 1

    return build_machine(
        t_factories=t_count,
        ccz_factories=ccz_count,
        buffer_capacity=buffer_capacity,
        latency=latency,
        p_success=p_success,
        conversions=conversions,
        name=f"cap{capacity:g}_ccz{ccz_share:g}",
        seed=seed,
    )


@lru_cache(maxsize=8192)
def _earliest_cycle(
    count_factories: int,
    period: int,
    latency: int,
    stagger: bool,
    p_success: float,
    resource: str,
    needed: int,
    seed: int | None,
) -> int:
    """Return the first cycle by which ``needed`` states have been produced.

    Cached, because the analytic policies query it once per candidate and the
    answer depends only on the bank's parameters.
    """

    bank = FactoryBank(
        resource=resource,
        count=count_factories,
        period=period,
        latency=latency,
        p_success=p_success,
        stagger=stagger,
    )
    horizon = latency + period * (2 + (needed + count_factories) // max(1, count_factories))
    while True:
        series = bank.arrival_series(horizon, seed=seed)
        running = 0
        for cycle, arrived in enumerate(series):
            running += arrived
            if running >= needed:
                return cycle
        horizon *= 2
