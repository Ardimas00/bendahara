from app import db
from datetime import datetime

# Model utilitas sederhana untuk koleksi acara/pencatatan
class AcaraModel:
    @staticmethod
    def create_acara(nama, keterangan=None):
        acara = {
            'nama': nama,
            'keterangan': keterangan or '',
            'tanggal_dibuat': datetime.utcnow()
        }
        result = db.acara.insert_one(acara)
        return str(result.inserted_id)

    @staticmethod
    def get_all():
        return list(db.acara.find())

    @staticmethod
    def get_by_id(acara_id):
        from bson.objectid import ObjectId
        return db.acara.find_one({'_id': ObjectId(acara_id)})

    @staticmethod
    def update_acara(acara_id, nama=None, keterangan=None):
        from bson.objectid import ObjectId
        update_fields = {}
        if nama is not None:
            update_fields['nama'] = nama
        if keterangan is not None:
            update_fields['keterangan'] = keterangan
        if update_fields:
            db.acara.update_one({'_id': ObjectId(acara_id)}, {'$set': update_fields})

    @staticmethod
    def delete_acara(acara_id):
        from bson.objectid import ObjectId
        db.acara.delete_one({'_id': ObjectId(acara_id)})
