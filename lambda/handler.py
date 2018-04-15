import json
import mimetypes
import os
import os.path
import tempfile
import time

import boto3

import dumb_pypi.main


def _load_config():
    with open(os.path.join(os.path.dirname(__file__), 'config.json')) as f:
        return json.load(f)


def _list_bucket(bucket):
    s3 = boto3.client('s3')
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket):
        yield from (
            json.dumps(
                {
                    'filename': package['Key'],
                    'upload_timestamp': time.mktime(package['LastModified'].timetuple()),
                },
                sort_keys=True,
            )
            for package in page.get('Contents', ())
        )


def _sync_bucket(localdir, bucket_name):
    # TODO: should also delete removed files
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucket_name)
    for dirpath, _, filenames in os.walk(localdir):
        for filename in filenames:
            path_on_disk = os.path.join(dirpath, filename)
            key = os.path.relpath(path_on_disk, localdir)
            print(f'Uploading {path_on_disk} => s3://{bucket_name}/{key}')
            with open(path_on_disk, 'rb') as f:
                bucket.put_object(
                    Key=key,
                    Body=f,
                    ContentType=mimetypes.guess_type(filename)[0]
                )


def main(event, context):
    config = _load_config()

    with tempfile.TemporaryDirectory() as td:
        with tempfile.NamedTemporaryFile(mode='w') as tf:
            for line in _list_bucket(config['source-bucket']):
                tf.write(line + '\n')
            tf.flush()

            dumb_pypi.main.main((
                '--package-list-json', tf.name,
                '--output-dir', td,
                *config['args'],
            ))

        _sync_bucket(td, config['output-bucket'])


# Strictly for testing; we don't look at the event or context anyway.
if __name__ == '__main__':
    exit(main(None, None))
