#!/usr/bin/env python

from __future__ import print_function
import boto3
import os
import subprocess
import glob
import shutil
import zipfile

aws_region = 'us-west-2'


def replace_in_file(filename, old, new):
    with open(filename, 'r') as file:
        filedata = file.read()
    filedata = filedata.replace(old, new)
    with open(filename, 'w') as file:
        file.write(filedata)


def upload_cf_template(template, s3_bucket):
    local_filepath = os.path.realpath('cloudformation/{}'.format(template))
    replace_in_file(local_filepath, 'da39a3ee5e6b4b0d3255bfef95601890afd80709', os.environ['LAMBCI_COMMIT'])
    s3_key = 'cloudformation/{}/{}/{}'.format(os.environ['PROJECT'], os.environ['LAMBCI_COMMIT'], template)
    print('    Uploading {} to s3://{}/{} '.format(template, s3_bucket.name, s3_key))
    s3_bucket.upload_file(local_filepath, s3_key)


def upload_lambda_bundle(filename, s3_bucket):
    filename = os.path.join(os.environ['SHALLOW_DIR'], filename)
    print('Zipping bundle')
    if filename[-3:] == '.py':
        # Zipping one file
        output_filename = filename.replace('.py', '.zip')
        zipfile.ZipFile(output_filename + '.zip', mode='w').write(filename)
    else:
        # A whole bundle; install pip requirements first
        os.chdir(filename)
        subprocess.check_call('pip install -t . -r pip_requirements', shell=True)
        os.chdir(os.environ['SHALLOW_DIR'])
        shutil.make_archive(filename, 'zip', filename)
        output_filename = filename + '.zip'

    s3_key = 'lambdas/{}/{}/{}'.format(os.environ['PROJECT'], os.environ['LAMBCI_COMMIT'], os.path.basename(output_filename))
    print('    Uploading {} to s3://{}/{}'.format(output_filename, s3_bucket.name, s3_key))
    s3_bucket.upload_file(output_filename, s3_key)


def main():
    os.environ['SHALLOW_DIR'] = os.environ['PWD']
    os.environ['PROJECT'] = os.environ['LAMBCI_REPO'].split('/')[-1].lower()

    print("Deploying CloudFormation templates")
    os.chdir(os.environ['SHALLOW_DIR'])
    s3_bucket = boto3.resource('s3').Bucket('biometrix-infrastructure-{}'.format(aws_region))
    for file in glob.glob(os.path.join(os.environ['SHALLOW_DIR'], 'cloudformation', '*.yaml')):
        file_name = os.path.basename(file)
        upload_cf_template(file_name, s3_bucket)

    print("Deploying Lambda functions")
    upload_lambda_bundle('apigateway', s3_bucket)


if __name__ == '__main__':
    main()
