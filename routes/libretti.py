from flask import Blueprint, redirect, url_for, flash, request
from flask_login import login_required, current_user
from functools import wraps
from app import db, Production, Libretto, LibrettoRole
from utils import save_file, get_or_create_libretto, get_or_create_libretto_role
from audit import commit_with_audit

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
    production = db.get_or_404(Production, pid)
    file = request.files.get('libretto_file')
    fp, fn = save_file(file, material_type='libretto', production_id=pid) if file else (None, None)
    if not fp:
        flash('Выберите файл либретто.', 'danger')
        return redirect(url_for('productions.detail', pid=pid) + '#libretto')
    lib = get_or_create_libretto(pid)
    action = 'update' if lib.file_path else 'create'
    lib.file_path = fp
    lib.file_name = fn
    commit_with_audit(action, 'Либретто', f'{production.name}: {fn}', lib.id,
                      'Основной файл либретто')
    flash('Файл либретто загружен.', 'success')
    return redirect(url_for('productions.detail', pid=pid) + '#libretto')

@libretti_bp.route('/<int:pid>/libretto/main/delete', methods=['POST'])
@_libretto_required
def delete_main_file(pid):
    production = db.get_or_404(Production, pid)
    lib = Libretto.query.filter_by(production_id=pid).first()
    if lib:
        label = f'{production.name}: {lib.file_name or "основной файл"}'
        lib.file_path = None
        lib.file_name = None
        commit_with_audit('delete', 'Либретто', label, lib.id,
                          'Основной файл либретто')
        flash('Файл либретто удалён.', 'success')
    return redirect(url_for('productions.detail', pid=pid) + '#libretto')

@libretti_bp.route('/<int:pid>/libretto/role/add', methods=['POST'])
@_libretto_required
def add_role(pid):
    production = db.get_or_404(Production, pid)
    role_name = request.form.get('role_name', '').strip()
    if not role_name:
        flash('Укажите название роли.', 'danger')
        return redirect(url_for('productions.detail', pid=pid) + '#libretto')
    lib = get_or_create_libretto(pid)
    existing_role_ids = {role.id for role in lib.roles}
    lr = get_or_create_libretto_role(lib.id, role_name)
    file = request.files.get('role_file')
    if file and file.filename:
        fp, fn = save_file(file, material_type='libretto', production_id=pid)
        if fp:
            lr.file_path = fp
            lr.file_name = fn
        else:
            flash('Ошибка при сохранении файла.', 'danger')
    action = 'update' if lr.id in existing_role_ids else 'create'
    details = f'Файл: {lr.file_name}' if lr.file_name else None
    commit_with_audit(action, 'Роль либретто', f'{production.name}: {lr.role_name}', lr.id, details)
    flash('Роль добавлена.', 'success')
    return redirect(url_for('productions.detail', pid=pid) + '#libretto')

@libretti_bp.route('/<int:pid>/libretto/role/<int:rid>/file', methods=['POST'])
@_libretto_required
def attach_role_file(pid, rid):
    production = db.get_or_404(Production, pid)
    lr = db.get_or_404(LibrettoRole, rid)
    file = request.files.get('role_file')
    fp, fn = save_file(file, material_type='libretto', production_id=pid) if file else (None, None)
    if not fp:
        flash('Выберите файл.', 'danger')
        return redirect(url_for('productions.detail', pid=pid) + '#libretto')
    lr.file_path = fp
    lr.file_name = fn
    commit_with_audit('update', 'Роль либретто', f'{production.name}: {lr.role_name}', lr.id,
                      f'Прикреплён файл: {fn}')
    flash('Файл роли прикреплён.', 'success')
    return redirect(url_for('productions.detail', pid=pid) + '#libretto')

@libretti_bp.route('/<int:pid>/libretto/role/<int:rid>/delete', methods=['POST'])
@_libretto_required
def delete_role(pid, rid):
    production = db.get_or_404(Production, pid)
    lr = db.get_or_404(LibrettoRole, rid)
    label = f'{production.name}: {lr.role_name}'
    details = f'Файл: {lr.file_name}' if lr.file_name else None
    db.session.delete(lr)
    commit_with_audit('delete', 'Роль либретто', label, rid, details)
    flash('Роль удалена.', 'success')
    return redirect(url_for('productions.detail', pid=pid) + '#libretto')
