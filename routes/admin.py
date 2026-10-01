from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db, User, Role, AuditLog, ROLE_ADMIN
from audit import commit_with_audit

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

@admin_bp.route('/audit-log')
@admin_required
def audit_log():
    page = request.args.get('page', 1, type=int)
    action = request.args.get('action', '').strip()
    object_type = request.args.get('object_type', '').strip()
    user_id = request.args.get('user_id', type=int)

    query = AuditLog.query
    if action:
        query = query.filter_by(action=action)
    if object_type:
        query = query.filter_by(object_type=object_type)
    if user_id:
        query = query.filter_by(user_id=user_id)

    pagination = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    users_for_filter = User.query.order_by(User.full_name).all()
    object_types = [row[0] for row in db.session.query(AuditLog.object_type).distinct().order_by(AuditLog.object_type)]
    return render_template(
        'admin/audit_log.html', pagination=pagination,
        actions=AuditLog.ACTION_LABELS, object_types=object_types,
        users_for_filter=users_for_filter,
        selected_action=action, selected_object_type=object_type, selected_user_id=user_id,
    )


@admin_bp.route('/roles/permissions', methods=['GET', 'POST'])
@admin_required
def role_permissions():
    roles = Role.query.order_by(Role.id).all()
    permissions = Role.CONFIGURABLE_PERMISSIONS
    if request.method == 'POST':
        details = []
        for role in roles:
            enabled = []
            for field, label, _description in permissions:
                # Administrative access cannot be removed, including by a forged POST.
                value = True if role.name == ROLE_ADMIN else (
                    f'role_{role.id}_{field}' in request.form
                )
                setattr(role, field, value)
                if value:
                    enabled.append(label)
            details.append(f'{role.display_name}: {", ".join(enabled) or "нет"}')
        commit_with_audit(
            'update', 'Права ролей', 'Настройки доступа ролей',
            details='; '.join(details),
        )
        flash('Права ролей сохранены.', 'success')
        return redirect(url_for('admin.role_permissions'))
    return render_template(
        'admin/role_permissions.html', roles=roles, permissions=permissions,
    )

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
        db.session.flush()
        commit_with_audit('create', 'Пользователь', f'{u.full_name} ({u.login})', u.id)
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
        commit_with_audit('update', 'Пользователь', f'{u.full_name} ({u.login})', u.id,
                          'Карточка пользователя обновлена')
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
        state = 'активирован' if u.is_active else 'деактивирован'
        commit_with_audit('update', 'Пользователь', f'{u.full_name} ({u.login})', u.id,
                          f'Пользователь {state}')
        flash('Статус изменён.', 'success')
    return redirect(url_for('admin.users'))
