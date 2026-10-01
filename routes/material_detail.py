from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from app import db, Material, MaterialArtist, MaterialDirector, Artist, Director, editor_required
from audit import commit_with_audit

material_detail_bp = Blueprint('material_detail', __name__, url_prefix='/materials')

@material_detail_bp.route('/<int:mid>')
@login_required
def detail(mid):
    mat = db.get_or_404(Material, mid)
    return render_template('materials/detail.html', mat=mat)

@material_detail_bp.route('/<int:mid>/artists/add', methods=['POST'])
@editor_required
def add_artist_link(mid):
    material = db.get_or_404(Material, mid)
    artist_id = request.form.get('artist_id')
    if not artist_id:
        flash('Выберите артиста.', 'danger')
        return redirect(url_for('material_detail.detail', mid=mid))
    if not MaterialArtist.query.filter_by(material_id=mid, artist_id=int(artist_id)).first():
        artist = db.get_or_404(Artist, int(artist_id))
        link = MaterialArtist(material_id=mid, artist_id=artist.id)
        db.session.add(link)
        db.session.flush()
        commit_with_audit(
            'create', 'Связь материала с артистом',
            f'{material.title or material.file_name or material.url}: {artist.full_name}', link.id,
        )
        flash('Артист привязан к материалу.', 'success')
    else:
        flash('Этот артист уже привязан.', 'warning')
    return redirect(url_for('material_detail.detail', mid=mid))

@material_detail_bp.route('/<int:mid>/artists/<int:link_id>/remove', methods=['POST'])
@editor_required
def remove_artist_link(mid, link_id):
    link = db.get_or_404(MaterialArtist, link_id)
    label = f'{link.material.title or link.material.file_name or link.material.url}: {link.artist.full_name}'
    db.session.delete(link)
    commit_with_audit('delete', 'Связь материала с артистом', label, link_id)
    flash('Связь с артистом удалена.', 'success')
    return redirect(url_for('material_detail.detail', mid=mid))

@material_detail_bp.route('/<int:mid>/directors/add', methods=['POST'])
@editor_required
def add_director_link(mid):
    material = db.get_or_404(Material, mid)
    director_id = request.form.get('director_id')
    if not director_id:
        flash('Выберите постановщика.', 'danger')
        return redirect(url_for('material_detail.detail', mid=mid))
    if not MaterialDirector.query.filter_by(material_id=mid, director_id=int(director_id)).first():
        director = db.get_or_404(Director, int(director_id))
        link = MaterialDirector(material_id=mid, director_id=director.id)
        db.session.add(link)
        db.session.flush()
        commit_with_audit(
            'create', 'Связь материала с постановщиком',
            f'{material.title or material.file_name or material.url}: {director.full_name}', link.id,
        )
        flash('Постановщик привязан к материалу.', 'success')
    else:
        flash('Этот постановщик уже привязан.', 'warning')
    return redirect(url_for('material_detail.detail', mid=mid))

@material_detail_bp.route('/<int:mid>/directors/<int:link_id>/remove', methods=['POST'])
@editor_required
def remove_director_link(mid, link_id):
    link = db.get_or_404(MaterialDirector, link_id)
    label = f'{link.material.title or link.material.file_name or link.material.url}: {link.director.full_name}'
    db.session.delete(link)
    commit_with_audit('delete', 'Связь материала с постановщиком', label, link_id)
    flash('Связь с постановщиком удалена.', 'success')
    return redirect(url_for('material_detail.detail', mid=mid))
