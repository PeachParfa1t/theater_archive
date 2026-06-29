from flask import Blueprint, redirect, url_for, flash, request, send_from_directory
from flask_login import login_required, current_user
from app import db, Document, Production, save_file, editor_required
import os, flask

documents_bp = Blueprint('documents', __name__, url_prefix='/productions')

@documents_bp.route('/<int:pid>/documents/add', methods=['POST'])
@editor_required
def add_document(pid):
    db.get_or_404(Production, pid)
    doc_type = request.form.get('doc_type', '').strip()
    title    = request.form.get('title', '').strip()
    file     = request.files.get('doc_file')
    if not doc_type or not file:
        flash('Укажите тип документа и прикрепите файл.', 'danger')
        return redirect(url_for('productions.detail', pid=pid) + '#documents')
    fp, fn = save_file(file, material_type='document', production_id=pid)
    if not fp:
        flash('Недопустимый формат файла.', 'danger')
        return redirect(url_for('productions.detail', pid=pid) + '#documents')
    doc = Document(production_id=pid, doc_type=doc_type, file_path=fp, file_name=fn, title=title or fn)
    db.session.add(doc)
    db.session.commit()
    flash('Документ прикреплён.', 'success')
    return redirect(url_for('productions.detail', pid=pid) + '#documents')

@documents_bp.route('/<int:pid>/documents/<int:did>/delete', methods=['POST'])
@editor_required
def delete_document(pid, did):
    doc = db.get_or_404(Document, did)
    db.session.delete(doc)
    db.session.commit()
    flash('Документ удалён.', 'success')
    return redirect(url_for('productions.detail', pid=pid) + '#documents')
