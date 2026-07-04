from flask import Blueprint, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db, MusicMaterial, Production, editor_required
from utils import save_file

music_materials_bp = Blueprint('music_materials', __name__, url_prefix='/productions')

@music_materials_bp.route('/<int:pid>/music/add', methods=['POST'])
@editor_required
def add_music_material(pid):
    db.get_or_404(Production, pid)
    category    = request.form.get('category', '').strip()
    description = request.form.get('description', '').strip()
    file        = request.files.get('music_file')

    if category not in MusicMaterial.CATEGORIES:
        flash('Выберите раздел (Клавиры/Партитуры/Фонограммы/Дэмо).', 'danger')
        return redirect(url_for('productions.detail', pid=pid) + '#music')

    fp, fn = save_file(file, material_type='music', production_id=pid) if file and file.filename else (None, None)
    if not fp:
        flash('Выберите файл поддерживаемого формата.', 'danger')
        return redirect(url_for('productions.detail', pid=pid) + '#music')

    mm = MusicMaterial(
        production_id     = pid,
        category          = category,
        file_path         = fp,
        original_filename = fn,
        description       = description or None,
    )
    db.session.add(mm)
    db.session.commit()
    flash('Файл добавлен в музыкальный материал.', 'success')
    return redirect(url_for('productions.detail', pid=pid) + '#music')

@music_materials_bp.route('/<int:pid>/music/<int:mmid>/delete', methods=['POST'])
@editor_required
def delete_music_material(pid, mmid):
    mm = db.get_or_404(MusicMaterial, mmid)
    db.session.delete(mm)
    db.session.commit()
    flash('Файл удалён.', 'success')
    return redirect(url_for('productions.detail', pid=pid) + '#music')
