from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db, Material, MaterialArtist, Artist, editor_required
from utils import save_file

photobank_bp = Blueprint('photobank', __name__, url_prefix='/photobank')

@photobank_bp.route('/')
@login_required
def list_photobank():
    materials = (Material.query
                 .filter(Material.production_id.is_(None))
                 .order_by(Material.created_at.desc())
                 .all())
    return render_template('photobank/list.html', materials=materials)

@photobank_bp.route('/add', methods=['GET', 'POST'])
@editor_required
def add_photo():
    if request.method == 'POST':
        mat_type   = request.form.get('material_type', 'photo').strip() or 'photo'
        title      = request.form.get('title', '').strip()
        url        = request.form.get('url', '').strip()
        file       = request.files.get('mat_file')
        artist_ids = request.form.getlist('artist_ids')

        fp, fn = save_file(file, material_type=mat_type, production_id=None) if file and file.filename else (None, None)
        if not fp and not url:
            flash('Загрузите файл или укажите URL.', 'danger')
            return redirect(url_for('photobank.add_photo'))

        mat = Material(
            production_id = None,
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
        flash('Фото добавлено в фотобанк.', 'success')
        return redirect(url_for('photobank.list_photobank'))

    artists = Artist.query.order_by(Artist.full_name).all()
    return render_template('photobank/form.html', artists=artists)

@photobank_bp.route('/<int:mid>/delete', methods=['POST'])
@editor_required
def delete_photo(mid):
    mat = db.get_or_404(Material, mid)
    db.session.delete(mat)
    db.session.commit()
    flash('Фото удалено.', 'success')
    return redirect(url_for('photobank.list_photobank'))
