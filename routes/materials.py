from flask import Blueprint, redirect, url_for, flash, request, render_template
from flask_login import login_required, current_user
from app import db, Material, MaterialArtist, Artist, Production, save_file, editor_required

materials_bp = Blueprint('materials', __name__, url_prefix='/productions')

@materials_bp.route('/<int:pid>/materials/add', methods=['GET', 'POST'])
@editor_required
def add_material(pid):
    p = db.get_or_404(Production, pid)
    if request.method == 'POST':
        mat_type   = request.form.get('material_type', '').strip()
        title      = request.form.get('title', '').strip()
        url        = request.form.get('url', '').strip()
        file       = request.files.get('mat_file')
        artist_ids = request.form.getlist('artist_ids')

        if not mat_type:
            flash('Укажите тип материала.', 'danger')
            return redirect(url_for('productions.detail', pid=pid))

        fp, fn = save_file(file) if file and file.filename else (None, None)
        if not fp and not url:
            flash('Загрузите файл или укажите URL.', 'danger')
            return redirect(url_for('productions.detail', pid=pid))

        mat = Material(
            production_id = pid,
            material_type = mat_type,
            file_path     = fp,
            file_name     = fn,
            url           = url or None,
            title         = title or fn or url,
        )
        db.session.add(mat)
        db.session.flush()
        for aid in artist_ids:
            try:
                db.session.add(MaterialArtist(material_id=mat.id, artist_id=int(aid)))
            except (ValueError, TypeError):
                pass
        db.session.commit()
        flash('Материал добавлен.', 'success')
        return redirect(url_for('productions.detail', pid=pid))

    artists = Artist.query.order_by(Artist.full_name).all()
    return render_template('materials/form.html', p=p, artists=artists)

@materials_bp.route('/<int:pid>/materials/<int:mid>/delete', methods=['POST'])
@editor_required
def delete_material(pid, mid):
    mat = db.get_or_404(Material, mid)
    db.session.delete(mat)
    db.session.commit()
    flash('Материал удалён.', 'success')
    return redirect(url_for('productions.detail', pid=pid))
