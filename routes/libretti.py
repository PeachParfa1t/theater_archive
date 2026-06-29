from flask import Blueprint, redirect, url_for, flash, request
from flask_login import login_required, current_user
from functools import wraps
from app import db, Production, Libretto, LibrettoRole, save_file, get_or_create_libretto, get_or_create_libretto_role

libretti_bp = Blueprint('libretti', __name__, url_prefix='/productions')

def _libretto_required(f):
    @wraps(f)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.can_edit_libretto():
            flash('Доступ к либретто только у роли "Завлит".', 'danger')
            pid = kwargs.get('pid')
            return redirect((url_for('productions.detail', pid=pid) + '#libretto') if pid else url_for('productions.list_productions'))
        return f(*args, **kwargs)
    return wrapped

@libretti_bp.route('/<int:pid>/libretto/main/upload', methods=['POST'])
@_libretto_required
def upload_main(pid):
    db.get_or_404(Production, pid)
    file = request.files.get('libretto_file')
    fp, fn = save_file(file, material_type='libretto', production_id=pid) if file else (None, None)
    if not fp:
        flash('Выберите файл либретто.', 'danger')
        return redirect(url_for('productions.detail', pid=pid) + '#libretto')
    lib = get_or_create_libretto(pid)
    lib.file_path = fp
    lib.file_name = fn
    db.session.commit()
    flash('Файл либретто загружен.', 'success')
    return redirect(url_for('productions.detail', pid=pid) + '#libretto')

@libretti_bp.route('/<int:pid>/libretto/main/delete', methods=['POST'])
@_libretto_required
def delete_main_file(pid):
    lib = Libretto.query.filter_by(production_id=pid).first()
    if lib:
        lib.file_path = None
        lib.file_name = None
        db.session.commit()
        flash('Файл либретто удалён.', 'success')
    return redirect(url_for('productions.detail', pid=pid) + '#libretto')

@libretti_bp.route('/<int:pid>/libretto/role/add', methods=['POST'])
@_libretto_required
def add_role(pid):
    db.get_or_404(Production, pid)
    role_name = request.form.get('role_name', '').strip()
    if not role_name:
        flash('Укажите название роли.', 'danger')
        return redirect(url_for('productions.detail', pid=pid) + '#libretto')
    lib = get_or_create_libretto(pid)
    lr = get_or_create_libretto_role(lib.id, role_name)
    file = request.files.get('role_file')
    if file and file.filename:
        fp, fn = save_file(file, material_type='libretto', production_id=pid)
        if fp:
            lr.file_path = fp
            lr.file_name = fn
    db.session.commit()
    flash('Роль добавлена.', 'success')
    return redirect(url_for('productions.detail', pid=pid) + '#libretto')

@libretti_bp.route('/<int:pid>/libretto/role/<int:rid>/file', methods=['POST'])
@_libretto_required
def attach_role_file(pid, rid):
    lr = db.get_or_404(LibrettoRole, rid)
    file = request.files.get('role_file')
    fp, fn = save_file(file, material_type='libretto', production_id=pid) if file else (None, None)
    if not fp:
        flash('Выберите файл.', 'danger')
        return redirect(url_for('productions.detail', pid=pid) + '#libretto')
    lr.file_path = fp
    lr.file_name = fn
    db.session.commit()
    flash('Файл роли прикреплён.', 'success')
    return redirect(url_for('productions.detail', pid=pid) + '#libretto')

@libretti_bp.route('/<int:pid>/libretto/role/<int:rid>/delete', methods=['POST'])
@_libretto_required
def delete_role(pid, rid):
    lr = db.get_or_404(LibrettoRole, rid)
    db.session.delete(lr)
    db.session.commit()
    flash('Роль удалена.', 'success')
    return redirect(url_for('productions.detail', pid=pid) + '#libretto')
