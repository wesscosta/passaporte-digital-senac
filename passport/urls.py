from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("cadastro/", views.register, name="register"),
    path("recuperar/", views.recover, name="recover"),
    path("meu-passaporte/", views.passport_page, name="passport"),
    path("carimbar/", views.manual_stamp, name="manual_stamp"),
    path("visitar/<int:stand_id>/<str:code>/", views.scan_stamp, name="scan_stamp"),
    path("retirada/gerar/", views.issue_redemption, name="issue_redemption"),
    path("equipe/entrar/", auth_views.LoginView.as_view(template_name="passport/staff_login.html"), name="staff_login"),
    path("equipe/sair/", auth_views.LogoutView.as_view(), name="staff_logout"),
    path("equipe/", views.staff_home, name="staff_home"),
    path("equipe/estande/<int:stand_id>/", views.station, name="station"),
    path("equipe/premios/", views.prize_lookup, name="prize_lookup"),
    path("equipe/premios/<str:code>/", views.prize_review, name="prize_review"),
]
