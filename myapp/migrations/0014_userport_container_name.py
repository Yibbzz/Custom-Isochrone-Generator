# Generated by Django 5.0 on 2024-01-05 20:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0013_rename_port_userport_port1_userport_port2'),
    ]

    operations = [
        migrations.AddField(
            model_name='userport',
            name='container_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
