from celery import shared_task


@shared_task(bind=True, max_retries=3)
def send_verification_email_task(self, user_id: int):
    """
    TODO: implement -- send activation email asynchronously.
    Replace direct send_email_async call in services.py with this task.
    """
    pass


@shared_task(bind=True, max_retries=3)
def send_role_request_email_task(self, user_id: int, role_name: str):
    """TODO: notify KTTO/RDCO by email when a new role request comes in."""
    pass
