from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import (
    db, Festival, FestivalStatus, FestivalEdition, FestivalProgramEntry,
    FestivalMaterial, FestivalDocument, editor_required,
)
from utils import save_file
from audit import commit_with_audit

festivals_bp = Blueprint('festivals', __name__, url_prefix='/festivals')


def _program_entry_label(entry):
    parts = [entry.date_display or 'дата не указана']
    if entry.time:
        parts.append(entry.time)
    if entry.location:
        parts.append(entry.location)
    return ' • '.join(parts)


def _get_or_create_status(name):
    """Resolve (or create) the FestivalStatus for a single combobox field: matches
    case-insensitively so e.g. "международный" and "Международный" reuse the same row
    instead of creating a near-duplicate."""
    name = (name or '').strip()
    if not name:
        return None
    target = name.lower()
    existing = next((s for s in FestivalStatus.query.all() if s.name.strip().lower() == target), None)
    if existing:
        return existing.id
    st = FestivalStatus(name=name)
    db.session.add(st)
    db.session.flush()
    return st.id


# ---------- Уровень 1: фестивали (серии) ----------
@festivals_bp.route('/')
@login_required
def list_festivals():
    q = request.args.get('q', '').strip()
    festivals = Festival.query.order_by(Festival.name).all()
    if q:
        # Matched in Python, not via SQL LIKE/ilike: SQLite's lower() only folds ASCII
        # a-z and leaves Cyrillic untouched, so a SQL-side comparison would miss most
        # real searches here (see utils.get_or_create_libretto_role for the same issue).
        target = q.lower()
        def matches(f):
            if target in (f.name or '').lower():
                return True
            if any(target in str(e.year) for e in f.editions):
                return True
            return False
        festivals = [f for f in festivals if matches(f)]
    return render_template('festivals/list.html', festivals=festivals, q=q)


@festivals_bp.route('/create', methods=['GET', 'POST'])
@editor_required
def create():
    statuses = FestivalStatus.query.order_by(FestivalStatus.name).all()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Укажите название фестиваля.', 'danger')
            return render_template('festivals/form.html', f=None, statuses=statuses)
        fest = Festival(
            name      = name,
            status_id = _get_or_create_status(request.form.get('status')),
        )
        db.session.add(fest)
        db.session.flush()
        commit_with_audit('create', 'Фестиваль', fest.name, fest.id, fest.status_name)
        flash('Фестиваль создан.', 'success')
        return redirect(url_for('festivals.list_editions', fid=fest.id))
    return render_template('festivals/form.html', f=None, statuses=statuses)


@festivals_bp.route('/<int:fid>/edit', methods=['GET', 'POST'])
@editor_required
def edit(fid):
    fest = db.get_or_404(Festival, fid)
    statuses = FestivalStatus.query.order_by(FestivalStatus.name).all()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Укажите название фестиваля.', 'danger')
            return render_template('festivals/form.html', f=fest, statuses=statuses)
        fest.name      = name
        fest.status_id = _get_or_create_status(request.form.get('status'))
        commit_with_audit('update', 'Фестиваль', fest.name, fest.id, fest.status_name)
        flash('Фестиваль обновлён.', 'success')
        return redirect(url_for('festivals.list_festivals'))
    return render_template('festivals/form.html', f=fest, statuses=statuses)


@festivals_bp.route('/<int:fid>/delete', methods=['POST'])
@editor_required
def delete(fid):
    fest = db.get_or_404(Festival, fid)
    label = fest.name
    details = fest.status_name
    db.session.delete(fest)
    commit_with_audit('delete', 'Фестиваль', label, fid, details)
    flash('Фестиваль удалён.', 'success')
    return redirect(url_for('festivals.list_festivals'))


# ---------- Уровень 2: выпуски фестиваля ----------
@festivals_bp.route('/<int:fid>')
@login_required
def list_editions(fid):
    fest = db.get_or_404(Festival, fid)
    editions = FestivalEdition.query.filter_by(festival_id=fid).order_by(FestivalEdition.year.desc()).all()
    return render_template('festivals/editions_list.html', festival=fest, editions=editions)


@festivals_bp.route('/<int:fid>/editions/create', methods=['GET', 'POST'])
@editor_required
def create_edition(fid):
    fest = db.get_or_404(Festival, fid)
    if request.method == 'POST':
        year = request.form.get('year', '')
        if not year:
            flash('Укажите год проведения.', 'danger')
            return render_template('festivals/edition_form.html', festival=fest, e=None)
        edition = FestivalEdition(
            festival_id = fid,
            year        = int(year),
            description = request.form.get('description', '').strip() or None,
        )
        db.session.add(edition)
        db.session.flush()
        commit_with_audit('create', 'Выпуск фестиваля',
                          f'{fest.name}, {edition.year}', edition.id)
        flash('Выпуск фестиваля создан.', 'success')
        return redirect(url_for('festivals.edition_detail', eid=edition.id))
    return render_template('festivals/edition_form.html', festival=fest, e=None)


@festivals_bp.route('/editions/<int:eid>/edit', methods=['GET', 'POST'])
@editor_required
def edit_edition(eid):
    edition = db.get_or_404(FestivalEdition, eid)
    if request.method == 'POST':
        year = request.form.get('year', '')
        if not year:
            flash('Укажите год проведения.', 'danger')
            return render_template('festivals/edition_form.html', festival=edition.festival, e=edition)
        edition.year        = int(year)
        edition.description = request.form.get('description', '').strip() or None
        commit_with_audit('update', 'Выпуск фестиваля',
                          f'{edition.festival.name}, {edition.year}', edition.id)
        flash('Выпуск фестиваля обновлён.', 'success')
        return redirect(url_for('festivals.edition_detail', eid=edition.id))
    return render_template('festivals/edition_form.html', festival=edition.festival, e=edition)


@festivals_bp.route('/editions/<int:eid>/delete', methods=['POST'])
@editor_required
def delete_edition(eid):
    edition = db.get_or_404(FestivalEdition, eid)
    fid = edition.festival_id
    label = f'{edition.festival.name}, {edition.year}'
    db.session.delete(edition)
    commit_with_audit('delete', 'Выпуск фестиваля', label, eid)
    flash('Выпуск фестиваля удалён.', 'success')
    return redirect(url_for('festivals.list_editions', fid=fid))


@festivals_bp.route('/editions/<int:eid>')
@login_required
def edition_detail(eid):
    edition = db.get_or_404(FestivalEdition, eid)
    return render_template('festivals/edition_detail.html', e=edition)


# ---------- Программа по дням ----------
@festivals_bp.route('/editions/<int:eid>/program/add', methods=['POST'])
@editor_required
def add_program_entry(eid):
    edition = db.get_or_404(FestivalEdition, eid)
    entry = FestivalProgramEntry(
        edition_id  = eid,
        day         = request.form.get('day') or None,
        month       = request.form.get('month') or None,
        time        = request.form.get('time', '').strip() or None,
        location    = request.form.get('location', '').strip() or None,
        description = request.form.get('description', '').strip() or None,
    )
    db.session.add(entry)
    db.session.flush()
    commit_with_audit('create', 'Программа фестиваля',
                      f'{edition.festival.name}, {edition.year}: {_program_entry_label(entry)}',
                      entry.id)
    flash('Запись программы добавлена.', 'success')
    return redirect(url_for('festivals.edition_detail', eid=eid) + '#program')


@festivals_bp.route('/editions/<int:eid>/program/<int:pid>/edit', methods=['GET', 'POST'])
@editor_required
def edit_program_entry(eid, pid):
    edition = db.get_or_404(FestivalEdition, eid)
    entry = db.get_or_404(FestivalProgramEntry, pid)
    if request.method == 'POST':
        entry.day         = request.form.get('day') or None
        entry.month       = request.form.get('month') or None
        entry.time        = request.form.get('time', '').strip() or None
        entry.location    = request.form.get('location', '').strip() or None
        entry.description = request.form.get('description', '').strip() or None
        commit_with_audit('update', 'Программа фестиваля',
                          f'{edition.festival.name}, {edition.year}: {_program_entry_label(entry)}',
                          entry.id)
        flash('Запись программы обновлена.', 'success')
        return redirect(url_for('festivals.edition_detail', eid=eid) + '#program')
    return render_template('festivals/program_form.html', e=edition, entry=entry)


@festivals_bp.route('/editions/<int:eid>/program/<int:pid>/delete', methods=['POST'])
@editor_required
def delete_program_entry(eid, pid):
    edition = db.get_or_404(FestivalEdition, eid)
    entry = db.get_or_404(FestivalProgramEntry, pid)
    label = f'{edition.festival.name}, {edition.year}: {_program_entry_label(entry)}'
    db.session.delete(entry)
    commit_with_audit('delete', 'Программа фестиваля', label, pid)
    flash('Запись программы удалена.', 'success')
    return redirect(url_for('festivals.edition_detail', eid=eid) + '#program')


# ---------- Материалы выпуска ----------
@festivals_bp.route('/editions/<int:eid>/materials/add', methods=['POST'])
@editor_required
def add_material(eid):
    edition = db.get_or_404(FestivalEdition, eid)
    mat_type = request.form.get('material_type', '').strip()
    title    = request.form.get('title', '').strip()
    url      = request.form.get('url', '').strip()
    file     = request.files.get('mat_file')

    if not mat_type:
        flash('Укажите тип материала.', 'danger')
        return redirect(url_for('festivals.edition_detail', eid=eid) + '#materials')

    fp, fn = save_file(file, material_type=mat_type, edition_id=eid) if file and file.filename else (None, None)
    if file and file.filename and not fp:
        flash('Ошибка при сохранении файла.', 'danger')
        return redirect(url_for('festivals.edition_detail', eid=eid) + '#materials')
    if not fp and not url:
        flash('Загрузите файл или укажите URL.', 'danger')
        return redirect(url_for('festivals.edition_detail', eid=eid) + '#materials')

    mat = FestivalMaterial(
        edition_id    = eid,
        material_type = mat_type,
        file_path     = fp,
        file_name     = fn,
        url           = url or None,
        title         = title or fn or url,
    )
    db.session.add(mat)
    db.session.flush()
    commit_with_audit('create', 'Материал фестиваля',
                      f'{edition.festival.name}, {edition.year}: {mat.title or mat.file_name or mat.url}',
                      mat.id, mat.type_display)
    flash('Материал добавлен.', 'success')
    return redirect(url_for('festivals.edition_detail', eid=eid) + '#materials')


@festivals_bp.route('/editions/<int:eid>/materials/<int:mid>/delete', methods=['POST'])
@editor_required
def delete_material(eid, mid):
    edition = db.get_or_404(FestivalEdition, eid)
    mat = db.get_or_404(FestivalMaterial, mid)
    label = f'{edition.festival.name}, {edition.year}: {mat.title or mat.file_name or mat.url}'
    details = mat.type_display
    db.session.delete(mat)
    commit_with_audit('delete', 'Материал фестиваля', label, mid, details)
    flash('Материал удалён.', 'success')
    return redirect(url_for('festivals.edition_detail', eid=eid) + '#materials')


# ---------- Документы выпуска ----------
@festivals_bp.route('/editions/<int:eid>/documents/add', methods=['POST'])
@editor_required
def add_document(eid):
    edition = db.get_or_404(FestivalEdition, eid)
    doc_type = request.form.get('doc_type', '').strip()
    title    = request.form.get('title', '').strip()
    file     = request.files.get('doc_file')
    if not doc_type or not file:
        flash('Укажите тип документа и прикрепите файл.', 'danger')
        return redirect(url_for('festivals.edition_detail', eid=eid) + '#documents')
    fp, fn = save_file(file, material_type='festival_document', edition_id=eid)
    if not fp:
        flash('Недопустимый формат файла.', 'danger')
        return redirect(url_for('festivals.edition_detail', eid=eid) + '#documents')
    doc = FestivalDocument(edition_id=eid, doc_type=doc_type, file_path=fp, file_name=fn, title=title or fn)
    db.session.add(doc)
    db.session.flush()
    commit_with_audit('create', 'Документ фестиваля',
                      f'{edition.festival.name}, {edition.year}: {doc.title or doc.file_name}',
                      doc.id, doc.doc_type_display)
    flash('Документ прикреплён.', 'success')
    return redirect(url_for('festivals.edition_detail', eid=eid) + '#documents')


@festivals_bp.route('/editions/<int:eid>/documents/<int:did>/delete', methods=['POST'])
@editor_required
def delete_document(eid, did):
    edition = db.get_or_404(FestivalEdition, eid)
    doc = db.get_or_404(FestivalDocument, did)
    label = f'{edition.festival.name}, {edition.year}: {doc.title or doc.file_name}'
    details = doc.doc_type_display
    db.session.delete(doc)
    commit_with_audit('delete', 'Документ фестиваля', label, did, details)
    flash('Документ удалён.', 'success')
    return redirect(url_for('festivals.edition_detail', eid=eid) + '#documents')
