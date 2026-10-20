from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Settings:
    """Exploratory defaults, not thresholds recovered from the report."""

    min_side: int = 128
    max_clipped_fraction: float = .35
    min_contrast: float = .035
    min_laplacian_variance: float = 8.
    min_tenengrad: float = 40.
    max_registration_shift_fraction: float = .08
    registration_min_ecc: float = .35
    registration_max_residual_px: float = 5.
    direction_separation_deg: float = 40.
    projection_max_drift_deg: float = 12.
    response_polarities: tuple = ("bright", "dark")
    widths_min_samples: int = 20
    widths_min_tracks: int = 3
    widths_max_cv: float = .5
    twill_exclude_yarn_deg: float = 12.
    weave_min_known: int = 16
    weave_min_coverage: float = .35
    weave_min_agreement: float = .82
    weave_min_margin: float = .06
    yarn_reference_rules: tuple = field(default_factory=tuple)
    camera_profile: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.response_polarities or any(p not in ("bright", "dark") for p in self.response_polarities):
            raise ValueError("response_polarities must contain bright/dark")
        if self.projection_max_drift_deg < 0 or not 0 < self.direction_separation_deg < 90:
            raise ValueError("Invalid direction settings")
        if any(not 0 < x <= 1 for x in (self.max_clipped_fraction, self.weave_min_coverage,
                                        self.weave_min_agreement, self.weave_min_margin)):
            raise ValueError("Fraction settings must be in (0,1]")

    def to_dict(self):
        return asdict(self)
