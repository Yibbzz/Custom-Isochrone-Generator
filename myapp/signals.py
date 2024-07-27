from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from myapp.models import UserSessionStatus

@receiver(user_logged_in)
def handle_user_login(sender, request, user, **kwargs):
    UserSessionStatus.objects.update_or_create(
        user=user,
        defaults={'is_logged_in': True}
    )

@receiver(user_logged_out)
def handle_user_logout(sender, request, user, **kwargs):
    UserSessionStatus.objects.filter(user=user).update(
        is_logged_in=False
    )
