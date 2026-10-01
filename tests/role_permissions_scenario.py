"""Child-process scenario for configurable role permissions."""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


database = Path(os.environ['DATABASE_PATH'])
uploads = Path(os.environ['UPLOAD_FOLDER'])
database.parent.mkdir(parents=True)

# Start from the schema that existed before configurable permissions.  Successful
# initialization below proves that an existing installation receives permissive columns.
with sqlite3.connect(database) as connection:
    connection.execute('''
        CREATE TABLE roles (
            id INTEGER PRIMARY KEY,
            name VARCHAR(50) UNIQUE NOT NULL,
            display_name VARCHAR(100) NOT NULL
        )
    ''')

from init_db import init
from app import (app, db, AuditLog, Libretto, Material, MusicMaterial,
                 Production, Role, User)


init()

with sqlite3.connect(database) as connection:
    role_columns = {row[1] for row in connection.execute('PRAGMA table_info(roles)')}
assert {
    'allow_report_generation', 'allow_report_download', 'allow_archive_download'
}.issubset(role_columns)

regular_path = 'documents/permission-check/archive.pdf'
music_path = 'music/permission-check/score.pdf'
libretto_path = 'libretti/permission-check/libretto.pdf'
for relative, contents in (
    (regular_path, b'ordinary archive file'),
    (music_path, b'restricted music file'),
    (libretto_path, b'restricted libretto file'),
):
    target = uploads / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(contents)

with app.app_context():
    production = Production.query.first()
    production_id = production.id
    db.session.add(Material(
        production_id=production_id,
        material_type='document',
        file_path=regular_path,
        file_name='archive.pdf',
        title='Permission archive file',
    ))
    db.session.add(MusicMaterial(
        production_id=production_id,
        category='score',
        file_path=music_path,
        original_filename='score.pdf',
    ))
    db.session.add(Libretto(
        production_id=production_id,
        file_path=libretto_path,
        file_name='libretto.pdf',
    ))

    role_ids = {role.name: role.id for role in Role.query.all()}
    user_ids = {'admin': User.query.filter_by(login='admin').one().id}
    for role_name in ('editor', 'observer', 'music_lib', 'zavlit'):
        user = User(
            full_name=f'Permission {role_name}',
            login=f'permission-{role_name}',
            role_id=role_ids[role_name],
        )
        user.set_password('test-password')
        db.session.add(user)
        db.session.flush()
        user_ids[role_name] = user.id
    db.session.commit()


client = app.test_client()


def login_as(role_name: str):
    with client.session_transaction() as session:
        session.clear()
        session['_user_id'] = str(user_ids[role_name])
        session['_fresh'] = True


# Configure all roles through the administrator-facing endpoint.  Deliberately omit
# admin fields to verify that a forged/empty form cannot remove administrator access.
login_as('admin')
permission_page = client.get('/admin/roles/permissions')
assert permission_page.status_code == 200
for label in ('Формирование отчётов', 'Скачивание отчётов', 'Скачивание файлов архива'):
    assert label.encode() in permission_page.data
permission_page.close()

form = {}
for field in ('allow_report_generation', 'allow_report_download', 'allow_archive_download'):
    form[f'role_{role_ids["editor"]}_{field}'] = 'on'
form[f'role_{role_ids["observer"]}_allow_report_generation'] = 'on'
form[f'role_{role_ids["music_lib"]}_allow_report_download'] = 'on'
form[f'role_{role_ids["music_lib"]}_allow_archive_download'] = 'on'
form[f'role_{role_ids["zavlit"]}_allow_archive_download'] = 'on'
response = client.post('/admin/roles/permissions', data=form)
assert response.status_code == 302
response.close()

with app.app_context():
    admin = db.session.get(User, user_ids['admin'])
    assert admin.can_manage_users()
    assert admin.can_generate_reports()
    assert admin.can_download_reports()
    assert admin.can_download_archive_files()
    admin_role = Role.query.filter_by(name='admin').one()
    assert admin_role.allow_report_generation
    assert admin_role.allow_report_download
    assert admin_role.allow_archive_download
    assert AuditLog.query.filter_by(object_type='Права ролей', action='update').count() == 1

# Editor: all three configurable permissions; ordinary editing remains available,
# but the special music and libretto restrictions still apply.
login_as('editor')
detail = client.get(f'/productions/{production_id}')
assert detail.status_code == 200
assert b'href="/reports/"' in detail.data
assert regular_path.encode() in detail.data
assert b'href="#libretto"' not in detail.data
detail.close()

reports = client.get('/reports/')
assert reports.status_code == 200
assert b'/reports/productions/export' in reports.data
reports.close()
export = client.get('/reports/productions/export?format=xlsx')
assert export.status_code == 200
assert 'attachment' in export.headers.get('Content-Disposition', '')
export.close()
ordinary_file = client.get(f'/uploads/{regular_path}')
assert ordinary_file.status_code == 200 and ordinary_file.data == b'ordinary archive file'
ordinary_file.close()
music_file = client.get(f'/uploads/{music_path}')
assert music_file.status_code == 302
music_file.close()
libretto_file = client.get(f'/uploads/{libretto_path}')
assert libretto_file.status_code == 403
libretto_file.close()

create = client.post('/productions/create', data={
    'name': 'Editor-created production', 'genre': 'Test',
    'premiere_year': '2026', 'status': 'active',
})
assert create.status_code == 302
create.close()
delete_libretto = client.post(f'/productions/{production_id}/libretto/main/delete')
assert delete_libretto.status_code == 302
delete_libretto.close()
with app.app_context():
    assert Production.query.filter_by(name='Editor-created production').one_or_none() is not None
    assert Libretto.query.filter_by(production_id=production_id).one().file_path == libretto_path

# Observer: may open report parameters, but sees no export actions and cannot bypass
# either the report download or archive-file checks by typing a URL directly.
login_as('observer')
detail = client.get(f'/productions/{production_id}')
assert detail.status_code == 200
assert b'href="/reports/"' in detail.data
assert regular_path.encode() not in detail.data
detail.close()
reports = client.get('/reports/')
assert reports.status_code == 200
assert b'/reports/productions/export' not in reports.data
assert 'скачивание'.encode() in reports.data.lower()
reports.close()
denied_export = client.get('/reports/productions/export?format=xlsx')
assert denied_export.status_code == 403
denied_export.close()
denied_file = client.get(f'/uploads/{regular_path}')
assert denied_file.status_code == 403
denied_file.close()
denied_create = client.post('/productions/create', data={
    'name': 'Observer must not create', 'genre': 'Test',
    'premiere_year': '2026', 'status': 'active',
})
assert denied_create.status_code == 302
denied_create.close()
with app.app_context():
    assert Production.query.filter_by(name='Observer must not create').one_or_none() is None

# Music librarian: report download alone cannot bypass report-generation permission;
# music access still works while libretto remains restricted.
login_as('music_lib')
detail = client.get(f'/productions/{production_id}')
assert detail.status_code == 200
assert b'href="/reports/"' not in detail.data
assert b'href="#music"' in detail.data
detail.close()
assert client.get('/reports/').status_code == 403
assert client.get('/reports/productions/export?format=xlsx').status_code == 403
music_file = client.get(f'/uploads/{music_path}')
assert music_file.status_code == 200 and music_file.data == b'restricted music file'
music_file.close()
assert client.get(f'/uploads/{libretto_path}').status_code == 403

# Zavlit retains libretto access and general editing, but not music access.
login_as('zavlit')
detail = client.get(f'/productions/{production_id}')
assert detail.status_code == 200
assert b'href="#libretto"' in detail.data
assert libretto_path.encode() in detail.data
detail.close()
libretto_file = client.get(f'/uploads/{libretto_path}')
assert libretto_file.status_code == 200 and libretto_file.data == b'restricted libretto file'
libretto_file.close()
assert client.get(f'/uploads/{music_path}').status_code == 302

# Only the administrator can manage the settings page, and forced rights still work.
assert client.get('/admin/roles/permissions').status_code == 302
login_as('admin')
assert client.get('/admin/roles/permissions').status_code == 200
assert client.get('/reports/').status_code == 200
assert client.get(f'/uploads/{regular_path}').status_code == 200

with app.app_context():
    db.session.remove()
    db.engine.dispose()

print('ROLE_PERMISSIONS_OK roles=4 direct_checks=reports,files special=edit,music,libretto')
