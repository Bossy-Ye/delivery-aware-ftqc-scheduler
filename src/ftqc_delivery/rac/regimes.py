"""Named magic-state supply regimes used across the pilot experiments."""

from __future__ import annotations

from dataclasses import dataclass

from .supply import UNBOUNDED, SupplyModel


@dataclass(frozen=True)
class Regime:
    """A named supply configuration."""

    name: str
    supply: SupplyModel

    @property
    def rate(self) -> float:
        """Return the steady-state supply rate."""

        return self.supply.rate


def _bank(rate: float, latency: int = 10, buffer: int = 32) -> SupplyModel:
    return SupplyModel(
        num_factories=max(1, round(rate * latency)),
        production_latency=latency,
        factory_period=latency,
        buffer_capacity=buffer,
    )


#: Rates span the distillation era (a state every few tens of cycles) through
#: the cultivation era, where a state can be produced about as fast as a
#: logical Clifford.
MAIN_RATES = (0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0)


def main_regimes(buffer: int = 32, latency: int = 10) -> list[Regime]:
    """Return the primary rate sweep at a fixed buffer and production latency."""

    regimes = []
    for rate in MAIN_RATES:
        supply = _bank(rate, latency=latency, buffer=buffer)
        regimes.append(Regime(name=f"rate{supply.rate:g}", supply=supply))
    return regimes


def unconstrained_regime(states: int) -> Regime:
    """Return a regime that cannot constrain execution, used as a control."""

    return Regime(
        name="unconstrained",
        supply=SupplyModel(
            num_factories=max(1, states),
            production_latency=1,
            factory_period=1,
            buffer_capacity=UNBOUNDED,
            initial_stock=max(1, states),
        ),
    )


def buffer_regimes(rate: float = 1.0, latency: int = 10) -> list[Regime]:
    """Return a buffer sweep at a fixed supply rate."""

    regimes = [
        Regime(
            name=f"buffer{buffer}",
            supply=_bank(rate, latency=latency, buffer=buffer),
        )
        for buffer in (1, 2, 4, 8, 16, 32, 128)
    ]
    regimes.append(
        Regime(
            name="bufferinf",
            supply=SupplyModel(
                num_factories=max(1, round(rate * latency)),
                production_latency=latency,
                factory_period=latency,
                buffer_capacity=UNBOUNDED,
            ),
        )
    )
    return regimes


def factory_configurations(rate: float = 1.0, buffer: int = 32) -> list[Regime]:
    """Return several factory banks that deliver the same average rate.

    Same rate, different granularity and phasing: a few slow factories deliver
    states in coarse bursts, many fast ones deliver a fine stream, and a
    synchronised bank delivers everything on the same cycle. If the effect
    under study were only about average throughput, these would be equivalent.
    """

    configurations = []
    for latency in (2, 5, 10, 20, 40):
        factories = max(1, round(rate * latency))
        for stagger in (True, False):
            configurations.append(
                Regime(
                    name=f"F{factories}_L{latency}_{'stag' if stagger else 'sync'}",
                    supply=SupplyModel(
                        num_factories=factories,
                        production_latency=latency,
                        factory_period=latency,
                        buffer_capacity=buffer,
                        stagger=stagger,
                    ),
                )
            )
    return configurations


def pipelined_regimes(rate: float = 1.0, buffer: int = 32) -> list[Regime]:
    """Return banks that reach the same rate with different production latency.

    Production latency delays the first state without changing throughput, so
    it separates start-up cost from steady-state cost.
    """

    return [
        Regime(
            name=f"latency{latency}",
            supply=SupplyModel(
                num_factories=max(1, round(rate * period)),
                production_latency=latency,
                factory_period=period,
                buffer_capacity=buffer,
            ),
        )
        for latency, period in ((1, 10), (10, 10), (40, 10), (100, 10))
    ]
