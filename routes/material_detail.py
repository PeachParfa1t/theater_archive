from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from app import db, Material, MaterialArtist, MaterialDirector, Artist, Director, editor_required

material_detail_bp = Blueprint('material_detail', __name__, url_prefix='/materials')

@material_detail_bp.route('/<int:mid>')
@login_required
def detail(mid):
    mat = db.get_or_404(Material, mid)
    return render_template('materials/detail.html', mat=mat)

@material_detail_bp.route('/<int:mid>/artists/add', methods=['POST'])
@editor_required
def add_artist_link(mid):
    db.get_or_404(Material, mid)
    artist_id = request.form.get('artist_id')
    if not artist_id:
        flash('Выберите артиста.', 'danger')
        return redirect(url_for('material_detail.detail', mid=mid))
    if not MaterialArtist.query.filter_by(material_id=mid, artist_id=int(artist_id)).first():
        db.session.add(MaterialArtist(material_id=mid, artist_id=int(artist_id)))
        db.session.commit()
        flash('Артист привязан к материалу.', 'success')
    else:
        flash('Этот артист уже привязан.', 'warning')
    return redirect(url_for('material_detail.detail', mid=mid))

@material_detail_bp.route('/<int:mid>/artists/<int:link_id>/remove', methods=['POST'])
@editor_required
def remove_artist_link(mid, link_id):
    link = db.get_or_404(MaterialArtist, link_id)
    db.session.delete(link)
    db.session.commit()
    flash('Связь с артистом удалена.', 'success')
    return redirect(url_for('material_detail.detail', mid=mid))

@material_detail_bp.route('/<int:mid>/directors/add', methods=['POST'])
@editor_required
def add_director_link(mid):
    db.get_or_404(Material, mid)
    director_id = request.form.get('director_id')
    if not director_id:
        flash('Выберите постановщика.', 'danger')
        return redirect(url_for('material_detail.detail', mid=mid))
    if not MaterialDirector.query.filter_by(material_id=mid, director_id=int(director_id)).first():
        db.session.add(MaterialDirector(material_id=mid, director_id=int(director_id)))
        db.session.commit()
        flash('Постановщик привязан к материалу.', 'success')
    else:
        flash('Этот постановщик уже привязан.', 'warning')
    return redirect(url_for('material_detail.detail', mid=mid))

@material_detail_bp.route('/<int:mid>/directors/<int:link_id>/remove', methods=['POST'])
@editor_required
def remove_director_link(mid, link_id):
    link = db.get_or_404(MaterialDirector, link_id)
    db.session.delete(link)
    db.session.commit()
    flash('Связь с постановщиком удалена.', 'success')
    return redirect(url_for('material_detail.detail', mid=mid))
