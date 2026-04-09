"""S2 单元测试 — 预计算模块物理纯函数。

覆盖 5 个函数 × (正常值手算对照 + 边界兜底) 场景。
手算参考值来源: 文档/A3_precompute_impl_plan.md §S2。
"""

import math

from edge_uav.model.precompute import (
    _channel_gain,
    _rate_from_gain,
    _rate_from_gain_sinr,
    _local_delay,
    _offload_delay,
    _edge_energy,
)

# 通用数值保护参数
EPS_DIST_SQ = 1e-12
EPS_RATE = 1e-12
EPS_FREQ = 1e-12
BIG_M = 1e6


# =====================================================================
# _channel_gain
# =====================================================================

class TestChannelGain:
    """空地信道增益 g = rho_0 / max(H^2 + ||pos_i - q_jt||^2, eps)。"""

    def test_normal_manual_reference(self):
        """手算: pos=(200,300), q=(500,500), H=100 → denom=140000, g=7.142857e-11。"""
        gain = _channel_gain(
            (200.0, 300.0), (500.0, 500.0),
            H=100.0, rho_0=1e-5, eps_dist_sq=EPS_DIST_SQ,
        )
        expected = 1e-5 / 140_000.0
        assert abs(gain - expected) < 1e-18

    def test_directly_above(self):
        """UAV 在终端正上方: dist_sq=0, denom=H^2=10000。"""
        gain = _channel_gain(
            (500.0, 500.0), (500.0, 500.0),
            H=100.0, rho_0=1e-5, eps_dist_sq=EPS_DIST_SQ,
        )
        expected = 1e-5 / 10_000.0
        assert abs(gain - expected) < 1e-18

    def test_eps_floor_prevents_infinity(self):
        """H=0 且 pos_i==q_jt → dist_sq=0, denom 被 eps 兜底。"""
        gain = _channel_gain(
            (123.0, 456.0), (123.0, 456.0),
            H=0.0, rho_0=1e-5, eps_dist_sq=1e-6,
        )
        expected = 1e-5 / 1e-6  # = 10.0
        assert math.isfinite(gain)
        assert abs(gain - expected) < 1e-9


# =====================================================================
# _rate_from_gain
# =====================================================================

class TestRateFromGain:
    """Shannon 速率 r = B * log1p(P*g/N0) / ln(2)。"""

    def test_normal_manual_reference(self):
        """手算: g=7.142857e-11, B=1e6, P=0.5, N0=1e-10 → ~440691 bps。"""
        gain = 1e-5 / 140_000.0
        rate = _rate_from_gain(
            gain, bandwidth=1e6, tx_power=0.5,
            noise_power=1e-10, eps_rate=EPS_RATE,
        )
        snr = 0.5 * gain / 1e-10
        expected = 1e6 * math.log1p(snr) / math.log(2.0)
        assert abs(rate - expected) < 1e-6

    def test_uses_log1p_precision(self):
        """极小 SNR (1e-15) 时 log1p 仍返回正值，log2(1+x) 会丢精度。"""
        tiny_gain = 1e-20
        rate = _rate_from_gain(
            tiny_gain, bandwidth=1e6, tx_power=0.5,
            noise_power=1e-10, eps_rate=EPS_RATE,
        )
        assert rate > 0

    def test_eps_rate_floor(self):
        """gain=0 → rate=0 → 兜底返回 eps_rate。"""
        rate = _rate_from_gain(
            0.0, bandwidth=1e6, tx_power=0.5,
            noise_power=1e-10, eps_rate=42.0,
        )
        assert rate == 42.0

    def test_kwargs_enforced(self):
        """bandwidth 以后的参数必须用关键字传递。"""
        try:
            _rate_from_gain(1e-10, 1e6, 0.5, 1e-10, 1e-12)
            assert False, "应当抛出 TypeError"
        except TypeError:
            pass


# =====================================================================
# _rate_from_gain_sinr
# =====================================================================

class TestRateFromGainSinr:
    """SINR 速率 r = B * log1p(P*g/(N0+I)) / ln(2)。"""

    def test_zero_interference_equals_snr(self):
        """interference=0 时应与 _rate_from_gain 结果完全一致。"""
        gain = 1e-5 / 140_000.0
        rate_snr = _rate_from_gain(
            gain, bandwidth=1e6, tx_power=0.5,
            noise_power=1e-10, eps_rate=EPS_RATE,
        )
        rate_sinr = _rate_from_gain_sinr(
            gain, bandwidth=1e6, tx_power=0.5,
            noise_power=1e-10, interference=0.0, eps_rate=EPS_RATE,
        )
        assert abs(rate_sinr - rate_snr) < 1e-9

    def test_nonzero_interference_lowers_rate(self):
        """加入干扰后速率应严格低于纯 SNR 速率。"""
        gain = 1e-5 / 140_000.0
        rate_snr = _rate_from_gain(
            gain, bandwidth=1e6, tx_power=0.5,
            noise_power=1e-10, eps_rate=EPS_RATE,
        )
        rate_sinr = _rate_from_gain_sinr(
            gain, bandwidth=1e6, tx_power=0.5,
            noise_power=1e-10, interference=1e-10, eps_rate=EPS_RATE,
        )
        assert rate_sinr < rate_snr

    def test_manual_reference(self):
        """手算: g=7.142857e-11, I=N0=1e-10, SINR=P*g/(N0+I)=P*g/(2*N0)。"""
        gain = 1e-5 / 140_000.0
        p, b, n0 = 0.5, 1e6, 1e-10
        sinr = p * gain / (n0 + n0)           # I = N0
        expected = b * math.log1p(sinr) / math.log(2.0)
        rate = _rate_from_gain_sinr(
            gain, bandwidth=b, tx_power=p,
            noise_power=n0, interference=n0, eps_rate=EPS_RATE,
        )
        assert abs(rate - expected) < 1e-6

    def test_large_interference_hits_eps_floor(self):
        """干扰极大时 SINR→0，速率兜底到 eps_rate。"""
        rate = _rate_from_gain_sinr(
            1e-20, bandwidth=1e6, tx_power=0.5,
            noise_power=1e-10, interference=1e10, eps_rate=42.0,
        )
        assert rate == 42.0


# =====================================================================
# _local_delay
# =====================================================================

class TestLocalDelay:
    """本地时延 D = workload / freq。"""

    def test_normal_value(self):
        """3e9 cycles / 1.5e9 Hz = 2.0 s。"""
        delay = _local_delay(3e9, 1.5e9, eps_freq=EPS_FREQ, big_m_delay=BIG_M)
        assert abs(delay - 2.0) < 1e-12

    def test_zero_freq_returns_big_m(self):
        """freq=0 → 返回 big_m_delay。"""
        delay = _local_delay(3e9, 0.0, eps_freq=EPS_FREQ, big_m_delay=999.0)
        assert delay == 999.0

    def test_near_zero_freq_returns_big_m(self):
        """freq 极小但非零（< eps_freq）→ 返回 big_m_delay。"""
        delay = _local_delay(3e9, 1e-20, eps_freq=EPS_FREQ, big_m_delay=BIG_M)
        assert delay == BIG_M


# =====================================================================
# _offload_delay
# =====================================================================

class TestOffloadDelay:
    """远程卸载总时延 = T_up + T_comp + T_down。"""

    def test_normal_value(self):
        """手算: D_l/r_up + workload/f_edge + D_r/r_down = 0.5 + 2.0 + 0.25 = 2.75。"""
        delay = _offload_delay(
            D_l=2e6, D_r=5e5, workload=4e9,
            r_up=4e6, r_down=2e6, f_edge=2e9,
            eps_rate=EPS_RATE, eps_freq=EPS_FREQ, big_m_delay=BIG_M,
        )
        expected = (2e6 / 4e6) + (4e9 / 2e9) + (5e5 / 2e6)
        assert abs(delay - expected) < 1e-9

    def test_zero_uplink_rate_returns_big_m(self):
        """r_up=0 → T_up 爆大 → 封顶 big_m_delay。"""
        delay = _offload_delay(
            D_l=1e6, D_r=1e5, workload=1e9,
            r_up=0.0, r_down=1e6, f_edge=1e9,
            eps_rate=EPS_RATE, eps_freq=EPS_FREQ, big_m_delay=100.0,
        )
        assert delay == 100.0

    def test_zero_f_edge_returns_big_m(self):
        """f_edge=0 → T_comp 爆大 → 封顶 big_m_delay。"""
        delay = _offload_delay(
            D_l=1e6, D_r=1e5, workload=1e9,
            r_up=1e6, r_down=1e6, f_edge=0.0,
            eps_rate=EPS_RATE, eps_freq=EPS_FREQ, big_m_delay=100.0,
        )
        assert delay == 100.0

    def test_large_total_capped_at_big_m(self):
        """三段之和超过 big_m → 封顶。"""
        delay = _offload_delay(
            D_l=1e6, D_r=1e6, workload=1e9,
            r_up=1e3, r_down=1e3, f_edge=1e6,
            eps_rate=EPS_RATE, eps_freq=EPS_FREQ, big_m_delay=10.0,
        )
        assert delay == 10.0

    def test_t_up_dominant(self):
        """上行主导: r_up 极小，其余正常。验证各阶段累加逻辑。"""
        delay = _offload_delay(
            D_l=1e6, D_r=100.0, workload=1e6,
            r_up=100.0, r_down=1e9, f_edge=1e9,
            eps_rate=EPS_RATE, eps_freq=EPS_FREQ, big_m_delay=BIG_M,
        )
        t_up = 1e6 / 100.0   # = 10000
        t_comp = 1e6 / 1e9   # ≈ 0.001
        t_down = 100.0 / 1e9  # ≈ 1e-7
        expected = t_up + t_comp + t_down
        assert abs(delay - expected) < 1e-6


# =====================================================================
# _edge_energy
# =====================================================================

class TestEdgeEnergy:
    """边缘能耗 E = gamma_j * f_edge^2 * workload。"""

    def test_normal_value(self):
        """手算: 1e-28 * (2e9)^2 * 5e8 = 1e-28 * 4e18 * 5e8 = 0.2。"""
        energy = _edge_energy(
            gamma_j=1e-28, f_edge=2e9, workload=5e8,
            eps_freq=EPS_FREQ,
        )
        assert abs(energy - 0.2) < 1e-9

    def test_zero_freq_returns_zero(self):
        """f_edge=0 → 不计算 → 能耗 0.0。"""
        energy = _edge_energy(
            gamma_j=1e-28, f_edge=0.0, workload=5e8,
            eps_freq=EPS_FREQ,
        )
        assert energy == 0.0

    def test_near_zero_freq_returns_zero(self):
        """f_edge 极小（< eps_freq）→ 返回 0.0。"""
        energy = _edge_energy(
            gamma_j=1e-28, f_edge=1e-20, workload=5e8,
            eps_freq=EPS_FREQ,
        )
        assert energy == 0.0
