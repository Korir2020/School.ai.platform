from django.db import models


class School(models.Model):
    name = models.CharField(max_length=200)
        code = models.CharField(max_length=50, unique=True)
            location = models.CharField(max_length=200, blank=True)
                email = models.EmailField(blank=True)
                    phone = models.CharField(max_length=30, blank=True)
                        created_at = models.DateTimeField(auto_now_add=True)

                            def __str__(self):
                                    return self.name