"""Regras de acesso da equipe, aplicadas no servidor em cada rota."""
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

PRIZE_GROUP = "Premiação"
MANAGER_PERMISSION = "passport.manage_event"


def is_team(user):
    return user.is_authenticated and user.is_active and user.is_staff


def is_manager(user):
    # has_perm devolve True para superusuários ativos; contas comuns precisam da permissão explícita.
    return is_team(user) and user.has_perm(MANAGER_PERMISSION)


def prize_allowed(user):
    # Regra anterior preservada: superusuário ou grupo Premiação. A permissão de gestor sozinha não libera entregas.
    return is_team(user) and (user.is_superuser or user.groups.filter(name=PRIZE_GROUP).exists())


def assigned_stands(user, stands):
    return stands if is_manager(user) else stands.filter(staff=user)


def can_search_passports(user):
    """Consulta de passaportes: gestão, premiação ou quem atende algum estande ativo."""
    if not is_team(user):
        return False
    if is_manager(user) or prize_allowed(user):
        return True
    return user.assigned_stands.filter(active=True, event__active=True).exists()


def forbidden(request, message):
    """403 com explicação e caminho de volta, em vez de uma linha de texto sem navegação."""
    return render(request, "passport/forbidden.html", {
        "message": message, "is_team": is_team(request.user),
    }, status=403)


def _guard(check, message):
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not is_team(request.user):
                return forbidden(request, "Acesso restrito à equipe autorizada.")
            if check and not check(request.user):
                return forbidden(request, message)
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


staff_only = _guard(None, "")
manager_only = _guard(is_manager, "Acesso restrito à gestão do evento.")
prize_only = _guard(prize_allowed, "Acesso restrito à equipe de premiação.")
search_only = _guard(can_search_passports, "Sua conta não tem permissão para consultar passaportes.")
