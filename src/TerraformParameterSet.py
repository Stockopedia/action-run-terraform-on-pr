from dataclasses import dataclass


@dataclass(frozen=True)
class TerraformParameterSet:
    provider: str
    environment: str
    layer: str
