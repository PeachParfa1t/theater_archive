from flask import Blueprint, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db, CastEntry, Artist, Production, editor_required, get_or_create_libretto, get_or_create_libretto_role

cast_bp = Blueprint('cast', __name__, url_prefix='/productions')

@cast_bp.route('/<int:pid>/cast/add', methods=['POST'])
@editor_required
def add_cast(pid):
    db.get_or_404(Production, pid)
    artist_id = request.form.get('artist_id')
    role_name = request.form.get('role_name', '').strip()
    year_from = request.form.get('year_from') or None
    year_to   = request.form.get('year_to') or None

    if not artist_id:
        flash('Выберите артиста.', 'danger')
        return redirect(url_for('productions.detail', pid=pid))

    if year_from and year_to and int(year_from) > int(year_to):
        flash('Год начала участия не может быть позже года окончания.', 'danger')
        return redirect(url_for('productions.detail', pid=pid))

    entry = CastEntry(
        production_id=pid,
        artist_id=int(artist_id),
        role_name=role_name,
        year_from=year_from,
        year_to=year_to,
    )
    db.session.add(entry)

    # Mirror the role into the libretto "Роли" section so files can be attached there
    if role_name:
        lib = get_or_create_libretto(pid)
        get_or_create_libretto_role(lib.id, role_name)

    db.session.commit()
    flash('Артист добавлен в состав.', 'success')
    return redirect(url_for('productions.detail', pid=pid))

@cast_bp.route('/<int:pid>/cast/<int:cid>/delete', methods=['POST'])
@editor_required
def delete_cast(pid, cid):
    entry = db.get_or_404(CastEntry, cid)
    db.session.delete(entry)
    db.session.commit()
    flash('Запись состава удалена.', 'success')
    return redirect(url_for('productions.detail', pid=pid))
