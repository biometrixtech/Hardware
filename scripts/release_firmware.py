#!/usr/bin/env python3
#
# Example:
#
#   release_firmware.py                                                           \
#       --region us-west-2                                                        \
#       --environment dev                                                         \
#       /full/path/to/firmware/binary.bin                                         \
#       accessory                                                                 \
#       1.42.0                                                                    \
#       --notes "This version fixes a bug where the accessory sometimes explodes" \
#       /full/path/to/firmware/binary.bin
#
import argparse
import datetime
import re
import os

try:
    import boto3
    from boto3.dynamodb.conditions import Key, Attr
    from colorama import Fore, Style
    from semver import VersionInfo
except ImportError:
    raise ImportError('You must install the `boto3`, `colorama` and `semver` pip packages to use this script')


class ApplicationException(Exception):
    pass


def cprint(*pargs, **kwargs):
    if 'colour' in kwargs:
        print(kwargs['colour'], end="")
        del kwargs['colour']

        end = kwargs.get('end', '\n')
        kwargs['end'] = ''
        print(*pargs, **kwargs)

        print(Style.RESET_ALL, end=end)

    else:
        print(*pargs, **kwargs)


class DynamodbUpdate:
    def __init__(self):
        self._add = []
        self._set = []
        self._parameters = {}

    def set(self, field, value):
        self._set.append(f"{field} = :{field}")
        self._parameters[':' + field] = value

    def add(self, field, value):
        self._add.append(f"{field} :{field}")
        self._parameters[':' + field] = value

    @property
    def update_expression(self):
        return 'SET {} '.format(', '.join(self._set)) + (
            'ADD {}'.format(', '.join(self._add)) if len(self._add) else '')

    @property
    def parameters(self):
        return self._parameters


def validate_semver_tag(new_tag, old_tags):
    """
    Check for various version consistency gotchas
    :param VersionInfo new_tag:
    :param list[VersionInfo] old_tags:
    :return:
    """
    for old_tag in old_tags:
        if old_tag == new_tag:
            raise ApplicationException(f'Release {new_tag} already exists')
        elif old_tag > new_tag:
            if old_tag.major != new_tag.major:
                # It's ok to prepare a legacy release
                pass
            elif old_tag.minor != new_tag.minor:
                # It's ok to patch an old minor release when a new minor release exists
                pass
            elif args.force:
                cprint(f"Shouldn't be releasing {new_tag} because a later version {old_tag} already exists.")
            else:
                raise ApplicationException(f'Cannot release {new_tag} because a later version {old_tag} already exists.')

    # Prevent skipping versions
    previous_tag = get_previous_semver(new_tag)
    if previous_tag != VersionInfo.parse('0.0.0'):
        for old_tag in old_tags:
            if old_tag >= previous_tag:
                break

        else:
            if args.force:
                cprint(f"Shouldn't be releasing {new_tag} because it skips (at least) version {previous_tag}.", colour=Fore.RED)
            else:
                raise ApplicationException(f'Cannot release {new_tag} because it skips (at least) version {previous_tag}.')

    if args.environment == 'production' and new_tag.prerelease is not None:
        raise ApplicationException('Pre-release versions (ie with build suffixes) cannot be deployed to production')


def get_previous_semver(v: VersionInfo) -> VersionInfo:
    """
    Return a semantic version which is definitely less than the target version
    :param VersionInfo v:
    :return: VersionInfo
    """
    if v.build is not None:
        raise ApplicationException(f'Cannot calculate previous version because {v} has a build number')

    if v.prerelease is not None:
        prerelease_parts = v.prerelease.split('.')
        if prerelease_parts[-1].isdigit() and int(prerelease_parts[-1]) > 1:
            return VersionInfo(v.major, v.minor, v.patch, prerelease_parts[0] + '.' + str(int(prerelease_parts[-1]) - 1))

    if v.patch > 0:
        return VersionInfo(v.major, v.minor, v.patch - 1)

    if v.minor > 0:
        return VersionInfo(v.major, v.minor - 1, 0)

    if v.major > 1:
        return VersionInfo(v.major - 1, 0, 0)

    raise ApplicationException(f'Could not calculate a previous version for {v}')


def main():

    filepath = os.path.realpath(args.filepath)

    if not os.path.exists(filepath):
        raise ApplicationException(f'File {filepath} does not exist')

    try:
        version = VersionInfo.parse(args.version)
    except ValueError:
        raise ApplicationException('Version must be a valid semantic version number')

    s3_bucket = boto3.resource('s3', region_name=args.region).Bucket(f'biometrix-hardware-{args.environment}-{args.region}')
    ddb_table = boto3.resource('dynamodb', region_name=args.region).Table(f'hardware-{args.environment}-firmware')

    # Check that this version doesn't already exist
    released_versions = []
    for firmware in ddb_table.query(KeyConditionExpression=Key('device_type').eq(args.devicetype))['Items']:
        try:
            released_versions.append(VersionInfo.parse(firmware['version']))
        except ValueError:
            cprint(f"Existing release '{firmware['version']}' is not a valid semantic version", colour=Fore.YELLOW)
    validate_semver_tag(version, released_versions)

    # Upload the firmware file
    s3_key = f'firmware/{args.devicetype}/{args.version}'
    s3_bucket.put_object(Key=s3_key, Body=open(filepath, 'rb'))
    cprint(f'Uploaded firware file from {filepath} to s3://{s3_bucket.name}/{s3_key}', colour=Fore.GREEN)

    # Create the DDB record
    insert = DynamodbUpdate()
    insert.set('created_date', datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))

    if args.notes:
        insert.set('notes', args.notes)

    ddb_table.update_item(
        Key={'device_type': args.devicetype, 'version': str(version)},
        ConditionExpression=Attr('id').not_exists(),
        UpdateExpression=insert.update_expression,
        ExpressionAttributeValues=insert.parameters,
    )
    cprint('Created DynamoDB record', colour=Fore.GREEN)


if __name__ == '__main__':
    def version_number(x):
        try:
            VersionInfo.parse(x)
        except ValueError:
            raise argparse.ArgumentTypeError('Version number must be a semantic version number')
        return x

    epilog = '''
Examples:
    %(prog)s /path/to/binary.bin accessory 1.42.0-test.1
    %(prog)s /path/to/binary.bin accessory 1.42.0 --notes "Exciting new features"
    %(prog)s /path/to/binary.bin accessory 1.42.0 --environment production
    %(prog)s /path/to/binary.bin accessory 1.42.1 --notes "Fixes a bug in 1.42.0 where the accessory would sometimes explode"
'''

    parser = argparse.ArgumentParser(
        description='Uploads a new firmware version',
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--region', '-r',
                        type=str,
                        help='AWS Region',
                        choices=['us-west-2'],
                        default='us-west-2')
    parser.add_argument('--environment',
                        type=str,
                        help='Environment',
                        choices=['dev', 'test', 'production'],
                        default='dev')
    parser.add_argument('filepath',
                        type=str,
                        help='Path to the new firmware binary')
    parser.add_argument('devicetype',
                        type=str,
                        help='The device type',
                        choices=['accessory', 'ankle', 'hip'])
    parser.add_argument('version',
                        help='Version number.  This must be a semantic version (ie `major.minor.patch` or `major.minor.patch-test.N`)',
                        type=version_number)
    parser.add_argument('--notes',
                        help='Optional version release notes',
                        default='')
    parser.add_argument('--force', '-f',
                        help='Override sanity checks',
                        action='store_true',
                        default=False,
                        dest='force')

    args = parser.parse_args()

    try:
        main()
    except KeyboardInterrupt:
        exit(0)
    except ApplicationException as e:
        cprint(str(e), colour=Fore.RED)
        exit(1)
    except Exception as e:
        cprint(str(e), colour=Fore.RED)
        raise e
    else:
        exit(0)
