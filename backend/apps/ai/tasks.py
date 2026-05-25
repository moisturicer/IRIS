from celery import shared_task

@shared_task
def metadata_extraction_task(document_id):
    pass

@shared_task
def embedding_generation_task(document_id):
    pass
