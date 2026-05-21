from rest_framework.exceptions import APIException
from rest_framework import status


class RecordNotFound(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Record not found."


class NotRecordOwner(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "You do not own this record."


class RecordAlreadyApproved(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This record has already been approved and cannot be modified."


class InvalidPipelineTransition(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This pipeline status transition is not allowed."


class PinInvalid(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The PIN is invalid or has already been used."
