from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db, User, Role, ROLE_ADMIN

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    from functools import wraps
    @wraps(f)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.can_manage_users():
            flash('Доступ только для администратора.', 'danger')
            return redirect(url_for('productions.list_productions'))
        return f(*args, **kwargs)
    return wrapped

@admin_bp.route('/users')
@admin_required
def users():
    all_users = User.query.order_by(User.full_name).all()
    return render_template('admin/users.html', users=all_users)

@admin_bp.route('/users/create', methods=['GET', 'POST'])
@admin_required
def create_user():
    roles = Role.query.all()
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        login_val = request.form.get('login', '').strip()
        password  = request.form.get('password', '')
        role_id   = request.form.get('role_id')
        if not full_name or not login_val or not password or not role_id:
            flash('Заполните все обязательные поля.', 'danger')
            return render_template('admin/user_form.html', u=None, roles=roles)
        if User.query.filter_by(login=login_val).first():
            flash('Логин уже занят.', 'danger')
            return render_template('admin/user_form.html', u=None, roles=roles)
        u = User(full_name=full_name, login=login_val, role_id=int(role_id))
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        flash('Пользователь создан.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', u=None, roles=roles)

@admin_bp.route('/users/<int:uid>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(uid):
    u     = db.get_or_404(User, uid)
    roles = Role.query.all()
    if request.method == 'POST':
        u.full_name = request.form.get('full_name', '').strip() or u.full_name
        u.role_id   = int(request.form.get('role_id', u.role_id))
        u.is_active = 'is_active' in request.form
        new_pass    = request.form.get('password', '').strip()
        if new_pass:
            u.set_password(new_pass)
        db.session.commit()
        flash('Пользователь обновлён.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', u=u, roles=roles)

@admin_bp.route('/users/<int:uid>/toggle', methods=['POST'])
@admin_required
def toggle_user(uid):
    u = db.get_or_404(User, uid)
    if u.id == current_user.id:
        flash('Нельзя деактивировать себя.', 'warning')
    else:
        u.is_active = not u.is_active
        db.session.commit()
        flash('Статус изменён.', 'success')
    return redirect(url_for('admin.users'))
