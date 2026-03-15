# Backend

## Generic S3 Storage

The backend can store uploaded media on any S3-compatible provider via django-storages.

Set `S3_STORAGE_ENABLED=True` and provide at least:

- `AWS_STORAGE_BUCKET_NAME`
- `AWS_S3_ENDPOINT_URL`
- `AWS_S3_REGION_NAME`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

Optional settings:

- `AWS_S3_CUSTOM_DOMAIN`
- `AWS_DEFAULT_ACL`
- `AWS_QUERYSTRING_AUTH`
- `AWS_QUERYSTRING_EXPIRE`
- `AWS_S3_FILE_OVERWRITE`
- `AWS_S3_ADDRESSING_STYLE`
- `AWS_LOCATION`
- `MEDIA_URL`

When `S3_STORAGE_ENABLED=False`, media continues to use the local filesystem.
