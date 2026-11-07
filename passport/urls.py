from django.contrib.auth import views as auth_views
from django.urls import path
from . import views
from .auth import StaffAuthenticationForm

urlpatterns = [
    path("", views.home, name="home"),
    path("cadastro/", views.register, name="register"),
    path("recuperar/", views.recover, name="recover"),
    path("meu-passaporte/", views.passport_page, name="passport"),
    path("carimbar/", views.manual_stamp, name="manual_stamp"),
    path("visitar/confirmar/", views.scan_voucher_confirm, name="scan_voucher_confirm"),
    path("visitar/<int:stand_id>/<str:code>/", views.scan_stamp, name="scan_stamp"),
    path("retirada/gerar/", views.issue_redemption, name="issue_redemption"),
    path("equipe/entrar/", auth_views.LoginView.as_view(
        template_name="passport/staff_login.html", authentication_form=StaffAuthenticationForm,
    ), name="staff_login"),
    path("equipe/sair/", auth_views.LogoutView.as_view(), name="staff_logout"),
    path("equipe/", views.staff_home, name="staff_home"),
    path("equipe/estande/<int:stand_id>/", views.station, name="station"),
    path("equipe/passaportes/", views.passport_search, name="passport_search"),
    path("equipe/passaportes/<str:public_id>/", views.passport_detail, name="passport_detail"),
    path("equipe/gestao/", views.manager_home, name="manager_home"),
    path("equipe/gestao/relatorio/", views.manager_report, name="manager_report"),
    path("equipe/pin/", views.pin_reset_search, name="pin_reset_search"),
    path("equipe/pin/<str:public_id>/", views.pin_reset_confirm, name="pin_reset_confirm"),
    path("equipe/premios/", views.prize_lookup, name="prize_lookup"),
    path("equipe/premios/<str:code>/", views.prize_review, name="prize_review"),
]
