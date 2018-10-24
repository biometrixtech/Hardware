#!/usr/bin/env python

from __future__ import print_function
import boto3
import json
import os
import subprocess
import shutil
import zipfile

aws_region = 'us-west-2'
s3_bucket = boto3.resource('s3').Bucket('biometrix-infrastructure-{}'.format(aws_region))


def replace_in_file(filename, old, new):
    with open(filename, 'r') as file:
        filedata = file.read()
    filedata = filedata.replace(old, new)
    with open(filename, 'w') as file:
        file.write(filedata)


def upload_cf_template(local_filepath, s3_filename):
    replace_in_file(local_filepath, 'da39a3ee5e6b4b0d3255bfef95601890afd80709', os.environ['LAMBCI_COMMIT'])
    s3_key = 'cloudformation/{}/{}/{}'.format(os.environ['PROJECT'], os.environ['LAMBCI_COMMIT'], s3_filename)
    print('    Uploading {} to s3://{}/{} '.format(local_filepath, s3_bucket.name, s3_key))
    s3_bucket.upload_file(local_filepath, s3_key)


def upload_lambda_bundle(local_filepath, s3_filename, pip_install=True):
    print('Zipping bundle')

    # Zipping one file
    if local_filepath[-3:] == '.py':
        # Write in the version
        replace_in_file(local_filepath, 'da39a3ee5e6b4b0d3255bfef95601890afd80709', os.environ['LAMBCI_COMMIT'])

        output_filename = local_filepath.replace('.py', '.zip')
        zipfile.ZipFile(output_filename + '.zip', mode='w').write(local_filepath)

    # A whole bundle
    else:
        # Install pip requirements first
        if pip_install:
            subprocess.check_call('python3 -m pip install --upgrade -t {f} -r {f}/pip_requirements'.format(f=local_filepath), shell=True)

        # Write the version into the bundle
        with open(os.path.join(local_filepath, 'version'), "w") as file:
            file.write(os.environ['LAMBCI_COMMIT'])

        # Now zip
        shutil.make_archive(local_filepath, 'zip', local_filepath)
        output_filename = local_filepath + '.zip'

    s3_key = 'lambdas/{}/{}/{}'.format(os.environ['PROJECT'], os.environ['LAMBCI_COMMIT'], s3_filename)
    print('    Uploading {} to s3://{}/{}'.format(output_filename, s3_bucket.name, s3_key))
    s3_bucket.upload_file(output_filename, s3_key)


def read_config():
    with open('resource_index.json', 'r') as file:
        return json.load(file)


def main():
    os.environ['PROJECT'] = os.environ['LAMBCI_REPO'].split('/')[-1].lower()
    config = read_config()

    print("Deploying Lambda functions")
    for lambda_bundle in config['lambdas']:
        upload_lambda_bundle(
            os.path.realpath(lambda_bundle['src']),
            lambda_bundle['s3_filename'],
            lambda_bundle['pip']
        )

    print("Deploying CloudFormation templates")
    for template in config['templates']:
        local_filename = os.path.realpath(template['src'])
        upload_cf_template(local_filename, template['s3_filename'])


if __name__ == '__main__':
    main()
