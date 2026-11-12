from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('schools', '0071_offsite_backup_and_offline_marks'),
    ]
    operations = [
        migrations.CreateModel(
            name='FinalSubjectMark',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('marks', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('mark_status', models.CharField(choices=[('scored', 'Scored'), ('absent', 'Absent'), ('exempted', 'Exempted'), ('not_assessed', 'Not assessed'), ('pending', 'Pending')], default='scored', max_length=16)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('submitted', 'Submitted'), ('approved', 'Approved'), ('locked', 'Locked')], default='draft', max_length=10)),
                ('updated_at', models.DateTimeField(auto_now=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('entered_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='final_subject_marks', to='schools.exam')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='final_subject_marks', to='schools.student')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='final_subject_marks', to='schools.subject')),
            ],
            options={'constraints': [
                models.UniqueConstraint(fields=('exam', 'student', 'subject'), name='unique_final_subject_mark_per_exam_student_subject'),
                models.CheckConstraint(condition=models.Q(('mark_status', 'scored'), ('marks__isnull', False), ('marks__gte', 0), ('marks__lte', 100), _connector='AND') | models.Q(('mark_status__in', ['absent', 'exempted', 'not_assessed', 'pending']), ('marks__isnull', True), _connector='AND'), name='final_subject_mark_status_valid'),
            ]},
        ),
    ]
