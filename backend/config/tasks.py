from celery import shared_task


@shared_task(name="infrastructure.check", ignore_result=True)
def infrastructure_check():
    """Provide a side-effect-free task for worker wiring diagnostics."""

    return {"status": "ok"}
