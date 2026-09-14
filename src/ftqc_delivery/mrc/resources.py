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


RAW = "RAW"
T = "T"
CCZ = "CCZ"
#: RAW is the level-1 magic-state stream that distillers consume; circuits
#: never consume it directly. T and CCZ are the distilled products.
RESOURCES = (RAW, T, CCZ)

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
    #: A proactive conversion runs whenever inputs are available and the target
    #: buffer has room, like a distillation pipeline; an on-demand one runs only
    #: when the target is starved, like a catalysis unit.
    proactive: bool = False


#: A 15-to-1 distiller turning fifteen level-1 T states into one usable T
#: state, on 11 tiles in 11 logical cycles (Litinski 2019, arXiv:1808.02892).
T_DISTILLER_15_TO_1 = Conversion(
    source=RAW,
    target=T,
    inputs=15,
    outputs=1,
    latency=11,
    concurrency=1,
    tiles=11,
    source_note="Litinski 2019 (arXiv:1808.02892), 15-to-1 block: 11 tiles, 11 cycles",
    proactive=True,
)

#: Gidney & Fowler's CCZ factory consumes eight level-1 T states and yields one
#: CCZ on 12d x 6d in 5.5d code cycles; period rounded up to 6.
CCZ_DISTILLER_8_TO_1 = Conversion(
    source=RAW,
    target=CCZ,
    inputs=8,
    outputs=1,
    latency=6,
    concurrency=1,
    tiles=72,
    source_note="Gidney & Fowler 2019 (arXiv:1812.01238), 8 T -> 1 CCZ, 72 tiles, 5.5d",
    proactive=True,
)

#: Level-1 (raw) T supply feeding the distillers. The footprint and period are
#: an assumption in the cultivation/injection class (Gidney, Shutty & Jones
#: 2024, arXiv:2409.17595, report T states "as cheap as CNOT gates"); they are
#: swept in the coupled-provisioning study rather than trusted.
RAW_REFERENCE = {"tiles": 2, "period": 2}


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
    #: Buffer capacities for resources that have no bank of their own because
    #: they are produced only by conversions.
    buffers: tuple[tuple[str, int], ...] = ()
    #: Which coupling model built this machine, for tables.
    model: str = "A"
    #: States already in each buffer when execution starts. Used to evaluate a
    #: stage of a program from the buffer state its predecessor left behind.
    initial_stock: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        seen = [bank.resource for bank in self.banks]
        if len(set(seen)) != len(seen):
            raise ValueError("each resource may have at most one bank")

    def initial(self, resource: str) -> int:
        """Return the stock of ``resource`` present when execution starts."""

        for name, count in self.initial_stock:
            if name == resource:
                return count
        return 0

    def with_initial_stock(self, stock: dict[str, int]) -> "Machine":
        """Return a copy of this machine starting with the given buffer contents."""

        from dataclasses import replace

        return replace(
            self,
            initial_stock=tuple(
                (resource, min(int(count), self.buffer(resource)) if self.buffer(resource) >= 0 else int(count))
                for resource, count in sorted(stock.items())
            ),
        )

    def buffer(self, resource: str) -> int:
        """Return the buffer capacity for ``resource`` (``UNBOUNDED`` if none)."""

        bank = self.bank(resource)
        if bank is not None:
            return bank.buffer_capacity
        for name, capacity in self.buffers:
            if name == resource:
                return capacity
        return 32

    @property
    def producible(self) -> tuple[str, ...]:
        """Return every resource the machine can deliver, by bank or conversion."""

        names = [bank.resource for bank in self.banks]
        for conversion in self.conversions:
            if conversion.target not in names:
                names.append(conversion.target)
        return tuple(name for name in RESOURCES if name in names)

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
        """Return the expected steady-state delivery rate of ``resource``.

        For a resource with its own bank this is the bank's rate. For one
        produced only by conversions it is the conversions' throughput, capped
        by the share of the source stream they can draw: when several
        distillers pull from the same raw stream, the stream is divided in
        proportion to how much each could consume. Catalysis units are
        on-demand and are not counted as steady-state supply.
        """

        bank = self.bank(resource)
        if bank is not None:
            return bank.rate
        total = 0.0
        for conversion in self.conversions:
            if conversion.target != resource or not conversion.proactive:
                continue
            total += self._conversion_rate(conversion)
        return total

    def _conversion_rate(self, conversion: "Conversion") -> float:
        """Return the steady-state output rate of one proactive conversion."""

        capacity = conversion.concurrency * conversion.outputs / conversion.latency
        siblings = [
            other
            for other in self.conversions
            if other.source == conversion.source and other.proactive
        ]
        draws = {
            other: other.concurrency * other.inputs / other.latency for other in siblings
        }
        total_draw = sum(draws.values())
        supply = self.rate(conversion.source)
        if total_draw <= 0:
            return 0.0
        share = supply * draws[conversion] / total_draw
        fed = min(draws[conversion], share) / conversion.inputs * conversion.outputs
        return min(capacity, fed)

    @property
    def factory_tiles(self) -> int:
        """Return the space occupied by factories and conversion units."""

        return (
            sum(bank.tiles for bank in self.banks)
            + sum(conversion.tiles * conversion.concurrency for conversion in self.conversions)
            + self.extra_tiles
        )

    @property
    def distiller_counts(self) -> dict[str, int]:
        """Return how many proactive conversion units feed each resource."""

        counts: dict[str, int] = {}
        for conversion in self.conversions:
            if conversion.proactive:
                counts[conversion.target] = counts.get(conversion.target, 0) + conversion.concurrency
        return counts

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

        parts = [f"model{self.model}"] + [bank.describe() for bank in self.banks]
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


def _scaled(conversion: Conversion, concurrency: int) -> Conversion:
    """Return ``conversion`` with a different number of units."""

    return Conversion(
        source=conversion.source,
        target=conversion.target,
        inputs=conversion.inputs,
        outputs=conversion.outputs,
        latency=conversion.latency,
        concurrency=max(0, int(concurrency)),
        tiles=conversion.tiles,
        source_note=conversion.source_note,
        proactive=conversion.proactive,
    )


def coupled_machine(
    model: str,
    tiles: int,
    ccz_share: float,
    buffer_capacity: int = 32,
    raw_period: int | None = None,
    raw_tiles: int | None = None,
    raw_buffer: int = 64,
    raw_scale: float = 1.0,
    seed: int = 0,
) -> Machine:
    """Return a machine under one of three provisioning models at a fixed area.

    ``tiles`` is the total factory area, held fixed so that no model is
    quietly given more hardware than another. ``ccz_share`` is the fraction of
    the *distiller* area devoted to CCZ production.

    Model ``A``
        The independent reference: standalone T and CCZ banks whose outputs
        are unrelated, as in the earlier study.
    Model ``B``
        Shared upstream production. A single bank of level-1 T states feeds
        15-to-1 T distillers and 8-to-1 CCZ distillers that draw from the same
        stream, so the two products compete for one raw supply and neither can
        be dialled independently of the other. The raw bank's area comes out of
        the same budget.
    Model ``C``
        Model B plus the catalyzed one-CCZ-to-two-T conversion, one unit per
        CCZ distiller, so CCZ output can also serve T demand at a lossy rate.

    ``raw_scale`` sizes the raw stream relative to what the distillers could
    consume: 1.0 exactly covers them, below 1.0 makes them compete for it.
    ``raw_tiles=0`` is the literature-faithful reading in which level-1
    production sits inside each factory's published footprint, so the shared
    stream costs no extra area; the default charges for it separately, which
    is conservative against the coupled models.
    """

    if model not in ("A", "B", "C"):
        raise ValueError(f"unknown coupling model {model!r}")
    if tiles <= 0:
        raise ValueError("tiles must be positive")
    if not 0.0 <= ccz_share <= 1.0:
        raise ValueError("ccz_share must lie in [0, 1]")

    t_tiles = int(FACTORY_REFERENCE[T]["tiles"])
    ccz_tiles = int(FACTORY_REFERENCE[CCZ]["tiles"])
    raw_period = RAW_REFERENCE["period"] if raw_period is None else raw_period
    raw_tiles = RAW_REFERENCE["tiles"] if raw_tiles is None else raw_tiles

    def split(area: int) -> tuple[int, int]:
        ccz_count = int(round(ccz_share * area / ccz_tiles))
        t_count = int(round((1.0 - ccz_share) * area / t_tiles))
        if 0.0 < ccz_share < 1.0:
            ccz_count = max(1, ccz_count)
            t_count = max(1, t_count)
        elif ccz_share == 0.0:
            ccz_count, t_count = 0, max(1, t_count)
        else:
            ccz_count, t_count = max(1, ccz_count), 0
        return t_count, ccz_count

    if model == "A":
        t_count, ccz_count = split(tiles)
        return build_machine(
            t_factories=t_count,
            ccz_factories=ccz_count,
            buffer_capacity=buffer_capacity,
            seed=seed,
            name=f"A_tiles{tiles}_ccz{ccz_share:g}",
        )

    # Models B and C: distillers plus the raw bank that feeds them, all within
    # the same area. Iterate to a fixed point on the area left for distillers.
    distiller_area = tiles
    for _ in range(12):
        t_count, ccz_count = split(distiller_area)
        raw_demand = (
            t_count * T_DISTILLER_15_TO_1.inputs / T_DISTILLER_15_TO_1.latency
            + ccz_count * CCZ_DISTILLER_8_TO_1.inputs / CCZ_DISTILLER_8_TO_1.latency
        )
        raw_count = max(1, ceil(raw_demand * raw_period * raw_scale))
        catalysis_tiles = CATALYZED_CCZ_TO_T.tiles * ccz_count if model == "C" else 0
        remaining = tiles - raw_count * raw_tiles - catalysis_tiles
        if remaining == distiller_area:
            break
        distiller_area = max(t_tiles, remaining)

    t_count, ccz_count = split(distiller_area)
    raw_demand = (
        t_count * T_DISTILLER_15_TO_1.inputs / T_DISTILLER_15_TO_1.latency
        + ccz_count * CCZ_DISTILLER_8_TO_1.inputs / CCZ_DISTILLER_8_TO_1.latency
    )
    raw_count = max(1, ceil(raw_demand * raw_period * raw_scale))

    raw_bank = FactoryBank(
        resource=RAW,
        count=raw_count,
        period=raw_period,
        latency=0,
        buffer_capacity=raw_buffer,
        tiles_per_factory=raw_tiles,
    )
    conversions: list[Conversion] = []
    if t_count > 0:
        conversions.append(_scaled(T_DISTILLER_15_TO_1, t_count))
    if ccz_count > 0:
        conversions.append(_scaled(CCZ_DISTILLER_8_TO_1, ccz_count))
    if model == "C" and ccz_count > 0:
        conversions.append(_scaled(CATALYZED_CCZ_TO_T, ccz_count))

    return Machine(
        banks=(raw_bank,),
        conversions=tuple(conversions),
        name=f"{model}_tiles{tiles}_ccz{ccz_share:g}_raw{raw_period}x{raw_scale:g}",
        seed=seed,
        buffers=((T, buffer_capacity), (CCZ, buffer_capacity)),
        model=model,
    )
