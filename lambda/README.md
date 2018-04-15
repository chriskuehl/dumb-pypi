# Integrating dumb-pypi with AWS Lambda

[AWS Lambda][lambda] is a way to run code ("functions") in response to triggers
(like a change in an S3 bucket) without running any servers yourself.

dumb-pypi works very well with Lambda; you only need to regenerate the index
when your list of packages changes (relatively rare), and you can serve the
generated index without involving dumb-pypi at all.

The steps below walk you through an example AWS Lambda setup where a change in
a "source" bucket (containing all your packages) automatically triggers
dumb-pypi to regenerate the index and store it in the "output" bucket.

Depending on if you need to support old pip versions, you may even be able to
serve your index directly from S3, avoiding running any servers entirely.


## Initial deployment

These instructions use the sample code in this directory as the base for the
Lambda handler. The specifics of your bucket will likely vary; it's expected
that you may need to adjust configuration options or the code itself to match
your deployment.

1. Create two S3 buckets, e.g. `dumb-pypi-source` and `dumb-pypi-output`.

   The source bucket is where you'll drop Python packages (tarballs, wheels,
   etc.) in a flat listing (all objects at the root of the bucket).

   The output bucket will contain the generated index (HTML files) which pip
   uses.

2. Create an IAM role which allows reading from the source bucket and
   reading/writing to the output bucket. Select "Lambda" as the AWS resource
   the role applies to during creation.

   Here's an example policy (adjust as needed):

   ```json
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Sid": "AllowReadToSourceBucket",
               "Effect": "Allow",
               "Action": [
                   "s3:List*",
                   "s3:Get*"
               ],
               "Resource": [
                   "arn:aws:s3:::dumb-pypi-source/*",
                   "arn:aws:s3:::dumb-pypi-source"
               ]
           },
           {
               "Sid": "AllowReadWriteToOutputBucket",
               "Effect": "Allow",
               "Action": [
                   "s3:List*",
                   "s3:Get*",
                   "s3:PutObject",
                   "s3:DeleteObject"
               ],
               "Resource": [
                   "arn:aws:s3:::dumb-pypi-output/*",
                   "arn:aws:s3:::dumb-pypi-output"
               ]
           }
       ]
   }
   ```

3. Adjust `config.json` in this directory as necessary (e.g. update
   source/output bucket and the arguments). You can easily change this stuff
   later.

4. Build the first deployment bundle to upload to Lambda. From this directory,
   just run `make bundle.zip`.

5. Create the function. For example, here's how you might do it with the AWS cli:

   ```bash
   aws lambda create-function \
       --region us-west-1 \
       --function-name dumb-pypi \
       --runtime python3.6 \
       --role arn:aws:iam::XXXXXXXXXXXX:role/dumb-pypi \
       --handler handler.main \
       --zip-file fileb://bundle.zip
   ```

   (Replace the role, region, etc. to match your setup.)

6. [Give your S3 source bucket permission][s3-allow-trigger] to trigger your new
   Lambda function. For example:

   ```bash
    aws lambda add-permission \
        --region us-west-1 \
        --function-name dumb-pypi \
        --statement-id AllowSourceBucketToTriggerDumbPyPI \
        --action lambda:InvokeFunction \
        --principal s3.amazonaws.com \
        --source-arn arn:aws:s3:::dumb-pypi-source \
        --source-account XXXXXXXXXXXX
   ```

7. Set up a trigger so that changes to the source bucket cause the `dumb-pypi`
   function to run and regenerate the index.

   The AWS cli is very awkward, the easiest way to do this is to make a file
   like `policy.json` with contents like:

   ```json
   {
       "LambdaFunctionConfigurations": [
           {
             "Id": "NotifyDumbPyPI",
             "LambdaFunctionArn": "arn:aws:lambda:us-west-1:XXXXXXXXXXXX:function:dumb-pypi",
             "Events": ["s3:ObjectCreated:*", "s3:ObjectRemoved:*"]
           }
       ]
   }
   ```

   (Again, replacing the function's ARN as appropriate for your account.)

   Then, using the AWS cli, add a "notification configuration" to the source
   bucket:

   ```bash
   aws s3api put-bucket-notification-configuration \
       --bucket dumb-pypi-source \
       --notification-configuration "$(< policy.json)"
   ```


## Serving from the S3 buckets directly

The whole point of Lambda is to avoid running your own servers, so you might as
well serve directly from S3 :)

Keep in mind that if you need to support old pip versions, you [can't yet serve
directly from S3][rationale] because these old versions rely on the PyPI server
to do package name normalization; see [the README][README] for suggestions on
how to use nginx to do this normalization.

If you **do** want to serve from S3 directly, it's pretty easy:

1. Enable read access to your source bucket. You can enable this to the public,
   whitelisted only to your company's IPs, etc.

   Here's an example policy which whitelists your bucket to everyone:

   ```json
   {
       "Version": "2008-10-17",
       "Id": "AllowReadOnlyAccess",
       "Statement": [
           {
               "Sid": "AllowReadOnlyAccess",
               "Effect": "Allow",
               "Principal": {
                   "AWS": "*"
               },
               "Action": "s3:GetObject",
               "Resource": "arn:aws:s3:::dumb-pypi-source/*"
           }
       ]
   }
   ```

   This will make your source bucket available at a URL like
   `https://dumb-pypi-source.s3.amazonaws.com`.

2. Enable read access to your output bucket. Again, it's up to you who you
   allow; you can use the same example policy from above (just adjust the
   bucket name).

3. Enable static website hosting for your output bucket, and set `index.html`
   as your "Index document". This appears to be the only way to get
   `index.html` to show up when accessing the root of a "directory" in S3.

   This will make your output bucket available at a URL like
   `http://dumb-pypi-output.s3-website-us-west-1.amazonaws.com/`.


## Updating the code or config

Any time you update the code or config, you need to re-deploy the bundle to
Lambda.

1. Run `make deploy.zip` to build a new deployment bundle.

2. Use the AWS cli to update the code for the function:

   ```bash.
   aws lambda update-function-code \
       --function-name dumb-pypi \
       --zip-file fileb://bundle.zip
   ```

[lambda]: https://aws.amazon.com/lambda/
[rationale]: https://github.com/chriskuehl/dumb-pypi/blob/master/RATIONALE.md
[s3-allow-trigger]: https://docs.aws.amazon.com/AmazonS3/latest/dev/NotificationHowTo.html#grant-destinations-permissions-to-s3
[README]: https://github.com/chriskuehl/dumb-pypi/blob/master/README.md
