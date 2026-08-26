"""Storage behind one small interface.

MemoryStore   - local dev / demo without any cloud dependency.
FirestoreStore- Google Cloud Firestore (native mode), used on Cloud Run.

Select with env STORE=memory|firestore (default: firestore when
GOOGLE_CLOUD_PROJECT is set, else memory).
"""
import os
import threading

COLLECTIONS = [
    "shipments", "wagons", "ships", "teams", "customers",
    "plans", "runs", "events", "outcomes", "emails", "meta",
]


class MemoryStore:
    def __init__(self):
        self._lock = threading.RLock()
        self._data = {c: {} for c in COLLECTIONS}

    def reset(self, state: dict):
        with self._lock:
            self._data = {c: {} for c in COLLECTIONS}
            for coll, items in state.items():
                for obj in items:
                    self._data[coll][obj["id"]] = obj

    def all(self, coll: str) -> list[dict]:
        with self._lock:
            return [dict(v) for v in self._data[coll].values()]

    def get(self, coll: str, oid: str):
        with self._lock:
            v = self._data[coll].get(oid)
            return dict(v) if v else None

    def upsert(self, coll: str, obj: dict):
        with self._lock:
            self._data[coll][obj["id"]] = dict(obj)

    def update(self, coll: str, oid: str, patch: dict):
        with self._lock:
            if oid in self._data[coll]:
                self._data[coll][oid].update(patch)

    def state(self) -> dict:
        with self._lock:
            return {c: [dict(v) for v in self._data[c].values()] for c in COLLECTIONS}


class FirestoreStore:
    """Same interface, backed by Firestore. Documents keyed by object id."""

    def __init__(self):
        from google.cloud import firestore  # lazy: only needed in cloud mode
        self._db = firestore.Client()
        self._prefix = os.environ.get("FS_PREFIX", "dispatch")

    def _coll(self, coll: str):
        return self._db.collection(f"{self._prefix}_{coll}")

    def reset(self, state: dict):
        """Batched wipe, then a single batched repopulate, so the dashboard
        sees an empty store for as short a window as possible."""
        batch, pending = self._db.batch(), 0
        for coll in COLLECTIONS:
            for doc in self._coll(coll).stream():
                batch.delete(doc.reference)
                pending += 1
                if pending >= 400:
                    batch.commit()
                    batch, pending = self._db.batch(), 0
        if pending:
            batch.commit()
        batch, pending = self._db.batch(), 0
        for coll, items in state.items():
            for obj in items:
                batch.set(self._coll(coll).document(obj["id"]), obj)
                pending += 1
                if pending >= 400:
                    batch.commit()
                    batch, pending = self._db.batch(), 0
        if pending:
            batch.commit()

    def all(self, coll: str) -> list[dict]:
        return [d.to_dict() for d in self._coll(coll).stream()]

    def get(self, coll: str, oid: str):
        snap = self._coll(coll).document(oid).get()
        return snap.to_dict() if snap.exists else None

    def upsert(self, coll: str, obj: dict):
        self._coll(coll).document(obj["id"]).set(obj)

    def update(self, coll: str, oid: str, patch: dict):
        # set(merge=True) would CREATE a missing document - a phantom row with
        # no id field that later crashes {s["id"]: s for s in ...}. MemoryStore
        # no-ops on a missing key, so match that exactly.
        from google.api_core.exceptions import NotFound
        try:
            self._coll(coll).document(oid).update(patch)
        except NotFound:
            pass

    def state(self) -> dict:
        return {c: self.all(c) for c in COLLECTIONS}


_store = None


def get_store():
    global _store
    if _store is None:
        mode = os.environ.get("STORE", "").lower()
        if not mode:
            mode = "firestore" if os.environ.get("GOOGLE_CLOUD_PROJECT") else "memory"
        _store = FirestoreStore() if mode == "firestore" else MemoryStore()
    return _store
