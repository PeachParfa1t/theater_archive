from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db, Artist, editor_required

artists_bp = Blueprint('artists', __name__, url_prefix='/artists')

@artists_bp.route('/')
@login_required
def list_artists():
    artists = Artist.query.order_by(Artist.full_name).all()
    titles  = sorted({a.title for a in artists if a.title})
    return render_template('artists/list.html', artists=artists, titles=titles)

@artists_bp.route('/<int:aid>')
@login_required
def detail(aid):
    a = db.get_or_404(Artist, aid)
    return render_template('artists/detail.html', a=a)

@artists_bp.route('/create', methods=['GET', 'POST'])
@editor_required
def create():
    if request.method == 'POST':
        name = request.form.get('full_name', '').strip()
        if not name:
            flash('ФИО обязательно.', 'danger')
            return render_template('artists/form.html', a=None)
        a = Artist(
            full_name       = name,
            title           = request.form.get('title', '').strip() or None,
            birth_year      = request.form.get('birth_year') or None,
            death_year      = request.form.get('death_year') or None,
            description     = request.form.get('description', '').strip() or None,
            work_start_year = request.form.get('work_start_year') or None,
            work_end_year   = request.form.get('work_end_year') or None,
        )
        db.session.add(a)
        db.session.commit()
        flash('Карточка артиста создана.', 'success')
        return redirect(url_for('artists.detail', aid=a.id))
    return render_template('artists/form.html', a=None)

@artists_bp.route('/<int:aid>/edit', methods=['GET', 'POST'])
@editor_required
def edit(aid):
    a = db.get_or_404(Artist, aid)
    if request.method == 'POST':
        name = request.form.get('full_name', '').strip()
        if not name:
            flash('ФИО обязательно.', 'danger')
            return render_template('artists/form.html', a=a)
        a.full_name       = name
        a.title           = request.form.get('title', '').strip() or None
        a.birth_year      = request.form.get('birth_year') or None
        a.death_year      = request.form.get('death_year') or None
        a.description     = request.form.get('description', '').strip() or None
        a.work_start_year = request.form.get('work_start_year') or None
        a.work_end_year   = request.form.get('work_end_year') or None
        db.session.commit()
        flash('Карточка артиста обновлена.', 'success')
        return redirect(url_for('artists.detail', aid=a.id))
    return render_template('artists/form.html', a=a)

@artists_bp.route('/<int:aid>/delete', methods=['POST'])
@editor_required
def delete(aid):
    a = db.get_or_404(Artist, aid)
    db.session.delete(a)
    db.session.commit()
    flash('Артист удалён.', 'success')
    return redirect(url_for('artists.list_artists'))
