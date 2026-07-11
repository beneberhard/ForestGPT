from abc import ABC, abstractmethod

from app.simulation.schemas import GrowthSimulationRequest, SimulationResult, SimulatorCapability


class SimulationAdapter(ABC):
    adapter_key: str
    model_name: str
    model_version: str | None = None

    @abstractmethod
    def capability(self) -> SimulatorCapability:
        """Describe what this simulator can do and what runtime it needs."""

    @abstractmethod
    def run(self, request: GrowthSimulationRequest) -> SimulationResult:
        """Run a growth simulation and return normalized outputs."""
