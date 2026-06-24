"""
Demonstration: does "supply more features, the model drops the irrelevant ones" come for free?

We take the proven-best feature set (components + trajectory) and add columns of PURE RANDOM NOISE
(definitionally unrelated to who wins). If selection were a perfect oracle, the elastic-net would
zero them out and out-of-sample performance would be unchanged. We show instead that (a) noise
features survive selection in a non-trivial fraction of folds, and (b) out-of-sample log-loss gets
WORSE — the cost of estimating useless coefficients on a finite sample. Same nested-CV protocol.

Run:  python -m models_ml.analyze_noise_demo
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import log_loss

from models_ml.analyze_kitchen_sink import _pull, _build, _client, _loso, SHORT

N_NOISE = 10
SEED = 1


def main():
    c = _client()
    df = _build(*_pull(c))
    y = df.hi_won.values
    rng = np.random.default_rng(SEED)
    noise_cols = [f"noise_{i}" for i in range(N_NOISE)]
    for col in noise_cols:
        df[col] = rng.standard_normal(len(df))     # pure noise, independent of the outcome

    core = SHORT + ["traj_gap"]
    print(f"Noise demonstration — {len(df)} series, core={len(core)} real features + "
          f"{N_NOISE} pure-noise features\n")

    p_core, _, _ = _loso(df, core, enet=True)
    p_noisy, sel, _ = _loso(df, core + noise_cols, enet=True)
    nf = len(sorted(df.season.unique()))

    print(f"  core (real features only)      OOS log-loss {log_loss(y, p_core):.4f}")
    print(f"  core + {N_NOISE} random noise feats  OOS log-loss {log_loss(y, p_noisy):.4f}   "
          f"({log_loss(y, p_core) - log_loss(y, p_noisy):+.4f} — worse if negative)")

    kept = [sel[n] for n in noise_cols]
    print(f"\n  noise features that survived selection:")
    print(f"    avg noise feature kept in {100*np.mean(kept)/nf:.0f}% of folds "
          f"(a perfect oracle would be 0%)")
    print(f"    most-kept noise feature survived {100*max(kept)/nf:.0f}% of folds")
    real_kept = {k: sel[k] for k in core}
    print(f"    for comparison, real-feature selection: "
          f"{ {k: f'{100*v/nf:.0f}%' for k, v in real_kept.items()} }")


if __name__ == "__main__":
    main()
