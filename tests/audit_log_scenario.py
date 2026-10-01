"""Child-process web scenario for audit logging (excluded from test discovery)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from init_db import init
from app import app, db, Artist, AuditLog, Production, User


init()

with app.app_context():
    admin_id = User.query.filter_by(login='admin').one().id
    assert AuditLog.query.count() == 0

client = app.test_client()
with client.session_transaction() as session:
    session['_user_id'] = str(admin_id)
    session['_fresh'] = True

# Ordinary reads, including the audit page itself, are not actions.
for path in ('/productions/', '/artists/', '/tours/', '/competitions/', '/admin/audit-log'):
    response = client.get(path)
    assert response.status_code == 200, (path, response.status_code)
    response.close()
with app.app_context():
    assert AuditLog.query.count() == 0

response = client.post('/productions/create', data={
    'name': 'Audit production', 'genre': 'Test', 'premiere_year': '2026', 'status': 'active',
})
assert response.status_code == 302
response.close()

response = client.post('/artists/create', data={'full_name': 'Audit Artist'})
assert response.status_code == 302
response.close()
with app.app_context():
    artist_id = Artist.query.filter_by(full_name='Audit Artist').one().id
    production_id = Production.query.filter_by(name='Audit production').one().id

response = client.post(f'/artists/{artist_id}/edit', data={
    'full_name': 'Audit Artist Updated', 'position': 'Soloist',
})
assert response.status_code == 302
response.close()

response = client.post('/tours/create', data={'city': 'Audit City', 'year': '2026'})
assert response.status_code == 302
response.close()

response = client.post('/competitions/create', data={'name': 'Audit Competition', 'year': '2026'})
assert response.status_code == 302
response.close()

response = client.get('/reports/productions/export?format=xlsx')
assert response.status_code == 200
response.close()

secret_password = 'TOP-SECRET-PASSWORD-123'
with app.app_context():
    role_id = User.query.filter_by(login='admin').one().role_id
response = client.post('/admin/users/create', data={
    'full_name': 'Audit User', 'login': 'audit-user',
    'password': secret_password, 'role_id': str(role_id),
})
assert response.status_code == 302
response.close()

response = client.post(f'/artists/{artist_id}/delete')
assert response.status_code == 302
response.close()

with app.app_context():
    entries = AuditLog.query.order_by(AuditLog.id).all()
    assert len(entries) == 8, [(entry.action, entry.object_type) for entry in entries]
    assert [(entry.action, entry.object_type) for entry in entries] == [
        ('create', 'Постановка'),
        ('create', 'Артист'),
        ('update', 'Артист'),
        ('create', 'Гастроль'),
        ('create', 'Конкурс'),
        ('report', 'Отчёт по постановкам'),
        ('create', 'Пользователь'),
        ('delete', 'Артист'),
    ]
    deleted = entries[-1]
    assert deleted.object_id == str(artist_id)
    assert deleted.object_label == 'Audit Artist Updated'
    assert Artist.query.get(artist_id) is None
    assert Production.query.get(production_id) is not None
    serialized = ' '.join(
        str(value) for entry in entries for value in (
            entry.user_name, entry.user_login, entry.object_label, entry.details,
        ) if value
    )
    assert secret_password not in serialized
    count_before_reads = len(entries)

for path in (f'/productions/{production_id}', '/admin/audit-log'):
    response = client.get(path)
    assert response.status_code == 200
    if path == '/admin/audit-log':
        assert 'Audit Artist Updated'.encode() in response.data
        assert 'Формирование отчёта'.encode() in response.data
    response.close()

with app.app_context():
    assert AuditLog.query.count() == count_before_reads
    db.session.remove()
    db.engine.dispose()
