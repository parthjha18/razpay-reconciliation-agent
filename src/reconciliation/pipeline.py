"""Orchestrates Layers 1-4 end to end."""
from __future__ import annotations

import pandas as pd

from . import engine
from .layer3_fuzzy_match import run_layer_3
from .layer4_classify import run_layer_4


def run_full_pipeline(data_dir: str) -> pd.DataFrame:
    gateway, settlement, ledger = engine.load_sources(data_dir)
    audit = engine.run_layer_1_2(gateway, settlement, ledger)
    audit = run_layer_3(audit, gateway, ledger)
    audit = run_layer_4(audit)
    return audit
