from django.core.management.base import BaseCommand
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.contrib.auth import get_user_model
from myapp.models import UserSessionStatus

User = get_user_model()

class Command(BaseCommand):
    """
    Command to check and update expired sessions, and perform cleanup actions.

    This command identifies expired sessions, updates the session status of users,
    and deletes the expired sessions from the database.

    Attributes:
        help (str): Description of the command.
    """

    help = 'Check and update expired sessions, and perform cleanup actions.'

    def handle(self, *args: tuple, **kwargs: dict) -> None:
        """
        Handle the command execution.

        Args:
            *args (tuple): Variable length argument list.
            **kwargs (dict): Arbitrary keyword arguments.
        """
        now = timezone.now()
        expired_sessions = Session.objects.filter(expire_date__lt=now)

        for session in expired_sessions:
            user_id = session.get_decoded().get('_auth_user_id')
            if user_id:
                try:
                    user = User.objects.get(pk=user_id)
                    UserSessionStatus.objects.update_or_create(
                        user=user,
                        defaults={
                            'is_logged_in': False,
                            'session_expired': True
                        }
                    )
                    print(f"Updated session status for user {user.username}")
                except User.DoesNotExist:
                    print(f"User ID {user_id} not found in User model.")

            session.delete()  # Delete the expired session

        print("Expired sessions have been processed and cleaned up.")