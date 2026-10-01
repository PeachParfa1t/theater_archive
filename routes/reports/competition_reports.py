from flask import request
from flask_login import login_required
from app import Competition
from audit import commit_with_audit
from . import reports_bp, xlsx_response, docx_table_response

# ---------- Конкурсы: фильтруемый список ----------
@reports_bp.route('/competitions/export')
@login_required
def export_competitions():
    fmt = request.args.get('format', 'xlsx')
    name_q = request.args.get('name', '').strip()
    year_from = request.args.get('year_from', '').strip()
    year_to = request.args.get('year_to', '').strip()
    status = request.args.get('status', '').strip()
    artist_q = request.args.get('artist', '').strip()
    award_level = request.args.get('award_level', '').strip()

    competitions = Competition.query.order_by(Competition.year.desc(), Competition.name).all()

    def matches(c):
        if name_q and name_q.lower() not in c.name.lower():
            return False
        if year_from and c.year < int(year_from):
            return False
        if year_to and c.year > int(year_to):
            return False
        if status and c.status_name != status:
            return False
        if artist_q:
            target = artist_q.lower()
            if not any(target in link.artist.full_name.lower() for link in c.artist_links):
                return False
        if award_level:
            has_level = (any(l.award_level_name == award_level for l in c.artist_links) or
                        any(l.award_level_name == award_level for l in c.production_links))
            if not has_level:
                return False
        return True

    filtered = [c for c in competitions if matches(c)]

    headers = ['№', 'Название конкурса', 'Год', 'Статус', 'Артист', 'Постановка', 'Уровень награды']
    rows = []
    for c in filtered:
        if not c.artist_links and not c.production_links:
            rows.append([len(rows) + 1, c.name, c.year, c.status_name, '—', '—', '—'])
            continue
        for link in c.artist_links:
            rows.append([len(rows) + 1, c.name, c.year, c.status_name, link.artist.full_name, '—', link.award_level_name])
        for link in c.production_links:
            rows.append([len(rows) + 1, c.name, c.year, c.status_name, '—', link.production.name, link.award_level_name])

    title = 'Отчёт по конкурсам'
    if fmt == 'docx':
        response = docx_table_response(title, headers, rows, title)
        actual_format = 'DOCX'
    else:
        response = xlsx_response(headers, rows, title)
        actual_format = 'XLSX'
    commit_with_audit('report', 'Отчёт по конкурсам', title,
                      details=f'Формат: {actual_format}; строк: {len(rows)}')
    return response
