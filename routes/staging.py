from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db, Director, DirectorPosition, Production, ProductionDirector, ProductionDirectorPosition, editor_required

staging_bp = Blueprint('staging', __name__)

@staging_bp.route('/staging')
@login_required
def list_directors():
    directors = Director.query.order_by(Director.full_name).all()
    return render_template('staging/list.html', directors=directors, positions=Director.POSITIONS)

@staging_bp.route('/staging/create', methods=['GET', 'POST'])
@editor_required
def create_director():
    if request.method == 'POST':
        name           = request.form.get('full_name', '').strip()
        position_codes = [p for p in request.form.getlist('positions') if p in Director.POSITIONS]
        if not name or not position_codes:
            flash('ФИО и хотя бы одна должность обязательны.', 'danger')
            return render_template('staging/form.html', d=None, positions=Director.POSITIONS,
                                   selected_positions=set(position_codes))
        d = Director(
            full_name  = name,
            birth_year = request.form.get('birth_year') or None,
            death_year = request.form.get('death_year') or None,
        )
        db.session.add(d)
        db.session.flush()
        for code in position_codes:
            db.session.add(DirectorPosition(director_id=d.id, position=code))
        db.session.commit()
        flash('Постановщик добавлен.', 'success')
        return redirect(url_for('staging.list_directors'))
    return render_template('staging/form.html', d=None, positions=Director.POSITIONS, selected_positions=set())

@staging_bp.route('/staging/<int:did>/edit', methods=['GET', 'POST'])
@editor_required
def edit_director(did):
    d = db.get_or_404(Director, did)
    if request.method == 'POST':
        name           = request.form.get('full_name', '').strip()
        position_codes = [p for p in request.form.getlist('positions') if p in Director.POSITIONS]
        if not name or not position_codes:
            flash('ФИО и хотя бы одна должность обязательны.', 'danger')
            return render_template('staging/form.html', d=d, positions=Director.POSITIONS,
                                   selected_positions=set(position_codes))
        d.full_name  = name
        d.birth_year = request.form.get('birth_year') or None
        d.death_year = request.form.get('death_year') or None

        DirectorPosition.query.filter_by(director_id=d.id).delete()
        for code in position_codes:
            db.session.add(DirectorPosition(director_id=d.id, position=code))

        db.session.commit()
        flash('Данные обновлены.', 'success')
        return redirect(url_for('staging.list_directors'))
    return render_template('staging/form.html', d=d, positions=Director.POSITIONS,
                           selected_positions=set(d.position_codes))

@staging_bp.route('/staging/<int:did>/delete', methods=['POST'])
@editor_required
def delete_director(did):
    d = db.get_or_404(Director, did)
    db.session.delete(d)
    db.session.commit()
    flash('Постановщик удалён.', 'success')
    return redirect(url_for('staging.list_directors'))

@staging_bp.route('/productions/<int:pid>/staging/add', methods=['POST'])
@editor_required
def add_to_production(pid):
    db.get_or_404(Production, pid)
    did = request.form.get('director_id')
    if not did:
        flash('Выберите постановщика.', 'danger')
        return redirect(url_for('productions.detail', pid=pid) + '#staging')
    director = db.get_or_404(Director, int(did))

    # Only positions actually assigned to this director may be selected for this production
    allowed_codes = set(director.position_codes)
    position_codes = [p for p in request.form.getlist('positions') if p in allowed_codes]

    existing = ProductionDirector.query.filter_by(production_id=pid, director_id=director.id).first()
    if not existing:
        pd = ProductionDirector(production_id=pid, director_id=director.id)
        db.session.add(pd)
        db.session.flush()
        for code in position_codes:
            db.session.add(ProductionDirectorPosition(production_director_id=pd.id, position=code))
        db.session.commit()
        flash('Постановщик добавлен в постановку.', 'success')
    else:
        flash('Этот постановщик уже в постановочной группе.', 'warning')
    return redirect(url_for('productions.detail', pid=pid) + '#staging')

@staging_bp.route('/productions/<int:pid>/staging/<int:pdid>/remove', methods=['POST'])
@editor_required
def remove_from_production(pid, pdid):
    pd = db.get_or_404(ProductionDirector, pdid)
    db.session.delete(pd)
    db.session.commit()
    flash('Постановщик удалён из постановки.', 'success')
    return redirect(url_for('productions.detail', pid=pid) + '#staging')
