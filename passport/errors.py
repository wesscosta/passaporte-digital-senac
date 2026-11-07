"""Respostas seguras para erros de formulário."""
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache

# Apenas páginas que aceitam GET podem ser reabertas depois de um POST recusado.
_RETRY_VIEWS = {
    "register", "recover", "manual_stamp", "scan_stamp", "staff_login",
    "manager_home", "prize_lookup", "prize_review",
}


@never_cache
def csrf_failure(request, reason=""):
    """Mantém o 403 sem expor o motivo técnico nem reenviar dados automaticamente."""
    match = request.resolver_match
    destination = reverse("home")
    if match:
        if match.namespace == "admin":
            destination = reverse("admin:index")
        elif match.url_name == "issue_redemption":
            destination = reverse("passport")
        elif match.url_name == "staff_logout":
            destination = reverse("staff_home")
        elif match.url_name in _RETRY_VIEWS:
            destination = reverse(match.view_name, args=match.args, kwargs=match.kwargs)
    return render(request, "passport/csrf_failure.html", {"retry_url": destination}, status=403)
