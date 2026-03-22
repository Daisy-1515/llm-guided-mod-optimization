"""Tests for edge_uav.model.propulsion module."""

import math
import pytest
from edge_uav.model.propulsion import (
    propulsion_power,
    flight_energy_per_slot,
    total_flight_energy,
)

# Default propulsion parameters (from config.py)
PROP = dict(eta_1=79.86, eta_2=88.63, eta_3=0.0151, eta_4=0.0048, v_tip=120.0)


class TestPropulsionPower:
    """Tests for propulsion_power (Eq.18)."""

    def test_hover_power(self):
        """v=0 → hover power = η₁ + η₂√(√η₃), no drag term."""
        p = propulsion_power(0.0, **PROP)
        # η₁ + η₂ * sqrt(sqrt(0.0151)) = 79.86 + 88.63 * sqrt(0.12288..)
        expected = 79.86 + 88.63 * math.sqrt(math.sqrt(0.0151))
        assert p == pytest.approx(expected, rel=1e-10)
        # Sanity: should be around 110.9 W
        assert 110.0 < p < 112.0

    def test_known_speed(self):
        """v=10 m/s → hand-calculated verification."""
        v = 10.0
        v_sq = v * v  # 100

        # term1 = 79.86 * (1 + 3*100/14400) = 79.86 * 1.02083.. ≈ 81.523
        term1 = 79.86 * (1.0 + 3.0 * v_sq / (120.0 ** 2))

        # term2: inner = sqrt(0.0151 + 100^2/4) - 100/2
        #       = sqrt(0.0151 + 2500) - 50 = sqrt(2500.0151) - 50
        #       ≈ 50.00001510 - 50 = 0.00001510
        # term2 = 88.63 * sqrt(0.00001510) ≈ 88.63 * 0.003886 ≈ 0.3443
        inner = math.sqrt(0.0151 + v_sq ** 2 / 4.0) - v_sq / 2.0
        term2 = 88.63 * math.sqrt(inner)

        # term3 = 0.0048 * 100 * 10 = 4.8
        term3 = 0.0048 * v_sq * math.sqrt(v_sq)

        expected = term1 + term2 + term3
        p = propulsion_power(v_sq, **PROP)
        assert p == pytest.approx(expected, rel=1e-10)

    def test_u_shaped_power_curve(self):
        """Rotorcraft power curve is U-shaped: high at hover, dips, then rises."""
        speeds = [0, 5, 10, 15, 20, 25, 30]
        powers = [propulsion_power(v * v, **PROP) for v in speeds]

        # Hover power should be higher than some mid-range speed
        p_hover = powers[0]
        p_min = min(powers)
        assert p_hover > p_min, "Hover should not be the minimum power"

        # At high speeds (>= 20 m/s), power should increase monotonically
        high_speed_powers = [propulsion_power(v * v, **PROP) for v in [20, 25, 30]]
        for i in range(len(high_speed_powers) - 1):
            assert high_speed_powers[i] < high_speed_powers[i + 1]


class TestFlightEnergy:
    """Tests for flight_energy_per_slot and total_flight_energy."""

    def test_stationary_uav(self):
        """UAV stays at same position → all slots get hover energy."""
        q_j = {0: (100.0, 200.0), 1: (100.0, 200.0), 2: (100.0, 200.0)}
        delta = 1.0
        energies = flight_energy_per_slot(q_j, delta, **PROP)

        hover_power = propulsion_power(0.0, **PROP)
        for t, e in energies.items():
            assert e == pytest.approx(hover_power * delta, rel=1e-10)

    def test_flight_energy_moving(self):
        """UAV moves 10m/slot → v=10m/s, energy = P(100)*δ per slot."""
        q_j = {0: (0.0, 0.0), 1: (10.0, 0.0), 2: (20.0, 0.0)}
        delta = 1.0
        energies = flight_energy_per_slot(q_j, delta, **PROP)

        p_moving = propulsion_power(100.0, **PROP)  # v_sq = 10^2
        hover_p = propulsion_power(0.0, **PROP)

        assert energies[0] == pytest.approx(p_moving * delta, rel=1e-10)
        assert energies[1] == pytest.approx(p_moving * delta, rel=1e-10)
        assert energies[2] == pytest.approx(hover_p * delta, rel=1e-10)  # last slot

    def test_total_flight_energy(self):
        """Multi-UAV: each UAV has independent total energy."""
        q = {
            0: {0: (0.0, 0.0), 1: (10.0, 0.0), 2: (20.0, 0.0)},
            1: {0: (50.0, 50.0), 1: (50.0, 50.0), 2: (50.0, 50.0)},
        }
        delta = 1.0
        totals = total_flight_energy(q, delta, **PROP)

        # UAV 0: 2 moving slots + 1 hover slot
        e0_slots = flight_energy_per_slot(q[0], delta, **PROP)
        assert totals[0] == pytest.approx(sum(e0_slots.values()), rel=1e-10)

        # UAV 1: all stationary
        hover_power = propulsion_power(0.0, **PROP)
        assert totals[1] == pytest.approx(3 * hover_power * delta, rel=1e-10)

        # UAV 0 (moving at 10m/s) uses less energy than UAV 1 (hovering)
        # because the U-shaped power curve means hover is more expensive
        # than moderate-speed flight
        assert totals[0] < totals[1]
