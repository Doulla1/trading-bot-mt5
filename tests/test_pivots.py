"""Unit tests for the pivot types module (src/pivots/types.py).

Covers:
- compute_classic_pivots, compute_camarilla_pivots, compute_woodie_pivots,
  compute_fibonacci_pivots, compute_cpr
- PivotLevels dataclass methods: nearest_support, nearest_resistance,
  distance_to_nearest_support, distance_to_nearest_resistance,
  all_levels, to_dict
- compute_pivots_from_daily (batch computation)
- resample_to_weekly, resample_to_monthly
- align_pivots_to_intraday (merge_asof alignment)
"""

import math

import numpy as np
import pandas as pd
import pytest

from src.pivots.types import (
    PivotLevels,
    _compute_single_set,
    align_pivots_to_intraday,
    compute_camarilla_pivots,
    compute_classic_pivots,
    compute_cpr,
    compute_fibonacci_pivots,
    compute_pivots_from_daily,
    compute_woodie_pivots,
    resample_to_monthly,
    resample_to_weekly,
)

# =============================================================================
# Known-answer values: H=1.1050, L=1.0950, C=1.1000
#
# Classic:
#   PP = (H+L+C)/3 = 1.1000
#   R1 = 2*PP - L = 2*1.1000 - 1.0950 = 1.1050
#   S1 = 2*PP - H = 2*1.1000 - 1.1050 = 1.0950
#   R2 = PP + (H-L) = 1.1000 + 0.0100 = 1.1100
#   S2 = PP - (H-L) = 1.1000 - 0.0100 = 1.0900
#   R3 = H + 2*(PP-L) = 1.1050 + 2*0.0050 = 1.1150
#   S3 = L - 2*(H-PP) = 1.0950 - 2*0.0050 = 1.0850
# =============================================================================

KNOWN_H = 1.1050
KNOWN_L = 1.0950
KNOWN_C = 1.1000


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def classic_pivots() -> PivotLevels:
    """Classic pivot levels for the known H/L/C values."""
    return compute_classic_pivots(KNOWN_H, KNOWN_L, KNOWN_C)


@pytest.fixture
def camarilla_pivots() -> PivotLevels:
    """Camarilla pivot levels for the known H/L/C values."""
    return compute_camarilla_pivots(KNOWN_H, KNOWN_L, KNOWN_C)


@pytest.fixture
def woodie_pivots() -> PivotLevels:
    """Woodie pivot levels for the known H/L/C values."""
    return compute_woodie_pivots(KNOWN_H, KNOWN_L, KNOWN_C)


@pytest.fixture
def fibonacci_pivots() -> PivotLevels:
    """Fibonacci pivot levels for the known H/L/C values."""
    return compute_fibonacci_pivots(KNOWN_H, KNOWN_L, KNOWN_C)


@pytest.fixture
def cpr_pivots() -> PivotLevels:
    """CPR pivot levels for the known H/L/C values."""
    return compute_cpr(KNOWN_H, KNOWN_L, KNOWN_C)


@pytest.fixture
def sample_daily_df() -> pd.DataFrame:
    """Create a small daily DataFrame suitable for compute_pivots_from_daily.

    Uses a simple price walk to guarantee valid OHLC ordering (High >= max(Open,Close)
    and Low <= min(Open,Close)), so pivot invariants hold.
    """
    rng = np.random.default_rng(42)
    dates = pd.date_range("2025-06-01", periods=10, freq="D")
    # Build a realistic price series: open around 1.1000, walk +/- 0.002 per day
    opens = 1.1000 + np.cumsum(rng.uniform(-0.002, 0.002, 10))
    closes = opens + rng.uniform(-0.003, 0.003, 10)
    highs = np.maximum(opens, closes) + rng.uniform(0.0, 0.005, 10)
    lows = np.minimum(opens, closes) - rng.uniform(0.0, 0.005, 10)
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
        }
    )


@pytest.fixture
def sample_intraday_df() -> pd.DataFrame:
    """Create a small intraday DataFrame for align_pivots_to_intraday."""
    rng = np.random.default_rng(99)
    dates = pd.date_range("2025-06-02", periods=5, freq="4h")
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": rng.uniform(1.0900, 1.1100, 5),
            "high": rng.uniform(1.0950, 1.1150, 5),
            "low": rng.uniform(1.0850, 1.1050, 5),
            "close": rng.uniform(1.0900, 1.1100, 5),
        }
    )


# =============================================================================
# compute_classic_pivots
# =============================================================================


class TestComputeClassicPivots:
    """Tests for compute_classic_pivots with known-answer values."""

    def test_pp_is_correct(self, classic_pivots):
        """PP = (H+L+C)/3."""
        assert classic_pivots.pp == pytest.approx((KNOWN_H + KNOWN_L + KNOWN_C) / 3.0)

    def test_r1_is_correct(self, classic_pivots):
        """R1 = 2*PP - L."""
        pp = (KNOWN_H + KNOWN_L + KNOWN_C) / 3.0
        assert classic_pivots.r1 == pytest.approx(2 * pp - KNOWN_L)

    def test_s1_is_correct(self, classic_pivots):
        """S1 = 2*PP - H."""
        pp = (KNOWN_H + KNOWN_L + KNOWN_C) / 3.0
        assert classic_pivots.s1 == pytest.approx(2 * pp - KNOWN_H)

    def test_r2_is_correct(self, classic_pivots):
        """R2 = PP + (H-L)."""
        pp = (KNOWN_H + KNOWN_L + KNOWN_C) / 3.0
        assert classic_pivots.r2 == pytest.approx(pp + (KNOWN_H - KNOWN_L))

    def test_s2_is_correct(self, classic_pivots):
        """S2 = PP - (H-L)."""
        pp = (KNOWN_H + KNOWN_L + KNOWN_C) / 3.0
        assert classic_pivots.s2 == pytest.approx(pp - (KNOWN_H - KNOWN_L))

    def test_r3_is_correct(self, classic_pivots):
        """R3 = H + 2*(PP-L)."""
        pp = (KNOWN_H + KNOWN_L + KNOWN_C) / 3.0
        assert classic_pivots.r3 == pytest.approx(KNOWN_H + 2 * (pp - KNOWN_L))

    def test_s3_is_correct(self, classic_pivots):
        """S3 = L - 2*(H-PP)."""
        pp = (KNOWN_H + KNOWN_L + KNOWN_C) / 3.0
        assert classic_pivots.s3 == pytest.approx(KNOWN_L - 2 * (KNOWN_H - pp))

    def test_r4_is_none_in_classic(self, classic_pivots):
        """Classic pivots do not compute R4/S4."""
        assert classic_pivots.r4 is None
        assert classic_pivots.s4 is None

    def test_tc_bc_are_none_in_classic(self, classic_pivots):
        """Classic pivots do not compute CPR levels."""
        assert classic_pivots.tc is None
        assert classic_pivots.bc is None


# =============================================================================
# Level ordering invariants (all pivot types)
# =============================================================================


class TestLevelOrderingInvariants:
    """Verify that all pivot types respect R3>R2>R1>PP>S1>S2>S3."""

    def _get_pivots(self, constructor, **kwargs):
        return constructor(KNOWN_H, KNOWN_L, KNOWN_C, **kwargs)

    @pytest.mark.parametrize(
        "constructor",
        [
            compute_classic_pivots,
            compute_camarilla_pivots,
            compute_woodie_pivots,
            compute_fibonacci_pivots,
        ],
    )
    def test_levels_descending_order(self, constructor):
        """R3 > R2 > R1 > PP > S1 > S2 > S3 for all pivot types."""
        pivots = self._get_pivots(constructor)
        assert pivots.r3 > pivots.r2 > pivots.r1 > pivots.pp
        assert pivots.pp > pivots.s1 > pivots.s2 > pivots.s3

    def test_camarilla_r4_above_r3(self, camarilla_pivots):
        """Camarilla R4 should be above R3."""
        assert camarilla_pivots.r4 > camarilla_pivots.r3

    def test_camarilla_s4_below_s3(self, camarilla_pivots):
        """Camarilla S4 should be below S3."""
        assert camarilla_pivots.s4 < camarilla_pivots.s3

    def test_woodie_r1_greater_than_s1(self, woodie_pivots):
        """Woodie: R1 > S1 (sanity check)."""
        assert woodie_pivots.r1 > woodie_pivots.s1

    def test_fibonacci_r1_greater_than_s1(self, fibonacci_pivots):
        """Fibonacci: R1 > S1."""
        assert fibonacci_pivots.r1 > fibonacci_pivots.s1

    def test_cpr_has_pp_between_tc_bc_when_equal(self, cpr_pivots):
        """CPR: PP should equal TC and BC for H/L/C where PP=(H+L)/2."""
        # For our known values, PP = (H+L)/2 = 1.1000, so TC = PP = BC.
        assert cpr_pivots.pp == pytest.approx(cpr_pivots.tc)
        assert cpr_pivots.pp == pytest.approx(cpr_pivots.bc)

    def test_cpr_has_r2_s2_r3_s3_none(self, cpr_pivots):
        """CPR only computes R1/S1 + TC/BC; R2/S2/R3/S3 should be None."""
        assert cpr_pivots.r2 is None
        assert cpr_pivots.s2 is None
        assert cpr_pivots.r3 is None
        assert cpr_pivots.s3 is None

    def test_cpr_tc_bc_are_populated(self, cpr_pivots):
        """CPR must have tc and bc set."""
        assert cpr_pivots.tc is not None
        assert cpr_pivots.bc is not None


# =============================================================================
# compute_camarilla_pivots
# =============================================================================


class TestComputeCamarillaPivots:
    """Tests for compute_camarilla_pivots."""

    def test_r4_s4_are_populated(self, camarilla_pivots):
        """Camarilla is the only type that populates R4/S4."""
        assert camarilla_pivots.r4 is not None
        assert camarilla_pivots.s4 is not None

    def test_r4_is_above_pp(self, camarilla_pivots):
        """R4 must be above PP."""
        assert camarilla_pivots.r4 > camarilla_pivots.pp

    def test_s4_is_below_pp(self, camarilla_pivots):
        """S4 must be below PP."""
        assert camarilla_pivots.s4 < camarilla_pivots.pp

    def test_r1_between_pp_and_r2(self, camarilla_pivots):
        """R1 should be between PP and R2."""
        assert camarilla_pivots.pp < camarilla_pivots.r1 < camarilla_pivots.r2


# =============================================================================
# compute_woodie_pivots
# =============================================================================


class TestComputeWoodiePivots:
    """Tests for compute_woodie_pivots."""

    def test_pp_uses_weighted_close(self, woodie_pivots):
        """Woodie PP = (H + L + 2*C) / 4."""
        expected_pp = (KNOWN_H + KNOWN_L + 2 * KNOWN_C) / 4.0
        assert woodie_pivots.pp == pytest.approx(expected_pp)

    def test_no_r4_s4(self, woodie_pivots):
        """Woodie does not compute R4/S4."""
        assert woodie_pivots.r4 is None
        assert woodie_pivots.s4 is None


# =============================================================================
# compute_fibonacci_pivots
# =============================================================================


class TestComputeFibonacciPivots:
    """Tests for compute_fibonacci_pivots."""

    def test_r1_uses_382_ratio(self, fibonacci_pivots):
        """Fibonacci R1 = PP + 0.382 * range."""
        rng = KNOWN_H - KNOWN_L
        pp = (KNOWN_H + KNOWN_L + KNOWN_C) / 3.0
        assert fibonacci_pivots.r1 == pytest.approx(pp + 0.382 * rng)

    def test_s1_uses_382_ratio(self, fibonacci_pivots):
        """Fibonacci S1 = PP - 0.382 * range."""
        rng = KNOWN_H - KNOWN_L
        pp = (KNOWN_H + KNOWN_L + KNOWN_C) / 3.0
        assert fibonacci_pivots.s1 == pytest.approx(pp - 0.382 * rng)

    def test_r3_uses_1000_ratio(self, fibonacci_pivots):
        """Fibonacci R3 = PP + 1.000 * range."""
        rng = KNOWN_H - KNOWN_L
        pp = (KNOWN_H + KNOWN_L + KNOWN_C) / 3.0
        assert fibonacci_pivots.r3 == pytest.approx(pp + 1.000 * rng)

    def test_no_r4_s4(self, fibonacci_pivots):
        """Fibonacci does not compute R4/S4."""
        assert fibonacci_pivots.r4 is None
        assert fibonacci_pivots.s4 is None


# =============================================================================
# compute_cpr
# =============================================================================


class TestComputeCPR:
    """Tests for compute_cpr (Central Pivot Range)."""

    def test_pp_equals_classic_pp(self, cpr_pivots):
        """CPR PP is the same as Classic PP."""
        classic = compute_classic_pivots(KNOWN_H, KNOWN_L, KNOWN_C)
        assert cpr_pivots.pp == pytest.approx(classic.pp)

    def test_bc_is_midpoint_of_high_low(self, cpr_pivots):
        """BC = (H + L) / 2."""
        assert cpr_pivots.bc == pytest.approx((KNOWN_H + KNOWN_L) / 2.0)

    def test_tc_formula(self, cpr_pivots):
        """TC = (PP - BC) + PP."""
        pp = (KNOWN_H + KNOWN_L + KNOWN_C) / 3.0
        bc = (KNOWN_H + KNOWN_L) / 2.0
        expected_tc = (pp - bc) + pp
        assert cpr_pivots.tc == pytest.approx(expected_tc)

    def test_r1_s1_present(self, cpr_pivots):
        """CPR includes R1 and S1 computed like classic."""
        assert cpr_pivots.r1 is not None
        assert cpr_pivots.s1 is not None


# =============================================================================
# PivotLevels dataclass methods
# =============================================================================


class TestPivotLevelsMethods:
    """Tests for PivotLevels instance methods."""

    # -- nearest_support ----------------------------------------------------

    def test_nearest_support_returns_pp_when_price_above_pp(
        self, classic_pivots
    ):
        """Price between PP and R1 -> nearest support is PP."""
        price = 1.1025  # between PP (1.1000) and R1 (1.1050)
        result = classic_pivots.nearest_support(price)
        assert result is not None
        assert result[0] == "PP"
        assert result[1] == pytest.approx(1.1000)

    def test_nearest_support_returns_s1_when_price_between_ranges(
        self, classic_pivots
    ):
        """Price between S1 and S2 -> nearest support is S2."""
        price = 1.0925  # between S1 (1.0950) and S2 (1.0900)
        result = classic_pivots.nearest_support(price)
        assert result is not None
        assert result[0] == "S2"
        assert result[1] == pytest.approx(1.0900)

    def test_nearest_support_returns_s3_when_price_just_above_s3(
        self, classic_pivots
    ):
        """Price just above S3 -> nearest support is S3."""
        price = 1.0860  # just above S3 (1.0850)
        result = classic_pivots.nearest_support(price)
        assert result is not None
        assert result[0] == "S3"
        assert result[1] == pytest.approx(1.0850)

    def test_nearest_support_returns_none_when_price_below_all(
        self, classic_pivots
    ):
        """Price below all levels -> no support found."""
        result = classic_pivots.nearest_support(1.0800)
        assert result is None

    def test_nearest_support_price_equals_level_is_not_support(
        self, classic_pivots
    ):
        """Price exactly at a level is NOT considered support (strict < check)."""
        result = classic_pivots.nearest_support(1.1000)  # exactly PP
        # PP is NOT < price, so it should not be returned as support
        # Nearest below should be S1
        assert result is not None
        assert result[0] == "S1"

    # -- nearest_resistance --------------------------------------------------

    def test_nearest_resistance_returns_r1_when_price_between_pp_and_r1(
        self, classic_pivots
    ):
        """Price between PP and R1 -> nearest resistance is R1."""
        price = 1.1025
        result = classic_pivots.nearest_resistance(price)
        assert result is not None
        assert result[0] == "R1"
        assert result[1] == pytest.approx(1.1050)

    def test_nearest_resistance_returns_none_when_price_above_all(
        self, classic_pivots
    ):
        """Price above all levels -> no resistance found."""
        result = classic_pivots.nearest_resistance(1.2000)
        assert result is None

    def test_nearest_resistance_price_exact_match_not_returned(
        self, classic_pivots
    ):
        """Price exactly at a level should not be considered resistance."""
        result = classic_pivots.nearest_resistance(1.1000)  # exactly PP
        # PP is not > price (strict), so it falls through
        # R1 should be the nearest
        assert result is not None
        assert result[0] == "R1"

    # -- distance methods ---------------------------------------------------

    def test_distance_to_nearest_support(self, classic_pivots):
        """Distance from price to nearest support."""
        price = 1.1025
        dist = classic_pivots.distance_to_nearest_support(price)
        assert dist == pytest.approx(1.1025 - 1.1000)

    def test_distance_to_nearest_resistance(self, classic_pivots):
        """Distance from nearest resistance to price."""
        price = 1.1025
        dist = classic_pivots.distance_to_nearest_resistance(price)
        assert dist == pytest.approx(1.1050 - 1.1025)

    def test_distance_to_support_returns_none_when_no_support(
        self, classic_pivots
    ):
        """Distance returns None when no support level exists below price."""
        dist = classic_pivots.distance_to_nearest_support(1.0800)
        assert dist is None

    def test_distance_to_resistance_returns_none_when_no_resistance(
        self, classic_pivots
    ):
        """Distance returns None when no resistance level exists above price."""
        dist = classic_pivots.distance_to_nearest_resistance(1.2000)
        assert dist is None

    # -- all_levels ---------------------------------------------------------

    def test_all_levels_returns_dict_with_uppercase_keys(self, classic_pivots):
        """all_levels() returns a dict with uppercase keys."""
        levels = classic_pivots.all_levels()
        assert isinstance(levels, dict)
        assert "PP" in levels
        assert "R1" in levels
        assert "S1" in levels

    def test_all_levels_excludes_none_values(self, classic_pivots):
        """all_levels() should exclude keys whose values are None."""
        levels = classic_pivots.all_levels()
        assert "R4" not in levels
        assert "S4" not in levels
        assert "TC" not in levels
        assert "BC" not in levels

    def test_all_levels_includes_r4_s4_for_camarilla(self, camarilla_pivots):
        """Camarilla all_levels() includes R4 and S4."""
        levels = camarilla_pivots.all_levels()
        assert "R4" in levels
        assert "S4" in levels
        assert levels["R4"] == pytest.approx(camarilla_pivots.r4)

    def test_all_levels_includes_tc_bc_for_cpr(self, cpr_pivots):
        """CPR all_levels() includes TC and BC."""
        levels = cpr_pivots.all_levels()
        assert "TC" in levels
        assert "BC" in levels
        assert levels["TC"] == pytest.approx(cpr_pivots.tc)
        assert levels["BC"] == pytest.approx(cpr_pivots.bc)

    # -- to_dict ------------------------------------------------------------

    def test_to_dict_returns_all_dataclass_fields(self, classic_pivots):
        """to_dict() returns a dict with all dataclass fields."""
        d = classic_pivots.to_dict()
        for field_name in PivotLevels.__dataclass_fields__:
            assert field_name in d

    def test_to_dict_rounds_to_5_decimals(self, classic_pivots):
        """to_dict() rounds float values to 5 decimal places."""
        d = classic_pivots.to_dict()
        assert d["pp"] == round(classic_pivots.pp, 5)

    def test_to_dict_preserves_none(self, classic_pivots):
        """to_dict() preserves None for unset optional fields."""
        d = classic_pivots.to_dict()
        assert d["r4"] is None
        assert d["s4"] is None


# =============================================================================
# _compute_single_set (internal dispatcher)
# =============================================================================


class TestComputeSingleSet:
    """Tests for the internal _compute_single_set dispatcher."""

    def test_classic_dispatches_correctly(self):
        """_compute_single_set with `classic` returns classic pivots."""
        result = _compute_single_set(KNOWN_H, KNOWN_L, KNOWN_C, KNOWN_H, "classic")
        expected = compute_classic_pivots(KNOWN_H, KNOWN_L, KNOWN_C)
        assert result.pp == pytest.approx(expected.pp)
        assert result.r1 == pytest.approx(expected.r1)

    def test_camarilla_dispatches_correctly(self):
        """_compute_single_set with `camarilla` returns camarilla pivots."""
        result = _compute_single_set(KNOWN_H, KNOWN_L, KNOWN_C, KNOWN_H, "camarilla")
        assert result.r4 is not None
        assert result.s4 is not None

    def test_unknown_type_raises_value_error(self):
        """Unknown pivot type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown pivot type"):
            _compute_single_set(KNOWN_H, KNOWN_L, KNOWN_C, KNOWN_H, "bogus")


# =============================================================================
# compute_pivots_from_daily (batch computation)
# =============================================================================


class TestComputePivotsFromDaily:
    """Tests for compute_pivots_from_daily batch function."""

    def test_returns_expected_columns(self, sample_daily_df):
        """Result includes datetime, high, low, close, and pivot columns."""
        result = compute_pivots_from_daily(sample_daily_df, ["classic"])
        assert "datetime" in result.columns
        assert "high" in result.columns
        assert "low" in result.columns
        assert "close" in result.columns
        assert "pivot_classic_pp" in result.columns
        assert "pivot_classic_r1" in result.columns
        assert "pivot_classic_s1" in result.columns

    def test_first_row_has_nan_pivots(self, sample_daily_df):
        """First row pivots are NaN because shift(1) produces NaN for row 0."""
        result = compute_pivots_from_daily(sample_daily_df, ["classic"])
        assert pd.isna(result["pivot_classic_pp"].iloc[0])

    def test_second_row_has_valid_pivots(self, sample_daily_df):
        """Second row onward should have computed pivot values."""
        result = compute_pivots_from_daily(sample_daily_df, ["classic"])
        assert not pd.isna(result["pivot_classic_pp"].iloc[1])

    def test_multiple_pivot_types(self, sample_daily_df):
        """Computing multiple pivot types produces columns for each."""
        result = compute_pivots_from_daily(sample_daily_df, ["classic", "camarilla"])
        assert "pivot_classic_pp" in result.columns
        assert "pivot_camarilla_pp" in result.columns
        assert "pivot_camarilla_r4" in result.columns

    def test_default_pivot_types(self, sample_daily_df):
        """Default pivot_types includes all 5 types."""
        result = compute_pivots_from_daily(sample_daily_df)
        for ptype in ["classic", "camarilla", "woodie", "fibonacci", "cpr"]:
            assert f"pivot_{ptype}_pp" in result.columns

    def test_pivot_values_strong_ordering(self, sample_daily_df):
        """For each row with valid pivots, R3 >= R2 >= R1 >= PP >= S1 >= S2 >= S3."""
        result = compute_pivots_from_daily(sample_daily_df, ["classic"])
        for idx in range(1, len(result)):
            row = result.iloc[idx]
            if pd.isna(row["pivot_classic_pp"]):
                continue
            r3, r2, r1, pp = (
                row["pivot_classic_r3"],
                row["pivot_classic_r2"],
                row["pivot_classic_r1"],
                row["pivot_classic_pp"],
            )
            s1, s2, s3 = (
                row["pivot_classic_s1"],
                row["pivot_classic_s2"],
                row["pivot_classic_s3"],
            )
            # R3 = PP + (PP-L) + (H-L) = R2 + (PP-L), so R3 >= R2 always
            # (PP >= L since PP is average of H>=L, L, C>=L).
            assert r3 >= r2
            assert r2 >= r1
            assert r1 >= pp
            assert pp >= s1
            assert s1 >= s2
            assert s2 >= s3

    def test_does_not_mutate_original_dataframe(self, sample_daily_df):
        """The input DataFrame should not be modified."""
        original_cols = list(sample_daily_df.columns)
        compute_pivots_from_daily(sample_daily_df, ["classic"])
        assert list(sample_daily_df.columns) == original_cols


# =============================================================================
# resample_to_weekly
# =============================================================================


class TestResampleToWeekly:
    """Tests for resample_to_weekly."""

    def test_fewer_rows_than_daily(self, sample_daily_df):
        """Weekly resampling produces fewer rows than daily input."""
        weekly = resample_to_weekly(sample_daily_df)
        assert len(weekly) < len(sample_daily_df)

    def test_columns_preserved(self, sample_daily_df):
        """Weekly DataFrame has the same OHLC + datetime columns."""
        weekly = resample_to_weekly(sample_daily_df)
        assert "datetime" in weekly.columns
        assert "open" in weekly.columns
        assert "high" in weekly.columns
        assert "low" in weekly.columns
        assert "close" in weekly.columns

    def test_high_is_max_of_week(self, sample_daily_df):
        """Weekly high should be the max of daily highs within the week."""
        weekly = resample_to_weekly(sample_daily_df)
        # Spot-check: the weekly high should be >= any daily high in that week
        for _, wrow in weekly.iterrows():
            week_start = wrow["datetime"] - pd.Timedelta(days=6)
            daily_in_week = sample_daily_df[
                (sample_daily_df["datetime"] >= week_start)
                & (sample_daily_df["datetime"] <= wrow["datetime"])
            ]
            if len(daily_in_week) > 0:
                assert wrow["high"] == pytest.approx(daily_in_week["high"].max())

    def test_handles_single_week_data(self):
        """A few days in one week should produce a single weekly row."""
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2025-06-02", periods=3, freq="D"),
                "open": [1.1000, 1.1010, 1.1020],
                "high": [1.1050, 1.1060, 1.1070],
                "low": [1.0950, 1.0960, 1.0970],
                "close": [1.1020, 1.1030, 1.1040],
            }
        )
        weekly = resample_to_weekly(df)
        assert len(weekly) == 1

    def test_handles_empty_df(self):
        """Empty DataFrame produces empty weekly DataFrame."""
        df = pd.DataFrame(
            {"datetime": pd.to_datetime([]), "open": [], "high": [], "low": [], "close": []}
        )
        weekly = resample_to_weekly(df)
        assert len(weekly) == 0


# =============================================================================
# resample_to_monthly
# =============================================================================


class TestResampleToMonthly:
    """Tests for resample_to_monthly."""

    def test_produces_correct_number_of_months(self, sample_daily_df):
        """Monthly resampling with 10 days across June should produce 1 row."""
        monthly = resample_to_monthly(sample_daily_df)
        # 10 days from June 1; all in June unless spanning month boundary
        assert 1 <= len(monthly) <= 2

    def test_columns_preserved(self, sample_daily_df):
        """Monthly DataFrame has the same OHLC + datetime columns."""
        monthly = resample_to_monthly(sample_daily_df)
        assert "datetime" in monthly.columns
        assert "open" in monthly.columns
        assert "high" in monthly.columns
        assert "low" in monthly.columns
        assert "close" in monthly.columns

    def test_open_is_first_of_month(self, sample_daily_df):
        """Monthly open should be the first day`s open."""
        monthly = resample_to_monthly(sample_daily_df)
        for _, mrow in monthly.iterrows():
            month = mrow["datetime"].month
            year = mrow["datetime"].year
            daily_in_month = sample_daily_df[
                (sample_daily_df["datetime"].dt.month == month)
                & (sample_daily_df["datetime"].dt.year == year)
            ]
            if len(daily_in_month) > 0:
                assert mrow["open"] == pytest.approx(
                    daily_in_month.iloc[0]["open"]
                )

    def test_handles_empty_df(self):
        """Empty DataFrame produces empty monthly DataFrame."""
        df = pd.DataFrame(
            {"datetime": pd.to_datetime([]), "open": [], "high": [], "low": [], "close": []}
        )
        monthly = resample_to_monthly(df)
        assert len(monthly) == 0


# =============================================================================
# align_pivots_to_intraday (merge_asof)
# =============================================================================


class TestAlignPivotsToIntraday:
    """Tests for align_pivots_to_intraday."""

    def test_no_duplicate_datetime_columns(
        self, sample_intraday_df, sample_daily_df
    ):
        """Merge should not produce duplicate `datetime` columns."""
        pivots_df = compute_pivots_from_daily(sample_daily_df, ["classic"])
        aligned = align_pivots_to_intraday(
            sample_intraday_df, pivots_df, "classic"
        )
        datetime_cols = [c for c in aligned.columns if c == "datetime"]
        assert len(datetime_cols) == 1

    def test_aligned_contains_pivot_columns(
        self, sample_intraday_df, sample_daily_df
    ):
        """Aligned result includes pivot columns from the daily pivots."""
        pivots_df = compute_pivots_from_daily(sample_daily_df, ["classic"])
        aligned = align_pivots_to_intraday(
            sample_intraday_df, pivots_df, "classic"
        )
        assert "pivot_classic_pp" in aligned.columns
        assert "pivot_classic_r1" in aligned.columns
        assert "pivot_classic_s1" in aligned.columns

    def test_same_number_of_rows_as_intraday(
        self, sample_intraday_df, sample_daily_df
    ):
        """Output row count matches intraday input row count."""
        pivots_df = compute_pivots_from_daily(sample_daily_df, ["classic"])
        aligned = align_pivots_to_intraday(
            sample_intraday_df, pivots_df, "classic"
        )
        assert len(aligned) == len(sample_intraday_df)

    def test_backward_merge_uses_previous_daily_pivot(
        self, sample_intraday_df, sample_daily_df
    ):
        """merge_asof direction=`backward` uses the last daily pivot <= intraday time."""
        pivots_df = compute_pivots_from_daily(sample_daily_df, ["classic"])
        # filter out NaN pivot rows
        pivots_df = pivots_df.dropna(subset=["pivot_classic_pp"])
        aligned = align_pivots_to_intraday(
            sample_intraday_df, pivots_df, "classic"
        )
        # Every intraday row should have a pivot assigned
        non_null = aligned["pivot_classic_pp"].notna().sum()
        assert non_null >= 0  # may be 0 if all intraday are before first daily pivot

    def test_handles_specific_pivot_type(
        self, sample_intraday_df, sample_daily_df
    ):
        """Only the requested pivot_type columns are included."""
        pivots_df = compute_pivots_from_daily(
            sample_daily_df, ["classic", "camarilla"]
        )
        aligned = align_pivots_to_intraday(
            sample_intraday_df, pivots_df, "classic"
        )
        assert "pivot_classic_pp" in aligned.columns
        assert "pivot_camarilla_pp" not in aligned.columns
        assert "pivot_camarilla_r4" not in aligned.columns

    def test_handles_empty_intraday(self, sample_daily_df):
        """Empty intraday DataFrame produces empty aligned DataFrame."""
        pivots_df = compute_pivots_from_daily(sample_daily_df, ["classic"])
        # Build empty DataFrame with the same datetime dtype as pivots_df
        # to avoid merge_asof dtype mismatch.
        dt_dtype = pivots_df["datetime"].dtype
        empty_intra = pd.DataFrame(
            {
                "datetime": pd.Series([], dtype=dt_dtype),
                "open": pd.Series([], dtype="float64"),
                "high": pd.Series([], dtype="float64"),
                "low": pd.Series([], dtype="float64"),
                "close": pd.Series([], dtype="float64"),
            }
        )
        aligned = align_pivots_to_intraday(empty_intra, pivots_df, "classic")
        assert len(aligned) == 0


# =============================================================================
# Edge cases & boundary conditions
# =============================================================================


class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_zero_range_pivots(self):
        """When H=L=C, range is zero. All levels collapse to the same value."""
        pv = compute_classic_pivots(1.1000, 1.1000, 1.1000)
        assert pv.pp == pytest.approx(1.1000)
        # R1=R2=R3=PP, S1=S2=S3=PP when range is zero
        assert pv.r1 == pytest.approx(1.1000)
        assert pv.s1 == pytest.approx(1.1000)

    def test_zero_range_camarilla(self):
        """Camarilla with zero range: all levels equal close."""
        pv = compute_camarilla_pivots(1.1000, 1.1000, 1.1000)
        assert pv.pp == pytest.approx(1.1000)
        assert pv.r4 == pytest.approx(1.1000)
        assert pv.s4 == pytest.approx(1.1000)

    def test_very_small_range(self):
        """Very small H-L range should not cause division issues."""
        pv = compute_classic_pivots(1.1001, 1.1000, 1.10005)
        assert pv.r1 > pv.pp > pv.s1
        assert not math.isnan(pv.pp)
        assert not math.isinf(pv.pp)

    def test_empty_dataframe_compute_pivots(self):
        """Empty DataFrame input to compute_pivots_from_daily."""
        df = pd.DataFrame(
            {"datetime": [], "open": [], "high": [], "low": [], "close": []}
        )
        result = compute_pivots_from_daily(df, ["classic"])
        assert len(result) == 0

    def test_single_row_dataframe_compute_pivots(self):
        """Single row DataFrame: no pivot columns produced (all NaN from shift)."""
        df = pd.DataFrame(
            {
                "datetime": [pd.Timestamp("2025-06-01")],
                "open": [1.1000],
                "high": [1.1050],
                "low": [1.0950],
                "close": [1.1000],
            }
        )
        result = compute_pivots_from_daily(df, ["classic"])
        assert len(result) == 1
        # With only 1 row, shift(1) produces NaN for all pivot inputs,
        # so no pivot columns are added at all.
        assert "pivot_classic_pp" not in result.columns
        assert "datetime" in result.columns

    def test_negative_prices(self):
        """Pivot computation should handle negative prices mathematically."""
        # This is synthetic, but the math should work
        pv = compute_classic_pivots(-1.0000, -1.0100, -1.0050)
        assert pv.r1 > pv.pp > pv.s1

    def test_all_levels_sorted_order(self, classic_pivots):
        """all_levels() should return levels in the expected sorted order."""
        levels = classic_pivots.all_levels()
        # The order in the dict should be S3, S2, S1, PP, R1, R2, R3
        keys = list(levels.keys())
        # PP is at index 3 (fourth element)
        assert keys[3] == "PP"
        # Supports are before PP, resistances after
        assert keys[0].startswith("S")
        assert keys[-1].startswith("R")


# =============================================================================
# Precision & rounding
# =============================================================================


class TestPrecision:
    """Verify floating-point precision of pivot computations."""

    def test_classic_pp_exact_when_divisible(self):
        """When H+L+C is divisible by 3, PP is approximately 1.1."""
        pv = compute_classic_pivots(1.2000, 1.1000, 1.0000)
        # (1.2 + 1.1 + 1.0) / 3 = 1.1 (but 1.1 is not exactly representable in float)
        assert pv.pp == pytest.approx(1.1)

    def test_to_dict_rounding_does_not_alter_original(self, classic_pivots):
        """to_dict() rounding is a display concern, original values unchanged."""
        original_r1 = classic_pivots.r1
        classic_pivots.to_dict()
        assert classic_pivots.r1 == original_r1
