from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from app import db
from datetime import datetime, timedelta
from bson.objectid import ObjectId
import io
import csv

main_bp = Blueprint('main', __name__)

from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps

# Decorator: login required (admin or viewer)
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session:
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

# Decorator: admin only
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Akses hanya untuk admin.', 'error')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

@main_bp.route('/')
def root_redirect():
    # Jika belum login, redirect ke login
    if 'role' not in session:
        return redirect(url_for('main.login'))
    # Jika belum pilih acara, redirect ke select_acara
    if 'acara_id' not in session:
        return redirect(url_for('main.select_acara'))
    # Admin ke dashboard, viewer ke laporan viewer
    if session['role'] == 'admin':
        return redirect(url_for('main.dashboard'))
    else:
        return redirect(url_for('main.viewer_report'))

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        user = db.users.find_one({'username': username})
        if user and check_password_hash(user['password_hash'], password):
            session['role'] = user['role']
            session['username'] = user['username']
            # Selalu hapus acara_id dan paksa pilih acara setiap login
            session.pop('acara_id', None)
            return redirect(url_for('main.select_acara'))
        else:
            flash('Username atau password salah.', 'error')
    return render_template('login.html')

# Pilih acara setelah login
@main_bp.route('/select-acara', methods=['GET', 'POST'])
@login_required
def select_acara():
    from app.acara_model import AcaraModel
    if request.method == 'POST':
        acara_id = request.form.get('acara_id')
        if acara_id:
            session['acara_id'] = acara_id
            # Setelah pilih acara, redirect sesuai role
            if session.get('role') == 'admin':
                return redirect(url_for('main.dashboard'))
            else:
                return redirect(url_for('main.viewer_report'))
    acara_list = AcaraModel.get_all()
    return render_template('select_acara.html', acara_list=acara_list)

# Buat acara baru
@main_bp.route('/create-acara', methods=['POST'])
@login_required
def create_acara():
    from app.acara_model import AcaraModel
    nama = request.form.get('nama')
    keterangan = request.form.get('keterangan')
    if nama:
        AcaraModel.create_acara(nama, keterangan)
        flash('Acara berhasil dibuat.', 'success')
    return redirect(url_for('main.select_acara'))

# Hapus acara
@main_bp.route('/delete-acara', methods=['POST'])
@login_required
def delete_acara():
    from app.acara_model import AcaraModel
    acara_id = request.form.get('acara_id')
    if acara_id:
        # Cek apakah acara yang akan dihapus sedang aktif
        if session.get('acara_id') == acara_id:
            session.pop('acara_id', None)  # Hapus dari session jika sedang aktif
        AcaraModel.delete_acara(acara_id)
        flash('Acara berhasil dihapus.', 'success')
    return redirect(url_for('main.select_acara'))

@main_bp.route('/viewer-entry', methods=['POST'])
def viewer_entry():
    session['role'] = 'viewer'
    session['username'] = 'viewer'
    # Selalu hapus acara_id dan paksa pilih acara setiap masuk sebagai viewer
    session.pop('acara_id', None)
    return redirect(url_for('main.select_acara'))

@main_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.login'))

@main_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    from bson.objectid import ObjectId
    acara_id = ObjectId(session['acara_id'])
    
    # Statistik, saldo, grafik tren - filter by acara_id
    total_pemasukan = 0
    total_pengeluaran = 0
    transactions_cursor = db.transaksi.find({'acara_id': acara_id})
    for t in transactions_cursor:
        original_amount = t.get('jumlah', 0)
        adjustments_total = sum(adj.get('amount', 0) for adj in t.get('adjustments', []))
        adjusted_jumlah = original_amount + adjustments_total
        kat = t.get('kategori', t.get('tipe'))
        if kat == 'Pemasukan':
            total_pemasukan += adjusted_jumlah
        else:
            total_pengeluaran += adjusted_jumlah
    saldo_akhir = total_pemasukan - total_pengeluaran

    # Grafik tren 30 hari terakhir - filter by acara_id
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    pipeline = [
        {'$match': {'tanggal': {'$gte': thirty_days_ago}, 'acara_id': acara_id}},
        {'$addFields': {
            'adjusted_jumlah': {'$add': ['$jumlah', {'$sum': {'$map': {'input': '$adjustments', 'as': 'adj', 'in': '$$adj.amount'}}}]} ,
            'kategori_effective': {'$ifNull': ['$kategori', '$tipe']}
        }},
        {'$group': {'_id': {'date': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$tanggal'}}, 'kategori': '$kategori_effective'}, 'daily_total': {'$sum': '$adjusted_jumlah'}}},
        {'$group': {'_id': '$_id.date', 'pemasukan': {'$sum': {'$cond': [{'$eq': ['$_id.kategori', 'Pemasukan']}, '$daily_total', 0]}}, 'pengeluaran': {'$sum': {'$cond': [{'$eq': ['$_id.kategori', 'Pengeluaran']}, '$daily_total', 0]}}}},
        {'$sort': {'_id': 1}}
    ]
    chart_data_cursor = db.transaksi.aggregate(pipeline)
    chart_data = {item['_id']: item for item in chart_data_cursor}
    chart_labels = []
    chart_pemasukan = []
    chart_pengeluaran = []
    for i in range(30):
        date = (datetime.utcnow() - timedelta(days=29 - i)).strftime('%Y-%m-%d')
        chart_labels.append(date[5:])
        data_on_date = chart_data.get(date, {})
        chart_pemasukan.append(data_on_date.get('pemasukan', 0))
        chart_pengeluaran.append(data_on_date.get('pengeluaran', 0))
    return render_template('dashboard.html',
        total_pemasukan=total_pemasukan,
        total_pengeluaran=total_pengeluaran,
        saldo_akhir=saldo_akhir,
        title='Dashboard',
        chart_labels=chart_labels,
        chart_pemasukan=chart_pemasukan,
        chart_pengeluaran=chart_pengeluaran)

@main_bp.route('/viewer-report')
@login_required
def viewer_report():
    if session.get('role') != 'viewer':
        return redirect(url_for('main.root_redirect'))
    # Ambil nama acara aktif untuk ditampilkan
    from app.acara_model import AcaraModel
    acara = AcaraModel.get_by_id(session['acara_id'])
    acara_name = acara['nama'] if acara else 'Unknown'
    return render_template('viewer_report.html', title='Laporan Viewer', acara_name=acara_name)

@main_bp.route('/api/viewer-report')
@login_required
def api_viewer_report():
    from datetime import datetime, timedelta
    from bson.objectid import ObjectId
    acara_id = ObjectId(session['acara_id'])
    
    # Summary - filter by acara_id
    total_pemasukan = 0
    total_pengeluaran = 0
    transactions_cursor = db.transaksi.find({'acara_id': acara_id})
    for t in transactions_cursor:
        original_amount = t.get('jumlah', 0)
        adjustments_total = sum(adj.get('amount', 0) for adj in t.get('adjustments', []))
        adjusted_jumlah = original_amount + adjustments_total
        if t.get('kategori') == 'Pemasukan':
            total_pemasukan += adjusted_jumlah
        else:
            total_pengeluaran += adjusted_jumlah
    saldo = total_pemasukan - total_pengeluaran

    # Chart data: 30 hari terakhir - filter by acara_id
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    pipeline = [
        {'$match': {'tanggal': {'$gte': thirty_days_ago}, 'acara_id': acara_id}},
        {'$addFields': {'adjusted_jumlah': {'$add': ['$jumlah', {'$sum': {'$map': {'input': '$adjustments', 'as': 'adj', 'in': '$$adj.amount'}}}]}}},
        {'$group': {'_id': {'date': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$tanggal'}}, 'kategori': '$kategori'}, 'daily_total': {'$sum': '$adjusted_jumlah'}}},
        {'$group': {'_id': '$_id.date', 'pemasukan': {'$sum': {'$cond': [{'$eq': ['$_id.kategori', 'Pemasukan']}, '$daily_total', 0]}}, 'pengeluaran': {'$sum': {'$cond': [{'$eq': ['$_id.kategori', 'Pengeluaran']}, '$daily_total', 0]}}}},
        {'$sort': {'_id': 1}}
    ]
    chart_data_cursor = db.transaksi.aggregate(pipeline)
    chart_data = {item['_id']: item for item in chart_data_cursor}
    chart_labels = []
    chart_pemasukan = []
    chart_pengeluaran = []
    for i in range(30):
        date = (datetime.utcnow() - timedelta(days=29 - i)).strftime('%Y-%m-%d')
        chart_labels.append(date[5:])
        data_on_date = chart_data.get(date, {})
        chart_pemasukan.append(data_on_date.get('pemasukan', 0))
        chart_pengeluaran.append(data_on_date.get('pengeluaran', 0))

    # 10 transaksi terbaru - filter by acara_id
    latest_cursor = db.transaksi.find({'acara_id': acara_id}).sort('tanggal', -1).limit(10)
    transactions = []
    for t in latest_cursor:
        original_amount = t.get('jumlah', 0)
        adjustments_total = sum(adj.get('amount', 0) for adj in t.get('adjustments', []))
        adjusted_jumlah = original_amount + adjustments_total
        transactions.append({
            'tanggal': t['tanggal'].strftime('%d-%m-%Y'),
            'deskripsi': t.get('deskripsi', ''),
            'kategori': t.get('kategori', t.get('tipe', '')),
            'jumlah': original_amount,
            'adjusted_jumlah': adjusted_jumlah
        })

    return {
        'total_pemasukan': total_pemasukan,
        'total_pengeluaran': total_pengeluaran,
        'saldo_akhir': saldo,
        'chart_labels': chart_labels,
        'chart_pemasukan': chart_pemasukan,
        'chart_pengeluaran': chart_pengeluaran,
        'transaksi_terbaru': transactions
    }
    for t in transactions_cursor:
        original_amount = t.get('jumlah', 0)
        adjustments_total = sum(adj.get('amount', 0) for adj in t.get('adjustments', []))
        adjusted_jumlah = original_amount + adjustments_total
        if t['tipe'] == 'Pemasukan':
            total_pemasukan += adjusted_jumlah
        else:
            total_pengeluaran += adjusted_jumlah
    saldo_akhir = total_pemasukan - total_pengeluaran

    # Grafik tren 30 hari terakhir
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    pipeline = [
        {'$match': {'tanggal': {'$gte': thirty_days_ago}}},
        {'$addFields': {'adjusted_jumlah': {'$add': ['$jumlah', {'$sum': {'$map': {'input': '$adjustments', 'as': 'adj', 'in': '$$adj.amount'}}}]}}},
        {'$group': {'_id': {'date': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$tanggal'}}, 'kategori': '$kategori'}, 'daily_total': {'$sum': '$adjusted_jumlah'}}},
        {'$group': {'_id': '$_id.date', 'pemasukan': {'$sum': {'$cond': [{'$eq': ['$_id.kategori', 'Pemasukan']}, '$daily_total', 0]}}, 'pengeluaran': {'$sum': {'$cond': [{'$eq': ['$_id.kategori', 'Pengeluaran']}, '$daily_total', 0]}}}},
        {'$sort': {'_id': 1}}
    ]
    chart_data_cursor = db.transaksi.aggregate(pipeline)
    chart_data = {item['_id']: item for item in chart_data_cursor}
    chart_labels = []
    chart_pemasukan = []
    chart_pengeluaran = []
    for i in range(30):
        date = (datetime.utcnow() - timedelta(days=29 - i)).strftime('%Y-%m-%d')
        chart_labels.append(date[5:])
        data_on_date = chart_data.get(date, {})
        chart_pemasukan.append(data_on_date.get('pemasukan', 0))
        chart_pengeluaran.append(data_on_date.get('pengeluaran', 0))
    return render_template('dashboard.html',
        total_pemasukan=total_pemasukan,
        total_pengeluaran=total_pengeluaran,
        saldo_akhir=saldo_akhir,
        title='Dashboard',
        chart_labels=chart_labels,
        chart_pemasukan=chart_pemasukan,
        chart_pengeluaran=chart_pengeluaran)

@main_bp.route('/history')
@login_required
@admin_required
def history():
    from bson.objectid import ObjectId
    acara_id = ObjectId(session['acara_id'])
    
    # Filter & search - always include acara_id
    search_query = request.args.get('q', '')
    kategori_filter = request.args.get('kategori', '')
    query = {'acara_id': acara_id}  # Always filter by acara_id
    if search_query:
        query['deskripsi'] = {'$regex': search_query, '$options': 'i'}
    if kategori_filter:
        # match new field or legacy 'tipe'
        query['$or'] = [
            {'kategori': kategori_filter},
            {'tipe': kategori_filter}
        ]
    transactions_cursor = db.transaksi.find(query).sort('tanggal', -1)
    processed_transactions = []
    for t in transactions_cursor:
        original_amount = t.get('jumlah', 0)
        adjustments_total = sum(adj.get('amount', 0) for adj in t.get('adjustments', []))
        t['adjusted_jumlah'] = original_amount + adjustments_total
        processed_transactions.append(t)
    # Get acara name for display
    from app.acara_model import AcaraModel
    acara = AcaraModel.get_by_id(session['acara_id'])
    acara_name = acara['nama'] if acara else 'Unknown'
    
    return render_template('history.html', transactions=processed_transactions, search_query=search_query, kategori_filter=kategori_filter, title='Riwayat Transaksi', acara_name=acara_name)


@main_bp.route('/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_transaction():
    if request.method == 'POST':
        from bson.objectid import ObjectId
        transaction = {
            'tanggal': datetime.strptime(request.form['tanggal'], '%Y-%m-%d'),
            'deskripsi': request.form['deskripsi'],
            'jumlah': int(request.form['jumlah'].replace('.', '').replace(',', '')),
            'kategori': request.form['kategori'],
            'acara_id': ObjectId(session['acara_id']),  # Tambahkan acara_id dari session
            'created_at': datetime.utcnow()
        }
        # Handle rincian pengeluaran
        rincian = []
        if transaction['kategori'] == 'Pengeluaran':
            rincian_nama = request.form.getlist('rincian_nama')
            rincian_jumlah = request.form.getlist('rincian_jumlah')
            for nama, jumlah in zip(rincian_nama, rincian_jumlah):
                if nama.strip() and jumlah.strip():
                    try:
                        jumlah_int = int(jumlah.replace('.', '').replace(',', ''))
                        rincian.append({'nama': nama.strip(), 'jumlah': jumlah_int})
                    except ValueError:
                        continue
            if rincian:
                transaction['rincian'] = rincian
        db.transaksi.insert_one(transaction)
        return redirect(url_for('main.dashboard'))
    # GET: selalu render template dengan variabel yang benar
    # Get acara name for display
    from app.acara_model import AcaraModel
    acara = AcaraModel.get_by_id(session['acara_id'])
    acara_name = acara['nama'] if acara else 'Unknown'
    
    return render_template('add_transaction.html', title='Tambah Transaksi', acara_name=acara_name)

@main_bp.route('/expenses/quick-add', methods=['POST'])
@login_required
@admin_required
def quick_add_expense():
    from bson.objectid import ObjectId
    # Validate required fields
    deskripsi = request.form.get('deskripsi', '').strip()
    tanggal_str = request.form.get('tanggal', '').strip()
    if not deskripsi or not tanggal_str:
        flash('Deskripsi dan tanggal wajib diisi.', 'error')
        return redirect(url_for('main.add_transaction'))

    # Collect rincian arrays
    names = request.form.getlist('rincian_nama_q')
    qtys = request.form.getlist('rincian_qty_q')
    prices = request.form.getlist('rincian_harga_q')

    rincian = []
    total = 0

    def to_int(val: str) -> int:
        try:
            return int(val.replace('.', '').replace(',', ''))
        except Exception:
            try:
                return int(float(val))
            except Exception:
                return 0

    for nama, q, h in zip(names, qtys, prices):
        nama = (nama or '').strip()
        if not nama:
            continue
        q_int = to_int((q or '1'))
        h_int = to_int((h or '0'))
        line_total = max(q_int, 0) * max(h_int, 0)
        if line_total <= 0:
            continue
        rincian.append({'nama': nama, 'qty': q_int, 'harga': h_int, 'jumlah': line_total})
        total += line_total

    if not rincian:
        flash('Minimal satu rincian dengan nilai total > 0 diperlukan.', 'error')
        return redirect(url_for('main.add_transaction'))

    try:
        tanggal = datetime.strptime(tanggal_str, '%Y-%m-%d')
    except Exception:
        flash('Format tanggal tidak valid.', 'error')
        return redirect(url_for('main.add_transaction'))

    doc = {
        'tanggal': tanggal,
        'deskripsi': deskripsi,
        'jumlah': total,
        'kategori': 'Pengeluaran',
        'rincian': rincian,
        'acara_id': ObjectId(session['acara_id']),
        'created_at': datetime.utcnow()
    }
    res = db.transaksi.insert_one(doc)
    flash('Pengeluaran berhasil dibuat dari rincian.', 'success')
    return redirect(url_for('main.view_transaction', id=str(res.inserted_id)))

@main_bp.route('/edit/<id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_transaction(id):
    acara_id = ObjectId(session['acara_id'])
    transaction = db.transaksi.find_one({'_id': ObjectId(id), 'acara_id': acara_id})

    if request.method == 'POST':
        updated_transaction = {
            '$set': {
                'tanggal': datetime.strptime(request.form['tanggal'], '%Y-%m-%d'),
                'deskripsi': request.form['deskripsi'],
                'jumlah': int(request.form['jumlah'].replace('.', '').replace(',', '')),
                'kategori': request.form['kategori']
            }
        }
        db.transaksi.update_one({'_id': ObjectId(id)}, updated_transaction)
        return redirect(url_for('main.history'))

    return render_template('edit_transaction.html', title='Edit Transaksi', transaction=transaction)

@main_bp.route('/delete/<id>', methods=['POST'])
@login_required
@admin_required
def delete_transaction(id):
    acara_id = ObjectId(session['acara_id'])
    db.transaksi.delete_one({'_id': ObjectId(id), 'acara_id': acara_id})
    return redirect(url_for('main.history'))


@main_bp.route('/transaction/<id>/add_rincian', methods=['POST'])
@login_required
@admin_required
def add_rincian(id):
    acara_id = ObjectId(session['acara_id'])
    transaction = db.transaksi.find_one({'_id': ObjectId(id), 'acara_id': acara_id})
    if not transaction or transaction.get('kategori', transaction.get('tipe')) != 'Pengeluaran':
        return redirect(url_for('main.view_transaction', id=id))
    nama = request.form.get('rincian_nama', '').strip()
    jumlah = request.form.get('rincian_jumlah', '').replace('.', '').replace(',', '')
    try:
        jumlah = int(jumlah)
    except Exception:
        jumlah = 0
    if nama and jumlah > 0:
        rincian = transaction.get('rincian', [])
        rincian.append({'nama': nama, 'jumlah': jumlah})
        db.transaksi.update_one({'_id': ObjectId(id)}, {'$set': {'rincian': rincian}})
        # Validation flash
        total_rincian = sum(item.get('jumlah', 0) for item in rincian)
        selisih = (transaction.get('jumlah', 0)) - total_rincian
        if selisih == 0:
            flash('Rincian ditambahkan. Total rincian sudah sesuai dengan jumlah transaksi.', 'success')
        else:
            flash(f'Rincian ditambahkan. Peringatan: total rincian berbeda dari jumlah transaksi. Selisih: Rp {selisih:,}'.replace(',', '.'), 'warning')
    return redirect(url_for('main.view_transaction', id=id))

@main_bp.route('/transaction/<id>/edit_rincian/<int:idx>', methods=['POST'])
@login_required
@admin_required
def edit_rincian(id, idx):
    acara_id = ObjectId(session['acara_id'])
    transaction = db.transaksi.find_one({'_id': ObjectId(id), 'acara_id': acara_id})
    if not transaction or transaction.get('kategori', transaction.get('tipe')) != 'Pengeluaran':
        return redirect(url_for('main.view_transaction', id=id))
    rincian = transaction.get('rincian', [])
    if 0 <= idx < len(rincian):
        nama = request.form.get('edit_nama', '').strip()
        jumlah = request.form.get('edit_jumlah', '').replace('.', '').replace(',', '')
        try:
            jumlah = int(jumlah)
        except Exception:
            jumlah = 0
        if nama and jumlah > 0:
            rincian[idx] = {'nama': nama, 'jumlah': jumlah}
            db.transaksi.update_one({'_id': ObjectId(id)}, {'$set': {'rincian': rincian}})
            total_rincian = sum(item.get('jumlah', 0) for item in rincian)
            selisih = (transaction.get('jumlah', 0)) - total_rincian
            if selisih == 0:
                flash('Rincian diperbarui. Total rincian sudah sesuai.', 'success')
            else:
                flash(f'Rincian diperbarui. Peringatan: selisih dengan jumlah transaksi: Rp {selisih:,}'.replace(',', '.'), 'warning')
    return redirect(url_for('main.view_transaction', id=id))

@main_bp.route('/transaction/<id>/delete_rincian/<int:idx>', methods=['POST'])
@login_required
@admin_required
def delete_rincian(id, idx):
    acara_id = ObjectId(session['acara_id'])
    transaction = db.transaksi.find_one({'_id': ObjectId(id), 'acara_id': acara_id})
    if not transaction or transaction.get('kategori', transaction.get('tipe')) != 'Pengeluaran':
        return redirect(url_for('main.view_transaction', id=id))
    rincian = transaction.get('rincian', [])
    if 0 <= idx < len(rincian):
        rincian.pop(idx)
        db.transaksi.update_one({'_id': ObjectId(id)}, {'$set': {'rincian': rincian}})
        total_rincian = sum(item.get('jumlah', 0) for item in rincian)
        selisih = (transaction.get('jumlah', 0)) - total_rincian
        if selisih == 0:
            flash('Rincian dihapus. Total rincian sudah sesuai.', 'success')
        else:
            flash(f'Rincian dihapus. Peringatan: selisih dengan jumlah transaksi: Rp {selisih:,}'.replace(',', '.'), 'warning')
    return redirect(url_for('main.view_transaction', id=id))

@main_bp.route('/transaction/<id>')
@login_required
@admin_required
def view_transaction(id):
    acara_id = ObjectId(session['acara_id'])
    transaction = db.transaksi.find_one({'_id': ObjectId(id), 'acara_id': acara_id})

    # Recalculate adjusted amount for detail view
    original_amount = transaction.get('jumlah', 0)
    adjustments_total = sum(adj.get('amount', 0) for adj in transaction.get('adjustments', []))
    total_setelah_penyesuaian = original_amount + adjustments_total

    # Validation: sum rincian vs jumlah for Pengeluaran
    total_rincian = None
    selisih_rincian = None
    rincian_match = None
    if transaction.get('kategori', transaction.get('tipe')) == 'Pengeluaran':
        total_rincian = sum(item.get('jumlah', 0) for item in transaction.get('rincian', []))
        selisih_rincian = original_amount - total_rincian
        rincian_match = (selisih_rincian == 0)

    return render_template('view_transaction.html', 
                           title='Detail Transaksi', 
                           transaction=transaction,
                           total_setelah_penyesuaian=total_setelah_penyesuaian,
                           total_rincian=total_rincian,
                           selisih_rincian=selisih_rincian,
                           rincian_match=rincian_match)


@main_bp.route('/adjust_transaction/<id>', methods=['POST'])
@login_required
@admin_required
def adjust_transaction(id):
    try:
        # Amount can be positive (penambahan) or negative (pengurangan)
        amount = int(request.form['adjustment_amount'].replace('.', '').replace(',', ''))
        reason = request.form['reason']

        if not reason:
            flash('Alasan penyesuaian tidak boleh kosong.', 'error')
            return redirect(url_for('main.view_transaction', id=id))

        adjustment = {
            'amount': amount,
            'reason': reason,
            'timestamp': datetime.utcnow()
        }

        db.transaksi.update_one(
            {'_id': ObjectId(id)},
            {'$push': {'adjustments': adjustment}}
        )
        flash('Penyesuaian berhasil ditambahkan.', 'success')

    except ValueError:
        flash('Jumlah penyesuaian tidak valid.', 'error')
    
    return redirect(url_for('main.view_transaction', id=id))


@main_bp.route('/report', methods=['GET'])
@login_required
@admin_required
def report():
    from bson.objectid import ObjectId
    acara_id = ObjectId(session['acara_id'])
    
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    validate_flag = request.args.get('validate_rincian') in ('1', 'true', 'on', 'yes')
    # Pagination params (ledger only)
    try:
        page = int(request.args.get('page', '1'))
    except ValueError:
        page = 1
    page = max(page, 1)
    PAGE_SIZE = 500

    # Jika belum ada tanggal, tampilkan form laporan kosong
    if not start_date_str or not end_date_str:
        return render_template('report.html', title='Laporan Keuangan', show_form=True)
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    except Exception:
        return render_template('report.html', title='Laporan Keuangan', show_form=True, error='Tanggal tidak valid.')
    # Ensure inclusive end date by using $lte with the same date at 23:59:59.999
    end_date_inclusive = end_date

    query = {
        'tanggal': {
            '$gte': start_date,
            '$lte': end_date
        },
        'acara_id': acara_id  # Always filter by acara_id
    }

    # 1) Compute KPI using adjusted amounts across FULL result set (no pagination)
    all_cursor = db.transaksi.find(query).sort('tanggal', 1)
    report_pemasukan = 0
    report_pengeluaran = 0
    # Prepare structures for breakdown and recap and mismatch
    breakdown_map = {}
    mismatch_list = []
    recap_map = {}

    for t in all_cursor:
        kategori = t.get('kategori', t.get('tipe'))
        original_amount = t.get('jumlah', 0)
        adjustments_total = sum(adj.get('amount', 0) for adj in t.get('adjustments', []))
        adjusted = original_amount + adjustments_total
        # KPI
        if kategori == 'Pemasukan':
            report_pemasukan += adjusted
        else:
            report_pengeluaran += adjusted
        # Recap per tanggal (by day)
        key_day = t.get('tanggal')
        if isinstance(key_day, datetime):
            key_str = key_day.strftime('%Y-%m-%d')
        else:
            key_str = str(key_day)
        if key_str not in recap_map:
            recap_map[key_str] = {'pemasukan': 0, 'pengeluaran': 0}
        if kategori == 'Pemasukan':
            recap_map[key_str]['pemasukan'] += adjusted
        else:
            recap_map[key_str]['pengeluaran'] += adjusted
        # Breakdown rincian for Pengeluaran
        if kategori == 'Pengeluaran':
            rincian_items = t.get('rincian', []) or []
            # Mismatch collect (based on original vs sum rincian)
            total_r = sum(item.get('jumlah', 0) for item in rincian_items)
            if original_amount != total_r:
                mismatch_list.append({
                    'tanggal': t.get('tanggal'),
                    'deskripsi': t.get('deskripsi', ''),
                    'jumlah_transaksi': original_amount,
                    'total_rincian': total_r,
                    'selisih': original_amount - total_r
                })
            for it in rincian_items:
                nama = (it.get('nama') or '').strip()
                if not nama:
                    continue
                key = nama.lower()
                qty = it.get('qty')
                harga = it.get('harga')
                jumlah = it.get('jumlah', 0)
                if key not in breakdown_map:
                    breakdown_map[key] = {
                        'nama': nama,
                        'qty_total': 0,
                        'harga_sample': None,
                        'total': 0,
                        'count': 0
                    }
                b = breakdown_map[key]
                b['qty_total'] += (qty or 0)
                if b['harga_sample'] is None and (harga is not None):
                    b['harga_sample'] = harga
                b['total'] += jumlah
                b['count'] += 1

    report_saldo = report_pemasukan - report_pengeluaran

    # Build recap list sorted by date with cumulative saldo
    recap_days_sorted = sorted(recap_map.items(), key=lambda x: x[0])
    recap_list = []
    running_saldo = 0
    for day, vals in recap_days_sorted:
        running_saldo += (vals['pemasukan'] - vals['pengeluaran'])
        recap_list.append({
            'day': day,
            'pemasukan': vals['pemasukan'],
            'pengeluaran': vals['pengeluaran'],
            'saldo_kumulatif': running_saldo
        })

    # Build rincian grouped by transaction (for detailed display)
    rincian_by_trans = []
    for t in db.transaksi.find(query).sort('tanggal', 1):
        if t.get('kategori', t.get('tipe')) != 'Pengeluaran':
            continue
        rincis = (t.get('rincian', []) or [])
        if not rincis:
            continue
        total_r = sum((ri.get('jumlah') or 0) for ri in rincis)
        rincian_by_trans.append({
            'tanggal': t.get('tanggal'),
            'deskripsi': t.get('deskripsi', ''),
            'jumlah_transaksi': t.get('jumlah', 0),
            'total_rincian': total_r,
            'selisih': (t.get('jumlah', 0) - total_r),
            'rincian': [
                {
                    'nama': (ri.get('nama') or ''),
                    'qty': ri.get('qty'),
                    'harga': ri.get('harga'),
                    'jumlah': ri.get('jumlah')
                } for ri in rincis
            ]
        })

    # Breakdown list with percentage against adjusted total pengeluaran
    total_pengeluaran_adjusted = report_pengeluaran
    breakdown_list = []
    for _, b in breakdown_map.items():
        percent = (b['total'] / total_pengeluaran_adjusted * 100.0) if total_pengeluaran_adjusted > 0 else 0.0
        breakdown_list.append({
            'nama': b['nama'],
            'qty_total': b['qty_total'],
            'harga_sample': b['harga_sample'],
            'total': b['total'],
            'persen': percent,
            'count': b['count']
        })
    # Sort breakdown by total desc
    breakdown_list.sort(key=lambda x: x['total'], reverse=True)

    # 2) Ledger (paginated). Apply skip/limit and compute validate fields as requested
    total_count = db.transaksi.count_documents(query)
    total_pages = max((total_count + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page = min(page, total_pages)
    skip_n = (page - 1) * PAGE_SIZE
    ledger_cursor = db.transaksi.find(query).sort('tanggal', 1).skip(skip_n).limit(PAGE_SIZE)
    processed_transactions = []
    for t in ledger_cursor:
        original_amount = t.get('jumlah', 0)
        adjustments_total = sum(adj.get('amount', 0) for adj in t.get('adjustments', []))
        t['adjusted_jumlah'] = original_amount + adjustments_total
        if validate_flag and (t.get('kategori', t.get('tipe')) == 'Pengeluaran'):
            total_rincian = sum(item.get('jumlah', 0) for item in t.get('rincian', []))
            selisih_r = original_amount - total_rincian
            t['rincian_total'] = total_rincian
            t['rincian_selisih'] = selisih_r
            t['rincian_match'] = (selisih_r == 0)
        processed_transactions.append(t)

    return render_template('report.html',
                           transactions=processed_transactions,
                           start_date=start_date,
                           end_date=end_date_inclusive,
                           report_pemasukan=report_pemasukan,
                           report_pengeluaran=report_pengeluaran,
                           report_saldo=report_saldo,
                           validate_rincian=validate_flag,
                           page=page,
                           total_pages=total_pages,
                           total_count=total_count,
                           page_size=PAGE_SIZE,
                           breakdown=breakdown_list,
                           mismatch=mismatch_list,
                           recap=recap_list,
                           rincian_by_trans=rincian_by_trans)


# Admin utility: migrate legacy 'tipe' -> 'kategori'
@main_bp.route('/admin/migrate-kategori', methods=['POST'])
@login_required
@admin_required
def migrate_kategori():
    # Step 1: copy missing kategori from tipe
    to_copy = list(db.transaksi.find({'kategori': {'$exists': False}, 'tipe': {'$exists': True}}, {'tipe': 1}))
    copied = 0
    for doc in to_copy:
        kat = doc.get('tipe')
        if kat:
            db.transaksi.update_one({'_id': doc['_id']}, {'$set': {'kategori': kat}})
            copied += 1
    # Step 2: remove legacy field 'tipe'
    unset_result = db.transaksi.update_many({'tipe': {'$exists': True}}, {'$unset': {'tipe': ""}})
    removed = unset_result.modified_count if unset_result.acknowledged else 0
    flash(f"Migrasi selesai. Disalin: {copied} dokumen. Field 'tipe' dihapus dari {removed} dokumen.", 'success')
    return redirect(url_for('main.dashboard'))


# ==============================
# Report Exports (CSV)
# ==============================
@main_bp.route('/report/export', methods=['GET'])
@login_required
@admin_required
def report_export():
    """Export CSV for report tabs: ledger, breakdown, mismatch, recap."""
    from bson.objectid import ObjectId
    from app.acara_model import AcaraModel
    acara_id = ObjectId(session['acara_id'])

    type_ = request.args.get('type', 'ledger')  # ledger|breakdown|mismatch|rekap
    fmt = request.args.get('format', 'csv')     # currently only csv
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    validate_flag = request.args.get('validate_rincian') in ('1', 'true', 'on', 'yes')

    if fmt != 'csv':
        flash('Format ekspor belum didukung, gunakan CSV.', 'error')
        return redirect(url_for('main.report'))

    # Validate dates
    if not start_date_str or not end_date_str:
        flash('Tanggal mulai/akhir wajib diisi untuk ekspor.', 'error')
        return redirect(url_for('main.report'))
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    except Exception:
        flash('Format tanggal tidak valid.', 'error')
        return redirect(url_for('main.report'))

    query = {
        'tanggal': {
            '$gte': start_date,
            '$lte': end_date
        },
        'acara_id': acara_id
    }

    # Helper: slug acara for filename
    acara = AcaraModel.get_by_id(session['acara_id'])
    acara_name = (acara.get('nama') if acara else 'acara').strip() if isinstance(acara, dict) else 'acara'
    acara_slug = ''.join(ch.lower() if ch.isalnum() else '-' for ch in acara_name).strip('-') or 'acara'
    period_slug = f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"

    # Prepare CSV
    si = io.StringIO()
    cw = csv.writer(si)

    def write_and_return(filename_base: str):
        from flask import make_response
        output = si.getvalue()
        resp = make_response(output)
        resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
        resp.headers['Content-Disposition'] = f"attachment; filename={filename_base}_{acara_slug}_{period_slug}.csv"
        return resp

    if type_ == 'ledger':
        # Fetch all transactions (no pagination) and compute adjusted + optional validation
        cursor = db.transaksi.find(query).sort('tanggal', 1)
        headers = ['Tanggal', 'Deskripsi', 'Kategori', 'Jumlah (Asli)', 'Jumlah Setelah Penyesuaian']
        if validate_flag:
            headers += ['Total Rincian', 'Selisih', 'Kesesuaian']
        cw.writerow(headers)
        for t in cursor:
            original_amount = t.get('jumlah', 0)
            adjustments_total = sum(adj.get('amount', 0) for adj in t.get('adjustments', []))
            adjusted = original_amount + adjustments_total
            row = [
                t.get('tanggal').strftime('%Y-%m-%d') if isinstance(t.get('tanggal'), datetime) else str(t.get('tanggal')),
                t.get('deskripsi', ''),
                t.get('kategori', t.get('tipe')),
                original_amount,
                adjusted,
            ]
            if validate_flag and (t.get('kategori', t.get('tipe')) == 'Pengeluaran'):
                total_rincian = sum(item.get('jumlah', 0) for item in (t.get('rincian', []) or []))
                selisih_r = original_amount - total_rincian
                row += [total_rincian, selisih_r, 'Sesuai' if selisih_r == 0 else 'Tidak']
            elif validate_flag:
                row += ['', '', '']
            cw.writerow(row)
        return write_and_return('laporan-ledger')

    elif type_ == 'breakdown':
        # Aggregate breakdown from pengeluaran rincian
        breakdown = {}
        cursor = db.transaksi.find(query).sort('tanggal', 1)
        total_peng_adjusted = 0
        for t in cursor:
            kategori = t.get('kategori', t.get('tipe'))
            original_amount = t.get('jumlah', 0)
            adjustments_total = sum(adj.get('amount', 0) for adj in t.get('adjustments', []))
            adjusted = original_amount + adjustments_total
            if kategori == 'Pengeluaran':
                total_peng_adjusted += adjusted
                for it in (t.get('rincian', []) or []):
                    nama = (it.get('nama') or '').strip()
                    if not nama:
                        continue
                    key = nama.lower()
                    if key not in breakdown:
                        breakdown[key] = {'nama': nama, 'qty_total': 0, 'harga_sample': None, 'total': 0, 'count': 0}
                    b = breakdown[key]
                    b['qty_total'] += (it.get('qty') or 0)
                    if b['harga_sample'] is None and (it.get('harga') is not None):
                        b['harga_sample'] = it.get('harga')
                    b['total'] += it.get('jumlah', 0)
                    b['count'] += 1
        rows = []
        for _, b in breakdown.items():
            persen = (b['total'] / total_peng_adjusted * 100.0) if total_peng_adjusted > 0 else 0.0
            rows.append([b['nama'], b['qty_total'], b['harga_sample'] if b['harga_sample'] is not None else '', b['total'], f"{persen:.2f}%", b['count']])
        # Sort by total desc
        rows.sort(key=lambda r: r[3], reverse=True)
        cw.writerow(['Item', 'Qty Total', 'Harga (contoh)', 'Total', 'Kontribusi', 'Frekuensi'])
        cw.writerows(rows)
        return write_and_return('laporan-breakdown')

    elif type_ == 'mismatch':
        # List pengeluaran with mismatch (original vs sum rincian)
        cursor = db.transaksi.find(query).sort('tanggal', 1)
        cw.writerow(['Tanggal', 'Deskripsi', 'Jumlah Transaksi', 'Total Rincian', 'Selisih'])
        for t in cursor:
            if t.get('kategori', t.get('tipe')) != 'Pengeluaran':
                continue
            total_r = sum(item.get('jumlah', 0) for item in (t.get('rincian', []) or []))
            original_amount = t.get('jumlah', 0)
            if original_amount != total_r:
                cw.writerow([
                    t.get('tanggal').strftime('%Y-%m-%d') if isinstance(t.get('tanggal'), datetime) else str(t.get('tanggal')),
                    t.get('deskripsi', ''),
                    original_amount,
                    total_r,
                    original_amount - total_r
                ])
        return write_and_return('laporan-validasi')

    elif type_ == 'rincian':
        # Export per-transaction rincian rows
        cursor = db.transaksi.find(query).sort('tanggal', 1)
        cw.writerow(['Tanggal', 'Deskripsi', 'Item', 'Qty', 'Harga', 'Total Item', 'Total Transaksi', 'Total Rincian', 'Selisih'])
        for t in cursor:
            if t.get('kategori', t.get('tipe')) != 'Pengeluaran':
                continue
            rincis = (t.get('rincian', []) or [])
            if not rincis:
                continue
            total_r = sum((ri.get('jumlah') or 0) for ri in rincis)
            for ri in rincis:
                cw.writerow([
                    t.get('tanggal').strftime('%Y-%m-%d') if isinstance(t.get('tanggal'), datetime) else str(t.get('tanggal')),
                    t.get('deskripsi', ''),
                    ri.get('nama', ''),
                    ri.get('qty', ''),
                    ri.get('harga', ''),
                    ri.get('jumlah', ''),
                    t.get('jumlah', 0),
                    total_r,
                    t.get('jumlah', 0) - total_r
                ])
        return write_and_return('laporan-rincian')

    elif type_ == 'rekap':
        # Recap by day with cumulative saldo using adjusted figures
        cursor = db.transaksi.find(query).sort('tanggal', 1)
        by_day = {}
        for t in cursor:
            dt = t.get('tanggal')
            key = dt.strftime('%Y-%m-%d') if isinstance(dt, datetime) else str(dt)
            if key not in by_day:
                by_day[key] = {'pemasukan': 0, 'pengeluaran': 0}
            original_amount = t.get('jumlah', 0)
            adjustments_total = sum(adj.get('amount', 0) for adj in t.get('adjustments', []))
            adjusted = original_amount + adjustments_total
            if t.get('kategori', t.get('tipe')) == 'Pemasukan':
                by_day[key]['pemasukan'] += adjusted
            else:
                by_day[key]['pengeluaran'] += adjusted
        # Build rows with running saldo
        saldo = 0
        cw.writerow(['Tanggal', 'Pemasukan', 'Pengeluaran', 'Saldo Kumulatif'])
        for day in sorted(by_day.keys()):
            pemasukan = by_day[day]['pemasukan']
            pengeluaran = by_day[day]['pengeluaran']
            saldo += (pemasukan - pengeluaran)
            cw.writerow([day, pemasukan, pengeluaran, saldo])
        return write_and_return('laporan-rekap')

    else:
        flash('Tipe ekspor tidak dikenal.', 'error')
        return redirect(url_for('main.report'))
