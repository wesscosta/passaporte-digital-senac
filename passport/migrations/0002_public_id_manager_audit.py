import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def fill_public_ids(apps, schema_editor):
    # Aditivo: só preenche o novo campo; nenhum outro dado do passaporte é alterado.
    from passport.ids import new_public_id
    Passport = apps.get_model("passport", "Passport")
    used = set(Passport.objects.exclude(public_id=None).values_list("public_id", flat=True))
    for passport in Passport.objects.filter(public_id=None).only("pk"):
        candidate = new_public_id()
        while candidate in used:
            candidate = new_public_id()
        used.add(candidate)
        Passport.objects.filter(pk=passport.pk).update(public_id=candidate)


class Migration(migrations.Migration):

    dependencies = [
        ("passport", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="event",
            options={"permissions": [("manage_event", "Pode gerenciar o evento ativo e o intervalo entre carimbos")]},
        ),
        migrations.AddField(
            model_name="passport", name="public_id",
            field=models.CharField(editable=False, max_length=8, null=True, verbose_name="identificador"),
        ),
        migrations.RunPython(fill_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="passport", name="public_id",
            field=models.CharField(editable=False, max_length=8, unique=True, verbose_name="identificador"),
        ),
        migrations.CreateModel(
            name="AuditEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=40)),
                ("target", models.CharField(blank=True, max_length=40)),
                ("detail", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "registro de auditoria", "verbose_name_plural": "registros de auditoria", "ordering": ["-created_at"]},
        ),
    ]
