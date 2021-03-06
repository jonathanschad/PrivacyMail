# Generated by Django 2.0.4 on 2019-03-14 15:12

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Identity',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('first_name', models.CharField(max_length=50)),
                ('surname', models.CharField(max_length=50)),
                ('mail', models.EmailField(max_length=254, unique=True)),
                ('gender', models.BooleanField()),
                ('approved', models.BooleanField(default=False)),
                ('lastapprovalremindersend', models.TimeField(default=None, null=True)),
                ('receives_third_party_spam', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='Service',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.URLField()),
                ('name', models.CharField(max_length=50)),
            ],
        ),
        migrations.CreateModel(
            name='ServiceThirdPartyEmbeds',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('leaks_address', models.BooleanField(default=False)),
                ('embed_type', models.CharField(
                    choices=[('LINK', 'link'), ('IMAGE', 'image'), ('CSS', 'css'), ('UNDETERMINED', 'undetermined')],
                    default='UNDETERMINED', max_length=20)),
            ],
        ),
    ]
