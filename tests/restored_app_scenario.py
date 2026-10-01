"""Open a restored record and file with the application in a fresh process."""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app, db, Material, Production, User


with app.app_context():
    production = Production.query.filter_by(
        name=os.environ['EXPECTED_PRODUCTION']
    ).one()
    material = Material.query.filter_by(
        production_id=production.id,
        title=os.environ['EXPECTED_MATERIAL'],
    ).one()
    production_id = production.id
    relative_file = material.file_path
    admin_id = User.query.filter_by(login='admin').one().id

client = app.test_client()
with client.session_transaction() as session:
    session['_user_id'] = str(admin_id)
    session['_fresh'] = True

record_response = client.get(f'/productions/{production_id}')
assert record_response.status_code == 200
assert os.environ['EXPECTED_PRODUCTION'] in record_response.get_data(as_text=True)
record_response.close()

file_response = client.get(f'/uploads/{relative_file}')
assert file_response.status_code == 200
assert sha256(file_response.data).hexdigest() == os.environ['EXPECTED_FILE_SHA256']
file_response.close()

with app.app_context():
    db.session.remove()
    db.engine.dispose()

print('RESTORED_APP_OK')
