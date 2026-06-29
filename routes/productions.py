from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db, Production, ProductionAuthor, editor_required

productions_bp = Blueprint('productions', __name__, url_prefix='/productions')

def _save_authors(production_id, role, names):
    for name in names:
        name = name.strip()
        if name:
            db.session.add(ProductionAuthor(production_id=production_id, full_name=name, role=role))

@productions_bp.route('/')
@login_required
def list_productions():
    productions = Production.query.order_by(Production.premiere_year.desc()).all()
    genres = sorted({p.genre for p in productions if p.genre})
    return render_template('productions/list.html', productions=productions, genres=genres)

@productions_bp.route('/<int:pid>')
@login_required
def detail(pid):
    p = db.get_or_404(Production, pid)
    return render_template('productions/detail.html', p=p)

@productions_bp.route('/create', methods=['GET', 'POST'])
@editor_required
def create():
    if request.method == 'POST':
        name   = request.form.get('name', '').strip()
        genre  = request.form.get('genre', '').strip()
        year   = request.form.get('premiere_year', '')
        status = request.form.get('status', 'active')
        if not name or not genre or not year:
            flash('Заполните обязательные поля: Название, Жанр, Год премьеры.', 'danger')
            return render_template('productions/form.html', p=None)
        p = Production(
            name                  = name,
            status                = status,
            premiere_year         = int(year),
            premiere_day          = request.form.get('premiere_day') or None,
            premiere_month        = request.form.get('premiere_month') or None,
            genre                 = genre,
            acts_count            = request.form.get('acts_count') or None,
            literary_basis        = request.form.get('literary_basis', '').strip() or None,
            literary_basis_author = request.form.get('literary_basis_author', '').strip() or None,
        )
        db.session.add(p)
        db.session.flush()
        _save_authors(p.id, 'music', request.form.getlist('music_authors[]'))
        _save_authors(p.id, 'libretto', request.form.getlist('libretto_authors[]'))
        db.session.commit()
        flash('Постановка создана.', 'success')
        return redirect(url_for('productions.detail', pid=p.id))
    return render_template('productions/form.html', p=None)

@productions_bp.route('/<int:pid>/edit', methods=['GET', 'POST'])
@editor_required
def edit(pid):
    p = db.get_or_404(Production, pid)
    if request.method == 'POST':
        name   = request.form.get('name', '').strip()
        genre  = request.form.get('genre', '').strip()
        year   = request.form.get('premiere_year', '')
        if not name or not genre or not year:
            flash('Заполните обязательные поля.', 'danger')
            return render_template('productions/form.html', p=p)
        p.name                  = name
        p.status                = request.form.get('status', p.status)
        p.premiere_year         = int(year)
        p.premiere_day          = request.form.get('premiere_day') or None
        p.premiere_month        = request.form.get('premiere_month') or None
        p.genre                 = genre
        p.acts_count            = request.form.get('acts_count') or None
        p.literary_basis        = request.form.get('literary_basis', '').strip() or None
        p.literary_basis_author = request.form.get('literary_basis_author', '').strip() or None

        ProductionAuthor.query.filter_by(production_id=p.id).delete()
        _save_authors(p.id, 'music', request.form.getlist('music_authors[]'))
        _save_authors(p.id, 'libretto', request.form.getlist('libretto_authors[]'))

        db.session.commit()
        flash('Постановка обновлена.', 'success')
        return redirect(url_for('productions.detail', pid=p.id))
    return render_template('productions/form.html', p=p)
