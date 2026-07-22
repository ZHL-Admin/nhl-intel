"""10 Hz honesty: smoothed trajectories and velocities.

Global rule: every velocity is computed on a Savitzky-Golay-smoothed trajectory (window=7 frames=0.7s,
polyorder=2). For tracks too short for that window the fallback is a 5-frame centered rolling mean; for
tracks shorter than the fallback window, the raw finite difference. Which method was used is returned
per call so the fused table can record it. Speeds are approximate and never headline athletic numbers.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import savgol_filter

from . import config

HZ = config.HZ
W = config.SAVGOL_WINDOW
PO = config.SAVGOL_POLYORDER
FB = config.FALLBACK_ROLL_WINDOW


def _interp_nan(a: np.ndarray) -> np.ndarray:
    """Linear-interpolate interior NaNs (tracking dropouts) so smoothing has a continuous series."""
    a = a.astype(float).copy()
    n = len(a)
    idx = np.arange(n)
    good = ~np.isnan(a)
    if good.sum() == 0:
        return a
    if good.sum() < n:
        a[~good] = np.interp(idx[~good], idx[good], a[good])
    return a


def smooth(a: np.ndarray) -> tuple[np.ndarray, str]:
    """Smoothed copy of a 1-D position series; returns (smoothed, method_flag).

    Robust to tracking dropouts: interior NaNs are interpolated; an all-NaN series (an entity never
    tracked in the clip) returns zeros with method 'none' so downstream speeds are simply undefined,
    never a crash.
    """
    a = _interp_nan(np.asarray(a, dtype=float))
    n = len(a)
    if n == 0 or np.all(np.isnan(a)):
        return np.zeros(n), "none"
    if np.isnan(a).any():                     # residual NaN safety net
        a = np.where(np.isnan(a), np.nanmean(a), a)
    if n >= W:
        return savgol_filter(a, W, PO), "savgol7"
    if n >= FB:
        k = FB
        pad = k // 2
        ap = np.pad(a, pad, mode="edge")
        return np.convolve(ap, np.ones(k) / k, mode="valid"), "roll5"
    return a, "raw"


def speed_series(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, str]:
    """Approximate smoothed speed (ft/s) per frame from x/y position series at 10 Hz."""
    sx, m = smooth(x)
    sy, _ = smooth(y)
    vx = np.gradient(sx) * HZ
    vy = np.gradient(sy) * HZ
    return np.hypot(vx, vy), m


def lateral_speed_series(y: np.ndarray) -> np.ndarray:
    """Approximate smoothed lateral (y-axis) speed (ft/s)."""
    sy, _ = smooth(y)
    return np.abs(np.gradient(sy) * HZ)
