"""Magic-state supply process for resource-aware compilation experiments.

The supply side of the model is deliberately small. A bank of identical magic
state factories produces states at a fixed period, the first state of each
factory appears only after a production latency, and a bounded buffer stores
states that are produced but not yet consumed. Everything else (decoder
latency, routing, lattice surgery, memory errors) is intentionally absent so
that any observed effect can be attributed to supply versus demand alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import ceil


UNBOUNDED = -1


@dataclass(frozen=True)
class SupplyModel:
    """A bank of magic-state factories feeding a bounded buffer.

    Attributes:
        num_factories: Number of independent factories, ``F``.
        production_latency: Cycles before a factory yields its first state.
        factory_period: Cycles between consecutive states from one factory.
            Equal to ``production_latency`` for a non-pipelined factory and
            smaller for a pipelined one.
        buffer_capacity: Maximum number of stored states, or ``UNBOUNDED``.
            States produced while the buffer is full are lost (the factory
            idles), so storage is never free.
        stagger: Whether factory phases are spread across one period. A
            staggered bank yields a smooth supply, a synchronized bank yields
            a bursty one.
        initial_stock: States already available at the start of execution.
    """

    num_factories: int = 1
    production_latency: int = 1
    factory_period: int | None = None
    buffer_capacity: int = UNBOUNDED
    stagger: bool = True
    initial_stock: int = 0

    def __post_init__(self) -> None:
        if self.num_factories <= 0:
            raise ValueError("num_factories must be positive")
        if self.production_latency <= 0:
            raise ValueError("production_latency must be positive")
        if self.period <= 0:
            raise ValueError("factory_period must be positive")
        if self.buffer_capacity < 0 and self.buffer_capacity != UNBOUNDED:
            raise ValueError("buffer_capacity must be nonnegative or UNBOUNDED")
        if self.initial_stock < 0:
            raise ValueError("initial_stock must be nonnegative")

    @property
    def period(self) -> int:
        """Return the inter-arrival period of a single factory."""

        return self.production_latency if self.factory_period is None else self.factory_period

    @property
    def rate(self) -> float:
        """Return the steady-state supply rate in magic states per cycle."""

        return self.num_factories / self.period

    @property
    def unbounded_buffer(self) -> bool:
        """Return whether the buffer is unbounded."""

        return self.buffer_capacity == UNBOUNDED

    def phase(self, factory_index: int) -> int:
        """Return the first delivery cycle of one factory."""

        if not self.stagger:
            return self.production_latency
        offset = (factory_index * self.period) // self.num_factories
        return self.production_latency + offset

    def arrivals(self, cycle: int) -> int:
        """Return the number of states produced at the start of ``cycle``."""

        if cycle < 1:
            return 0
        count = 0
        for factory_index in range(self.num_factories):
            first = self.phase(factory_index)
            if cycle >= first and (cycle - first) % self.period == 0:
                count += 1
        return count

    def arrival_series(self, horizon: int) -> tuple[int, ...]:
        """Return arrivals for cycles ``1..horizon`` as a cached tuple.

        Simulation reads the arrival process once per cycle, so building it in
        one pass keeps the executor linear in the makespan rather than in the
        makespan times the number of factories.
        """

        return _arrival_series(
            self.num_factories,
            self.production_latency,
            self.period,
            self.stagger,
            max(1, int(horizon)),
        )

    def cumulative_arrivals(self, cycle: int) -> int:
        """Return the total number of states produced up to and including ``cycle``."""

        if cycle < 1:
            return 0
        total = 0
        for factory_index in range(self.num_factories):
            first = self.phase(factory_index)
            if cycle >= first:
                total += 1 + (cycle - first) // self.period
        return total

    def cycles_to_produce(self, count: int, start_cycle: int = 0) -> int:
        """Return the earliest cycle by which ``count`` extra states have arrived.

        The count is measured over cycles strictly after ``start_cycle``. The
        result is the absolute cycle index, not a duration. This ignores the
        buffer cap and is therefore a valid optimistic bound.
        """

        if count <= 0:
            return start_cycle
        already = self.cumulative_arrivals(start_cycle)
        target = already + count
        # The steady-state rate gives a tight starting guess; correct by scanning.
        guess = max(start_cycle, self.production_latency)
        guess = max(guess, start_cycle + int(count / self.rate) - self.period - 1)
        while self.cumulative_arrivals(guess) < target:
            guess += 1
        while guess > 0 and self.cumulative_arrivals(guess - 1) >= target:
            guess -= 1
        return guess

    def describe(self) -> str:
        """Return a compact identifier for tables and plot labels."""

        buffer_text = "inf" if self.unbounded_buffer else str(self.buffer_capacity)
        return (
            f"F{self.num_factories}_L{self.production_latency}"
            f"_P{self.period}_B{buffer_text}"
        )


def supply_for_rate(rate: float, production_latency: int = 10, buffer_capacity: int = UNBOUNDED) -> SupplyModel:
    """Return a staggered factory bank whose steady-state rate is close to ``rate``."""

    if rate <= 0:
        raise ValueError("rate must be positive")
    num_factories = max(1, int(round(rate * production_latency)))
    return SupplyModel(
        num_factories=num_factories,
        production_latency=production_latency,
        factory_period=production_latency,
        buffer_capacity=buffer_capacity,
    )


def saturating_supply(total_states: int) -> SupplyModel:
    """Return a supply model that never constrains execution."""

    return SupplyModel(
        num_factories=max(1, total_states),
        production_latency=1,
        factory_period=1,
        buffer_capacity=UNBOUNDED,
        initial_stock=max(1, total_states),
    )


def stall_free_rate(total_states: int, span: int) -> float:
    """Return the minimum average rate that could cover ``total_states`` in ``span``."""

    if span <= 0:
        return float("inf")
    return total_states / span


def min_factories_for_rate(rate: float, production_latency: int) -> int:
    """Return the smallest factory count reaching ``rate`` at a given period."""

    return max(1, ceil(rate * production_latency))


@lru_cache(maxsize=256)
def _arrival_series(
    num_factories: int,
    production_latency: int,
    period: int,
    stagger: bool,
    horizon: int,
) -> tuple[int, ...]:
    """Return the per-cycle arrival counts of a factory bank, 1-indexed."""

    series = [0] * (horizon + 1)
    for factory_index in range(num_factories):
        offset = (factory_index * period) // num_factories if stagger else 0
        cycle = production_latency + offset
        while cycle <= horizon:
            series[cycle] += 1
            cycle += period
    return tuple(series)


class StochasticSupplyModel:
    """A factory bank whose distillation attempts sometimes fail.

    Each scheduled delivery succeeds with probability ``p_accept``. The
    resulting arrival process has the same mean rate as the deterministic bank
    scaled by ``p_accept`` but is irregular, which is what a real distillation
    factory with post-selection looks like. The class deliberately mirrors the
    :class:`SupplyModel` interface so that every executor, cost model and
    policy can consume it unchanged; the analytic models see only its nominal
    rate, so this is a genuine out-of-model stress test rather than a fit.
    """

    def __init__(
        self,
        base: SupplyModel,
        p_accept: float = 0.8,
        seed: int = 0,
        horizon: int = 200_000,
    ) -> None:
        if not 0.0 < p_accept <= 1.0:
            raise ValueError("p_accept must lie in (0, 1]")
        self.base = base
        self.p_accept = p_accept
        self.seed = seed
        self.num_factories = base.num_factories
        self.production_latency = base.production_latency
        self.buffer_capacity = base.buffer_capacity
        self.stagger = base.stagger
        self.initial_stock = base.initial_stock
        self._horizon = horizon
        self._series = self._sample(horizon)
        self._cumulative = self._accumulate(self._series)

    def _sample(self, horizon: int) -> tuple[int, ...]:
        import random

        rng = random.Random((self.seed, self.p_accept, self.base.describe()).__hash__())
        nominal = self.base.arrival_series(horizon)
        return tuple(
            sum(1 for _ in range(count) if rng.random() < self.p_accept)
            for count in nominal
        )

    @staticmethod
    def _accumulate(series: tuple[int, ...]) -> tuple[int, ...]:
        total = 0
        running = []
        for value in series:
            total += value
            running.append(total)
        return tuple(running)

    @property
    def period(self) -> int:
        """Return the nominal inter-arrival period of a single factory."""

        return self.base.period

    @property
    def rate(self) -> float:
        """Return the expected steady-state supply rate."""

        return self.base.rate * self.p_accept

    @property
    def unbounded_buffer(self) -> bool:
        """Return whether the buffer is unbounded."""

        return self.base.unbounded_buffer

    def arrival_series(self, horizon: int) -> tuple[int, ...]:
        """Return the sampled arrivals for cycles ``1..horizon``."""

        if horizon > self._horizon:
            self._horizon = horizon
            self._series = self._sample(horizon)
            self._cumulative = self._accumulate(self._series)
        return self._series

    def arrivals(self, cycle: int) -> int:
        """Return the sampled arrivals at ``cycle``."""

        if cycle < 1:
            return 0
        return self.arrival_series(max(cycle, self._horizon))[cycle]

    def cumulative_arrivals(self, cycle: int) -> int:
        """Return the total sampled arrivals up to and including ``cycle``."""

        if cycle < 1:
            return 0
        self.arrival_series(max(cycle, self._horizon))
        index = min(cycle, len(self._cumulative) - 1)
        return self._cumulative[index]

    def cycles_to_produce(self, count: int, start_cycle: int = 0) -> int:
        """Return the earliest cycle delivering ``count`` further states."""

        if count <= 0:
            return start_cycle
        target = self.cumulative_arrivals(start_cycle) + count
        cycle = start_cycle
        while self.cumulative_arrivals(cycle) < target:
            cycle += 1
            if cycle > self._horizon:
                break
        return cycle

    def describe(self) -> str:
        """Return a compact identifier for tables and plot labels."""

        return f"{self.base.describe()}_p{self.p_accept:g}_s{self.seed}"
