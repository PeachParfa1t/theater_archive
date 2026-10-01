from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import (
    db, Tour, TourType, TourProduction, TourArtist, TourDocument, TourMaterial,
    Production, Artist, editor_required,
)
from utils import save_file
from audit import commit_with_audit

tours_bp = Blueprint('tours', __name__, url_prefix='/tours')


def _get_or_create_tour_type(name):
    """Resolve (or create) the TourType for a single combobox field: matches case-insensitively
    so e.g. "гастроли" and "Гастроли" reuse the same row instead of creating a near-duplicate."""
    name = (name or '').strip()
    if not name:
        return None
    target = name.lower()
    existing = next((t for t in TourType.query.all() if t.name.strip().lower() == target), None)
    if existing:
        return existing.id
    tt = TourType(name=name)
    db.session.add(tt)
    db.session.flush()
    return tt.id


@tours_bp.route('/')
@login_required
def list_tours():
    tours = Tour.query.order_by(Tour.year.desc(), Tour.city).all()
    cities = sorted({t.city for t in tours if t.city})
    tour_types = TourType.query.order_by(TourType.name).all()
    return render_template('tours/list.html', tours=tours, cities=cities, tour_types=tour_types)


@tours_bp.route('/create', methods=['GET', 'POST'])
@editor_required
def create():
    tour_types = TourType.query.order_by(TourType.name).all()
    if request.method == 'POST':
        city = request.form.get('city', '').strip()
        year = request.form.get('year', '')
        if not city or not year:
            flash('Заполните обязательные поля: Город, Год.', 'danger')
            return render_template('tours/form.html', t=None, tour_types=tour_types)
        t = Tour(
            city         = city,
            year         = int(year),
            tour_number  = request.form.get('tour_number') or None,
            tour_type_id = _get_or_create_tour_type(request.form.get('tour_type')),
            description  = request.form.get('description', '').strip() or None,
        )
        db.session.add(t)
        db.session.flush()
        commit_with_audit('create', 'Гастроль', f'{t.city}, {t.year}', t.id,
                          t.tour_type_name)
        flash('Гастроль создана.', 'success')
        return redirect(url_for('tours.detail', tid=t.id))
    return render_template('tours/form.html', t=None, tour_types=tour_types)


@tours_bp.route('/<int:tid>/edit', methods=['GET', 'POST'])
@editor_required
def edit(tid):
    t = db.get_or_404(Tour, tid)
    tour_types = TourType.query.order_by(TourType.name).all()
    if request.method == 'POST':
        city = request.form.get('city', '').strip()
        year = request.form.get('year', '')
        if not city or not year:
            flash('Заполните обязательные поля: Город, Год.', 'danger')
            return render_template('tours/form.html', t=t, tour_types=tour_types)
        t.city         = city
        t.year         = int(year)
        t.tour_number  = request.form.get('tour_number') or None
        t.tour_type_id = _get_or_create_tour_type(request.form.get('tour_type'))
        t.description  = request.form.get('description', '').strip() or None
        commit_with_audit('update', 'Гастроль', f'{t.city}, {t.year}', t.id,
                          t.tour_type_name)
        flash('Гастроль обновлена.', 'success')
        return redirect(url_for('tours.detail', tid=t.id))
    return render_template('tours/form.html', t=t, tour_types=tour_types)


@tours_bp.route('/<int:tid>/delete', methods=['POST'])
@editor_required
def delete(tid):
    t = db.get_or_404(Tour, tid)
    label = f'{t.city}, {t.year}'
    details = t.tour_type_name
    db.session.delete(t)
    commit_with_audit('delete', 'Гастроль', label, tid, details)
    flash('Гастроль удалена.', 'success')
    return redirect(url_for('tours.list_tours'))


@tours_bp.route('/<int:tid>')
@login_required
def detail(tid):
    t = db.get_or_404(Tour, tid)
    return render_template('tours/detail.html', t=t)


# ---------- Постановки, привязанные к гастроли ----------
@tours_bp.route('/<int:tid>/productions/add', methods=['POST'])
@editor_required
def add_production_link(tid):
    tour = db.get_or_404(Tour, tid)
    pid = request.form.get('production_id')
    if not pid:
        flash('Выберите постановку.', 'danger')
        return redirect(url_for('tours.detail', tid=tid) + '#productions')
    if not TourProduction.query.filter_by(tour_id=tid, production_id=int(pid)).first():
        production = db.get_or_404(Production, int(pid))
        link = TourProduction(tour_id=tid, production_id=production.id)
        db.session.add(link)
        db.session.flush()
        commit_with_audit('create', 'Постановка в гастроли',
                          f'{tour.city}, {tour.year}: {production.name}', link.id)
        flash('Постановка привязана к гастроли.', 'success')
    else:
        flash('Эта постановка уже привязана.', 'warning')
    return redirect(url_for('tours.detail', tid=tid) + '#productions')


@tours_bp.route('/<int:tid>/productions/<int:link_id>/edit', methods=['GET', 'POST'])
@editor_required
def edit_production_link(tid, link_id):
    t = db.get_or_404(Tour, tid)
    link = db.get_or_404(TourProduction, link_id)
    if request.method == 'POST':
        pid = request.form.get('production_id')
        if not pid:
            flash('Выберите постановку.', 'danger')
            return render_template('tours/edit_production_link.html', t=t, link=link)
        dup = TourProduction.query.filter(TourProduction.tour_id == tid,
                                          TourProduction.production_id == int(pid),
                                          TourProduction.id != link_id).first()
        if dup:
            flash('Эта постановка уже привязана.', 'warning')
            return redirect(url_for('tours.detail', tid=tid) + '#productions')
        production = db.get_or_404(Production, int(pid))
        link.production_id = production.id
        commit_with_audit('update', 'Постановка в гастроли',
                          f'{t.city}, {t.year}: {production.name}', link.id)
        flash('Привязка обновлена.', 'success')
        return redirect(url_for('tours.detail', tid=tid) + '#productions')
    return render_template('tours/edit_production_link.html', t=t, link=link)


@tours_bp.route('/<int:tid>/productions/<int:link_id>/remove', methods=['POST'])
@editor_required
def remove_production_link(tid, link_id):
    tour = db.get_or_404(Tour, tid)
    link = db.get_or_404(TourProduction, link_id)
    label = f'{tour.city}, {tour.year}: {link.production.name}'
    db.session.delete(link)
    commit_with_audit('delete', 'Постановка в гастроли', label, link_id)
    flash('Постановка отвязана от гастроли.', 'success')
    return redirect(url_for('tours.detail', tid=tid) + '#productions')


# ---------- Артисты, привязанные к гастроли ----------
@tours_bp.route('/<int:tid>/artists/add', methods=['POST'])
@editor_required
def add_artist_link(tid):
    tour = db.get_or_404(Tour, tid)
    aid = request.form.get('artist_id')
    if not aid:
        flash('Выберите артиста.', 'danger')
        return redirect(url_for('tours.detail', tid=tid) + '#artists')
    if not TourArtist.query.filter_by(tour_id=tid, artist_id=int(aid)).first():
        artist = db.get_or_404(Artist, int(aid))
        link = TourArtist(tour_id=tid, artist_id=artist.id)
        db.session.add(link)
        db.session.flush()
        commit_with_audit('create', 'Артист в гастроли',
                          f'{tour.city}, {tour.year}: {artist.full_name}', link.id)
        flash('Артист привязан к гастроли.', 'success')
    else:
        flash('Этот артист уже привязан.', 'warning')
    return redirect(url_for('tours.detail', tid=tid) + '#artists')


@tours_bp.route('/<int:tid>/artists/<int:link_id>/edit', methods=['GET', 'POST'])
@editor_required
def edit_artist_link(tid, link_id):
    t = db.get_or_404(Tour, tid)
    link = db.get_or_404(TourArtist, link_id)
    if request.method == 'POST':
        aid = request.form.get('artist_id')
        if not aid:
            flash('Выберите артиста.', 'danger')
            return render_template('tours/edit_artist_link.html', t=t, link=link)
        dup = TourArtist.query.filter(TourArtist.tour_id == tid,
                                      TourArtist.artist_id == int(aid),
                                      TourArtist.id != link_id).first()
        if dup:
            flash('Этот артист уже привязан.', 'warning')
            return redirect(url_for('tours.detail', tid=tid) + '#artists')
        artist = db.get_or_404(Artist, int(aid))
        link.artist_id = artist.id
        commit_with_audit('update', 'Артист в гастроли',
                          f'{t.city}, {t.year}: {artist.full_name}', link.id)
        flash('Привязка обновлена.', 'success')
        return redirect(url_for('tours.detail', tid=tid) + '#artists')
    return render_template('tours/edit_artist_link.html', t=t, link=link)


@tours_bp.route('/<int:tid>/artists/<int:link_id>/remove', methods=['POST'])
@editor_required
def remove_artist_link(tid, link_id):
    tour = db.get_or_404(Tour, tid)
    link = db.get_or_404(TourArtist, link_id)
    label = f'{tour.city}, {tour.year}: {link.artist.full_name}'
    db.session.delete(link)
    commit_with_audit('delete', 'Артист в гастроли', label, link_id)
    flash('Артист отвязан от гастроли.', 'success')
    return redirect(url_for('tours.detail', tid=tid) + '#artists')


# ---------- Документы гастроли ----------
@tours_bp.route('/<int:tid>/documents/add', methods=['POST'])
@editor_required
def add_document(tid):
    tour = db.get_or_404(Tour, tid)
    doc_type = request.form.get('doc_type', '').strip()
    title    = request.form.get('title', '').strip()
    file     = request.files.get('doc_file')
    if not doc_type or not file:
        flash('Укажите тип документа и прикрепите файл.', 'danger')
        return redirect(url_for('tours.detail', tid=tid) + '#documents')
    fp, fn = save_file(file, material_type='tour_document', tour_id=tid)
    if not fp:
        flash('Недопустимый формат файла.', 'danger')
        return redirect(url_for('tours.detail', tid=tid) + '#documents')
    doc = TourDocument(tour_id=tid, doc_type=doc_type, file_path=fp, file_name=fn, title=title or fn)
    db.session.add(doc)
    db.session.flush()
    commit_with_audit('create', 'Документ гастроли',
                      f'{tour.city}, {tour.year}: {doc.title or doc.file_name}', doc.id,
                      doc.doc_type_display)
    flash('Документ прикреплён.', 'success')
    return redirect(url_for('tours.detail', tid=tid) + '#documents')


@tours_bp.route('/<int:tid>/documents/<int:did>/delete', methods=['POST'])
@editor_required
def delete_document(tid, did):
    tour = db.get_or_404(Tour, tid)
    doc = db.get_or_404(TourDocument, did)
    label = f'{tour.city}, {tour.year}: {doc.title or doc.file_name}'
    details = doc.doc_type_display
    db.session.delete(doc)
    commit_with_audit('delete', 'Документ гастроли', label, did, details)
    flash('Документ удалён.', 'success')
    return redirect(url_for('tours.detail', tid=tid) + '#documents')


# ---------- Материалы гастроли ----------
@tours_bp.route('/<int:tid>/materials/add', methods=['POST'])
@editor_required
def add_material(tid):
    tour = db.get_or_404(Tour, tid)
    mat_type = request.form.get('material_type', '').strip()
    title    = request.form.get('title', '').strip()
    url      = request.form.get('url', '').strip()
    file     = request.files.get('mat_file')

    if not mat_type:
        flash('Укажите тип материала.', 'danger')
        return redirect(url_for('tours.detail', tid=tid) + '#materials')

    fp, fn = save_file(file, material_type=mat_type, tour_id=tid) if file and file.filename else (None, None)
    if file and file.filename and not fp:
        flash('Ошибка при сохранении файла.', 'danger')
        return redirect(url_for('tours.detail', tid=tid) + '#materials')
    if not fp and not url:
        flash('Загрузите файл или укажите URL.', 'danger')
        return redirect(url_for('tours.detail', tid=tid) + '#materials')

    mat = TourMaterial(
        tour_id       = tid,
        material_type = mat_type,
        file_path     = fp,
        file_name     = fn,
        url           = url or None,
        title         = title or fn or url,
    )
    db.session.add(mat)
    db.session.flush()
    commit_with_audit('create', 'Материал гастроли',
                      f'{tour.city}, {tour.year}: {mat.title or mat.file_name or mat.url}',
                      mat.id, mat.type_display)
    flash('Материал добавлен.', 'success')
    return redirect(url_for('tours.detail', tid=tid) + '#materials')


@tours_bp.route('/<int:tid>/materials/<int:mid>/delete', methods=['POST'])
@editor_required
def delete_material(tid, mid):
    tour = db.get_or_404(Tour, tid)
    mat = db.get_or_404(TourMaterial, mid)
    label = f'{tour.city}, {tour.year}: {mat.title or mat.file_name or mat.url}'
    details = mat.type_display
    db.session.delete(mat)
    commit_with_audit('delete', 'Материал гастроли', label, mid, details)
    flash('Материал удалён.', 'success')
    return redirect(url_for('tours.detail', tid=tid) + '#materials')
