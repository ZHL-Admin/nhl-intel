from __future__ import annotations
import polars as pl, pytest
from defbreak import config as C, adjrates as A
@pytest.mark.skipif(not A.RATES.exists(), reason="adj rates not built")
def test_adj_rates_shape():
    r=pl.read_parquet(A.RATES)
    assert set(r["position"].unique()) == {"D","F"}
    for v in ["raw","adj1","adj2","adj3","adj4","adjc"]: assert v in r.columns
    assert (r["adj1"]==r["raw"]).all()          # ADJ-1 is a rescaling of RAW (documented)
    assert r["ga"].min() >= 25                    # min-sample gate
@pytest.mark.skipif(not (C.REPORTS/"probe_adj.md").exists(), reason="report not written")
def test_no_banned_words_adj():
    txt=(C.REPORTS/"probe_adj.md").read_text().lower()
    for w in C.BANNED_WORDS: assert txt.count(w) <= C.FRAMING.lower().count(w)


@pytest.mark.skipif(not (C.REPORTS/"inspect.md").exists(), reason="inspect not built")
def test_inspect_clean():
    txt=(C.REPORTS/"inspect.md").read_text().lower()
    for w in C.BANNED_WORDS: assert w not in txt          # dump has no framing quote; must be fully clean
    csvd=C.REPORTS/"inspect_csv"
    assert csvd.exists() and len(list(csvd.glob("lb_*.csv"))) == 24   # 2 pos x 2 seasons x 6 versions
