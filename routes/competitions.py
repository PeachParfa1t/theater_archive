from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import (
    db, Competition, CompetitionStatus, AwardLevel, CompetitionArtist,
    CompetitionProduction, Artist, Production, editor_required,
)
from utils import save_file

competitions_bp = Blueprint('competitions', __name__, url_prefix='/competitions')


def _get_or_create_lookup(Model, name):
    """Resolve (or create) a user-managed lookup row (status, award level, ...) by name from a
    single combobox field. Matches case-insensitively so e.g. "лауреат" and "Лауреат" reuse the
    same row instead of creating a near-duplicate."""
    name = (name or '').strip()
    if not name:
        return None
    target = name.lower()
    existing = next((x for x in Model.query.all() if x.name.strip().lower() == target), None)
    if existing:
        return existing.id
    obj = Model(name=name)
    db.session.add(obj)
    db.session.flush()
    return obj.id


@competitions_bp.route('/')
@login_required
def list_competitions():
    competitions = Competition.query.order_by(Competition.year.desc(), Competition.name).all()
    statuses = CompetitionStatus.query.order_by(CompetitionStatus.name).all()
    return render_template('competitions/list.html', competitions=competitions, statuses=statuses)


@competitions_bp.route('/create', methods=['GET', 'POST'])
@editor_required
def create():
    statuses = CompetitionStatus.query.order_by(CompetitionStatus.name).all()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        year = request.form.get('year', '')
        if not name or not year:
            flash('Заполните обязательные поля: Название, Год.', 'danger')
            return render_template('competitions/form.html', c=None, statuses=statuses)
        comp = Competition(
            name      = name,
            year      = int(year),
            status_id = _get_or_create_lookup(CompetitionStatus, request.form.get('status')),
        )
        db.session.add(comp)
        db.session.commit()
        flash('Конкурс создан.', 'success')
        return redirect(url_for('competitions.detail', cid=comp.id))
    return render_template('competitions/form.html', c=None, statuses=statuses)


@competitions_bp.route('/<int:cid>/edit', methods=['GET', 'POST'])
@editor_required
def edit(cid):
    comp = db.get_or_404(Competition, cid)
    statuses = CompetitionStatus.query.order_by(CompetitionStatus.name).all()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        year = request.form.get('year', '')
        if not name or not year:
            flash('Заполните обязательные поля: Название, Год.', 'danger')
            return render_template('competitions/form.html', c=comp, statuses=statuses)
        comp.name      = name
        comp.year      = int(year)
        comp.status_id = _get_or_create_lookup(CompetitionStatus, request.form.get('status'))
        db.session.commit()
        flash('Конкурс обновлён.', 'success')
        return redirect(url_for('competitions.detail', cid=comp.id))
    return render_template('competitions/form.html', c=comp, statuses=statuses)


@competitions_bp.route('/<int:cid>/delete', methods=['POST'])
@editor_required
def delete(cid):
    comp = db.get_or_404(Competition, cid)
    db.session.delete(comp)
    db.session.commit()
    flash('Конкурс удалён.', 'success')
    return redirect(url_for('competitions.list_competitions'))


@competitions_bp.route('/<int:cid>')
@login_required
def detail(cid):
    comp = db.get_or_404(Competition, cid)
    award_levels = AwardLevel.query.order_by(AwardLevel.name).all()
    return render_template('competitions/detail.html', c=comp, award_levels=award_levels)


# ---------- Артисты конкурса ----------
@competitions_bp.route('/<int:cid>/artists/add', methods=['POST'])
@editor_required
def add_artist(cid):
    db.get_or_404(Competition, cid)
    artist_id = request.form.get('artist_id')
    if not artist_id:
        flash('Выберите артиста.', 'danger')
        return redirect(url_for('competitions.detail', cid=cid) + '#artists')
    if CompetitionArtist.query.filter_by(competition_id=cid, artist_id=int(artist_id)).first():
        flash('Этот артист уже привязан.', 'warning')
        return redirect(url_for('competitions.detail', cid=cid) + '#artists')

    award_level_id = _get_or_create_lookup(AwardLevel, request.form.get('award_level'))
    file = request.files.get('award_file')
    fp, fn = save_file(file, material_type='competition_file', competition_id=cid) if file and file.filename else (None, None)
    if file and file.filename and not fp:
        flash('Ошибка при сохранении файла.', 'danger')

    db.session.add(CompetitionArtist(
        competition_id=cid, artist_id=int(artist_id), award_level_id=award_level_id,
        file_path=fp, original_filename=fn,
    ))
    db.session.commit()
    flash('Артист привязан к конкурсу.', 'success')
    return redirect(url_for('competitions.detail', cid=cid) + '#artists')


@competitions_bp.route('/<int:cid>/artists/<int:link_id>/edit', methods=['GET', 'POST'])
@editor_required
def edit_artist(cid, link_id):
    comp = db.get_or_404(Competition, cid)
    link = db.get_or_404(CompetitionArtist, link_id)
    award_levels = AwardLevel.query.order_by(AwardLevel.name).all()
    if request.method == 'POST':
        artist_id = request.form.get('artist_id')
        if not artist_id:
            flash('Выберите артиста.', 'danger')
            return render_template('competitions/edit_artist.html', c=comp, link=link, award_levels=award_levels)
        dup = CompetitionArtist.query.filter(CompetitionArtist.competition_id == cid,
                                             CompetitionArtist.artist_id == int(artist_id),
                                             CompetitionArtist.id != link_id).first()
        if dup:
            flash('Этот артист уже привязан.', 'warning')
            return redirect(url_for('competitions.detail', cid=cid) + '#artists')

        link.artist_id = int(artist_id)
        link.award_level_id = _get_or_create_lookup(AwardLevel, request.form.get('award_level'))
        file = request.files.get('award_file')
        if file and file.filename:
            fp, fn = save_file(file, material_type='competition_file', competition_id=cid)
            if fp:
                link.file_path = fp
                link.original_filename = fn
            else:
                flash('Ошибка при сохранении файла.', 'danger')
        db.session.commit()
        flash('Привязка обновлена.', 'success')
        return redirect(url_for('competitions.detail', cid=cid) + '#artists')
    return render_template('competitions/edit_artist.html', c=comp, link=link, award_levels=award_levels)


@competitions_bp.route('/<int:cid>/artists/<int:link_id>/remove', methods=['POST'])
@editor_required
def remove_artist(cid, link_id):
    link = db.get_or_404(CompetitionArtist, link_id)
    db.session.delete(link)
    db.session.commit()
    flash('Артист отвязан от конкурса.', 'success')
    return redirect(url_for('competitions.detail', cid=cid) + '#artists')


# ---------- Постановки конкурса ----------
@competitions_bp.route('/<int:cid>/productions/add', methods=['POST'])
@editor_required
def add_production(cid):
    db.get_or_404(Competition, cid)
    production_id = request.form.get('production_id')
    if not production_id:
        flash('Выберите постановку.', 'danger')
        return redirect(url_for('competitions.detail', cid=cid) + '#productions')
    if CompetitionProduction.query.filter_by(competition_id=cid, production_id=int(production_id)).first():
        flash('Эта постановка уже привязана.', 'warning')
        return redirect(url_for('competitions.detail', cid=cid) + '#productions')

    award_level_id = _get_or_create_lookup(AwardLevel, request.form.get('award_level'))
    file = request.files.get('award_file')
    fp, fn = save_file(file, material_type='competition_file', competition_id=cid) if file and file.filename else (None, None)
    if file and file.filename and not fp:
        flash('Ошибка при сохранении файла.', 'danger')

    db.session.add(CompetitionProduction(
        competition_id=cid, production_id=int(production_id), award_level_id=award_level_id,
        file_path=fp, original_filename=fn,
    ))
    db.session.commit()
    flash('Постановка привязана к конкурсу.', 'success')
    return redirect(url_for('competitions.detail', cid=cid) + '#productions')


@competitions_bp.route('/<int:cid>/productions/<int:link_id>/edit', methods=['GET', 'POST'])
@editor_required
def edit_production(cid, link_id):
    comp = db.get_or_404(Competition, cid)
    link = db.get_or_404(CompetitionProduction, link_id)
    award_levels = AwardLevel.query.order_by(AwardLevel.name).all()
    if request.method == 'POST':
        production_id = request.form.get('production_id')
        if not production_id:
            flash('Выберите постановку.', 'danger')
            return render_template('competitions/edit_production.html', c=comp, link=link, award_levels=award_levels)
        dup = CompetitionProduction.query.filter(CompetitionProduction.competition_id == cid,
                                                 CompetitionProduction.production_id == int(production_id),
                                                 CompetitionProduction.id != link_id).first()
        if dup:
            flash('Эта постановка уже привязана.', 'warning')
            return redirect(url_for('competitions.detail', cid=cid) + '#productions')

        link.production_id = int(production_id)
        link.award_level_id = _get_or_create_lookup(AwardLevel, request.form.get('award_level'))
        file = request.files.get('award_file')
        if file and file.filename:
            fp, fn = save_file(file, material_type='competition_file', competition_id=cid)
            if fp:
                link.file_path = fp
                link.original_filename = fn
            else:
                flash('Ошибка при сохранении файла.', 'danger')
        db.session.commit()
        flash('Привязка обновлена.', 'success')
        return redirect(url_for('competitions.detail', cid=cid) + '#productions')
    return render_template('competitions/edit_production.html', c=comp, link=link, award_levels=award_levels)


@competitions_bp.route('/<int:cid>/productions/<int:link_id>/remove', methods=['POST'])
@editor_required
def remove_production(cid, link_id):
    link = db.get_or_404(CompetitionProduction, link_id)
    db.session.delete(link)
    db.session.commit()
    flash('Постановка отвязана от конкурса.', 'success')
    return redirect(url_for('competitions.detail', cid=cid) + '#productions')
