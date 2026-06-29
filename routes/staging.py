from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db, Director, Production, ProductionDirector, editor_required

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
        name     = request.form.get('full_name', '').strip()
        position = request.form.get('position', '').strip()
        if not name or not position:
            flash('ФИО и должность обязательны.', 'danger')
            return render_template('staging/form.html', d=None, positions=Director.POSITIONS)
        d = Director(
            full_name  = name,
            position   = position,
            birth_year = request.form.get('birth_year') or None,
            death_year = request.form.get('death_year') or None,
        )
        db.session.add(d)
        db.session.commit()
        flash('Постановщик добавлен.', 'success')
        return redirect(url_for('staging.list_directors'))
    return render_template('staging/form.html', d=None, positions=Director.POSITIONS)

@staging_bp.route('/staging/<int:did>/edit', methods=['GET', 'POST'])
@editor_required
def edit_director(did):
    d = db.get_or_404(Director, did)
    if request.method == 'POST':
        name     = request.form.get('full_name', '').strip()
        position = request.form.get('position', '').strip()
        if not name or not position:
            flash('ФИО и должность обязательны.', 'danger')
            return render_template('staging/form.html', d=d, positions=Director.POSITIONS)
        d.full_name  = name
        d.position   = position
        d.birth_year = request.form.get('birth_year') or None
        d.death_year = request.form.get('death_year') or None
        db.session.commit()
        flash('Данные обновлены.', 'success')
        return redirect(url_for('staging.list_directors'))
    return render_template('staging/form.html', d=d, positions=Director.POSITIONS)

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
        return redirect(url_for('productions.detail', pid=pid))
    existing = ProductionDirector.query.filter_by(production_id=pid, director_id=int(did)).first()
    if not existing:
        pd = ProductionDirector(production_id=pid, director_id=int(did))
        db.session.add(pd)
        db.session.commit()
        flash('Постановщик добавлен в постановку.', 'success')
    else:
        flash('Этот постановщик уже в постановочной группе.', 'warning')
    return redirect(url_for('productions.detail', pid=pid))

@staging_bp.route('/productions/<int:pid>/staging/<int:pdid>/remove', methods=['POST'])
@editor_required
def remove_from_production(pid, pdid):
    pd = db.get_or_404(ProductionDirector, pdid)
    db.session.delete(pd)
    db.session.commit()
    flash('Постановщик удалён из постановки.', 'success')
    return redirect(url_for('productions.detail', pid=pid))
