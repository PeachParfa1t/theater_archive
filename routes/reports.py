import re
from io import BytesIO
from flask import Blueprint, render_template, request, send_file
from flask_login import login_required
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment
from docx import Document as DocxDocument
from docx.shared import Pt
from app import (
    db, Production, CastEntry, Artist,
    Tour, TourType, TourArtist, TourProduction,
    Festival, FestivalStatus, FestivalEdition,
    Competition, CompetitionStatus, CompetitionArtist, CompetitionProduction, AwardLevel,
)

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

def safe_filename(name):
    return re.sub(r'[\\/:*?"<>|]', '_', name).strip() or 'report'

def xlsx_response(headers, rows, filename):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    for i, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(14, len(str(h)) + 4)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f'{safe_filename(filename)}.xlsx', mimetype=XLSX_MIME)

def docx_table_response(title, headers, rows, filename):
    doc = DocxDocument()
    doc.add_heading(title, level=1)
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = 'Light Grid Accent 1'
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = str(h)
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = str(val) if val not in (None, '') else '—'
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f'{safe_filename(filename)}.docx', mimetype=DOCX_MIME)

@reports_bp.route('/')
@login_required
def index():
    genres = sorted({p.genre for p in Production.query.all() if p.genre})
    tour_cities = sorted({t.city for t in Tour.query.all() if t.city})
    tour_types = TourType.query.order_by(TourType.name).all()
    festival_statuses = FestivalStatus.query.order_by(FestivalStatus.name).all()
    competition_statuses = CompetitionStatus.query.order_by(CompetitionStatus.name).all()
    award_levels = AwardLevel.query.order_by(AwardLevel.name).all()
    return render_template('reports/index.html', genres=genres,
                           stages=Production.STAGES, age_ratings=Production.AGE_RATINGS,
                           tour_cities=tour_cities, tour_types=tour_types,
                           festival_statuses=festival_statuses,
                           competition_statuses=competition_statuses,
                           award_levels=award_levels)

# ---------- Артисты: участие в постановках за период ----------
ARTIST_REPORT_SECTIONS = {'tours', 'competitions'}

def _artist_report_docx(title, headers, rows, artists, sections):
    doc = DocxDocument()
    doc.add_heading(title, level=1)
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = 'Light Grid Accent 1'
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = str(h)
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = str(val) if val not in (None, '') else '—'

    if 'tours' in sections:
        for artist in artists:
            doc.add_heading(f'Гастроли — {artist.full_name}', level=2)
            if artist.tour_links:
                t2 = doc.add_table(rows=1, cols=3)
                t2.style = 'Light Grid Accent 1'
                hdr = t2.rows[0].cells
                hdr[0].text, hdr[1].text, hdr[2].text = 'Город', 'Год', 'Постановки'
                for link in artist.tour_links:
                    cells = t2.add_row().cells
                    cells[0].text = link.tour.city
                    cells[1].text = str(link.tour.year)
                    cells[2].text = ', '.join(l.production.name for l in link.tour.production_links) or '—'
            else:
                doc.add_paragraph('Нет данных.')

    if 'competitions' in sections:
        for artist in artists:
            doc.add_heading(f'Конкурсы — {artist.full_name}', level=2)
            if artist.competition_links:
                t3 = doc.add_table(rows=1, cols=3)
                t3.style = 'Light Grid Accent 1'
                hdr = t3.rows[0].cells
                hdr[0].text, hdr[1].text, hdr[2].text = 'Название', 'Год', 'Уровень награды'
                for link in artist.competition_links:
                    cells = t3.add_row().cells
                    cells[0].text = link.competition.name
                    cells[1].text = str(link.competition.year)
                    cells[2].text = link.award_level_name
            else:
                doc.add_paragraph('Нет данных.')

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f'{safe_filename(title)}.docx', mimetype=DOCX_MIME)

def _artist_report_xlsx(headers, rows, artists, sections, title):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Репертуар'
    ws.append(headers)
    for row in rows:
        ws.append(row)
    for i, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(14, len(str(h)) + 4)

    if 'tours' in sections:
        ws2 = wb.create_sheet('Гастроли')
        ws2.append(['Артист', 'Город', 'Год', 'Постановки'])
        for artist in artists:
            for link in artist.tour_links:
                ws2.append([artist.full_name, link.tour.city, link.tour.year,
                           ', '.join(l.production.name for l in link.tour.production_links) or ''])
        for i in range(1, 5):
            ws2.column_dimensions[get_column_letter(i)].width = 28

    if 'competitions' in sections:
        ws3 = wb.create_sheet('Конкурсы')
        ws3.append(['Артист', 'Название', 'Год', 'Уровень награды'])
        for artist in artists:
            for link in artist.competition_links:
                ws3.append([artist.full_name, link.competition.name, link.competition.year, link.award_level_name])
        for i in range(1, 5):
            ws3.column_dimensions[get_column_letter(i)].width = 28

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f'{safe_filename(title)}.xlsx', mimetype=XLSX_MIME)

@reports_bp.route('/artists/export')
@login_required
def export_artists():
    fmt = request.args.get('format', 'xlsx')
    q = request.args.get('q', '').strip()
    year_from = request.args.get('year_from', '').strip()
    year_to = request.args.get('year_to', '').strip()
    sections = {s for s in request.args.getlist('sections') if s in ARTIST_REPORT_SECTIONS}

    query = CastEntry.query.join(Artist).join(Production)
    if q:
        query = query.filter(Artist.full_name.ilike(f'%{q}%'))
    entries = query.order_by(Artist.full_name, Production.premiere_year).all()

    yf = int(year_from) if year_from else None
    yt = int(year_to) if year_to else None

    def overlaps(ce):
        if not yf and not yt:
            return True
        ce_from = ce.year_from or ce.production.premiere_year
        ce_to = ce.year_to or ce_from
        if yf and ce_to < yf:
            return False
        if yt and ce_from > yt:
            return False
        return True

    def stage_director_name(production):
        """The production's Режиссёр-постановщик, if one is assigned in the staging group."""
        for pd in production.staging_group:
            codes = [pp.position for pp in pd.positions] or pd.director.position_codes
            if 'director' in codes:
                return pd.director.full_name
        return ''

    filtered = [ce for ce in entries if overlaps(ce)]

    headers = ['№', 'Название спектакля', 'Автор (композитор)', 'Роль', 'Год выпуска', 'Режиссёр-постановщик']
    rows = [[
        i + 1, ce.production.name, ce.production.music_authors_display, ce.role_name or '—',
        ce.production.premiere_year, stage_director_name(ce.production) or '—',
    ] for i, ce in enumerate(filtered)]

    title = 'Репертуарный лист артиста'
    if q:
        title += f' — {q}'

    artists_in_report = sorted({ce.artist for ce in filtered}, key=lambda a: a.full_name)

    if fmt == 'docx':
        return _artist_report_docx(title, headers, rows, artists_in_report, sections)
    return _artist_report_xlsx(headers, rows, artists_in_report, sections, title)

# ---------- Постановки: фильтруемый список ----------
@reports_bp.route('/productions/export')
@login_required
def export_productions():
    fmt = request.args.get('format', 'xlsx')
    status = request.args.get('status', '')
    genre = request.args.get('genre', '').strip()
    year_from = request.args.get('year_from', '').strip()
    year_to = request.args.get('year_to', '').strip()
    basis = request.args.get('basis', '').strip()
    stage = request.args.get('stage', '').strip()
    age_rating = request.args.get('age_rating', '').strip()
    removal_year_from = request.args.get('removal_year_from', '').strip()
    removal_year_to = request.args.get('removal_year_to', '').strip()

    query = Production.query
    if status:
        query = query.filter(Production.status == status)
    if genre:
        query = query.filter(Production.genre.ilike(f'%{genre}%'))
    if year_from:
        query = query.filter(Production.premiere_year >= int(year_from))
    if year_to:
        query = query.filter(Production.premiere_year <= int(year_to))
    if basis:
        query = query.filter(db.or_(
            Production.literary_basis.ilike(f'%{basis}%'),
            Production.literary_basis_author.ilike(f'%{basis}%'),
        ))
    if stage:
        query = query.filter(Production.stage == stage)
    if age_rating:
        query = query.filter(Production.age_rating == age_rating)
    if removal_year_from:
        query = query.filter(Production.removal_year >= int(removal_year_from))
    if removal_year_to:
        query = query.filter(Production.removal_year <= int(removal_year_to))
    productions = query.order_by(Production.premiere_year.desc()).all()

    headers = ['Название', 'Статус', 'Жанр', 'Премьера', 'Актов',
               'Авторы музыки', 'Авторы либретто', 'Литературная основа', 'Автор основы',
               'Сцена', 'Возрастной ценз', 'Продолжительность', 'Год снятия']
    rows = [[
        p.name, p.status_display, p.genre, p.premiere_display, p.acts_count or '',
        p.music_authors_display, p.libretto_authors_display,
        p.literary_basis or '', p.literary_basis_author or '',
        p.stage or '', p.age_rating or '',
        p.duration_display if (p.duration_hours or p.duration_minutes) else '',
        p.removal_year or '',
    ] for p in productions]

    title = 'Отчёт по постановкам'
    if fmt == 'docx':
        return docx_table_response(title, headers, rows, title)
    return xlsx_response(headers, rows, title)

# ---------- Полная информация по одной постановке ----------
REPORT_SECTIONS = {'cast', 'staging', 'documents', 'materials'}

def _production_docx(p, sections):
    doc = DocxDocument()
    doc.add_heading(p.name, level=1)
    doc.add_paragraph(f'Статус: {p.status_display}')
    doc.add_paragraph(f'Жанр: {p.genre}')
    doc.add_paragraph(f'Премьера: {p.premiere_display}')
    if p.acts_count:
        doc.add_paragraph(f'Количество актов: {p.acts_count}')
    if p.stage:
        doc.add_paragraph(f'Сцена: {p.stage}')
    if p.age_rating:
        doc.add_paragraph(f'Возрастной ценз: {p.age_rating}')
    if p.duration_hours or p.duration_minutes:
        doc.add_paragraph(f'Продолжительность: {p.duration_display}')
    if p.removal_year:
        doc.add_paragraph(f'Год снятия: {p.removal_year}')
    if p.music_authors:
        doc.add_paragraph(f'Авторы музыки: {p.music_authors_display}')
    if p.libretto_authors:
        doc.add_paragraph(f'Авторы либретто: {p.libretto_authors_display}')
    if p.literary_basis:
        line = f'Литературная основа: {p.literary_basis}'
        if p.literary_basis_author:
            line += f' (автор: {p.literary_basis_author})'
        doc.add_paragraph(line)

    if 'cast' in sections:
        doc.add_heading('Состав исполнителей', level=2)
        if p.cast_entries:
            table = doc.add_table(rows=1, cols=3)
            table.style = 'Light Grid Accent 1'
            hdr = table.rows[0].cells
            hdr[0].text, hdr[1].text, hdr[2].text = 'Артист', 'Роль', 'Годы участия'
            for ce in p.cast_entries:
                cells = table.add_row().cells
                cells[0].text = ce.artist.full_name
                cells[1].text = ce.role_name or '—'
                cells[2].text = ce.years_display or '—'
        else:
            doc.add_paragraph('Нет данных.')

    if 'staging' in sections:
        doc.add_heading('Постановочная группа', level=2)
        if p.staging_group:
            table = doc.add_table(rows=1, cols=3)
            table.style = 'Light Grid Accent 1'
            hdr = table.rows[0].cells
            hdr[0].text, hdr[1].text, hdr[2].text = 'ФИО', 'Должность', 'Годы жизни'
            for pd in p.staging_group:
                cells = table.add_row().cells
                cells[0].text = pd.director.full_name
                cells[1].text = pd.position_display
                cells[2].text = pd.director.life_years or '—'
        else:
            doc.add_paragraph('Нет данных.')

    if 'documents' in sections:
        doc.add_heading('Документы', level=2)
        if p.documents:
            for d in p.documents:
                doc.add_paragraph(f'{d.doc_type_display}: {d.title or d.file_name}', style='List Bullet')
        else:
            doc.add_paragraph('Нет данных.')

    if 'materials' in sections:
        doc.add_heading('Материалы', level=2)
        if p.materials:
            for m in p.materials:
                doc.add_paragraph(f'{m.type_display}: {m.title or m.file_name or m.url}', style='List Bullet')
        else:
            doc.add_paragraph('Нет данных.')

    return doc

def _production_xlsx(p, sections):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Информация'
    ws.append(['Поле', 'Значение'])
    ws.append(['Название', p.name])
    ws.append(['Статус', p.status_display])
    ws.append(['Жанр', p.genre])
    ws.append(['Премьера', p.premiere_display])
    ws.append(['Актов', p.acts_count or ''])
    ws.append(['Авторы музыки', p.music_authors_display])
    ws.append(['Авторы либретто', p.libretto_authors_display])
    ws.append(['Литературная основа', p.literary_basis or ''])
    ws.append(['Автор основы', p.literary_basis_author or ''])
    ws.append(['Сцена', p.stage or ''])
    ws.append(['Возрастной ценз', p.age_rating or ''])
    ws.append(['Продолжительность', p.duration_display if (p.duration_hours or p.duration_minutes) else ''])
    ws.append(['Год снятия', p.removal_year or ''])
    for col, width in (('A', 22), ('B', 50)):
        ws.column_dimensions[col].width = width

    sheets = []

    if 'cast' in sections:
        ws2 = wb.create_sheet('Состав')
        ws2.append(['Артист', 'Роль', 'Годы участия'])
        for ce in p.cast_entries:
            ws2.append([ce.artist.full_name, ce.role_name or '', ce.years_display or ''])
        sheets.append(ws2)

    if 'staging' in sections:
        ws3 = wb.create_sheet('Постановочная группа')
        ws3.append(['ФИО', 'Должность', 'Годы жизни'])
        for pd in p.staging_group:
            ws3.append([pd.director.full_name, pd.position_display, pd.director.life_years or ''])
        sheets.append(ws3)

    if 'documents' in sections:
        ws4 = wb.create_sheet('Документы')
        ws4.append(['Тип', 'Название', 'Файл'])
        for d in p.documents:
            ws4.append([d.doc_type_display, d.title or '', d.file_name])
        sheets.append(ws4)

    if 'materials' in sections:
        ws5 = wb.create_sheet('Материалы')
        ws5.append(['Тип', 'Название', 'Файл/ссылка'])
        for m in p.materials:
            ws5.append([m.type_display, m.title or '', m.file_name or m.url or ''])
        sheets.append(ws5)

    for sheet in sheets:
        for i, _ in enumerate(sheet[1], 1):
            sheet.column_dimensions[get_column_letter(i)].width = 28

    return wb

@reports_bp.route('/production/<int:pid>/export')
@login_required
def export_production(pid):
    p = db.get_or_404(Production, pid)
    fmt = request.args.get('format', 'docx')
    sections_param = request.args.get('sections', '').strip()
    sections = {s for s in sections_param.split(',') if s in REPORT_SECTIONS} if sections_param else set(REPORT_SECTIONS)
    filename = safe_filename(p.name)
    if fmt == 'xlsx':
        wb = _production_xlsx(p, sections)
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=f'{filename}.xlsx', mimetype=XLSX_MIME)
    doc = _production_docx(p, sections)
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f'{filename}.docx', mimetype=DOCX_MIME)

def _tour_artist_rows(t):
    """One row per (artist, production, role) the artist is credited with in a production
    that's part of this tour; falls back to a single placeholder row for artists linked to
    the tour with no matching cast entry in any of its productions."""
    prod_ids = {link.production_id for link in t.production_links}
    rows = []
    for link in t.artist_links:
        artist = link.artist
        matches = [ce for ce in artist.cast_entries if ce.production_id in prod_ids]
        if matches:
            for ce in matches:
                rows.append((artist, ce.production.name, ce.role_name or '—'))
        else:
            rows.append((artist, '—', '—'))
    return rows

def _tours_report_docx(title, headers, rows, tours):
    doc = DocxDocument()
    doc.add_heading(title, level=1)
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = 'Light Grid Accent 1'
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = str(h)
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = str(val) if val not in (None, '') else '—'

    for t in tours:
        doc.add_heading(f'{t.city}, {t.year}', level=2)

        doc.add_heading('Постановки', level=3)
        if t.production_links:
            pt = doc.add_table(rows=1, cols=4)
            pt.style = 'Light Grid Accent 1'
            hdr = pt.rows[0].cells
            hdr[0].text, hdr[1].text, hdr[2].text, hdr[3].text = 'Название', 'Жанр', 'Сцена', 'Продолжительность'
            for link in t.production_links:
                p = link.production
                cells = pt.add_row().cells
                cells[0].text = p.name
                cells[1].text = p.genre
                cells[2].text = p.stage or '—'
                cells[3].text = p.duration_display if (p.duration_hours or p.duration_minutes) else '—'
        else:
            doc.add_paragraph('Нет данных.')

        doc.add_heading('Артисты', level=3)
        artist_rows = _tour_artist_rows(t)
        if artist_rows:
            at = doc.add_table(rows=1, cols=5)
            at.style = 'Light Grid Accent 1'
            hdr = at.rows[0].cells
            hdr[0].text, hdr[1].text, hdr[2].text, hdr[3].text, hdr[4].text = 'ФИО', 'Должность', 'Звание', 'Постановка', 'Роль'
            for artist, prod_name, role in artist_rows:
                cells = at.add_row().cells
                cells[0].text = artist.full_name
                cells[1].text = artist.position or '—'
                cells[2].text = artist.title or '—'
                cells[3].text = prod_name
                cells[4].text = role
        else:
            doc.add_paragraph('Нет данных.')

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f'{safe_filename(title)}.docx', mimetype=DOCX_MIME)

def _tours_report_xlsx(headers, rows, tours, title):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Гастроли'
    ws.append(headers)
    for row in rows:
        ws.append(row)
    for i, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(14, len(str(h)) + 4)

    ws2 = wb.create_sheet('Постановки по гастролям')
    ws2.append(['Гастроль', 'Название', 'Жанр', 'Сцена', 'Продолжительность'])
    for t in tours:
        label = f'{t.city}, {t.year}'
        for link in t.production_links:
            p = link.production
            ws2.append([label, p.name, p.genre, p.stage or '',
                       p.duration_display if (p.duration_hours or p.duration_minutes) else ''])
    for i in range(1, 6):
        ws2.column_dimensions[get_column_letter(i)].width = 26

    ws3 = wb.create_sheet('Артисты по гастролям')
    ws3.append(['Гастроль', 'ФИО', 'Должность', 'Звание', 'Постановка', 'Роль'])
    for t in tours:
        label = f'{t.city}, {t.year}'
        for artist, prod_name, role in _tour_artist_rows(t):
            ws3.append([label, artist.full_name, artist.position or '', artist.title or '', prod_name, role])
    for i in range(1, 7):
        ws3.column_dimensions[get_column_letter(i)].width = 26

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f'{safe_filename(title)}.xlsx', mimetype=XLSX_MIME)

# ---------- Гастроли: фильтруемый список ----------
@reports_bp.route('/tours/export')
@login_required
def export_tours():
    fmt = request.args.get('format', 'xlsx')
    city = request.args.get('city', '').strip()
    year_from = request.args.get('year_from', '').strip()
    year_to = request.args.get('year_to', '').strip()
    tour_type = request.args.get('tour_type', '').strip()
    artist_q = request.args.get('artist', '').strip()
    production_q = request.args.get('production', '').strip()

    tours = Tour.query.order_by(Tour.year.desc(), Tour.city).all()

    def matches(t):
        if city and t.city != city:
            return False
        if year_from and t.year < int(year_from):
            return False
        if year_to and t.year > int(year_to):
            return False
        if tour_type and t.tour_type_name != tour_type:
            return False
        # Matched in Python, not via SQL LIKE/ilike: SQLite's lower() only folds ASCII
        # a-z and leaves Cyrillic untouched (see utils.get_or_create_libretto_role).
        if artist_q:
            target = artist_q.lower()
            if not any(target in link.artist.full_name.lower() for link in t.artist_links):
                return False
        if production_q:
            target = production_q.lower()
            if not any(target in link.production.name.lower() for link in t.production_links):
                return False
        return True

    filtered = [t for t in tours if matches(t)]

    headers = ['№', 'Город', 'Год', 'Номер поездки', 'Тип', 'Постановки', 'Количество артистов']
    rows = [[
        i + 1, t.city, t.year, t.tour_number or '—', t.tour_type_name,
        ', '.join(link.production.name for link in t.production_links) or '—',
        len(t.artist_links),
    ] for i, t in enumerate(filtered)]

    title = 'Отчёт по гастролям'
    if fmt == 'docx':
        return _tours_report_docx(title, headers, rows, filtered)
    return _tours_report_xlsx(headers, rows, filtered, title)

def _festivals_report_docx(title, headers, rows, editions):
    doc = DocxDocument()
    doc.add_heading(title, level=1)
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = 'Light Grid Accent 1'
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = str(h)
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = str(val) if val not in (None, '') else '—'

    for e in editions:
        doc.add_heading(f'{e.festival.name}, {e.year}', level=2)

        doc.add_heading('Описание', level=3)
        if e.description:
            p = doc.add_paragraph()
            lines = e.description.split('\n')
            for i, line in enumerate(lines):
                if i > 0:
                    p.add_run().add_break()
                p.add_run(line)
        else:
            doc.add_paragraph('Описание не заполнено.')

        doc.add_heading('Программа по дням', level=3)
        if e.program_entries:
            for entry in e.program_entries:
                header_parts = [entry.date_display or 'Дата не указана']
                if entry.time:
                    header_parts.append(entry.time)
                if entry.location:
                    header_parts.append(entry.location)
                header_p = doc.add_paragraph(style='List Bullet')
                header_p.add_run(' • '.join(header_parts)).bold = True
                if entry.description:
                    desc_p = doc.add_paragraph()
                    desc_p.paragraph_format.left_indent = Pt(18)
                    lines = entry.description.split('\n')
                    for i, line in enumerate(lines):
                        if i > 0:
                            desc_p.add_run().add_break()
                        desc_p.add_run(line)
        else:
            doc.add_paragraph('Нет данных.')

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f'{safe_filename(title)}.docx', mimetype=DOCX_MIME)

def _festivals_report_xlsx(headers, rows, editions, title):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Фестивали'
    ws.append(headers)
    for row in rows:
        ws.append(row)
    for i, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(14, len(str(h)) + 4)

    wrap = Alignment(wrap_text=True, vertical='top')

    ws2 = wb.create_sheet('Описания выпусков')
    ws2.append(['Выпуск', 'Описание'])
    for e in editions:
        ws2.append([f'{e.festival.name}, {e.year}', e.description or ''])
        ws2.cell(row=ws2.max_row, column=2).alignment = wrap
    ws2.column_dimensions['A'].width = 28
    ws2.column_dimensions['B'].width = 70

    ws3 = wb.create_sheet('Программа по дням')
    ws3.append(['Выпуск', 'Программа'])
    for e in editions:
        label = f'{e.festival.name}, {e.year}'
        for entry in e.program_entries:
            header_parts = [entry.date_display or 'Дата не указана']
            if entry.time:
                header_parts.append(entry.time)
            if entry.location:
                header_parts.append(entry.location)
            cell_text = ' • '.join(header_parts)
            if entry.description:
                cell_text += '\n' + entry.description
            ws3.append([label, cell_text])
            ws3.cell(row=ws3.max_row, column=2).alignment = wrap
    ws3.column_dimensions['A'].width = 26
    ws3.column_dimensions['B'].width = 80

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f'{safe_filename(title)}.xlsx', mimetype=XLSX_MIME)

# ---------- Фестивали: фильтруемый список выпусков ----------
@reports_bp.route('/festivals/export')
@login_required
def export_festivals():
    fmt = request.args.get('format', 'xlsx')
    name_q = request.args.get('name', '').strip()
    year_from = request.args.get('year_from', '').strip()
    year_to = request.args.get('year_to', '').strip()
    status = request.args.get('status', '').strip()

    editions = FestivalEdition.query.order_by(FestivalEdition.year.desc()).all()

    def matches(e):
        if name_q and name_q.lower() not in e.festival.name.lower():
            return False
        if year_from and e.year < int(year_from):
            return False
        if year_to and e.year > int(year_to):
            return False
        if status and e.status_name != status:
            return False
        return True

    filtered = [e for e in editions if matches(e)]

    def program_days_count(e):
        days = {(p.day, p.month) for p in e.program_entries if p.day and p.month}
        return len(days) if days else len(e.program_entries)

    headers = ['№', 'Название фестиваля', 'Год', 'Статус', 'Количество дней программы']
    rows = [[
        i + 1, e.festival.name, e.year, e.status_name, program_days_count(e),
    ] for i, e in enumerate(filtered)]

    title = 'Отчёт по фестивалям'
    if fmt == 'docx':
        return _festivals_report_docx(title, headers, rows, filtered)
    return _festivals_report_xlsx(headers, rows, filtered, title)

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
        return docx_table_response(title, headers, rows, title)
    return xlsx_response(headers, rows, title)
