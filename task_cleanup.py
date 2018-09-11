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

    logging.info('Looking for tasks with the prefix %s in the %s cluster' % (task_prefix, cluster_name))
    logging.info('Any tasks older than %s hours will be terminated' % max_age)

    def get_tasks_in_cluster(cluster_name, next_token=None):
        '''Get the running tasks in the given cluster'''
        result = []
        if next_token:
            query_result = ecs.list_tasks(cluster=cluster_name, nextToken=next_token)
        else:
            query_result = ecs.list_tasks(cluster=cluster_name)

        if 'ResponseMetadata' in query_result:
            if 'HTTPStatusCode' in query_result['ResponseMetadata']:
                if query_result['ResponseMetadata']['HTTPStatusCode'] == 200:
                    if 'nextToken' in query_result:
                        result.extend(query_result['taskArns'])
                        result.extend(get_tasks_in_cluster(cluster_name=cluster_name,
                                                           next_token=query_result['nextToken']))
                    else:
                        result.extend(query_result['taskArns'])
        return result


    session = boto3.session.Session(profile_name=profile, region_name=region)
    ecs = session.client('ecs')

    running_tasks = get_tasks_in_cluster(cluster_name, next_token=None)
    logging.info('Found %s running tasks in cluster: %s' % (len(running_tasks), cluster_name))
    # When describing tasks, can only query 100 at a time - break running_tasks into groups of 100
    task_list_groups_list = [running_tasks[i:i + 100] for i in range(0, len(running_tasks), 100)]
    for group in task_list_groups_list:
        query_result = ecs.describe_tasks(cluster=cluster_name, tasks=group)
        tasks = query_result['tasks']
        for task in tasks:
            task_arn = task['taskArn']
            logging.debug('   Processing task ARN: %s ' % task_arn)
            task_family = task['group']
            if any(filter in task_family for filter in exclude_filters):
                logging.debug("      Excluding: the task family (%s) is in the exclude list" % task_family)
                continue
            if not task_prefix in task_family:
                logging.debug("      Skipping: the task family (%s) doesn't match the given prefix" % task_family)
                continue
            if 'startedAt' in task:
                start_time = task['startedAt']
                start_time_utc = start_time.astimezone(pytz.utc)
                time_now_utc = datetime.datetime.now(pytz.UTC)
                logging.debug('      Started at      : %s' % str(start_time))
                logging.debug('      Started at (UTC): %s' % str(start_time_utc))
                logging.debug('      Time now   (UTC): %s' % str(time_now_utc))
                running_time = time_now_utc - start_time_utc
                running_time_seconds = running_time.total_seconds()
                running_time_minutes = int(running_time_seconds // 60)
                running_time_hours = int(running_time_seconds // 3600)
                logging.debug('      Running for : ~%d minutes' % running_time_minutes)
                if running_time_hours > max_age:
                    logging.info('         *** Terminating task (ARN: %s) due to old age (> %d hours)' % (task_arn, max_age))
                    reason = 'Killing task due to old age'
                    if not dryrun:
                        ecs.stop_task(cluster=cluster_name, task=task_arn, reason=reason)
                        post_to_slack_channel(notify_list)
                    else:
                        logging.warn('         *** dryrun selected, Task will not be killed')
            else:
                # No startedAt time - this must be just starting up - ignore it
                logging.warn('      * no startedAt time - ignoring for now')



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
                  max_age=int(args.max_age),
                  cluster_name=args.cluster_name,
                  exclude_filters=args.exclude_filters,
                  notify_list=args.notify_list,
                  region=args.region,
                  profile=args.profile,
                  dryrun=args.dryrun)
