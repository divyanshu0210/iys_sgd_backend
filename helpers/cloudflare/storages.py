from storages.backends.s3 import S3Storage

# class StaticFileStorage(S3Storage):
#     """
#     For staticfiles
#     """

#     location = "static"


class MediaFileStorage(S3Storage):
    """
    For general uploads
    """

    location = "media"

