import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from tinydb import TinyDB, Query

DATE_KEYS = {"tanggal", "created_at", "timestamp"}


def _is_dt_key(k: str) -> bool:
    return any(k.endswith(f".{d}") or k == d for d in DATE_KEYS)


def _serialize_value(k: str, v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _deserialize_value(k: str, v: Any) -> Any:
    if isinstance(v, str) and (k in DATE_KEYS):
        try:
            return datetime.fromisoformat(v)
        except Exception:
            return v
    return v


def _deep_deserialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in doc.items():
        if isinstance(v, dict):
            out[k] = _deep_deserialize(v)
        elif isinstance(v, list):
            out[k] = [(_deep_deserialize(x) if isinstance(x, dict) else _deserialize_value(k, x)) for x in v]
        else:
            out[k] = _deserialize_value(k, v)
    return out


def _deep_serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in doc.items():
        if isinstance(v, dict):
            out[k] = _deep_serialize(v)
        elif isinstance(v, list):
            out[k] = [(_deep_serialize(x) if isinstance(x, dict) else _serialize_value(k, x)) for x in v]
        else:
            out[k] = _serialize_value(k, v)
    return out


def _match_simple(filter_dict: Dict[str, Any], doc: Dict[str, Any]) -> bool:
    # Supports subset of Mongo-like filters used in app: equality, nested $or, $regex (case-insensitive), range for 'tanggal'
    for k, v in filter_dict.items():
        if k == '$or' and isinstance(v, list):
            if not any(_match_simple(cond, doc) for cond in v):
                return False
            continue
        if k == 'tanggal' and isinstance(v, dict):
            dt = doc.get('tanggal')
            if isinstance(dt, str):
                try:
                    dt = datetime.fromisoformat(dt)
                except Exception:
                    dt = None
            gte_ok = True
            lte_ok = True
            if '$gte' in v:
                gte = v['$gte']
                gte_ok = dt is not None and dt >= gte
            if '$lte' in v:
                lte = v['$lte']
                lte_ok = dt is not None and dt <= v['$lte']
            if not (gte_ok and lte_ok):
                return False
            continue
        if isinstance(v, dict) and '$regex' in v:
            # simple case-insensitive substring match
            pattern = v['$regex'].lower()
            options = v.get('$options', '')
            target = str(doc.get(k, '')).lower() if 'i' in options else str(doc.get(k, ''))
            if pattern not in target:
                return False
            continue
        # default equality compare (stringify both sides)
        if str(doc.get(k)) != str(v):
            return False
    return True


class InsertOneResult:
    def __init__(self, inserted_id: str):
        self.inserted_id = inserted_id


class CollectionCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = docs

    def sort(self, key: str, direction: int):
        reverse = direction < 0
        self._docs.sort(key=lambda d: d.get(key), reverse=reverse)
        return self

    def skip(self, n: int):
        self._docs = self._docs[n:]
        return self

    def limit(self, n: int):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


class Collection:
    def __init__(self, table):
        self.table = table

    def insert_one(self, doc: Dict[str, Any]) -> InsertOneResult:
        d = dict(doc)
        if '_id' not in d:
            d['_id'] = str(uuid.uuid4())
        ser = _deep_serialize(d)
        self.table.insert(ser)
        return InsertOneResult(d['_id'])

    def find_one(self, filter_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        all_docs = self.table.all()
        for raw in all_docs:
            if _match_simple(filter_dict, raw):
                return _deep_deserialize(raw)
        return None

    def find(self, filter_dict: Dict[str, Any]) -> CollectionCursor:
        result: List[Dict[str, Any]] = []
        for raw in self.table.all():
            if _match_simple(filter_dict, raw):
                result.append(_deep_deserialize(raw))
        return CollectionCursor(result)

    def update_one(self, filter_dict: Dict[str, Any], update_doc: Dict[str, Any]):
        all_docs = self.table.all()
        for raw in all_docs:
            if _match_simple(filter_dict, raw):
                doc = _deep_deserialize(raw)
                if '$set' in update_doc:
                    for k, v in update_doc['$set'].items():
                        doc[k] = v
                if '$push' in update_doc:
                    for k, v in update_doc['$push'].items():
                        arr = doc.get(k, [])
                        if not isinstance(arr, list):
                            arr = []
                        arr.append(v)
                        doc[k] = arr
                # write back
                ser = _deep_serialize(doc)
                self.table.update(ser, Query()._id == raw['_id'])
                break

    def delete_one(self, filter_dict: Dict[str, Any]):
        all_docs = self.table.all()
        for raw in all_docs:
            if _match_simple(filter_dict, raw):
                self.table.remove(Query()._id == raw['_id'])
                break

    def count_documents(self, filter_dict: Dict[str, Any]) -> int:
        cnt = 0
        for raw in self.table.all():
            if _match_simple(filter_dict, raw):
                cnt += 1
        return cnt

    def aggregate(self, pipeline: List[Dict[str, Any]]):
        # Only supports the specific trend aggregation used in the app
        # We will compute daily sums for last N days filtered by acara_id and category
        match = {}
        for stage in pipeline:
            if '$match' in stage:
                match.update(stage['$match'])
        docs = [ _deep_deserialize(raw) for raw in self.table.all() if _match_simple(match, raw) ]
        # Compute adjusted_jumlah
        items = []
        for t in docs:
            tanggal = t.get('tanggal')
            if isinstance(tanggal, datetime):
                date_key = tanggal.strftime('%Y-%m-%d')
            else:
                date_key = str(tanggal)[:10]
            adjusted = (t.get('jumlah', 0) or 0) + sum((adj.get('amount', 0) or 0) for adj in t.get('adjustments', []))
            kategori = t.get('kategori', t.get('tipe'))
            items.append((date_key, kategori, adjusted))
        # Group by date and kategori
        daily = {}
        for date_key, kategori, val in items:
            daily.setdefault(date_key, {'pemasukan': 0, 'pengeluaran': 0})
            if kategori == 'Pemasukan':
                daily[date_key]['pemasukan'] += val
            elif kategori == 'Pengeluaran':
                daily[date_key]['pengeluaran'] += val
        # Return in shape similar to pipeline result
        result = []
        for date_key in sorted(daily.keys()):
            result.append({'_id': date_key, 'pemasukan': daily[date_key]['pemasukan'], 'pengeluaran': daily[date_key]['pengeluaran']})
        return result


class TinyDatabase:
    def __init__(self, path: str = 'data.json'):
        self._db = TinyDB(path)
        self.users = Collection(self._db.table('users'))
        self.acara = Collection(self._db.table('acara'))
        self.transaksi = Collection(self._db.table('transaksi'))
