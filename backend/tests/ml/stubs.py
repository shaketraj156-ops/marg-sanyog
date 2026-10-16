"""Tiny stand-in models. They live in an importable module so joblib can save and load them."""
import numpy as np


class LinearStub:
    """Predicts 3 + 2 per train in the window (feature column 4 is the train count)."""

    def predict(self, X):
        return 3 + 2 * np.asarray(X)[:, 4]


class BrokenStub:
    def predict(self, X):
        raise RuntimeError("the model exploded")


def bundle(model, kind="delay", sections=("A-B", "B-C", "C-D", "D-E")):
    return {"kind": kind, "model": model, "sections": sorted(sections), "slot_minutes": 30}
