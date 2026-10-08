"""Fault knobs at runtime. They start from env vars and an admin can change them."""

import random
from dataclasses import dataclass, field

from app.config import Settings


@dataclass
class Faults:
    allowed: bool
    latency_ms: int = 0
    flaky_rate: float = 0.0
    bug: str = ""
    rng: random.Random = field(default_factory=random.Random)

    @classmethod
    def from_settings(cls, settings: Settings) -> "Faults":
        return cls(
            allowed=settings.faults_allowed,
            latency_ms=settings.latency_ms,
            flaky_rate=settings.flaky_rate,
            bug=settings.bug,
            rng=random.Random(settings.flaky_seed),
        )

    def update(self, latency_ms: int, flaky_rate: float, bug: str) -> None:
        if not self.allowed:
            return
        self.latency_ms = max(0, latency_ms)
        self.flaky_rate = min(1.0, max(0.0, flaky_rate))
        self.bug = bug.strip()

    def flaky_hit(self) -> bool:
        return self.allowed and self.flaky_rate > 0 and self.rng.random() < self.flaky_rate
