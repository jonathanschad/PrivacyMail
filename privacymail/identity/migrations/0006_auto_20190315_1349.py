# Generated by Django 2.0.4 on 2019-03-15 13:49

from django.db import migrations, models
import django_countries.fields


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0005_servicethirdpartyembeds_sets_cookie'),
    ]

    operations = [
        migrations.AddField(
            model_name='service',
            name='country_of_origin',
            field=django_countries.fields.CountryField(blank=True, max_length=2),
        ),
        migrations.AddField(
            model_name='service',
            name='sector',
            field=models.CharField(choices=[('adult', 'Adult'), ('art', 'Art'), ('games', 'Games'), ('entertainment', 'Entertainment'), ('health', 'Health'), ('finance', 'Financial'), ('news', 'News'), ('shopping', 'Shopping'), ('b2b', 'Business-to-Business'), ('reference', 'Reference'), ('science', 'Science'), ('politics', 'Political Party / Politician'), ('activist', 'Activist'), ('sports', 'Sports'), ('unknown', 'Unknown')], default='unknown', max_length=30),
        ),
    ]
