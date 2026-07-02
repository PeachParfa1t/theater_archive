"""Run on every startup. Safely migrates schema (additive only, never drops data) then seeds defaults."""
import os
from app import app, db, Role, User, Production, Artist, Director, DirectorPosition, ROLE_ADMIN
from migrations import (
    add_literary_basis_columns_to_productions,
    add_year_range_columns_to_cast_entries,
    relax_director_position_notnull,
    create_new_tables,
    migrate_director_positions_data,
)

def init():
    with app.app_context():
        add_literary_basis_columns_to_productions()
        add_year_range_columns_to_cast_entries()
        relax_director_position_notnull()
        create_new_tables()
        migrate_director_positions_data()

        roles_data = [
            (ROLE_ADMIN,    'Администратор'),
            ('editor',      'Редактор архива'),
            ('zavlit',      'Завлит'),
            ('music_lib',   'Нотный библиотекарь'),
            ('observer',    'Наблюдатель'),
        ]
        for name, display in roles_data:
            if not Role.query.filter_by(name=name).first():
                db.session.add(Role(name=name, display_name=display))
        db.session.commit()

        if not User.query.filter_by(login='admin').first():
            admin_password = os.environ.get('ADMIN_PASSWORD')
            if not admin_password:
                admin_password = 'admin123'
                print("WARNING: ADMIN_PASSWORD not set in environment/.env — using default password "
                      "'admin123' for the admin account. Set ADMIN_PASSWORD in .env for a secure password.")
            admin_role = Role.query.filter_by(name=ROLE_ADMIN).first()
            admin = User(full_name='Администратор', login='admin', role_id=admin_role.id)
            admin.set_password(admin_password)
            db.session.add(admin)
            db.session.commit()
            print("Admin created: login=admin")

        # Demo data — only inserted on a completely fresh database
        if Production.query.count() == 0:
            prods = [
                Production(name='Евгений Онегин', status='active', premiere_year=1998,
                           premiere_day=15, premiere_month=9,
                           genre='Опера', acts_count=3,
                           literary_basis='Роман в стихах «Евгений Онегин»',
                           literary_basis_author='А.С. Пушкин'),
                Production(name='Лебединое озеро', status='active', premiere_year=2005,
                           premiere_day=20, premiere_month=3,
                           genre='Балет', acts_count=4),
                Production(name='Свадьба Фигаро', status='removed', premiere_year=1987,
                           genre='Опера-буфф', acts_count=4,
                           literary_basis='Комедия «Безумный день, или Женитьба Фигаро»',
                           literary_basis_author='П. Бомарше'),
                Production(name='Весёлая вдова', status='active', premiere_year=2019,
                           premiere_day=1, premiere_month=11,
                           genre='Оперетта', acts_count=3),
            ]
            for p in prods:
                db.session.add(p)
            db.session.flush()
            from app import ProductionAuthor
            db.session.add(ProductionAuthor(production_id=prods[0].id, full_name='П.И. Чайковский', role='music'))
            db.session.add(ProductionAuthor(production_id=prods[0].id, full_name='М.И. Чайковский', role='libretto'))
            db.session.add(ProductionAuthor(production_id=prods[0].id, full_name='К.С. Шиловский', role='libretto'))
            db.session.add(ProductionAuthor(production_id=prods[1].id, full_name='П.И. Чайковский', role='music'))
            db.session.add(ProductionAuthor(production_id=prods[2].id, full_name='В.А. Моцарт', role='music'))
            db.session.add(ProductionAuthor(production_id=prods[2].id, full_name='Л. да Понте', role='libretto'))
            db.session.add(ProductionAuthor(production_id=prods[3].id, full_name='Ф. Легар', role='music'))

        if Artist.query.count() == 0:
            artists = [
                Artist(full_name='Петров Александр Иванович',
                       title='Заслуженный артист России',
                       birth_year=1965, work_start_year=1990,
                       description='Ведущий тенор театра'),
                Artist(full_name='Иванова Мария Сергеевна',
                       title='Народная артистка России',
                       birth_year=1958, death_year=2020,
                       work_start_year=1980, work_end_year=2015,
                       description='Прима-балерина, лауреат государственных премий'),
                Artist(full_name='Сидоров Николай Петрович',
                       birth_year=1980, work_start_year=2005,
                       description='Баритон'),
            ]
            for a in artists:
                db.session.add(a)

        if Director.query.count() == 0:
            seed_directors = [
                ('Загурский Николай Михайлович', ['director'], 1940, 2010),
                ('Орлов Виктор Семёнович', ['conductor'], 1955, None),
                ('Белова Ольга Николаевна', ['ballet_master', 'choreographer'], 1968, None),
            ]
            for name, position_codes, birth_year, death_year in seed_directors:
                d = Director(full_name=name, birth_year=birth_year, death_year=death_year)
                db.session.add(d)
                db.session.flush()
                for code in position_codes:
                    db.session.add(DirectorPosition(director_id=d.id, position=code))

        db.session.commit()
        print("Database ready (existing data preserved).")

if __name__ == '__main__':
    init()
