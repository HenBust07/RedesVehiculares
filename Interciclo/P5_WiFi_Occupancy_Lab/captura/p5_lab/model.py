"""Modelo preliminar independiente: parametros asumidos, NO CALIBRADO."""
from dataclasses import dataclass
import math

MODEL_STATUS = "NO CALIBRADO"


@dataclass(frozen=True)
class Parameters:
    background: float
    detection_probability: float

    def __post_init__(self):
        for value in (self.background, self.detection_probability):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("B y pd deben ser numeros finitos")
        if self.background < 0 or not 0 < self.detection_probability <= 1:
            raise ValueError("Se requiere B >= 0 y 0 < pd <= 1")
        if not math.isfinite(4 * (max(0, 512 - self.background) / self.detection_probability)):
            raise ValueError("pd es demasiado pequeño para una estimacion finita")

    def estimate(self, unique_addresses):
        if type(unique_addresses) is not int or not 0 <= unique_addresses <= 512:
            raise ValueError("D debe ser un entero entre 0 y 512 para estas sondas")
        return max(0.0, (unique_addresses - self.background) / self.detection_probability)

    def as_dict(self):
        return {"B": self.background, "pd": self.detection_probability, "status": MODEL_STATUS}
