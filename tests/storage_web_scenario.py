"""Child-process scenario used by test_storage_integration.py (not test discovery)."""
from io import BytesIO
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from init_db import init
from app import app, db, Material, Production, User


database = Path(os.environ['DATABASE_PATH'])
uploads = Path(os.environ['UPLOAD_FOLDER'])
backups = Path(os.environ['BACKUP_FOLDER'])
init()

assert Path(app.config['UPLOAD_FOLDER']) == uploads
assert Path(app.config['BACKUP_FOLDER']) == backups
assert database.is_file()

with app.app_context():
    production = Production.query.first()
    legacy_path = Path('legacy') / 'previously-uploaded.pdf'
    (uploads / legacy_path.parent).mkdir(parents=True, exist_ok=True)
    (uploads / legacy_path).write_bytes(b'previous file contents')
    legacy_material = Material(
        production_id=production.id,
        material_type='document',
        file_path=legacy_path.as_posix(),
        file_name='previously-uploaded.pdf',
        title='Existing file',
    )
    db.session.add(legacy_material)
    db.session.commit()
    admin_id = User.query.filter_by(login='admin').one().id

client = app.test_client()
with client.session_transaction() as session:
    session['_user_id'] = str(admin_id)
    session['_fresh'] = True

create_response = client.post('/productions/create', data={
    'name': 'Storage integration production',
    'genre': 'Test genre',
    'premiere_year': '2026',
    'status': 'active',
})
assert create_response.status_code == 302
create_response.close()

with app.app_context():
    created = Production.query.filter_by(name='Storage integration production').one()
    created_id = created.id

upload_response = client.post(
    f'/productions/{created_id}/materials/add',
    data={
        'material_type': 'photo',
        'title': 'Configured upload',
        'mat_file': (BytesIO(b'new image contents'), 'new-image.jpg'),
    },
    content_type='multipart/form-data',
)
assert upload_response.status_code == 302
upload_response.close()

with app.app_context():
    uploaded = Material.query.filter_by(
        production_id=created_id, title='Configured upload'
    ).one()
    uploaded_path = uploaded.file_path
    assert (uploads / uploaded_path).is_file()

uploaded_response = client.get(f'/uploads/{uploaded_path}')
assert uploaded_response.status_code == 200
assert uploaded_response.data == b'new image contents'
uploaded_response.close()

legacy_response = client.get(f'/uploads/{legacy_path.as_posix()}')
assert legacy_response.status_code == 200
assert legacy_response.data == b'previous file contents'
legacy_response.close()

with app.app_context():
    db.session.remove()
    db.engine.dispose()
