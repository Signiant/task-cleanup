import logging.handlers
import argparse
import boto3
import datetime
import pytz

logging.getLogger('botocore').setLevel(logging.CRITICAL)


def post_to_slack_channel(channels):
    if channels:
        for channel in channels:
            # TODO: Implement this
            logging.debug('Calling AWS lambda to post to slack channel')
    return True


def cleanup_tasks(task_prefix, max_age, cluster_name=None, exclude_filters=[], notify_list=[], region=None, profile=None, dryrun=False):
    '''
    :param task_prefix: prefix for the task name to cleanup
    :param max_age: Maximum age of the task, if > than this, kill it
    :param cluster_name: Cluster to query, if none provided, use cluster *this* instance is in
    :param region: AWS Region to query, if none provied, use region for *this* instance
    :param profile: aws cli profile to use, if none provided, use role credentials
    :param dryrun: dryrun only - no changes
    '''

    def get_active_task_defs(task_prefix, next_token=None):
        '''Get the active task definitions with the given prefix'''
        result = []
        if next_token:
            query_result = ecs.list_task_definition_families(familyPrefix=task_prefix, status='ACTIVE', nextToken=next_token)
        else:
            query_result = ecs.list_task_definition_families(familyPrefix=task_prefix, status='ACTIVE')

        if 'ResponseMetadata' in query_result:
            if 'HTTPStatusCode' in query_result['ResponseMetadata']:
                if query_result['ResponseMetadata']['HTTPStatusCode'] == 200:
                    if 'nextToken' in query_result:
                        result.extend(get_active_task_defs(task_prefix=task_prefix,
                                                           next_token=query_result['nextToken']))
                    else:
                        result.extend(query_result['families'])
        return result

    def get_tasks_with_name_in_cluster(task_name, cluster_name, next_token=None):
        '''Get the running tasks for the given task name'''
        result = []
        if next_token:
            query_result = ecs.list_tasks(cluster=cluster_name, family=task_name, nextToken=next_token)
        else:
            query_result = ecs.list_tasks(cluster=cluster_name, family=task_name)

        if 'ResponseMetadata' in query_result:
            if 'HTTPStatusCode' in query_result['ResponseMetadata']:
                if query_result['ResponseMetadata']['HTTPStatusCode'] == 200:
                    if 'nextToken' in query_result:
                        result.extend(query_result['taskArns'])
                        result.extend(get_tasks_with_name_in_cluster(task_name=task_name,
                                                                     cluster_name=cluster_name,
                                                                     next_token=query_result['nextToken']))
                    else:
                        result.extend(query_result['taskArns'])
        return result

    session = boto3.session.Session(profile_name=profile, region_name=region)
    ecs = session.client('ecs')

    # Get all active task defintions with the given task_prefix
    task_defs = get_active_task_defs(task_prefix)

    if exclude_filters and len(exclude_filters) > 0:
        logging.debug("Excluding task defs that contain text matching exclude_filters")
        if task_defs:
            # Now exclude any task defs that have any of the provided exclude_filters present in their name
            for task_def in list(task_defs):
                if any(filter in task_def for filter in exclude_filters):
                    logging.debug("   Excluding: %s" % task_def)
                    task_defs.remove(task_def)

    if task_defs:
        # For each task definition, get all running tasks in the cluster
        for task_def in task_defs:
            logging.info('Found %s' % task_def)
            logging.info('   Finding all running tasks for this task def')
            running_tasks = get_tasks_with_name_in_cluster(task_def, cluster_name, next_token=None)
            for task in running_tasks:
                logging.info('      task ARN: %s ' % str(task))
                task_info = ecs.describe_tasks(cluster=cluster_name, tasks=[task])
                if 'tasks' in task_info:
                    if 'startedAt' in task_info['tasks'][0]:
                        start_time = task_info['tasks'][0]['startedAt']
                        start_time_utc = start_time.astimezone(pytz.utc)
                        time_now_utc = datetime.datetime.now(pytz.UTC)
                        logging.debug('         Started at      : %s' % str(start_time))
                        logging.debug('         Started at (UTC): %s' % str(start_time_utc))
                        logging.debug('         Time now   (UTC): %s' % str(time_now_utc))
                        running_time = time_now_utc - start_time_utc
                        running_time_seconds = running_time.total_seconds()
                        running_time_minutes = int(running_time_seconds // 60)
                        running_time_hours = int(running_time_seconds // 3600)
                        logging.debug('         Running for : ~%d minutes' % running_time_minutes)
                        if running_time_hours > max_age:
                            logging.info('         *** Terminating task (ARN: %s) due to old age (> %d hours)' % (task, max_age))
                            reason = 'Killing task due to old age'
                            if not dryrun:
                                ecs.stop_task(cluster=cluster_name, task=task, reason=reason)
                                post_to_slack_channel(notify_list)
                            else:
                                logging.info('dryrun selected, so not killing any tasks')
                    else:
                        # No startedAt time - this must be just starting up - ignore it
                        logging.warn('         * no startedAt time - ignoring for now')


if __name__ == "__main__":

    LOG_FILENAME = 'task_cleanup.log'

    parser = argparse.ArgumentParser(description='transfer_task_cleanup')

    parser.add_argument("--aws-access-key-id", help="AWS Access Key ID", dest='aws_access_key', required=False)
    parser.add_argument("--aws-secret-access-key", help="AWS Secret Access Key", dest='aws_secret_key', required=False)
    parser.add_argument("--task-name-prefix", help="Prefix for task to clean up", dest='task_prefix', required=True)
    parser.add_argument("--exclude-filters", help="exclude any task defs that contain these filters", nargs="+", dest='exclude_filters')
    parser.add_argument("--max-age", help="Max age (hours) [48]", dest='max_age', default=48, required=False)
    parser.add_argument("--cluster-name", help="Cluster name to search", dest='cluster_name', required=False)
    parser.add_argument("--notify", help="List of slack channels to notify", nargs='+', dest='notify_list')
    parser.add_argument("--region", help="The AWS region the cluster is in", dest='region', required=True)
    parser.add_argument("--profile", help="The name of an aws cli profile to use.", dest='profile', required=False)
    parser.add_argument("--verbose", help="Turn on DEBUG logging", action='store_true', required=False)
    parser.add_argument("--dryrun", help="Do a dryrun - no changes will be performed", dest='dryrun',
                        action='store_true', default=False,
                        required=False)
    args = parser.parse_args()

    log_level = logging.INFO

    if args.verbose:
        print("Verbose logging selected")
        log_level = logging.DEBUG

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    # create file handler which logs even debug messages
    fh = logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes=5242880, backupCount=5)
    fh.setLevel(logging.DEBUG)
    # create console handler using level set in log_level
    ch = logging.StreamHandler()
    ch.setLevel(log_level)
    console_formatter = logging.Formatter('%(levelname)8s: %(message)s')
    ch.setFormatter(console_formatter)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)8s: %(message)s')
    fh.setFormatter(file_formatter)
    # Add the handlers to the logger
    logger.addHandler(fh)
    logger.addHandler(ch)

    cleanup_tasks(task_prefix=args.task_prefix,
                  max_age=args.max_age,
                  cluster_name=args.cluster_name,
                  exclude_filters=args.exclude_filters,
                  notify_list=args.notify_list,
                  region=args.region,
                  profile=args.profile,
                  dryrun=args.dryrun)
